import os
import pathlib
import pytest
import yaml

from ci_utils.ceph.ceph_setup import CephGaneshaSetup
from ci_utils.common import remote_session
from ci_utils.common.helpers import run_cmd, scp_copy
from ci_utils.common.logger import get_logger, set_test_name
from ci_utils.common.remote_session import RemoteSession
from ci_utils.cthon.cthon_setup import CthonManager
from ci_utils.dev_space.dependencies import install_checkpatch_fsal_dependencies, setup_install_client_deps_cthon_pynfs, setup_server_node_pynfs_cthon
from ci_utils.dev_space.node_reservation import delete_nodes, reserve_nodes
from ci_utils.nfs_ganesha.nfs_ganesha_setup import GaneshaManager
from ci_utils.pynfs.pynfs_setup import PyNFSManager
logger = get_logger(__name__)

PARAM_KEYS = [
    "TEST_SUITE",
    "SERVER_NODE_COUNT",
    "CLIENT_NODE_COUNT",
    "CMAKE_FLAGS",
    "CMAKE_OVERRIDE",
    "CENTOS_VERSION",
    "CENTOS_ARCH",
]
NFS_GANESHA_REPO = "/tmp/workspace/sanity_dev/nfs-ganesha"

@pytest.fixture(scope="session", autouse=True)
def ci_params():
    params = {k: os.environ.get(k) for k in PARAM_KEYS}

    params["SERVER_NODE_COUNT"] = int(params["SERVER_NODE_COUNT"])
    params["CLIENT_NODE_COUNT"] = int(params["CLIENT_NODE_COUNT"])
    params["CMAKE_OVERRIDE"] = params["CMAKE_OVERRIDE"] == "true"

    return params

@pytest.fixture(scope="session", autouse=True)
def reserved_nodes(ci_params):
    """
    Reserve nodes ONCE per pytest session,
    and always release even if tests fail.
    """
    server_count = ci_params["SERVER_NODE_COUNT"]
    client_count = ci_params["CLIENT_NODE_COUNT"]

    logger.info("Reserving nodes: %s server, %s client", server_count, client_count)

    # --- SETUP ---
    nodes = reserve_nodes(server_count, client_count)
    logger.info("Reserved nodes: %s", nodes)

    yield nodes   # Tests will run after this point

    # --- TEARDOWN ---
    logger.info("Releasing reserved nodes...")
    try:
        delete_nodes()
    except Exception as e:
        logger.error("Failed to release nodes: %s", e)

# Create remote sessions once for all nodes
@pytest.fixture(scope="session", autouse=True)
def remote_sessions(reserved_nodes):
    
    sessions = {"servers": [], "clients": []}

    # --- Setup: Connect to nodes ---
    for node in reserved_nodes["servers"]:
        logger.info(f"[RemoteSession] Connecting to server {node}")
        rs = RemoteSession(node_ip=node, default_dir="/root/test_session")
        rs.connect()
        rs.run("mkdir -p /root/test_session")
        sessions["servers"].append(rs)

    for node in reserved_nodes["clients"]:
        logger.info(f"[RemoteSession] Connecting to client {node}")
        rs = RemoteSession(node_ip=node, default_dir="/root/test_session")
        rs.connect()
        rs.run("mkdir -p /root/test_session")
        sessions["clients"].append(rs)

    yield sessions  # tests use these

    # --- Teardown: Close SSH sessions ---
    for group in sessions.values():
        for rs in group:
            try:
                rs.close()
            except Exception:
                pass

@pytest.fixture(scope="session", autouse=True)
def cmake_config():
    # Find repo root based on THIS file's location
    this_file = pathlib.Path(__file__).resolve()

    # Navigate to ci_utils/config/cmake_flags.yml relative to this conftest
    config_path = this_file.parent.parent.parent / "ci_utils" / "config" / "cmake_flags.yml"

    if not config_path.exists():
        raise FileNotFoundError(f"CMake flag config not found: {config_path}")

    with config_path.open() as f:
        return yaml.safe_load(f)
    
# -----------------------
# Fixtures - Test level
# -----------------------
@pytest.fixture(autouse=True)
def attach_test_name(request):
    logger.info("[Fixtures - Test]: Setting test name for logging")
    set_test_name(request.node.name)

@pytest.fixture
def cmake_flags(request, cmake_config):
    # Optional test-name override
    forced_test_name = getattr(request, "param", None)

    # Default behavior: real PyTest node name
    test_name = forced_test_name or request.node.name

    yaml_default = cmake_config.get("default", [])
    yaml_test_specific = cmake_config.get("tests", {}).get(test_name, [])
    logger.info(f"[CMake Flags] YAML test-specific for {test_name}: {yaml_test_specific}")

    # ENV variable: general flags
    env_flags = os.getenv("CMAKE_FLAGS", "")
    env_flags_list = env_flags.split(",") if env_flags else []

    # ENV override?
    override = os.getenv("CMAKE_OVERRIDE", "").lower() in ("1", "true", "yes")

    if override:
        # Jenkins wants to ignore YAML entirely
        return env_flags_list

    # Merge YAML and CLI (YAML first, then CLI append / override)
    return yaml_default + yaml_test_specific +  env_flags_list

# -------------------------
## Actual tests starts here
# -------------------------
@pytest.mark.parametrize("cmake_flags", ["test_fsal_cephfs"], indirect=True)
def test_cephfs_fsal(remote_sessions, reserved_nodes, cmake_flags):
    server = remote_sessions["servers"][0]
    server_ip = reserved_nodes["servers"][0]
    root_ganesha = "/root/nfs-ganesha"

    logger.info("Remote Sessions: %s", remote_sessions)

    flag_str = " ".join(cmake_flags)
    logger.info("Using CMake flags: %s", flag_str)

    logger.info("Starting FSAL CephFS test on server: %s", server_ip)
    scp_copy(server_ip, f"{NFS_GANESHA_REPO}/", remote_dir="/root")
    install_checkpatch_fsal_dependencies(server)
    run_cmd(server, f"ls -la {root_ganesha}")
    _, code = run_cmd(
        server,
        f"cd {root_ganesha} && "
        "rm -rf build && "
        "mkdir -p build && "
        "cd build && "
        f"cmake ../src {flag_str} && "
        "make", check=False
    )
    logger.info("Build completed with code: %s", code)

    assert code == 0, f"FSAL CephFS tests failed"


@pytest.mark.timeout(1200) 
def test_bringup_cephfs(remote_sessions, reserved_nodes):
    try:
        logger.info("[TEST START]: Cthon with CephFS")

        server = remote_sessions["servers"][0]
        server_ip = reserved_nodes["servers"][0]
        root_ganesha = "/root/nfs-ganesha"

        _, code = run_cmd(
            server,
            f"cd {root_ganesha} && cd build && "
            "make install"
        )

        assert code == 0, f"Cthon Make CephFS tests failed"

        logger.info(f"Installing dependencies on server node {server_ip}")
        for sess in remote_sessions["servers"]:
            setup_server_node_pynfs_cthon(sess)

        logger.info("Ceph setup")
        if len(remote_sessions["servers"]) > 1:
            ceph_setup = CephGaneshaSetup(session=server, extra_sessions=remote_sessions["servers"][1:])
        else:
            ceph_setup = CephGaneshaSetup(session=remote_sessions["servers"][0])
        subvol_path = ceph_setup.full_setup()

        logger.info("NFS Ganesha setup")
        ganesha_setup = GaneshaManager(
            session=server,
            subvol_path=subvol_path,
            cephfs_name=ceph_setup.cephfs_name
        )
        ganesha_setup.setup()
        assert f"CephFS setup completed"
    except Exception as e:
        logger.error(f"CephFS bringup failed: {e}")

@pytest.mark.timeout(1200) 
def test_cthon(remote_sessions, reserved_nodes):
    logger.info("[TEST START]: Cthon with CephFS")

    server_ip = reserved_nodes["servers"][0]
    client = remote_sessions["clients"][0]
    client_ip = reserved_nodes["clients"][0]    

    setup_install_client_deps_cthon_pynfs(client)
    logger.info("Running Cthon tests on node: %s", client_ip)
    cthon = CthonManager(session=client, server_ip=server_ip)
    cthon.clone_and_build()
    _, rc = cthon.run_all_cthon_test(skip_v3=True)
    
    assert rc == 0, f"Cthon CephFS tests failed"

def test_pynfs(remote_sessions, reserved_nodes):
    logger.info("[TEST START]: PyNFS with CephFS")

    server_ip = reserved_nodes["servers"][0]
    client = remote_sessions["clients"][0]
    client_ip = reserved_nodes["clients"][0]    

    setup_install_client_deps_cthon_pynfs(client)
    logger.info("Running PyNFS tests on node: %s", client_ip)
    pynfs = PyNFSManager(session=client, server_ip=server_ip, backend_type="ceph")
    _, failure_summary, code = pynfs.run_all_tests(export="/nfs/cephfs")
    logger.info("PyNFS test failure summary: %s", failure_summary)
    
    assert code == 0, f"PyNFS CephFS tests failed"