import os

from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger
logger = get_logger(__name__)


class VFSGaneshaManager:
    def __init__(self, session):
        """Handles VFS and NFS-Ganesha installation and setup on a VM.
        Args:
            session (RemoteSession): Remote session to the VM.
        """
        self.session = session

    # -------------------------------
    # Install Ganesha with VFS support
    # -------------------------------
    def install_ganesha(self, test_workspace: str):
        logger.info("[STEP]: Installing NFS-Ganesha with VFS support on the VM")
        yum_repo = os.getenv("VFS_YUM_REPO", "")

        if yum_repo:
            self._install_from_repo(yum_repo)
        else:
            self._build_from_source(test_workspace)

        self.start_ganesha_service()

    # -------------------------------
    # Install Ganesha from repo or build from source
    # -------------------------------
    def _install_from_repo(self, yum_repo: str):
        logger.info("[STEP]: Installing Ganesha from yum repo...")
        run_cmd(self.session, "yum-config-manager --add-repo=http://artifacts.ci.centos.org/nfs-ganesha/nightly/libntirpc/libntirpc-latest.repo")
        run_cmd(self.session, f"yum-config-manager --add-repo={yum_repo}")

    def _build_from_source(self, test_workspace: str):
        logger.info("[STEP]: Building Ganesha from source...")

        out, err, code = self.session.run(
            f"cd {test_workspace}/nfs-ganesha && "
            "rm -rf build && "
            "mkdir -p build && "
            "cd build && "
            "cmake ../src -DCMAKE_BUILD_TYPE=Maintainer "
            "-DUSE_FSAL_VFS=ON -DUSE_FSAL_GLUSTER=OFF "
            "-DUSE_FSAL_CEPH=OFF -DUSE_FSAL_RGW=OFF "
            "-DUSE_FSAL_GPFS=OFF -DUSE_MONITORING=ON && "
            "make dist"
        )

        logger.info("VFS Make CephFS output: %s", out)
        logger.error("VFS Make CephFS error: %s", err)
        logger.info("VFS Make CephFS exit code: %d", code)
        assert code == 0, f"VFS Make CephFS tests failed: {err}"
        
        build_dir = f"{test_workspace}/nfs-ganesha/build"
        src_dir = f"{test_workspace}/nfs-ganesha"
        out, code = run_cmd(self.session, f"ls {build_dir}/nfs-ganesha-*.tar.gz")
        logger.info("Tarball ls output: %s", out)
        tarball = out.strip().splitlines()[0]

        run_cmd(self.session, f"ls -la {src_dir}")
        run_cmd(self.session, f"ls -la {build_dir}")

        run_cmd(
            self.session,
            f"cd {build_dir} && "
            f"rpmbuild -ta --define \"_srcrpmdir {build_dir}\" "
            f"--define \"_rpmdir {build_dir}\" {tarball}"
        )
        
        rpm_arch, _ = run_cmd(self.session, "rpm -E '%{_arch}'")
        logger.info("RPM Arch: %s", rpm_arch)

        ganesha_version, _ = run_cmd(
            self.session,
            f"cd {build_dir} && rpm -q --qf '%{{VERSION}}-%{{RELEASE}}' -p *.src.rpm"
        )
        logger.info("Ganesha Version: %s", ganesha_version)

        ntirpc_check_cmd = f"cd build && ls {rpm_arch}/libntirpc-devel*.rpm || true"
        ntirpc_files, _ = run_cmd(self.session, ntirpc_check_cmd)

        if ntirpc_files.strip():
            ntirpc_version, _ = run_cmd(
                self.session,
                f"cd {build_dir} && rpm -q --qf '%{{VERSION}}-%{{RELEASE}}' -p {rpm_arch}/libntirpc-devel*.rpm"
            )
            ntirpc_rpm = f"{rpm_arch}/libntirpc-{ntirpc_version}.{rpm_arch}.rpm"
            logger.info("NTIRPC Version: %s", ntirpc_version)
            logger.info("NTIRPC RPM: %s", ntirpc_rpm)

        run_cmd(self.session, f"cd {build_dir} && dnf -y install {{x86_64,noarch}}/*.rpm")

        ganesha_conf = """
NFSv4 {
    Graceless = true;
    Enforce_UTF8_Validation = true;
}
"""
        cmd = f"bash -c 'cat > /etc/ganesha/ganesha.conf <<EOF\n{ganesha_conf}\nEOF'"
        run_cmd(self.session, cmd)
        run_cmd(self.session, "cat /etc/ganesha/ganesha.conf")

        logger.info("NFS-Ganesha build, install, and minimal config complete.")
    
    # -------------------------------
    # Start Ganesha service
    # -------------------------------
    def start_ganesha_service(self):
        logger.info("[STEP]: Starting NFS-Ganesha service...")
        out, rc = run_cmd(self.session, "systemctl start nfs-ganesha", check=False)
        if rc != 0:
            logger.error("Failed to start nfs-ganesha: %s", out)
            run_cmd(self.session, "systemctl status nfs-ganesha", check=False)
            run_cmd(self.session, "journalctl -xe", check=False)
            assert False, "Failed to start nfs-ganesha service"
        logger.info("NFS-Ganesha started successfully.")
    