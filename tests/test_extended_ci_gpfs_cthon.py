from concurrent.futures import ThreadPoolExecutor
import os
import pytest
import re
from pathlib import Path

from ci_utils.gpfs.gpfs_setup import SpectrumScaleInstaller
from ci_utils.common.remote_session import RemoteSession
from ci_utils.nfs_ganesha.gpfs_ganesha_setup import GPFSGaneshaManager
from ci_utils.common.logger import get_logger
from ci_utils.common.helpers import run_cmd

logger = get_logger(__name__)
WORKSPACE = "/root/workspace"

@pytest.fixture(scope="session")
def nodes(request):
    """Build nodes dictionary from CLI flags"""
    admin_ip = request.config.getoption("--admin-ip")
    servers = request.config.getoption("--server-ips") or [admin_ip]
    return {
        "admin": [admin_ip],
        "servers": servers,
        "clients": request.config.getoption("--client-ips") or [],
        "ces": request.config.getoption("--ces-ips") or [],
    }

@pytest.fixture(scope="session")
def create_sessions(request, nodes):
    username = request.config.getoption("--username")
    password = request.config.getoption("--password")

    all_nodes = list({*nodes["admin"], *nodes["servers"][1:], *nodes["clients"]})
    sessions = []

    def connect_to_node(idx, node_ip):
        test_name = request.node.name.split("[")[0]
        default_dir = f"/root/{test_name}_{idx}"
        logger.info(f"[Fixtures - Session]: Connecting to {node_ip} as {username}")

        session = RemoteSession(
            node_ip=node_ip,
            user=username,
            default_dir=default_dir,
            password=password,
        )
        session.connect()
        session.run(f"mkdir -p {default_dir}")
        return (session, default_dir, node_ip)

    with ThreadPoolExecutor(max_workers=min(8, len(all_nodes))) as executor:
        sessions = list(executor.map(lambda x: connect_to_node(*x), enumerate(all_nodes)))

    yield sessions


@pytest.fixture(scope="session")
def installer(request, nodes, create_sessions):
    system_type = request.config.getoption("--system-type")
    ssh_key = Path(request.config.getoption("--ssh-key"))
    password = request.config.getoption("--password")
    username = request.config.getoption("--username")
    scale_installer = request.config.getoption("--scale-installer")

    node_sessions = {ip: session for session, _, ip in create_sessions}
    admin_ip = nodes["admin"][0]

    return SpectrumScaleInstaller(
        session=node_sessions,
        username=username,
        vm_ip=admin_ip,
        path_version_to_use=scale_installer,
        workspace=WORKSPACE,
        ssh_key=None if password else ssh_key,
        password=password,
        nodes=nodes,
        system_type=system_type,
        installer_http_path=scale_installer if re.match(r"http?://", scale_installer) else None,
    )

@pytest.fixture(scope="session")
def cthon_params(request):
    return {
        "instances": int(request.config.getoption("--cthon-instances")),
        "repeat": int(request.config.getoption("--cthon-repeat")),
        "timeout": int(request.config.getoption("--cthon-timeout")),
    }


def test_spectrum_scale_cluster(installer, nodes, create_sessions, cthon_params):
    """
    Test Spectrum Scale deployment on single or multi-node cluster.
    """
    logger.info("[Test]: Starting Spectrum Scale installation flow")
    export_name = "/ibm/fs1"
    installer.run()

    # --- validate cluster state ---
    logger.info("Sanity checks post installation")
    installer.post_sanity_check()
    logger.info("CES IPs: %s", installer.ces_ips)

    node_sessions = {ip: session for session, _, ip in create_sessions}
    admin_ip = nodes["admin"][0]
    admin_session = node_sessions.get(admin_ip)
    client_ip_1 = nodes["clients"][0]
    client_session_1 = node_sessions.get(client_ip_1)
    ces_ip_1 = nodes["ces"][0] or []
    ces_ip_1 = installer.ces_ips[0] if installer.ces_ips else ValueError("No CES IPs found after installation")

    logger.info("NFS Ganesha setup for GPFS tests")
    ganesha_setup = GPFSGaneshaManager(
        session=admin_session,
        system_type=installer.system_type,
        export=export_name,
    )

    run_cmd(admin_session, "rm -rf nfs-ganesha && git clone --depth=1 https://github.com/nfs-ganesha/nfs-ganesha.git")
    run_cmd(admin_session, "cd nfs-ganesha && git submodule update --recursive --init || git submodule sync")
    
    ganesha_setup.intall_pre_reqs_on_vm()
    ganesha_setup.install_ganesha("/root")
    ganesha_setup.export_nfs_volume()
    ganesha_setup.start_ganesha_service()

    #Run Cthon in parallel
    # Get the repo root (assumes this test file is inside the repo)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    # Build full path to the script
    cthon_script = os.path.join(repo_root, "ci-tests", "ci_utils", "cthon", "cthon_parallel.py")
    # Remote path where you want to place the script
    remote_path = f"/tmp/{os.path.basename(cthon_script)}"

    logger.info(f"Cthon script path: {cthon_script}")
    logger.info(f"Remote path for Cthon script: {remote_path}")

    with open(cthon_script, "r") as f:
        content = f.read()

    # Use echo with EOF to safely write the content
    cmd = f'cat << "EOF" > {remote_path}\n{content}\nEOF'
    run_cmd(client_session_1, cmd)

    logger.info(f"Location of Cthon parallel script: {cthon_script}")
    run_cmd(
        client_session_1,
        f"python3 {remote_path} "
        f"--server {ces_ip_1} "
        f"--export {export_name} "
        f"--instances {cthon_params['instances']} "
        f"--log-dir /tmp "
        f"--nfs-version 4 "
        f"--repeat {cthon_params['repeat']} "
        f"--timeout {cthon_params['timeout']}"
    )


