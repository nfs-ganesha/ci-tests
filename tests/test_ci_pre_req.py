import os
from ci_utils.common.duffy_client import DuffySession
from ci_utils.common.helpers import read_json_file, run_cmd
from ci_utils.common.remote_session import RemoteSession
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest
from ci_utils.common.logger import get_logger, set_test_name
from ci_utils.common.git_helper import GitWorkspace

logger = get_logger(__name__)

# -----------------------
# Predefined paths
# -----------------------
WORKSPACE = os.getenv("WORKSPACE", "/tmp")
SESSION_FILE = os.path.join(WORKSPACE, "duffy_session.json")
BAREMETAL_SESSION_FILE = os.path.join(WORKSPACE, "baremetal_duffy_session.json")

# -------------------------
# Fixtures - Sessions level
# -------------------------
@pytest.fixture(scope="session")
def all_nodes():
    logger.info("[Fixtures - Session]: Getting all reserved nodes from Duffy session file: %s", SESSION_FILE)
    session_data = read_json_file(SESSION_FILE)
    return session_data.get("nodes", [])

@pytest.fixture(scope="session")
def all_baremetal_nodes():
    if not os.path.exists(BAREMETAL_SESSION_FILE):
        return []

    with open(BAREMETAL_SESSION_FILE) as f:
        session_data = read_json_file(BAREMETAL_SESSION_FILE)
    return session_data.get("nodes", [])

# -----------------------
# Fixtures - Test level
# -----------------------
@pytest.fixture(autouse=True)
def attach_test_name(request):
    logger.info("[Fixtures - Test]: Setting test name for logging")
    set_test_name(request.node.name)

# --------------------------
# Actual Pre-Req starts here
# --------------------------

# ------------------------------------
# Common Pre-Req: Clone Gerrit Ganesha Repo
# ------------------------------------
@pytest.mark.checkpatch_fsal
@pytest.mark.pynfs_cthon
def test_clone_gerrit_ganesha_repo():    
    logger.info("[Pre-Req][Common]: Cloning Gerrit Ganesha Repo into workspace: %s", WORKSPACE)
    
    gerrit_host = os.getenv("GERRIT_HOST", "review.gerrithub.io")
    gerrit_project = os.getenv("GERRIT_PROJECT", "ffilz/nfs-ganesha")
    gerrit_refspec = os.getenv("GERRIT_REFSPEC", "")
    if not gerrit_refspec:
        logger.error("GERRIT_REFSPEC environment variable is not set. Cannot proceed.")
        assert False, "GERRIT_REFSPEC is required"

    git_helper = GitWorkspace(
        workspace=WORKSPACE,
        gerrit_host=gerrit_host,
        gerrit_project=gerrit_project,
        gerrit_refspec=gerrit_refspec
    )

    git_helper.prepare_repo()
    assert git_helper.repo_exists()

# ----------------------------
# Pre-Req: Install dependencies
# 1. Checkpatch
# 2. Clang
# 3. FSAL
# Required Nodes: 1
# Node 0: Server + Client (Checkpatch, Clang, FSAL)
# ----------------------------
@pytest.mark.checkpatch_fsal
def test_install_dependencies_for_checkpatch_fsal(all_nodes):
    logger.info("[TEST][Pre-Req][Checkpatch, Clang, FSAL]: Installing dependencies on remote node(s)")
    server_node = all_nodes[0]
    session = RemoteSession(node_ip=server_node, user="root")
    
    logger.info("Installing dependencies on remote node for checkpatch and Clang: %s", server_node)
    _, code = run_cmd(session, "dnf -yq install git git-clang-format python3")
    assert code == 0, f"Failed to install dependencies for checkpatch and Clang"

    logger.info("Installing dependencies on remote node for FSAL: %s", server_node)
    _, code = run_cmd(session, "dnf -y install centos-release-ceph epel-release yum-utils")
    assert code == 0, f"Failed to install dependencies for FSAL"

    duffy_session = DuffySession()
    version = duffy_session.centos_version

    basic_packages = "yum-utils centos-release-ceph epel-release"

    build_requires_common = "git bison cmake dbus-devel flex gcc-c++ krb5-devel libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build xfsprogs-devel"
    build_requires_gpfs_vfs = ""

    build_requires_extra_common = "libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel"
    build_requires_extra_cephfs_vfs_rgw = "libcephfs-devel"
    build_requires_extra_rgw = "librgw-devel"
    build_requires_extra_centos10 = "python3-build python3-wheel"

    if version.startswith("9"):
        logger.info("Install packages for CentOS 9")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {basic_packages} {build_requires_common} {build_requires_gpfs_vfs} {build_requires_extra_common} {build_requires_extra_cephfs_vfs_rgw} {build_requires_extra_rgw}")
        assert code == 0, f"Failed to install dependencies for CentOS 9"
    elif version.startswith("10"):
        logger.info("Install packages for CentOS 10")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {basic_packages} {build_requires_common} {build_requires_gpfs_vfs} {build_requires_extra_common} {build_requires_extra_cephfs_vfs_rgw} {build_requires_extra_rgw} {build_requires_extra_centos10}")
        assert code == 0, f"Failed to install dependencies for CentOS 10"
    else:
        logger.info("Install packages for other CentOS")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {basic_packages} {build_requires_common} {build_requires_gpfs_vfs} {build_requires_extra_common} {build_requires_extra_cephfs_vfs_rgw} {build_requires_extra_rgw} {build_requires_extra_centos10}")
        assert code == 0, f"Failed to install dependencies for other CentOS"


# ----------------------------
# Helper functions: PyNFS & Cthon
# ----------------------------
def setup_install_client_deps(client_node):
    session = RemoteSession(node_ip=client_node, user="root")

    logger.info("Installing dependencies on remote node for PyNFS & Cthon: %s", client_node)
    common_deps = "git gcc nfs-utils"
    cthon_deps = "time make libtirpc-devel"
    pynfs_deps = "redhat-rpm-config krb5-devel python3-devel python3-gssapi python3-ply"
    _, code = run_cmd(session, f"yum --enablerepo=crb install -y {common_deps} {cthon_deps} {pynfs_deps}")
    assert code == 0, f"Failed to install NFS client dependencies"

def setup_node_pynfs_cthon(server_node):
    session = RemoteSession(node_ip=server_node, user="root")
    
    logger.info("Installing dependencies on remote node for PyNFS & Cthon: %s", server_node)
    _, code = run_cmd(session, "dnf -y install centos-release-ceph epel-release dnf-plugins-core")
    assert code == 0, f"Failed to install dependencies for PyNFS & Cthon"

    duffy_session = DuffySession()
    version = duffy_session.centos_version

    build_requires_cthon = "git bison cmake dbus-devel flex gcc-c++ krb5-devel libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build xfsprogs-devel lvm2"
    build_requires_extra_cthon = "libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel libcephfs-devel lua-devel"
    build_requires_extra_centos10 = "python3-build python3-wheel"

    if version.startswith("9"):
        logger.info("Install packages for CentOS 9")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {build_requires_cthon} {build_requires_extra_cthon}")
        assert code == 0, f"Failed to install dependencies for CentOS 9"
    elif version.startswith("10"):
        logger.info("Install packages for CentOS 10")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {build_requires_cthon} {build_requires_extra_cthon} {build_requires_extra_centos10}")
        assert code == 0, f"Failed to install dependencies for CentOS 10"
    else:
        logger.info("Install packages for other CentOS")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {build_requires_cthon} {build_requires_extra_cthon}")
        assert code == 0, f"Failed to install dependencies for other CentOS"

def setup_node_vfs(server_node):
    session = RemoteSession(node_ip=server_node, user="root")
    
    logger.info("Installing dependencies on remote node for VFS %s", server_node)
    run_cmd(session, "dnf -y install yum-utils centos-release-ceph epel-release rpcbind")


    logger.info("Starting rpcbind service on remote node for VFS %s", server_node)
    run_cmd(session, "systemctl start rpcbind")

    logger.info("Disabling SELinux and stopping firewalld on remote node for VFS %s", server_node)
    run_cmd(session, "setenforce 0")
    # run_cmd(session, "systemctl stop firewalld")

    duffy_session = DuffySession() 
    version = duffy_session.centos_version

    build_requires_vfs = "git bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel rpm-build redhat-rpm-config gdb libblkid-devel libcap-devel xfsprogs-devel"
    build_requires_extra_vfs= "libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel libcephfs-devel python3-devel"
    build_requires_add_on_vfs = "selinux-policy-devel sqlite"
    build_requires_extra_centos10 = "python3-build python3-wheel"

    if version.startswith("9"):
        logger.info("Install packages for CentOS 9")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {build_requires_vfs} {build_requires_extra_vfs} {build_requires_add_on_vfs}")
        assert code == 0, f"Failed to install dependencies for CentOS 9"
    elif version.startswith("10"):
        logger.info("Install packages for CentOS 10")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {build_requires_vfs} {build_requires_extra_vfs} {build_requires_add_on_vfs} {build_requires_extra_centos10}")
        assert code == 0, f"Failed to install dependencies for CentOS 10"
    else:
        logger.info("Install packages for other CentOS")
        _, code = run_cmd(session, f"dnf install --enablerepo=crb -y {build_requires_vfs} {build_requires_extra_vfs} {build_requires_add_on_vfs}")
        assert code == 0, f"Failed to install dependencies for other CentOS"

def setup_baremetal_node_pynfs_gpfs(server_node):
    session = RemoteSession(node_ip=server_node, user="root")

    logger.info("Pre-Req for Client operations: %s", server_node)
    setup_install_client_deps(server_node)

    logger.info("Installing dependencies on baremetal node for PyNFS & GPFS: %s", server_node)
    _, code = run_cmd(session, "dnf -y install virt-install libvirt-daemon-kvm qemu-img wget unzip")
    assert code == 0, f"Failed to install dependencies for PyNFS & GPFS"

# -----------------------
# Pre-Req: Install dependencies for PyNFS & Cthon
# Required Nodes: 4
# Node 0: Client (PyNFS)
# Node 1: Server (Cthon CephFS)
# Node 2: Server (PyNFS CephFS)
# Node 3: Server (PyNFS-ACL VFS)
# -----------------------
@pytest.mark.pynfs_cthon
def test_install_dependencies_for_pynfs_cthon(all_nodes, all_baremetal_nodes):
    tasks = {
        all_nodes[0]: setup_install_client_deps,
        all_nodes[1]: setup_node_pynfs_cthon,
        all_nodes[2]: setup_node_pynfs_cthon,
        all_nodes[3]: setup_node_vfs,
        all_baremetal_nodes[0]: setup_baremetal_node_pynfs_gpfs,
    }
    logger.info("[TEST][Pre-Req][PyNFS & Cthon]: Installing dependencies on remote node(s) in parallel")
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(func, node): node for node, func in tasks.items()}

        for future in as_completed(futures):
            node = futures[future]
            try:
                msg = future.result()
                logger.info(
                    "Parallel setup completed successfully on node: %s with output:\n%s",
                    node, msg
                )
            except Exception as e:
                pytest.fail(f"Setup failed on node {node}: {e}")
