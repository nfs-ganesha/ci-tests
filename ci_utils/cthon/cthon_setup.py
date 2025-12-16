
from typing import List, Tuple
from ci_utils.common.helpers import run_cmd

from ci_utils.common.logger import get_logger
logger = get_logger(__name__)

# ----------------------------
# Cthon Test Setup and Runner
# ----------------------------
class CthonManager:
    def __init__(self, session, server_ip=None, repo_url="git://git.linux-nfs.org/projects/steved/cthon04.git"):
        """
        Manager to setup and run Cthon NFS tests on a remote session.
        Args:
            session: RemoteSession instance for running commands.
            server_ip: NFS server IP/hostname. If None, uses local hostname IP.
            repo_url: Git URL of the Cthon repository.
        """
        self.session = session
        self.repo_url = repo_url
        self.cthon_dir = "cthon04"
        if server_ip:
            self.server_ip = server_ip
            logger.info(f"[INFO] Using IP: {self.server_ip}")
        else:
            logger.info("[INFO] No server IP provided, using local hostname IP")
            self.server_ip, _ = run_cmd(self.session, "hostname -I | awk '{print $1}'")
    # ----------------------------
    # Setup
    # ----------------------------
    def clone_and_build(self):
        logger.info("[STEP]: Cloning and building Cthon")
        run_cmd(self.session, f"rm -rf {self.cthon_dir}")
        run_cmd(self.session, f"git clone --depth=1 {self.repo_url} {self.cthon_dir}")
        run_cmd(self.session, f"cd {self.cthon_dir} && make all")
        logger.info("[OK] Cthon cloned and built")

    # ----------------------------
    # Internal helpers
    # ----------------------------
    def _mount(self, version, mount_dir, export="/nfs/cephfs"):
        logger.info(f"[STEP]: Mounting NFS v{version} export {export} at {mount_dir}")
        run_cmd(self.session, f"mkdir -p {mount_dir}")

        try:
            logger.info(f"[INFO] Attempting NFS v{version} mount at {mount_dir}")
            run_cmd(
                self.session,
                f"mount -t nfs -o vers={version} {self.server_ip}:{export} {mount_dir}"
            )
            run_cmd(self.session, f"mountpoint -q {mount_dir}")
            run_cmd(self.session, f"mount | grep {mount_dir}")
            logger.info(f"[OK] NFS v{version} mounted at {mount_dir}")
        except Exception as e:
            log_content, _ = run_cmd(self.session, "cat /var/log/ganesha.log", check=False)
            logger.error(f"[ERROR] Failed to mount NFS v{version}. Log:\n{log_content} Error:\n {e}")
            raise RuntimeError(f"NFS v{version} mount failed")

    def _run_cthon(self, version, mount_dir, export="/nfs/cephfs"):
        logger.info(f"[STEP] Running Cthon tests for NFS v{version}")
        out, rc = run_cmd(
            self.session,
            f"cd {self.cthon_dir} && ./server -a -p {export} -m {mount_dir} {self.server_ip}",
        )
        logger.info(f"[OK] Completed Cthon tests for NFS v{version}")
        return out, rc

    # ----------------------------
    # Public test runners
    # ----------------------------
    def run_v3(self, export="/nfs/cephfs"):
        mount_dir = "/mnt/nfs_ceph_v3"
        self._mount("3", mount_dir, export)
        out,rc = self._run_cthon("3", mount_dir, export)
        return out, rc

    def run_v4(self, export="/nfs/cephfs"):
        mount_dir = "/mnt/nfs_ceph_v4"
        self._mount("4", mount_dir, export)
        out, rc = self._run_cthon("4", mount_dir, export)
        return out, rc

    def run_v41(self, export="/nfs/cephfs"):
        mount_dir = "/mnt/nfs_ceph_v41"
        self._mount("4.1", mount_dir, export)
        out, rc = self._run_cthon("4.1", mount_dir, export)
        return out, rc

    # ----------------------------
    # Log collection
    # ----------------------------
    def collect_logs(self, outputs: List[Tuple[str, str]]) -> str:
        """Collect and format logs from multiple test runs.
        Args:
            outputs: List of tuples (version, log output).
        Returns:
            str: Formatted log summary.
        """
        logger.info("[STEP]: Collecting cthon logs...")
        log_summary = []
        summary_text = ""

        for version, out in outputs:
            if out:
                log_summary.append(f"cthon {version} test suite logs:")
                log_summary.append("------------------------------")
                log_summary.extend(out)
                log_summary.append("")

        if log_summary:
            summary_text = "\n".join(log_summary)
            logger.error("Failure summary:\n%s", summary_text)

        return summary_text
    
    # ----------------------------
    # Run all tests
    # ----------------------------
    def run_all_cthon_test(self, skip_v3=True):
        logger.info("[STEP]: Running all Cthon tests...")
        if not skip_v3:
            self.run_v3()

        log_cthon_40, rc_40 = self.run_v4()
        log_cthon_41, rc_41 = self.run_v41()

        if rc_40 != 0 or rc_41 != 0:
            return self.collect_logs([
                ("4.0", log_cthon_40),
                ("4.1", log_cthon_41)
            ]), 1
        
        return "All Cthon tests passed successfully", 0

