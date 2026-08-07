from ci_utils.common.duffy_client import DuffySession

from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger
from ci_utils.common.remote_session import RemoteSession
logger = get_logger(__name__)

def install_checkpatch_fsal_dependencies(session) -> None:
    """
    Install dependencies for Checkpatch, Clang, and FSAL on a remote node.

    Args:
        node_ip: IP of the remote node.
        user: SSH user (default: root)

    Raises:
        RuntimeError: if installation fails
    """

    logger.info("Installing dependencies on remote node: %s", session)

    # FSAL pre-requisites
    cmd = "dnf -y install centos-release-ceph-tentacle epel-release centos-release-gluster yum-utils"
    _, code = run_cmd(session, cmd)
    if code != 0:
        raise RuntimeError(f"Failed to install FSAL dependencies on {session}")

    # Determine CentOS version from Duffy session
    duffy_session = DuffySession()
    version = duffy_session.centos_version

    basic_packages = "centos-release-gluster yum-utils centos-release-ceph-tentacle epel-release"
    build_requires_common = "git bison cmake dbus-devel flex gcc-c++ krb5-devel libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build xfsprogs-devel openssl-devel"
    build_requires_extra_common = "libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel"
    build_requires_extra_cephfs_vfs_rgw = "libcephfs-devel"

    install_cmd = (
        f"dnf install --enablerepo=crb -y {basic_packages} "
        f"{build_requires_common} {build_requires_extra_common} "
        f"{build_requires_extra_cephfs_vfs_rgw}"
    )

    logger.info("Installing build dependencies for CentOS version: %s", version)
    _, code = run_cmd(session, install_cmd)
    if code != 0:
        raise RuntimeError(f"Failed to install build dependencies on {session} (CentOS {version})")

    logger.info("Dependencies installed successfully on %s", session)

def setup_install_client_deps_cthon_pynfs(session):
    logger.info("Installing dependencies on remote node for PyNFS & Cthon")
    common_deps = "git gcc nfs-utils"
    cthon_deps = "time make libtirpc-devel"
    pynfs_deps = "redhat-rpm-config krb5-devel python3-devel python3-gssapi python3-ply"
    _, code = run_cmd(session, f"yum --enablerepo=crb install -y {common_deps} {cthon_deps} {pynfs_deps}")
    assert code == 0, f"Failed to install NFS client dependencies"

def setup_server_node_pynfs_cthon(session):    
    logger.info("Installing dependencies on remote node for PyNFS & Cthon")
    _, code = run_cmd(session, "dnf -y install centos-release-ceph-tentacle epel-release dnf-plugins-core")
    assert code == 0, f"Failed to install dependencies for PyNFS & Cthon"

    duffy_session = DuffySession()
    version = duffy_session.centos_version

    build_requires_cthon = "git bison cmake dbus-devel flex gcc-c++ krb5-devel libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build xfsprogs-devel openssl-devel lvm2 podman chrony"
    build_requires_extra_cthon = "libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel libcephfs-devel lua-devel"

    if version.startswith("9"):
        logger.info("Install packages for CentOS 9")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {build_requires_cthon} {build_requires_extra_cthon}")
        assert code == 0, f"Failed to install dependencies for CentOS 9"
    else:
        logger.info("Install packages for other CentOS")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {build_requires_cthon} {build_requires_extra_cthon}")
        assert code == 0, f"Failed to install dependencies for other CentOS"