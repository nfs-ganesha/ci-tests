import time
from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger
logger = get_logger(__name__)

class VFSVolumeExporter:
    def __init__(self, session, vfs_volume: str, enable_acl: bool = False, security_label: bool = False):
        """Handles exporting a volume using NFS-Ganesha with VFS backend.
        Args:
            session (RemoteSession): Remote session to the VM.
            vfs_volume (str): Name of the volume to export.
            enable_acl (bool): Whether to enable ACL support.
            security_label (bool): Whether to enable Security_Label support.
        """
        self.session = session
        self.vfs_volume = vfs_volume
        self.enable_acl = enable_acl
        self.security_label = security_label
        self.export_conf = f"/etc/ganesha/exports/export.{self.vfs_volume}.conf"

    # -------------------------------
    # Setup ganesha environment
    # -------------------------------
    def setup_environment(self):
        logger.info("[TEST]: Setting up ganesha environment...")
        run_cmd(self.session, "mkdir -p /usr/libexec/ganesha")
        run_cmd(self.session, "cd /usr/libexec/ganesha && dnf -y install wget")
        run_cmd(
            self.session,
            "cd /usr/libexec/ganesha && "
            "wget https://raw.githubusercontent.com/gluster/glusterfs/release-3.10/extras/ganesha/scripts/dbus-send.sh"
        )
        run_cmd(self.session, "chmod 755 /usr/libexec/ganesha/dbus-send.sh")

    # -------------------------------
    # Configure export
    # -------------------------------
    def configure_export(self):
        logger.info(f"[TEST]: Configuring export for volume {self.vfs_volume}...")
        run_cmd(self.session, f"mkdir -p /{self.vfs_volume}")
        run_cmd(self.session, f"chmod ugo+w /{self.vfs_volume}")
        run_cmd(self.session, "mkdir -p /etc/ganesha/exports")

        export_conf_content = f"""
EXPORT {{
    Export_Id = 2;
    Path = "/{self.vfs_volume}";
    Pseudo = "/{self.vfs_volume}";
    Access_type = RW;
    Disable_ACL = {str(not self.enable_acl).capitalize()};
    Protocols = "3","4";
    Transports = "UDP","TCP";
    SecType = "sys";
    Security_Label = {str(self.security_label).capitalize()};
    FSAL {{
        Name = VFS;
    }}
}}
"""

        cmd = f"echo '{export_conf_content}' > {self.export_conf}"
        run_cmd(self.session, cmd)
        run_cmd(self.session, f"echo '%include \"{self.export_conf}\"' >> /etc/ganesha/ganesha.conf")
        run_cmd(self.session, f"/usr/libexec/ganesha/dbus-send.sh /etc/ganesha on {self.vfs_volume}")

    # -------------------------------
    # Validate export
    # -------------------------------
    def validate_export(self):
        logger.info("[TEST]: Validating ganesha export")
        time.sleep(5)
        logger.info("Validating ganesha export availability...")
        _, code = run_cmd(self.session, f"showmount -e | grep -q -w -e {self.vfs_volume}", check=False)
        if code != 0:
            logger.error("Export not found, printing debug logs...")
            run_cmd(self.session, "cat /var/log/ganesha/ganesha.log", check=False)
            run_cmd(self.session, "grep --with-filename -e '' /etc/ganesha/ganesha.conf", check=False)
            run_cmd(self.session, "grep --with-filename -e '' /etc/ganesha/exports/*.conf", check=False)
            raise RuntimeError(f"Export {self.vfs_volume} not found!")

    # Commenting out below enablement as the changes are already done in the export configuration
    # Retaining the code for future reference for enabling other features
    
    # -------------------------------
    # Enable ACL if required
    # -------------------------------
    # def enable_acl_if_required(self):
        # logger.info("[TEST]: Checking if ACL needs to be enabled")
        # if self.enable_acl:
        #     # logger.info("Enabling ACL for volume...")
        #     # run_cmd(self.session, f"sed -i s/'Disable_ACL = .*'/'Disable_ACL = false;'/g {self.export_conf}")
        #     run_cmd(self.session, f"cat {self.export_conf}")
        #     export_id, _ = run_cmd(self.session, f"grep 'Export_Id' {self.export_conf} | sed 's/^[[:space:]]*Export_Id.*=[[:space:]]*\\([0-9]*\\).*/\\1/'")
        #     run_cmd(
        #         self.session,
        #         f"dbus-send --type=method_call --print-reply --system "
        #         f"--dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr "
        #         f"org.ganesha.nfsd.exportmgr.UpdateExport string:{self.export_conf} "
        #         f"string:\"EXPORT(Export_Id = {export_id})\""
        #     )

    # -------------------------------
    # Enable Security_Label if required
    # -------------------------------
    # def enable_security_label_if_required(self):
    #     logger.info("[TEST]: Checking if Security_Label needs to be enabled")
    #     if self.security_label:
    #         logger.info("Enabling Security_Label for volume...")
    #         run_cmd(self.session, f"sed -i s/'Security_Label = .*'/'Security_Label = True;'/g {self.export_conf}")
    #         run_cmd(self.session, f"cat {self.export_conf}")
    #         export_id, _ = run_cmd(self.session, f"grep 'Export_Id' {self.export_conf} | sed 's/^[[:space:]]*Export_Id.*=[[:space:]]*\\([0-9]*\\).*/\\1/'")
    #         run_cmd(
    #             self.session,
    #             f"dbus-send --type=method_call --print-reply --system "
    #             f"--dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr "
    #             f"org.ganesha.nfsd.exportmgr.UpdateExport string:{self.export_conf} "
    #             f"string:\"EXPORT(Export_Id = {export_id})\""
    #         )

    # -------------------------------
    # Main export workflow
    # -------------------------------
    def export_volume(self):
        logger.info(f"[TEST]: Starting export process for volume {self.vfs_volume}")
        self.setup_environment()
        self.configure_export()
        run_cmd(self.session, "sleep 5")
        self.validate_export()
        # self.enable_acl_if_required()
        # self.enable_security_label_if_required()
        logger.info("Export completed successfully.")
