
from pathlib import Path
import re

from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger
from concurrent.futures import ThreadPoolExecutor, as_completed
logger = get_logger(__name__)

class SpectrumScaleInstaller:
    def __init__(self, session, username, vm_ip, path_version_to_use, workspace, ssh_key, nodes: dict = None, password=None, system_type="centos", installer_http_path=None, export_name="/ibm/fs1"):
        """Class to handle Spectrum Scale installation and setup on a VM.
        Args:
            session (RemoteSession): Remote session to the VM.
            username (str): Username for the VM.
            vm_ip (str): IP address of the VM.
            path_version_to_use (str): Path to the Spectrum Scale installer.
            workspace (str): Workspace directory on the VM.
            nodes (dict, optional): Additional nodes for multi-node setup. Defaults to None.
            Example:
                {
                    "admin": ["extensa001"],
                    "servers": ["extensa001", "extensa002", "extensa012"],
                    "clients": ["extensa013", "extensa014"],
                }
            system_type (str, optional): System type: baremetal|openstack|centos. Defaults to None.
            installer_http_path (str, optional): HTTP URL to download the installer. Defaults to None
        """
        self.session = session[vm_ip]
        self.node_sessions = session if isinstance(session, dict) else None
        self.username = username
        self.vm_ip = vm_ip
        self.version_file_name = path_version_to_use.split("/")[-1]
        self.path_version_to_use = path_version_to_use
        self.workspace_path = workspace
        self.ssh_key = Path(ssh_key) if ssh_key else None
        self.password = password
        self.nodes = nodes or {"admin": [vm_ip], "servers": [vm_ip], "clients": [vm_ip]}
        self.ces_ips = self.nodes.get("ces", [])
        self.system_type = system_type
        self.installer_http_path = installer_http_path
        self.export_name = export_name

        self.usable_ip = None
        self.hostname = None
        self.scale_version = None
        self.spectrum_scale_binary = None

    # -------------------------------
    # Helpers
    # -------------------------------
    def detect_platform(self):
        out, _ = run_cmd(self.session, "source /etc/os-release && echo $ID")
        platform = out.strip()
        logger.info(f"Detected platform: {platform}")
        return platform

    def _propagate_hosts_cluster(self, hosts_file="/etc/hosts"):
        """
        Cluster-wide /etc/hosts update and passwordless SSH setup.
        """
        cluster_entries = {}

        # 1️⃣ Ensure SSH keys exist and get hostnames on all nodes
        for ip, sess in self.node_sessions.items():
            home = run_cmd(sess, "echo $HOME")[0].strip()
            key_path = f"{home}/.ssh/id_rsa"
            pub_path = f"{key_path}.pub"

            # Generate key if missing
            if run_cmd(sess, f"test -f {key_path} && echo yes || echo no")[0].strip() != "yes":
                run_cmd(sess, f"ssh-keygen -t rsa -b 4096 -N '' -f {key_path}")

            # Read hostname and public key
            hostname = run_cmd(sess, "hostname")[0].strip()
            cluster_entries[ip] = {"hostname": hostname, "pub_key": run_cmd(sess, f"cat {pub_path}")[0].strip()}

        cluster_ips = set(cluster_entries.keys())
        cluster_hosts = {v["hostname"] for v in cluster_entries.values()}

        # 2️⃣ Update /etc/hosts and authorized_keys on all nodes
        for target_ip, target_sess in self.node_sessions.items():
            home = run_cmd(target_sess, "echo $HOME")[0].strip()
            ssh_dir = f"{home}/.ssh"

            # Update /etc/hosts
            current = run_cmd(target_sess, f"cat {hosts_file}")[0].splitlines()
            new_hosts = [line for line in current if not any(ip in line or host in line
                                                            for ip in cluster_ips for host in cluster_hosts)]
            new_hosts += [f"{ip}\t{v['hostname']}" for ip, v in cluster_entries.items()]
            run_cmd(target_sess, f"echo '{chr(10).join(new_hosts)}' | sudo tee {hosts_file} > /dev/null")

            # Ensure passwordless SSH
            run_cmd(target_sess, f"mkdir -p {ssh_dir} && chmod 700 {ssh_dir}")
            for v in cluster_entries.values():
                key = v["pub_key"]
                run_cmd(target_sess, f"grep -v '{key}' {ssh_dir}/authorized_keys 2>/dev/null > {ssh_dir}/authorized_keys.tmp || true")
                run_cmd(target_sess, f"echo '{key}' >> {ssh_dir}/authorized_keys")
            run_cmd(target_sess, f"chmod 600 {ssh_dir}/authorized_keys")
            run_cmd(target_sess, f"echo \"StrictHostKeyChecking no\" >> {ssh_dir}/config")
            run_cmd(target_sess, f"echo \"UserKnownHostsFile=/dev/null\" >> {ssh_dir}/config")
            logger.info(f"[INFO] /etc/hosts and passwordless SSH updated on {target_ip}")
    # -------------------------------
    # Install base packages
    # -------------------------------
    def install_packages(self):
        logger.info("[STEP]: Installing base packages on all nodes in parallel")

        platform = self.detect_platform()

        def _install_on_node(node, sess):
            """
            Install base packages on a single node session.
            """
            run_cmd(sess, "dnf clean packages")
            run_cmd(sess, "dnf install -y unzip python3-pip wget")

            if platform == "rhel":
                run_cmd(sess, "dnf install -y kernel-devel-$(uname -r) kernel-headers-$(uname -r)")
            else:
                logger.info(f"Attempting Koji fetch...")
                # Get kernel version and extract components for Koji URL
                # Example: 5.14.0-658.el9.x86_64 -> major=5.14.0, build=658, release=el9
                kernel_ver, _ = run_cmd(sess, "uname -r")
                kernel_ver = kernel_ver.strip()
                # Parse: 5.14.0-658.el9.x86_64 -> extract 5.14.0, 658, el9
                match = re.match(r'(\d+\.\d+\.\d+)-(\d+)\.(el\d+)', kernel_ver)
                if match:
                    major, build, release = match.groups()
                    koji_base = f"https://kojihub.stream.centos.org/kojifiles/packages/kernel/{major}/{build}.{release}/x86_64"
                    kernel_pkg_ver = f"{major}-{build}.{release}"
                    run_cmd(sess, f"wget {koji_base}/kernel-devel-{kernel_pkg_ver}.x86_64.rpm")
                    run_cmd(sess, f"wget {koji_base}/kernel-headers-{kernel_pkg_ver}.x86_64.rpm")
                    run_cmd(sess, "ls -la")
                    run_cmd(sess, f"dnf -y install openssl-fips-provider ./kernel-devel-{kernel_pkg_ver}.x86_64.rpm ./kernel-headers-{kernel_pkg_ver}.x86_64.rpm")
                else:
                    logger.warning(f"Could not parse kernel version {kernel_ver}, falling back to default")
                    run_cmd(sess, "wget https://kojihub.stream.centos.org/kojifiles/packages/kernel/5.14.0/570.el9/x86_64/kernel-devel-5.14.0-570.el9.x86_64.rpm")
                    run_cmd(sess, "wget https://kojihub.stream.centos.org/kojifiles/packages/kernel/5.14.0/570.el9/x86_64/kernel-headers-5.14.0-570.el9.x86_64.rpm")
                    run_cmd(sess, "ls -la")
                    run_cmd(sess, "dnf -y install openssl-fips-provider ./kernel-devel-5.14.0-570.el9.x86_64.rpm ./kernel-headers-5.14.0-570.el9.x86_64.rpm")
            run_cmd(
                sess,
                "yum -y install "
                "cpp gcc gcc-c++ binutils numactl jre make elfutils elfutils-devel "
                "rpcbind sssd-tools openldap-clients bind-utils net-tools "
                "krb5-workstation python3 --skip-broken"
            )
            run_cmd(sess, "python3 -m pip install --user ansible cherrypy")
            logger.info(f"[INFO] Base packages installed on {node}")

        # Limit concurrency to avoid overloading network / SSH sessions
        with ThreadPoolExecutor(max_workers=min(5, len(self.node_sessions))) as executor:
            futures = [executor.submit(_install_on_node, node, sess) for node, sess in self.node_sessions.items()]
            for f in as_completed(futures):
                f.result()  # Will raise exceptions if installation failed

        logger.info("[INFO] Base packages installed on all nodes.")

    # -------------------------------
    # SSH key setup
    # -------------------------------
    def setup_ssh_keys(self):
        if self.system_type == "centos":
            logger.info("[STEP]: Setting up SSH keys for passwordless access on the VM")
            run_cmd(self.session, "mkdir -p /root/.ssh && chmod 700 /root/.ssh")        

            run_cmd(self.session, f"cat /tmp/id_rsa.pub >> /root/.ssh/authorized_keys")  
            run_cmd(self.session, f"cp /tmp/id_rsa.pub {self.ssh_key}")    
            run_cmd(self.session, f"cp /tmp/id_rsa {self.ssh_key.with_suffix('')}")  

            run_cmd(self.session, "chmod 600 /root/.ssh/id_rsa")
            run_cmd(self.session, "chmod og-wx /root/.ssh/authorized_keys")
            run_cmd(self.session, "ls -la /root/.ssh")

            logger.info("SSH keys configured for passwordless localhost access.")
        
        elif self.system_type == "openstack" or self.system_type == "baremetal":
            self._propagate_hosts_cluster()

            logger.info("SSH keys configured for passwordless access on all nodes.")

    # -------------------------------
    # Detect usable IP
    # -------------------------------
    def detect_usable_ips(self):
        """
        Detects usable IPs for all servers and updates /etc/hosts.
        Stops as soon as enough free IPs are found.
        """
        if self.system_type not in ["centos", "openstack"]:
            return

        logger.info("[STEP]: Detecting usable IP addresses on the VM")

        # 1️⃣ Base IP
        base_ip, _ = run_cmd(self.session, "/sbin/ip -o -4 addr list eth0 | awk '{print $4}' | cut -d/ -f1 | head -n1")
        base_ip = base_ip.strip()
        logger.info(f"Base IP detected: {base_ip}")
        subnet_prefix = ".".join(base_ip.split(".")[:3])
        servers = self.nodes.get("servers", [])
        required_ips = len(servers)
        iface, _ = run_cmd(self.session, "ip -o -4 addr show up | awk '!/ lo / {print $2; exit}'")
        ip_cidr, _ = run_cmd(self.session, f"ip -o -4 addr show {iface} | awk '{{print $4}}' | head -n1")
        logger.info(f"Network interface: {iface.strip()}, CIDR: {ip_cidr}")

        _, cidr = ip_cidr.split("/")
        start = int(base_ip.split(".")[3]) + 1
        candidate_ips = [f"{subnet_prefix}.{i}" for i in range(start, 255)]

        self.ces_ips = []

        def is_free(ip):
            out, _ = run_cmd(self.session, f"ping -c 1 -W 1 {ip} >/dev/null 2>&1 && echo busy || echo free")
            return ip if "free" in out else None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(is_free, ip) for ip in candidate_ips]

            # Wait for futures and stop early once enough IPs are found
            for f in as_completed(futures):
                ip = f.result()
                if ip:
                    self.ces_ips.append(ip)
                    if len(self.ces_ips) >= required_ips:
                        # Cancel remaining futures
                        for rem in futures:
                            rem.cancel()
                        break

        if len(self.ces_ips) < required_ips:
            raise RuntimeError("Not enough usable IPs detected for CES nodes.")

        logger.info(f"Detected usable IPs: {self.ces_ips}")

        # Update /etc/hosts
        for idx, ip in enumerate(self.ces_ips, start=1):
            hostname = f"cesip{idx}"
            run_cmd(self.session, f"grep -qxF '{ip} {hostname}' /etc/hosts || echo '{ip} {hostname}' | sudo tee -a /etc/hosts")
            run_cmd(self.session, f"ip addr add {ip}/{cidr} dev {iface}")

    # -------------------------------
    # Example: Spectrum Scale setup
    # -------------------------------
    def setup_spectrumscale(self):
        if self.system_type == "centos":
            logger.info("[STEP]: Setting up Spectrum Scale on the VM")
            run_cmd(self.session, f"mkdir -p {self.workspace_path}/INSTALL_PATH")
            run_cmd(self.session, f"unzip {self.path_version_to_use} -d INSTALLER_PATH/")

            installer, _ = run_cmd(
                self.session,
                "ls INSTALLER_PATH/ --ignore='*.md5' --ignore='*.README' --ignore='*.pgp' | head -1"
            )
            installer_path = f"INSTALLER_PATH/{installer}"
        else:
            if self.installer_http_path:
                logger.info("[STEP]: Downloading Spectrum Scale installer on the VM")
                run_cmd(self.session, f"curl -C - -o /tmp/{self.version_file_name} {self.installer_http_path}")
                installer_path = f"/tmp/{self.version_file_name}"
        
        logger.info(f"Using installer at: {installer_path}")
        run_cmd(self.session, f"chmod +x {installer_path}")
        run_cmd(self.session, f"{installer_path} --silent")

        logger.info("Spectrum Scale installer executed.")

    def locate_spectrumscale_binary(self):
        out, code = run_cmd(self.session, "readlink -f /usr/lpp/mmfs/*/ansible-toolkit/spectrumscale")
        if code != 0 or not out:
            raise RuntimeError("Could not locate spectrumscale binary on VM")
        self.spectrum_scale_binary = out.strip()

        hostname, _ = run_cmd(self.session, "hostname")
        self.hostname = hostname.strip()

    def configure_spectrumscale(self):
        logger.info("[STEP]: Configuring Spectrum Scale cluster")
        run_cmd(
            self.session,
            f"{self.spectrum_scale_binary} setup -s {self.vm_ip} --storesecret",
        )

        # Admin node
        admin_node = self.nodes["admin"][0]
        run_cmd(
            self.session,
            f"{self.spectrum_scale_binary} node add {admin_node} -a -n -p",
        )

        # Other servers
        for node in self.nodes.get("servers", [])[1:]:
            run_cmd(self.session, f"{self.spectrum_scale_binary} node add {node} -n -p")

        # Clients
        for node in self.nodes.get("clients", []):
            run_cmd(self.session, f"{self.spectrum_scale_binary} node add {node}")

        run_cmd(
            self.session,
            f"{self.spectrum_scale_binary} config gpfs -c {admin_node}_cluster",
        )
        run_cmd(self.session, f"{self.spectrum_scale_binary} enable nfs")
        run_cmd(self.session, f"{self.spectrum_scale_binary} callhome disable")
        run_cmd(self.session, f"{self.spectrum_scale_binary} config perfmon -r off")

        logger.info("Spectrum Scale configured.")

    # -------------------------------
    # Create NSD and filesystem setup
    # -------------------------------
    def setup_storage(self):
        """
        Setup storage and NSDs for Spectrum Scale.
        Rules:
          - Baremetal multi-node: metadata = 1st usable disk, data = rest
          - OpenStack multi-node: same as baremetal
          - OpenStack single-node: same disk for metadata + data
          - CentOS single-node: loopback file for metadata + data
        """
        logger.info(f"[STEP]: Setting up storage for system type: {self.system_type}")
        nsd_map = {}

        # --------------------------
        # Baremetal
        # --------------------------
        if self.system_type == "baremetal":
            servers = self.nodes.get("servers", [])
            if not servers:
                raise RuntimeError("No server nodes defined")

            for node in servers:
                node_session = self.node_sessions[node]
                logger.info(f"Detecting disks on node: {node}")
                out, _ = run_cmd(
                    node_session,
                    "lsblk -dpno NAME,TYPE | grep disk | awk '{print $1}'"
                )
                disks = out.strip().splitlines()

                # Find root device
                root_disk, _ = run_cmd(node_session, "findmnt -n -o SOURCE /")
                root_disk = re.sub(r"\d+$", "", root_disk.strip())

                usable_disks = [d for d in disks if d != root_disk]
                if not usable_disks:
                    raise RuntimeError(f"No usable disks found on {node}")

                # --- Wipe first 100MB of all usable disks to remove old NSD metadata ---
                for disk in usable_disks:
                    logger.info(f"Wiping GPFS metadata on {disk} on node {node}")
                    run_cmd(node_session, f"dd if=/dev/zero of={disk} bs=1M count=100 status=progress")

                if self.system_type == "openstack" and len(servers) == 1:
                    # Single-node same disk for metadata & data
                    disk = usable_disks[0]
                    nsd_map[node] = {"dataAndMetadata": [disk]}
                else:
                    # Multi-node
                    nsd_map[node] = {
                        "metadata": [usable_disks[0]],
                        "data": usable_disks[1:] if len(usable_disks) > 1 else [],
                    }

        # --------------------------
        # CentOS (always single node)
        # --------------------------
        elif self.system_type == "centos":
            node = self.nodes["servers"][0]
            logger.info("CentOS detected: creating loopback file")
            run_cmd(
                self.session,
                "dd if=/dev/zero of=/home/nsd1.img bs=1M count=8192"
            )
            disk = "/home/nsd1.img"
            nsd_map[node] = {"dataAndMetadata": [disk]}

        # --------------------------
        # OpenStack
        # --------------------------
        elif self.system_type == "openstack":
            logger.info(f"{self.system_type.capitalize()} detected: creating loopback disks on all nodes")

            servers = self.nodes.get("servers", [])
            if not servers:
                raise RuntimeError("No server nodes defined")

            for node in servers:
                node_session = self.node_sessions[node]
                logger.info(f"Creating disks on {node}")
                disks = []

                # Create 2 disks of 10GB each
                for i in range(1, 3):
                    img = f"/home/nsd{i}_c84f2u09"
                    run_cmd(node_session, f"dd if=/dev/zero of={img} bs=1M count=8192")
                    disks.append(img)

                nsd_map[node] = {"metadata": [disks[0]], "data": [disks[1]] if len(disks) > 1 else [disks[0]]}
        else:
            raise ValueError(f"Unknown system_type: {self.system_type}")

        # --------------------------
        # Apply NSD config
        # --------------------------
        logger.info(f"NSD configuration: {nsd_map}")
        for node, disks in nsd_map.items():
            if disks.get("metadata"):
                md = " ".join(disks["metadata"])
                run_cmd(
                    self.session,
                    f"{self.spectrum_scale_binary} nsd add -p {node} -u metadataOnly -fs fs1 -fg 1 {md}",
                )
            if disks.get("data"):
                data = " ".join(disks["data"])
                run_cmd(
                    self.session,
                    f"{self.spectrum_scale_binary} nsd add -p {node} -u dataOnly -fs fs1 -fg 1 {data}",
                )
            
            if disks.get("dataAndMetadata"):
                dm = " ".join(disks["dataAndMetadata"])
                run_cmd(
                    self.session,
                    f"{self.spectrum_scale_binary} nsd add -p {node} -u dataAndMetadata -fs fs1 -fg 1 {dm}",
                )

        run_cmd(self.session, f"{self.spectrum_scale_binary} config protocols -f fs1 -m {self.export_name}")
        run_cmd(self.session, f"{self.spectrum_scale_binary} install --precheck")
        run_cmd(self.session, f"{self.spectrum_scale_binary} install")

        self.detect_usable_ips()
        run_cmd(self.session, f"{self.spectrum_scale_binary} config protocols -f fs1 -e {self.ces_ips[0]}")
        run_cmd(self.session, f"{self.spectrum_scale_binary} deploy --precheck")
        run_cmd(self.session, f"{self.spectrum_scale_binary} deploy")

        run_cmd(self.session, f"{self.spectrum_scale_binary} nsd list")
        run_cmd(self.session, f"{self.spectrum_scale_binary} filesystem list")

        if len(self.ces_ips) > 0:
            for ces_ip in self.ces_ips:
                for node in self.nodes["servers"]:
                    run_cmd(
                        self.session,
                        f"mmces address add --ces-ip {ces_ip} --ces-node {node}",
                        check=False,
                    )
        
        run_cmd(self.session, f"/usr/lpp/mmfs/bin/mmlscluster --ces")

        logger.info("Storage setup complete.")

    def post_sanity_check(self):
        self.locate_spectrumscale_binary()
        out, _ = run_cmd(self.session, "/usr/lpp/mmfs/bin/mmlscluster --ces")
        assert "GPFS cluster information" in out, "Cluster not properly set up"

        for server_ip in self.nodes["servers"]:
            assert server_ip in out, f"Server node {server_ip} missing from cluster"

        out, _ = run_cmd(self.session, f"{self.spectrum_scale_binary} filesystem list")
        assert "fs" in out or "scale_volume" in out, "No filesystem created"

        out, _ = run_cmd(self.session, f"{self.spectrum_scale_binary} nsd list")
        assert "nsd" in out.lower(), "No NSD created"

    # -------------------------------
    # Master flow
    # -------------------------------
    def run(self):
        logger.info("Running Spectrum Scale setup")
        self.setup_ssh_keys()
        self.install_packages()
        self.setup_spectrumscale()
        self.locate_spectrumscale_binary()
        self.configure_spectrumscale()
        self.setup_storage()
        logger.info("Spectrum Scale setup completed successfully")