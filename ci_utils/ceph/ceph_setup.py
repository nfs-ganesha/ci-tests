import time
import json

from ci_utils.common.helpers import run_cmd

from ci_utils.common.logger import get_logger
logger = get_logger(__name__)


class CephGaneshaSetup:
    def __init__(
        self,
        session,
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
        logger.info("[STEP]: Setting up virtual disks and LVMs")
        run_cmd(self.session, f"truncate -s {self.disk_size} {self.disk_img}")
        run_cmd(self.session, f"losetup -f {self.disk_img}")
        loop_dev, _ = run_cmd(self.session, f"losetup -j {self.disk_img} | cut -d: -f1")
        run_cmd(self.session, f"pvcreate {loop_dev}")
        run_cmd(self.session, f"vgcreate {self.vg_name} {loop_dev}")
        for i in range(1, self.osd_count + 1):
            run_cmd(self.session, f"lvcreate -L 10G -n osd{i} {self.vg_name}")
        logger.info("[OK] Virtual disks and LVMs created")

    # -----------------------
    # Ceph Bootstrap
    # -----------------------
    def bootstrap_ceph(self):
        logger.info("[STEP]: Bootstrapping Ceph cluster")
        run_cmd(self.session, "dnf install -y cephadm")
        run_cmd(self.session, "cephadm add-repo --release squid")
        run_cmd(self.session, "dnf install -y ceph")
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

    # -----------------------
    # OSD Setup
    # -----------------------
    def setup_osds(self):
        logger.info("[STEP]: Setting up OSDs")
        for i in range(1, self.osd_count + 1):
            run_cmd(self.session, f"ceph-volume lvm create --data /dev/{self.vg_name}/osd{i}")
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
        self.setup_osds()
        self.setup_cephfs()
        self.install_build_dependencies()
        self.coredump_setup()
        return self.subvol_path
