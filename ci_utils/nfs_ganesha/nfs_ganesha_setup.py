
import time
from ci_utils.common.helpers import run_cmd

from ci_utils.common.logger import get_logger, set_test_name
logger = get_logger(__name__)


class GaneshaManager:
    """
    NFS-Ganesha Setup and Management for CephFS
    """
    def __init__(self, session, subvol_path, ganesha_opts=None, cephfs_name="cephfs", export_id=101, test_type=None):
        """
        Manage NFS-Ganesha setup on a remote session.

        :param session: RemoteSession object
        :param subvol_path: CephFS subvolume path to export
        :param cephfs_name: CephFS volume name (default: "cephfs")
        :param export_id: Export ID for ganesha.conf
        """
        self.session = session
        self.subvol_path = subvol_path
        self.cephfs_name = cephfs_name
        self.export_id = export_id
        self.test_type = test_type
        self.ganesha_opts = ganesha_opts or {}

        self.conf = self._generate_conf()

    # ------------------------
    # Internal helpers
    # ------------------------
    def _generate_conf(self):

        # ---- defaults ----
        deleg_v4 = "true"
        deleg_export = "none"
        ceph_async = "true"

        # ---- override only if ganesha_opts are passed ----
        if self.ganesha_opts:
            if "delegations_v4" in self.ganesha_opts:
                deleg_v4 = self.ganesha_opts["delegations_v4"]

            if "delegations_export" in self.ganesha_opts:
                deleg_export = self.ganesha_opts["delegations_export"]

            if "ceph_async" in self.ganesha_opts:
                ceph_async = self.ganesha_opts["ceph_async"]

        return f"""NFS_CORE_PARAM {{
    Enable_NLM = true;
    Enable_RQUOTA = false;
    Protocols = 3,4;
}}

NFSv4 {{
    Enforce_UTF8_Validation = true;
    Delegations = {deleg_v4};
}}

EXPORT_DEFAULTS {{
    Access_Type = RW;
}}

CEPH {{
    async = {ceph_async};
}}

EXPORT {{
    Export_ID = {self.export_id};
    Path = "{self.subvol_path}";
    Pseudo = "/nfs/{self.cephfs_name}";
    Protocols = 3,4;
    Transports = TCP;
    Access_Type = RW;
    Squash = None;
    delegations = {deleg_export};
    FSAL {{
        Name = "CEPH";
    }}
}}"""


    # ------------------------
    # Public methods
    # ------------------------
    def write_conf(self):
        """Write ganesha.conf to remote system."""
        run_cmd(self.session, f"echo '{self.conf}' > /etc/ganesha/ganesha.conf")
        run_cmd(self.session, "cat /etc/ganesha/ganesha.conf")
        logger.info("[OK] ganesha.conf written")

    def prepare_dirs(self):
        """Prepare runtime and backend dirs for ganesha."""
        run_cmd(self.session, "mkdir -p /var/run/ganesha /var/lib/nfs/ganesha")
        run_cmd(self.session, "chmod 755 /var/run/ganesha /var/lib/nfs/ganesha")
        run_cmd(self.session, "chown root:root /var/run/ganesha /var/lib/nfs/ganesha")
        logger.info("[OK] Ganesha directories prepared")

    def start(self):
        """Start ganesha service and verify it is running."""
        run_cmd(self.session, "ganesha.nfsd -f /etc/ganesha/ganesha.conf -L /var/log/ganesha.log")
        if run_cmd(self.session, "pgrep ganesha", check=False):
            logger.info("[OK] NFS-Ganesha is running")
        else:
            raise RuntimeError("NFS-Ganesha failed to start")

    def stop(self):
        """Stop ganesha service if running."""
        run_cmd(self.session, "pkill ganesha", check=False)
        logger.info("[OK] Stopped NFS-Ganesha")

    def restart(self):
        """Restart ganesha service."""
        self.stop()
        
        # Wait up to 10 minutes for ganesha processes to stop
        for i in range(120):  # 120 * 5 seconds = 600 seconds (10 minutes)
            output, _ = run_cmd(self.session, "pgrep ganesha", check=False)
            if not output or not output.strip():
                break
            logger.warning(f"Ganesha processes still running, retrying... (attempt {i+1}/120)")
            time.sleep(5)
        else:
            raise RuntimeError("Ganesha processes still running after 10 minutes")
        
        self.start()

    def get_nfs_version(self):
        """
        Get the NFS-Ganesha version.
        
        Returns:
            str: NFS-Ganesha version string (first line only) or "Unknown" if unable to retrieve.
        """
        logger.info("[STEP]: Getting NFS-Ganesha version")
        output, code = run_cmd(self.session, "ganesha.nfsd -v", check=False)
        
        if code == 0 and output:
            # Parse only the first line to get the version
            first_line = output.strip().split('\n')[0]
            logger.info(f"[OK] NFS-Ganesha version: {first_line}")
            return first_line
        
        logger.warning("Failed to get NFS-Ganesha version")
        return "Unknown"

    def setup(self):
        """Full pipeline for setting up ganesha."""
        self.write_conf()
        self.prepare_dirs()
        self.start()
