
from pathlib import Path
import re

from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger
logger = get_logger(__name__)

class SpectrumScaleInstaller:
    def __init__(self, session, username, vm_ip, path_version_to_use, workspace, ssh_key):
        """Class to handle Spectrum Scale installation and setup on a VM.
        Args:
            session (RemoteSession): Remote session to the VM.
            username (str): Username for the VM.
            vm_ip (str): IP address of the VM.
            path_version_to_use (str): Path to the Spectrum Scale installer.
            workspace (str): Workspace directory on the VM.
        """
        self.session = session
        self.username = username
        self.vm_ip = vm_ip
        self.version_file_name = path_version_to_use.split("/")[-1]
        self.path_version_to_use = path_version_to_use
        self.workspace_path = workspace
        self.ssh_key = Path(ssh_key)

        self.usable_ip = None
        self.hostname = None
        self.scale_version = None
        self.spectrum_scale_binary = None

    # -------------------------------
    # Install base packages
    # -------------------------------
    def install_packages(self):
        logger.info("[STEP]: Installing base packages on the VM")
        
        run_cmd(self.session, "dnf clean packages")
        run_cmd(self.session, "dnf install -y unzip python3-pip wget")
        
        run_cmd(self.session, "wget https://kojihub.stream.centos.org/kojifiles/packages/kernel/5.14.0/522.el9/x86_64/kernel-devel-5.14.0-522.el9.x86_64.rpm")
        run_cmd(self.session, "wget https://kojihub.stream.centos.org/kojifiles/packages/kernel/5.14.0/522.el9/x86_64/kernel-headers-5.14.0-522.el9.x86_64.rpm")
        run_cmd(self.session, "ls -la")
        run_cmd(self.session, "dnf -y install openssl-fips-provider ./kernel-devel-5.14.0-522.el9.x86_64.rpm ./kernel-headers-5.14.0-522.el9.x86_64.rpm")
        
        run_cmd(
            self.session,
            "yum -y install "
            "cpp gcc gcc-c++ binutils numactl jre make elfutils elfutils-devel "
            "rpcbind sssd-tools openldap-clients bind-utils net-tools "
            "krb5-workstation python3 --skip-broken"
        )
        run_cmd(self.session, "python3 -m pip install --user ansible cherrypy")
        logger.info("Base packages installed.")

    # -------------------------------
    # SSH key setup
    # -------------------------------
    def setup_ssh_keys(self):
        logger.info("[STEP]: Setting up SSH keys for passwordless access on the VM")
        run_cmd(self.session, "mkdir -p /root/.ssh && chmod 700 /root/.ssh")        

        run_cmd(self.session, f"cat /tmp/id_rsa.pub >> /root/.ssh/authorized_keys")  
        run_cmd(self.session, f"cp /tmp/id_rsa.pub {self.ssh_key}")    
        run_cmd(self.session, f"cp /tmp/id_rsa {self.ssh_key.with_suffix('')}")  

        run_cmd(self.session, "chmod 600 /root/.ssh/id_rsa")
        run_cmd(self.session, "chmod og-wx /root/.ssh/authorized_keys")
        run_cmd(self.session, "ls -la /root/.ssh")

        logger.info("SSH keys configured for passwordless localhost access.")

    # -------------------------------
    # Detect usable IP
    # -------------------------------
    def detect_usable_ip(self):
        logger.info("[STEP]: Detecting usable IP address on the VM")
        ip_output, _ = run_cmd(
            self.session,
            "/sbin/ip -o -4 addr list eth0 | awk '{print $4}' | cut -d/ -f1"
        )
        base_ip = ip_output.strip()

        usable_ip, _ = run_cmd(
            self.session,
            f"""
            ip_address={base_ip}
            for new_ip in $(echo $ip_address | awk -F '.' '{{for(i=$4+1;i<=255;i++){{print $1"."$2"."$3"."i}}}}'); do
                ping -c 2 $new_ip >/dev/null 2>&1
                if [ "$?" == "1" ]; then
                    echo $new_ip
                    break
                fi
            done
            """
        )
        match = re.search(r'\d+\.\d+\.\d+\.\d+', usable_ip)
        if match:
            ip = match.group()
        self.usable_ip = ip
        logger.info(f"Detected usable IP: {self.usable_ip}")

        logger.info("Adding usable IP to /etc/hosts")
        run_cmd(self.session, "cat /etc/hosts")
        run_cmd(self.session, f"bash -c 'echo \"{self.usable_ip}    cesip1\" >> /etc/hosts'")
        run_cmd(self.session, "cat /etc/hosts")

    # -------------------------------
    # Example: Spectrum Scale setup
    # -------------------------------
    def setup_spectrumscale(self):
        logger.info("[STEP]: Setting up Spectrum Scale on the VM")
        run_cmd(self.session, f"mkdir -p {self.workspace_path}/INSTALL_PATH")
        run_cmd(self.session, f"unzip {self.path_version_to_use} -d INSTALLER_PATH/")

        installer, _ = run_cmd(
            self.session,
            "ls INSTALLER_PATH/ --ignore='*.md5' --ignore='*.README' --ignore='*.pgp' | head -1"
        )
        installer_path = f"INSTALLER_PATH/{installer}"
        run_cmd(self.session, f"chmod +x {installer_path}")
        run_cmd(self.session, f"{installer_path} --silent")

        logger.info("Spectrum Scale installer executed.")

        out, code = run_cmd(self.session, "readlink -f /usr/lpp/mmfs/*/ansible-toolkit/spectrumscale")
        if code != 0 or not out:
            raise RuntimeError("Could not locate spectrumscale binary on VM")
        self.spectrum_scale_binary = out.strip()

        hostname, _ = run_cmd(self.session, "hostname")
        self.hostname = hostname.strip()

        run_cmd(self.session, f"{self.spectrum_scale_binary} setup -s 127.0.0.1 --storesecret")
        run_cmd(self.session, f"{self.spectrum_scale_binary} node add {self.hostname} -n")
        run_cmd(self.session, f"{self.spectrum_scale_binary} node add {self.hostname} -p")
        run_cmd(self.session, f"{self.spectrum_scale_binary} config protocols -e {self.usable_ip}")
        run_cmd(self.session, f"{self.spectrum_scale_binary} node add -a {self.hostname}")
        run_cmd(self.session, f"{self.spectrum_scale_binary} config gpfs -c {self.hostname}_cluster")

        logger.info("Spectrum Scale configured.")

    # -------------------------------
    # Create NSD and filesystem setup
    # -------------------------------
    def setup_storage(self):
        logger.info("[STEP]: Creating NSD file...")
        run_cmd(self.session, "dd if=/dev/zero of=/home/nsd1_c84f2u09-rhel88a1 bs=1M count=8192")

        logger.info("Adding NSD to Spectrum Scale...")
        run_cmd(self.session, f"{self.spectrum_scale_binary} nsd add -p {self.hostname} -u dataAndMetadata -fs scale_volume -fg 1 /home/nsd1_c84f2u09-rhel88a1")

        logger.info("Configuring protocols, enabling NFS & SMB...")
        run_cmd(self.session, f"{self.spectrum_scale_binary} config protocols -f scale_volume -m /ibm/scale_volume")
        run_cmd(self.session, f"{self.spectrum_scale_binary} enable nfs")
        run_cmd(self.session, f"{self.spectrum_scale_binary} enable smb")
        run_cmd(self.session, f"{self.spectrum_scale_binary} callhome disable")
        run_cmd(self.session, f"{self.spectrum_scale_binary} config perfmon -r off")

        run_cmd(self.session, f"{self.spectrum_scale_binary} node list")
        run_cmd(self.session, f"{self.spectrum_scale_binary} install --precheck")
        run_cmd(self.session, f"{self.spectrum_scale_binary} install")
        run_cmd(self.session, f"{self.spectrum_scale_binary} deploy --precheck")
        run_cmd(self.session, f"{self.spectrum_scale_binary} deploy")

        run_cmd(self.session, f"{self.spectrum_scale_binary} nsd list")
        run_cmd(self.session, f"{self.spectrum_scale_binary} filesystem list")

        logger.info("Storage setup complete.")

    # -------------------------------
    # Master flow
    # -------------------------------
    def run(self):
        logger.info("Running Spectrum Scale setup")
        self.setup_ssh_keys()
        self.install_packages()
        self.detect_usable_ip()
        self.setup_spectrumscale()
        self.setup_storage()
        logger.info("Spectrum Scale setup completed successfully")