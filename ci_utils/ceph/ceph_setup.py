import time
import json

from ci_utils.common.helpers import run_cmd, scp_copy

from ci_utils.common.logger import get_logger
logger = get_logger(__name__)


class CephGaneshaSetup:
    def __init__(
        self,
        session,
        extra_sessions=None,
        disk_img="/tmp/ceph-disk.img",
        disk_size="35G",
        vg_name="ceph-vg",
        osd_count=3,
        cephfs_name="cephfs",
        subvol_group="ganeshagroup",
        subvol_name="nfs_subvol",
        timeout=300,
    ):
        """
        Setup and manage a Ceph cluster with CephFS for NFS-Ganesha testing
        Args:
            session: RemoteSession instance for running commands.
            disk_img (str): Path to the virtual disk image file.
            disk_size (str): Size of the virtual disk (e.g., "35G").
            vg_name (str): Name of the volume group for LVM.
            osd_count (int): Number of OSDs to create.
            cephfs_name (str): Name of the CephFS filesystem.
            subvol_group (str): Subvolume group name.
            subvol_name (str): Subvolume name.
            timeout (int): Timeout in seconds for waiting operations. 0 means no timeout.
        """
        self.session = session
        self.extra_sessions = extra_sessions if extra_sessions else []
        self.disk_img = disk_img
        self.disk_size = disk_size
        self.vg_name = vg_name
        self.osd_count = osd_count
        self.cephfs_name = cephfs_name
        self.subvol_group = subvol_group
        self.subvol_name = subvol_name
        self.timeout = timeout
        self.subvol_path = None

    # -----------------------
    # Disk + LVM Setup
    # -----------------------
    def setup_virtual_disks(self):
        target_sessions = [self.session] + self.extra_sessions 
        for sess in target_sessions:
            logger.info("[STEP]: Setting up virtual disks and LVMs")
            run_cmd(sess, f"truncate -s {self.disk_size} {self.disk_img}")
            run_cmd(sess, f"losetup -f {self.disk_img}")
            loop_dev, _ = run_cmd(sess, f"losetup -j {self.disk_img} | cut -d: -f1")
            run_cmd(sess, f"pvcreate {loop_dev}")
            run_cmd(sess, f"vgcreate {self.vg_name} {loop_dev}")
            for i in range(1, self.osd_count + 1):
                run_cmd(sess, f"lvcreate -L 10G -n osd{i} {self.vg_name}")
            logger.info("[OK] Virtual disks and LVMs created")

    # -----------------------
    # Ceph Bootstrap
    # -----------------------
    def bootstrap_ceph(self):
        target_sessions = [self.session] + self.extra_sessions 
        for sess in target_sessions:
            run_cmd(sess, "dnf install -y cephadm")
            run_cmd(sess, "cephadm add-repo --release squid")
            run_cmd(sess, "dnf install -y ceph")

        logger.info("[STEP]: Bootstrapping Ceph cluster")
        run_cmd(
            self.session,
            "cephadm bootstrap --mon-ip $(hostname -I | awk '{print $1}') "
            "--single-host-defaults --allow-fqdn-hostname"
        )
        run_cmd(
            self.session,
            "ceph auth get client.bootstrap-osd "
            "-o /var/lib/ceph/bootstrap-osd/ceph.keyring"
        )
        logger.info("[OK] Ceph cluster bootstrapped")

    def add_extra_hosts(self):
        if not self.extra_sessions:
            logger.info("[SKIP] No extra Ceph hosts provided.")
            return

        logger.info(f"[STEP] Adding {len(self.extra_sessions)} extra Ceph hosts")

        # Pack ceph configs for shipping
        run_cmd(self.session, "tar czf /tmp/ceph_conf.tgz /etc/ceph")

        # -------------------------------------------------------------------
        # 1) Ensure SSH key exists for scp + cephadm
        # -------------------------------------------------------------------
        run_cmd(
            self.session,
            "test -f /root/.ssh/id_ed25519.pub || "
            "(mkdir -p /root/.ssh && ssh-keygen -t ed25519 -N '' -f /root/.ssh/id_ed25519)"
        )

        # Read ssh key
        ssh_pubkey, _ = run_cmd(self.session, "cat /root/.ssh/id_ed25519.pub")

        # Read ceph orchestrator pubkey
        ceph_pubkey, _ = run_cmd(self.session, "cat /etc/ceph/ceph.pub")
        public_nw, _ = run_cmd(self.session, "echo $(ipcalc -n $(ip -o -4 addr show scope global | awk '{print $4}') | cut -d= -f2)/$(ip -o -4 addr show scope global | awk '{print $4}' | cut -d/ -f2)")
        run_cmd(self.session, f"ceph config set global public_network {public_nw}")
        
        for sess in self.extra_sessions:

            # -------------------------------------------------------------------
            # 2) Install authorized_keys on extra node
            # -------------------------------------------------------------------
            run_cmd(sess, "mkdir -p /root/.ssh")
            run_cmd(sess, f"echo '{ssh_pubkey.strip()}' >> /root/.ssh/authorized_keys")
            run_cmd(sess, f"echo '{ceph_pubkey.strip()}' >> /root/.ssh/authorized_keys")
            run_cmd(sess, "chmod 600 /root/.ssh/authorized_keys")

            # -------------------------------------------------------------------
            # 3) Copy ceph config bundle using scp
            # -------------------------------------------------------------------
            run_cmd(
                self.session,
                f"scp -o StrictHostKeyChecking=no /tmp/ceph_conf.tgz "
                f"root@{sess.node_ip}:/tmp/"
            )

            # Extract on extra node
            run_cmd(sess, "tar xzf /tmp/ceph_conf.tgz -C /")

            run_cmd(
                self.session,
                f"scp -o StrictHostKeyChecking=no /var/lib/ceph/bootstrap-osd/ceph.keyring "
                f"root@{sess.node_ip}:/var/lib/ceph/bootstrap-osd/"
            )

            # Set public network on extra node
            public_nw, _ = run_cmd(sess, "echo $(ipcalc -n $(ip -o -4 addr show scope global | awk '{print $4}') | cut -d= -f2)/$(ip -o -4 addr show scope global | awk '{print $4}' | cut -d/ -f2)")
            run_cmd(sess, f"ceph config set global public_network {public_nw}")

            # -------------------------------------------------------------------
            # 4) Add host to ceph orch
            # -------------------------------------------------------------------
            host_ip, _ = run_cmd(sess, "hostname -I | awk '{print $1}'")
            hostname, _ = run_cmd(sess, "hostname")
            run_cmd(self.session, f"ceph orch host add {hostname.strip()} {host_ip.strip()}")
            run_cmd(self.session, "ceph orch host ls")


    # -----------------------
    # OSD Setup
    # -----------------------
    def setup_osds(self):
        logger.info("[STEP]: Setting up OSDs")


        target_sessions = [self.session] + self.extra_sessions

        for sess in target_sessions:
            for i in range(1, self.osd_count + 1):
                run_cmd(sess, f"ceph-volume lvm create --data /dev/{self.vg_name}/osd{i}")
                        
        run_cmd(self.session, "ceph orch device ls")
        run_cmd(self.session, "ceph orch apply osd --all-available-devices")

        logger.info("Waiting for OSDs to be ready...")
        start_time = time.time()
        while True:
            output, _ = run_cmd(
                self.session,
                "ceph orch ls --service-type osd --format json",
                check=False,
            )
            if output:
                try:
                    status = json.loads(output)[0]["status"]
                    if status and "running" in status and status["running"] >= 1:
                        logger.info("[OK] OSDs are ready")
                        return
                except Exception:
                    pass
                finally:
                    run_cmd(self.session, "ceph osd tree")

            if self.timeout > 0 and (time.time() - start_time) >= self.timeout:
                raise TimeoutError("Timeout while waiting for OSDs to be ready")
            time.sleep(5)

    # -----------------------
    # CephFS Setup
    # -----------------------
    def setup_cephfs(self):
        logger.info("[STEP]: Setting up CephFS and subvolume")
        run_cmd(self.session, f"ceph fs volume create {self.cephfs_name}")
        run_cmd(self.session, f"ceph fs subvolumegroup create {self.cephfs_name} {self.subvol_group}")
        run_cmd(
            self.session,
            f"ceph fs subvolume create {self.cephfs_name} {self.subvol_name} "
            f"--group_name {self.subvol_group} --namespace-isolated",
        )

        self.subvol_path, _ = run_cmd(
            self.session,
            f"ceph fs subvolume getpath {self.cephfs_name} {self.subvol_name} "
            f"--group_name {self.subvol_group}",
            check=False,
        )
        if not self.subvol_path:
            raise RuntimeError("Failed to get subvolume path")
        logger.info(f"[OK] Subvolume created: {self.subvol_path}")

    def install_build_dependencies(self):
        logger.info("[STEP]: Installing build dependencies...")
        run_cmd(self.session, "yum --enablerepo=crb install -y git gcc nfs-utils time make libtirpc-devel")
    
    def coredump_setup(self):
        logger.info("[STEP]: Setting up coredump configuration")
        run_cmd(self.session, "echo '/tmp/cores/core.%e.%p.%h.%t' > /proc/sys/kernel/core_pattern")
        run_cmd(self.session, "mkdir -p /tmp/cores")

    def get_ceph_version(self):
        """
        Get the Ceph version from the cluster.
        
        Returns:
            str: Full Ceph version string or "Unknown" if unable to retrieve.
        """
        logger.info("[STEP]: Getting Ceph version")
        output, code = run_cmd(self.session, "ceph --version", check=False)
        
        if code == 0 and output:
            version = output.strip()
            logger.info(f"[OK] Ceph version: {version}")
            return version
        
        logger.warning("Failed to get Ceph version")
        return "Unknown"

    # -----------------------
    # Full Pipeline Setup
    # -----------------------
    def full_setup(self):
        """Run the complete pipeline in sequence.
        Returns:
            str: Path to the created subvolume.
        """
        self.setup_virtual_disks()
        self.bootstrap_ceph()
        self.add_extra_hosts()
        self.setup_osds()
        self.setup_cephfs()
        self.install_build_dependencies()
        self.coredump_setup()
        return self.subvol_path
