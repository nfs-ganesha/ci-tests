
from ci_utils.common.helpers import run_cmd

from ci_utils.common.logger import get_logger, set_test_name
logger = get_logger(__name__)


class GaneshaManager:
    """
    NFS-Ganesha Setup and Management for CephFS
    """
    def __init__(self, session, subvol_path, cephfs_name="cephfs", export_id=101, test_type=None):
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

    # ------------------------
    # Internal helpers
    # ------------------------
    def _generate_conf(self):
        delegations_v4 = ""
        delegations_export = ""

        if self.test_type == "pynfs":
            delegations_v4 = "    Delegations = true;"
            delegations_export = "    delegations = readwrite;"
        return f"""NFS_CORE_PARAM {{
    Enable_NLM = false;
    Enable_RQUOTA = false;
    Protocols = 4;
}}

NFSv4 {{
    Enforce_UTF8_Validation = true;
    {delegations_v4}
}}

EXPORT_DEFAULTS {{
    Access_Type = RW;
}}

EXPORT {{
    Export_ID = {self.export_id};
    Path = "{self.subvol_path}";
    Pseudo = "/nfs/{self.cephfs_name}";
    Protocols = 4;
    Transports = TCP;
    Access_Type = RW;
    Squash = None;
    {delegations_export}
    FSAL {{
        Name = "CEPH";
    }}
}}"""

    # ------------------------
    # Public methods
    # ------------------------
    def write_conf(self):
        """Write ganesha.conf to remote system."""
        conf_content = self._generate_conf()
        run_cmd(self.session, f"echo '{conf_content}' > /etc/ganesha/ganesha.conf")
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
        self.start()

    def setup(self):
        """Full pipeline for setting up ganesha."""
        self.write_conf()
        self.prepare_dirs()
        self.start()
