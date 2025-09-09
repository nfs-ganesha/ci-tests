import time
from pathlib import Path

from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger

logger = get_logger(__name__)


class VMManager:
    def __init__(self, session, workspace, vm_name, image_url, image_name, vm_cpu, vm_ram, vm_disk, ssh_key, username="root"):
        """Handles VM creation, cloud-init setup, and cleanup.
        Args:
            session (RemoteSession): Remote session to the host managing VMs.
            workspace (str): Directory on the host for VM-related files.
            vm_name (str): Name of the VM to create.
            image_url (str): URL to download the base image.
            image_name (str): Name of the image file.
            vm_cpu (int): Number of CPUs for the VM.
            vm_ram (int): Amount of RAM (in MB) for the VM.
            vm_disk (str): Disk size for the VM (e.g., '20G').
            ssh_key (str): Path to SSH key for accessing the VM.
            username (str): Username for SSH access inside the VM.
        """
        self.session = session
        self.workspace = Path(workspace)
        self.vm_name = vm_name
        self.image_url = image_url
        self.image_name = image_name
        self.vm_cpu = vm_cpu
        self.vm_ram = vm_ram
        self.vm_disk = vm_disk
        self.ssh_key = Path(ssh_key)
        self.username = username
        self.image_dir = self.workspace / "virt-images"

    # -----------------------
    # VM Dependencies
    # -----------------------
    def check_dependencies(self):
        logger.info("[STEP]: Checking VM dependencies on host")
        run_cmd(self.session, "systemctl list-unit-files | grep virt")
        run_cmd(self.session, "systemctl enable --now libvirtd")
        run_cmd(self.session, "systemctl status libvirtd")
        run_cmd(self.session, "command -v virt-install")

    # -----------------------
    # VM Setup Network
    # -----------------------
    def setup_network(self):
        logger.info("[STEP]: Setting up VM network")
        networks, _ = run_cmd(
            self.session,
            "virsh net-list --name | grep -v '^\\s*$' | head -n 1",
            check=False
        )
        
        if networks != "":
            self.network = networks.strip()
        else:
            logger.info("No existing libvirt networks found. Creating default network.")
            run_cmd(self.session, f"mkdir -p {self.image_dir}")

            xml_content = """<network>
<name>default</name>
<bridge name="virbr0"/>
<forward mode="nat"/>
<ip address="192.168.122.1" netmask="255.255.255.0">
    <dhcp>
    <range start="192.168.122.2" end="192.168.122.254"/>
    </dhcp>
</ip>
</network>"""

            remote_xml = self.image_dir / "default-network.xml"
            run_cmd(
                self.session,
                f"cat > {remote_xml} <<'EOF'\n{xml_content}\nEOF"
            )
            run_cmd(self.session, f"virsh net-define {remote_xml}")
            run_cmd(self.session, "virsh net-start default")
            run_cmd(self.session, "virsh net-autostart default")
            self.network = "default"

    # -----------------------
    # Download Image
    # -----------------------
    def download_image(self):
        logger.info("[STEP]: Downloading VM image")
        remote_image_path = self.image_dir / self.image_name

        # Check if the file exists on the remote host using return code
        _, return_code = run_cmd(
            self.session, f"test -f {remote_image_path}", check=False
        )

        if return_code != 0:
            logger.info(f"Downloading image {self.image_name} to remote host...")
            run_cmd(self.session, f"wget -O {remote_image_path} {self.image_url}")
        else:
            logger.info(f"Image {self.image_name} already exists on remote host. Skipping download.")

        logger.info(f"Resizing image to {self.vm_disk}...")
        run_cmd(self.session, f"qemu-img resize {remote_image_path} {self.vm_disk}")

    # -----------------------
    # Generate SSH Key
    # -----------------------
    def generate_ssh_key(self):
        logger.info("[STEP]: Generating SSH key for VM access")
        remote_key_path = self.ssh_key.with_suffix("")
        remote_ssh_dir = remote_key_path.parent

        run_cmd(self.session, f"mkdir -p {remote_ssh_dir}")

        _, rc = run_cmd(self.session, f"test -f {self.ssh_key}", check=False)
        if rc != 0:
            logger.info(f"Generating SSH key at {remote_key_path} on remote host...")
            run_cmd(
                self.session,
                f"ssh-keygen -t rsa -b 4096 -f {remote_key_path} -N ''"
            )
        else:
            logger.info(f"SSH key already exists at {self.ssh_key} on remote host. Skipping generation.")

    # -----------------------
    # Create Cloud-Init ISO
    # -----------------------
    def create_cloud_init_iso(self, user_data: str, meta_data: str):
        logger.info("[STEP]: Creating cloud-init ISO for VM")
        cloud_dir = self.image_dir / "cloud-init"

        run_cmd(self.session, f"mkdir -p {cloud_dir}")
        run_cmd(
            self.session,
            f"cat > {cloud_dir}/user-data << 'EOF'\n{user_data}\nEOF"
        )
        run_cmd(
            self.session,
            f"cat > {cloud_dir}/meta-data << 'EOF'\n{meta_data}\nEOF"
        )

        iso_path = self.image_dir / "cloud-init.iso"
        run_cmd(
            self.session,
            f"genisoimage -output {iso_path} -volid cidata -joliet -rock {cloud_dir}/user-data {cloud_dir}/meta-data"
        )

        return iso_path

    # -----------------------
    # Prepare Image Directory
    # -----------------------
    def prepare_image_dir(self):
        logger.info("[STEP]: Preparing image directory on host")
        remote_libvirt_dir = "/var/lib/libvirt/images"

        run_cmd(self.session, f"mkdir -p {remote_libvirt_dir}")
        run_cmd(self.session, f"mv {self.image_dir}/*.qcow2 {remote_libvirt_dir}/")
        run_cmd(self.session, f"mv {self.image_dir}/*.iso {remote_libvirt_dir}/")
        run_cmd(self.session, f"chown qemu:qemu {remote_libvirt_dir}/*")

        self.image_path = Path(remote_libvirt_dir) / self.image_name
        self.iso_path = Path(remote_libvirt_dir) / "cloud-init.iso"

    # -----------------------
    # Create VM
    # -----------------------
    def create_vm(self):
        logger.info("[STEP]: Creating and starting VM")
        run_cmd(
            self.session,
            f"""virt-install \
            --name "{self.vm_name}" \
            --memory {self.vm_ram} \
            --vcpus {self.vm_cpu} \
            --disk path="{self.image_path}",format=qcow2,bus=virtio \
            --disk path="{self.iso_path}",device=cdrom \
            --network network={self.network},model=virtio \
            --os-variant centos-stream9 \
            --virt-type kvm \
            --graphics none \
            --import \
            --noautoconsole"""
        )

    # -----------------------
    # VM Utilities
    # -----------------------
    def wait_for_vm_ip(self, max_wait=120, interval=5):
        logger.info("[STEP]: Waiting for VM to obtain IP address")
        vm_ip = ""
        elapsed = 0
        while elapsed < max_wait and not vm_ip:
            output, _ = run_cmd(self.session, f"virsh domifaddr {self.vm_name} | grep ipv4", check=False)
            logger.info(f"Output while fetching IP: {output}")

            lines = output.splitlines()
            if lines:
                vm_ip = lines[0].split()[3].split('/')[0]  # extract IP
            if not vm_ip:
                logger.info(f"Waiting for VM IP... {elapsed}/{max_wait} seconds elapsed")
                time.sleep(interval)
                elapsed += interval

        if not vm_ip:
            raise RuntimeError(f"Failed to get VM IP for {self.vm_name}")

        self.vm_ip = vm_ip
        return vm_ip

    def wait_for_ssh(self, interval=2):
        logger.info(f"[STEP]: Waiting for SSH to be available on VM {self.vm_ip}")
        while True:
            _, rc = run_cmd(self.session, f"nc -z {self.vm_ip} 22", check=False)
            if rc == 0:
                break
            logger.info(f"Waiting for SSH to be available on {self.vm_ip}...")
            time.sleep(interval)

    # -----------------------
    # VM Actions
    # -----------------------
    def add_vm_to_known_hosts(self):
        logger.info("[STEP]: Adding VM to known_hosts")
        run_cmd(self.session, f"ssh-keyscan -H {self.vm_ip} >> ~/.ssh/known_hosts", check=False)

    def copy_file_to_vm(self, local_path, remote_path="/tmp"):
        logger.info(f"[STEP]: Copying {local_path} to VM {self.vm_ip}:{remote_path}")
        run_cmd(
            self.session,
            f"scp -i {self.ssh_key.with_suffix('')} {local_path} {self.username}@{self.vm_ip}:{remote_path}"
        )

        logger.info(f"Copying SSH keys and nfs-ganesha source to VM {self.vm_ip}")
        run_cmd(self.session, f"scp -i {self.ssh_key.with_suffix('')} {self.ssh_key} {self.username}@{self.vm_ip}:/tmp")
        run_cmd(self.session, f"scp -i {self.ssh_key.with_suffix('')} {self.ssh_key.with_suffix('')} {self.username}@{self.vm_ip}:/tmp")
        run_cmd(self.session, f"scp -i {self.ssh_key.with_suffix('')} -r {self.workspace}/nfs-ganesha {self.username}@{self.vm_ip}:/root")

    # -----------------------
    # Shutdown and Cleanup
    # -----------------------
    def shutdown_vm(self):
        logger.info("[STEP]: Shutting down and cleaning up VM")
        run_cmd(self.session, f"virsh shutdown {self.vm_name}")
        for _ in range(12):
            state, _ = run_cmd(self.session, f"virsh domstate {self.vm_name}", check=False)
            if "shut off" in state:
                break
            time.sleep(5)
        else:
            run_cmd(self.session, f"virsh destroy {self.vm_name}")
        run_cmd(self.session, f"virsh undefine {self.vm_name} --nvram --remove-all-storage")
