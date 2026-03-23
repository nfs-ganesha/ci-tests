import os
import pathlib
from time import sleep
from typing import Any
from py import log
import pytest
import yaml

from ci_utils.ceph.ceph_setup import CephGaneshaSetup
from ci_utils.common.helpers import check_process_crash_and_backtrace, run_cmd, scp_copy, identify_matching_qcow_image
from ci_utils.common.logger import get_logger, set_test_name
from ci_utils.common.remote_session import RemoteSession, RemoteSessionThroughJump
from ci_utils.cthon.cthon_setup import CthonManager
from ci_utils.dev_space.dependencies import install_checkpatch_fsal_dependencies, setup_install_client_deps_cthon_pynfs, setup_server_node_pynfs_cthon
from ci_utils.dev_space.node_reservation import delete_nodes, reserve_nodes
from ci_utils.gpfs.aws_setup import AWSSetupForGPFS
from ci_utils.gpfs.gpfs_setup import SpectrumScaleInstaller
from ci_utils.nfs_ganesha.gpfs_ganesha_setup import GPFSGaneshaManager
from ci_utils.nfs_ganesha.nfs_ganesha_setup import GaneshaManager
from ci_utils.pjdfs.pjdfs_setup import PJDFSManager
from ci_utils.pynfs.pynfs_setup import PyNFSManager
from ci_utils.virtual_machine.vm_setup import VMManager

logger = get_logger(__name__)

PARAM_KEYS = [
    "SERVER_NODE_COUNT",
    "CLIENT_NODE_COUNT",
    "CMAKE_FLAGS",
    "CMAKE_OVERRIDE",
    "CENTOS_VERSION",
    "CENTOS_ARCH",
]
# Get the current working directory as WORKSPACE
WORKSPACE = os.getcwd()
NFS_GANESHA_REPO = os.path.join(WORKSPACE, "nfs-ganesha")
FAILURE_FILE = os.path.join(WORKSPACE, "failures")
os.makedirs(FAILURE_FILE, exist_ok=True)

GPFS_GDB_CMD = (
    "'gdb -q -batch "
    "-ex \"set debuginfod enabled on\" "
    "-ex \"set pagination off\" "
    "-ex \"thread apply all bt full\" "
    "{binary_path} "
    "{core_path}'"
)

# -------------------------
# Fixtures - Session level
# -------------------------
@pytest.fixture(scope="session", autouse=True)
def ci_params():
    params: dict[str, Any] = {k: os.environ.get(k) for k in PARAM_KEYS}

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

    yield nodes  # Tests will run after this point

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
    if reserved_nodes.get("servers"):
        for node in reserved_nodes["servers"]:
            logger.info("[RemoteSession] Connecting to server %s", node)
            try:
                rs = RemoteSession(node_ip=node, default_dir="/root/test_session")
                rs.connect()
                rs.run("mkdir -p /root/test_session")
                sessions["servers"].append(rs)
            except Exception as e:
                logger.error("Failed to connect to server %s: %s", node, e)
                raise

    if reserved_nodes.get("clients"):
        for node in reserved_nodes["clients"]:
            logger.info("[RemoteSession] Connecting to client %s", node)
            try:
                rs = RemoteSession(node_ip=node, default_dir="/root/test_session")
                rs.connect()
                rs.run("mkdir -p /root/test_session")
                sessions["clients"].append(rs)
            except Exception as e:
                logger.error("Failed to connect to client %s: %s", node, e)
                raise

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
    config_path = this_file.parent.parent / "ci_utils" / "config" / "cmake_flags.yml"

    if not config_path.exists():
        raise FileNotFoundError(f"CMake flag config not found: {config_path}")

    with config_path.open() as f:
        return yaml.safe_load(f)

@pytest.fixture(scope="session")
def cmake_flags(request, cmake_config):
    # Optional test-name override
    forced_test_name = getattr(request, "param", None)

    # Default behavior: real PyTest node name
    test_name = forced_test_name or request.node.name

    yaml_default = cmake_config.get("default", [])
    yaml_test_specific = cmake_config.get("tests", {}).get(test_name, [])
    logger.info("[CMake Flags] YAML test-specific for %s: %s", test_name, yaml_test_specific)

    # ENV variable: general flags
    env_flags = os.getenv("CMAKE_FLAGS", "")
    env_flags_list = env_flags.split(",") if env_flags else []

    # ENV override?
    override = os.getenv("CMAKE_OVERRIDE", "").lower() in ("1", "true", "yes")

    if override:
        # Jenkins wants to ignore YAML entirely
        return env_flags_list

    # Merge YAML and CLI (YAML first, then CLI append / override)
    return yaml_default + yaml_test_specific + env_flags_list

# -----------------------
# Fixtures - Test level
# -----------------------
@pytest.fixture(autouse=True)
def attach_test_name(request):
    logger.info("[Fixtures - Test]: Setting test name for logging")
    set_test_name(request.node.name)

# -----------------------
# Fixtures - Module level
# -----------------------

@pytest.fixture(scope="module")
def cephfs_env(remote_sessions):
    logger.info("\n" + "=" * 80 + "\n[Fixture] Setting up CephFS + Ganesha\n" + "=" * 80)

    server = remote_sessions["servers"][0]

    # Ceph setup
    if len(remote_sessions["servers"]) > 1:
        ceph_setup = CephGaneshaSetup(
            session=server,
            extra_sessions=remote_sessions["servers"][1:]
        )
    else:
        ceph_setup = CephGaneshaSetup(session=server)

    subvol_path = ceph_setup.full_setup()

    # Default Ganesha setup (normal mode)
    ganesha_setup = GaneshaManager(
        session=server,
        subvol_path=subvol_path,
        cephfs_name=ceph_setup.cephfs_name
    )
    ganesha_setup.setup()

    return {
        "ceph_setup": ceph_setup,
        "ganesha_setup": ganesha_setup,
        "subvol_path": subvol_path,
        "server": server
    }

@pytest.fixture(scope="module")
@pytest.mark.parametrize("cmake_flags", ["test_fsal_gpfs"], indirect=True)
def gpfs_env(remote_sessions, reserved_nodes, cmake_flags):
    logger.info("\n" + "=" * 80 + "\n[Fixture] Setting up GPFS + Ganesha\n" + "=" * 80)
    
    server = remote_sessions["servers"][0]
    server_ip = reserved_nodes["servers"][0]
    
    logger.info("Pre-reqs for GPFS: %s", server_ip)
    _, code = run_cmd(server, "dnf -y install virt-install libvirt-daemon-kvm qemu-img wget unzip")
    assert code == 0, "Failed to install GPFS prerequisites"

    logger.info("Copying Ganesha repo from Jenkins base path to Root folder")
    scp_copy(server_ip, f"{NFS_GANESHA_REPO}/", remote_dir="/root")

    version, _ = run_cmd(server, "rpm -E %{rhel}")
    version = version.strip()
    logger.info("CentOS Version for GPFS: %s", version)
    
    vm_name = "server-1-vm"
    username = "root"
    ssh_key = "/root/.ssh/id_rsa.pub"
    
    if version.startswith("9"):
        version_constraints = "5.14.0-611.16.1.el9_7"  # Assuming GPFS 6.0
    elif version.startswith("10"):
        version_constraints = "6.12.0-124.11.1.el10_1"  # Assuming GPFS 6.0
    else:
        version_constraints = "6.12.0-124.11.1.el10_1"  # Assuming GPFS 6.0
    
    # -----------------------
    # AWS Setup
    # -----------------------
    logger.info("AWS CLI setup on server node")
    aws_setup = AWSSetupForGPFS(server, aws_repo="https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip")
    aws_setup.setup_aws_cli()
    version_to_use = aws_setup.fetch_versioned_object().strip()
    logger.info("Scale version to use: %s", version_to_use)
    
    # -----------------------
    # VM Setup
    # -----------------------
    image_url = identify_matching_qcow_image(
        server,
        "x86_64",
        version,
        f"https://cloud.centos.org/centos/{version}-stream/x86_64/images/",
        version_constraints=version_constraints
    )
    logger.info("Image URL: %s", image_url)
    
    logger.info("Setting up VM on server node: %s", server_ip)
    vm = VMManager(
        session=server,
        workspace="/root",
        vm_name=vm_name,
        image_url=image_url,
        image_name=image_url.split("/")[-1],
        vm_cpu="2",
        vm_ram="8192",
        vm_disk="30G",
        ssh_key=ssh_key
    )
    vm.check_dependencies()
    vm.setup_network()
    vm.download_image()
    vm.generate_ssh_key()
    
    pubkey, _ = run_cmd(server, f"cat {ssh_key}")
    pubkey = pubkey.strip()
    
    user_data = f"""#cloud-config
users:
  - name: {username}
    ssh-authorized-keys:
      - {pubkey}
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    groups: wheel
    shell: /bin/bash

# Enable passwordless sudo for the user
sudo: ['ALL=(ALL) NOPASSWD:ALL']

# Update system on first boot
package_update: true
package_upgrade: true

# Install required packages
packages:
  - qemu-guest-agent
  - cloud-utils
  - openssh-server

# Enable SSH
ssh_pwauth: false

# Write global environment variables
write_files:
  - path: /etc/environment
    append: true
    content: |
      VERSION_TO_USE={version_to_use}

  - path: /etc/profile.d/custom_vars.sh
    content: |
      export VERSION_TO_USE="{version_to_use}"

# Run commands on first boot
runcmd:
  - systemctl enable qemu-guest-agent
  - systemctl start qemu-guest-agent
  - sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
  - systemctl restart sshd
  - source /etc/environment
  - source /etc/profile.d/custom_vars.sh
"""
    meta_data = f"""instance-id: {vm_name}
local-hostname: {vm_name}
"""
    iso_path = vm.create_cloud_init_iso(user_data=user_data, meta_data=meta_data)
    logger.info("Cloud-init ISO created at: %s", iso_path)
    
    vm.prepare_image_dir()
    vm.create_vm()
    vm_ip = vm.wait_for_vm_ip()
    logger.info("VM IP Address: %s", vm_ip)
    
    vm.wait_for_ssh()
    vm.add_vm_to_known_hosts()
    vm.copy_file_to_vm(local_path=version_to_use, remote_path=f"/tmp/{version_to_use}")
    
    # -----------------------
    # Create Jump Session to VM
    # -----------------------
    logger.info("Creating jump session to VM")
    default_vm_dir = f"/root/test_gpfs_in_vm"
    vm_session = RemoteSessionThroughJump(
        jump_session=server,
        node_ip=vm_ip,
        key_file="/root/.ssh/id_rsa",
    )
    run_cmd(vm_session, f"mkdir -p {default_vm_dir}")
    run_cmd(vm_session, f"cp /tmp/{version_to_use} {default_vm_dir}/")
    run_cmd(vm_session, f"ls -l {default_vm_dir}")
    
    # -----------------------
    # Update Python on VM
    # -----------------------
    logger.info("Updating Python on VM")
    run_cmd(vm_session, "dnf install python3.11 -y")
    bin_path, _ = run_cmd(vm_session, "which python3.11")
    run_cmd(vm_session, f"export ANSIBLE_PYTHON_INTERPRETER={bin_path}")
    
    # -----------------------
    # GPFS Setup
    # -----------------------
    logger.info("Spectrum Scale setup inside VM: %s", vm_ip)
    nodes = {"admin": [vm_ip], "servers": [vm_ip], "clients": [vm_ip]}
    node_sessions_info = {vm_ip: vm_session}
    logger.debug("Node sessions info: %s", node_sessions_info)
    logger.debug("Nodes info: %s", nodes)
    gpfs_installer = SpectrumScaleInstaller(
        node_sessions_info,
        username="root",
        vm_ip=vm_ip,
        path_version_to_use=f"{default_vm_dir}/{version_to_use}",
        workspace=default_vm_dir,
        ssh_key=ssh_key,
        nodes=nodes
    )
    logger.debug("GPFS Installer info: %s", gpfs_installer)
    gpfs_installer.run()
    
    # -----------------------
    # NFS Ganesha Setup for GPFS
    # -----------------------
    logger.info("NFS Ganesha setup for GPFS tests")
    
    flag_str = " ".join(cmake_flags)
    logger.info("Using CMake flags: %s", flag_str)
    
    ganesha_setup = GPFSGaneshaManager(
        session=vm_session,
        cmake_flags=flag_str
    )
    ganesha_setup.intall_pre_reqs_on_vm()
    ganesha_setup.install_ganesha("/root")
    ganesha_setup.export_nfs_volume()
    ganesha_setup.start_ganesha_service()
    
    return {
        "server": server,
        "vm_session": vm_session,
        "vm_ip": vm_ip,
        "ganesha_setup": ganesha_setup,
        "gpfs_setup": gpfs_installer
    }

# # --------------------------------
# ## Actual tests starts here - Ceph
# # --------------------------------
@pytest.mark.dependency(name="test_cephfs_fsal")
@pytest.mark.parametrize("cmake_flags", ["test_fsal_cephfs"], indirect=True)
def test_cephfs_fsal(remote_sessions, reserved_nodes, cmake_flags):
    logger.info("\n" + "=" * 80 + "\n[TEST START]: FSAL CephFS\n" + "=" * 80)

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
        "make -j$(nproc) && make install", check=False
    )
    logger.info("Build completed with code: %s", code)
    logger.info(f"Installing dependencies on server node {server_ip}")
    for sess in remote_sessions["servers"]:
        setup_server_node_pynfs_cthon(sess)
    
    assert code == 0, f"FSAL CephFS tests failed"
    
@pytest.mark.timeout(1200)
@pytest.mark.dependency(name="test_bringup_cephfs", depends=["test_cephfs_fsal"])
def test_bringup_cephfs(cephfs_env):
    logger.info("\n" + "=" * 80 + "\n[TEST START]: Bringup CephFS\n" + "=" * 80)
    
    ceph_setup = cephfs_env["ceph_setup"]
    ganesha_setup = cephfs_env["ganesha_setup"]
    
    # Get Ceph version and write to file for Jenkins post section
    ceph_version = ceph_setup.get_ceph_version()
    logger.info("Ceph version: %s", ceph_version)
    
    # Write version to file so Jenkins can read it in post section
    with open("ceph_version.txt", "w") as f:
        f.write(ceph_version)
    logger.info("Written CEPH_VERSION to ceph_version.txt: %s", ceph_version)
    
    # Get NFS-Ganesha version and write to file for Jenkins post section
    nfs_version = ganesha_setup.get_nfs_version()
    logger.info("NFS-Ganesha version: %s", nfs_version)
    
    # Write version to file so Jenkins can read it in post section
    with open("nfs_version.txt", "w") as f:
        f.write(nfs_version)
    logger.info("Written NFS_VERSION to nfs_version.txt: %s", nfs_version)
    
    assert cephfs_env is not None

@pytest.mark.timeout(1200)
@pytest.mark.dependency(name="test_cthon", depends=["test_cephfs_fsal", "test_bringup_cephfs"])
def test_cthon(remote_sessions, reserved_nodes, cephfs_env):
    logger.info("\n" + "=" * 80 + "\n[TEST START]: Cthon with CephFS\n" + "=" * 80)

    server = remote_sessions["servers"][0]
    server_ip = reserved_nodes["servers"][0]
    client = remote_sessions["clients"][0]
    client_ip = reserved_nodes["clients"][0]  
    subvol_path = cephfs_env["subvol_path"]  

    setup_install_client_deps_cthon_pynfs(client)
    logger.info("Running Cthon tests on node: %s", client_ip)
    cthon = CthonManager(session=client, server_ip=server_ip)
    cthon.clone_and_build()
    fail_found, cthon_logs, rc = cthon.run_all_cthon_test(skip_v3=False)

    # Check for process crash and backtrace
    logger.info("Checking for process crash and backtrace for Ceph-Cthon")
    stacktrace = check_process_crash_and_backtrace(
        server,
        process_name="ganesha",
        cores_dir="/tmp/cores",
        binary_path="/usr/bin/ganesha.nfsd",
        force_check=True,
    )
    if stacktrace:
        backtrace_file = os.path.join(FAILURE_FILE, "cthon_cephfs_ganesha_backtrace.txt")
        with open(backtrace_file, "w", encoding="utf-8") as f:
            f.write(stacktrace)
        logger.info("Ganesha backtrace written to %s", backtrace_file)
    
    # Export logs if there is a failure
    if fail_found:
        cthon_failure_file = os.path.join(FAILURE_FILE, "cthon_logs.txt")
        with open(cthon_failure_file, "w", encoding="utf-8") as f:
            f.write(cthon_logs)
        logger.info("Cthon logs written to %s", cthon_failure_file)
    assert rc == 0 and not fail_found, "Cthon CephFS tests failed"

@pytest.mark.timeout(3600)
@pytest.mark.dependency(name="test_pjdfs", depends=["test_cephfs_fsal", "test_bringup_cephfs"])
def test_pjdfs(remote_sessions, reserved_nodes, cephfs_env):
    logger.info("\n" + "=" * 80 + "\n[TEST START]: PJDFS with CephFS\n" + "=" * 80)

    server = remote_sessions["servers"][0]
    server_ip = reserved_nodes["servers"][0]
    client = remote_sessions["clients"][0]
    client_ip = reserved_nodes["clients"][0]
    subvol_path = cephfs_env["subvol_path"] 

    setup_install_client_deps_cthon_pynfs(client)
    logger.info("Running PJDFS tests on node: %s", client_ip)
    pjdfs = PJDFSManager(session=client, server_ip=server_ip, backend_type="ceph")
    fail_found, failure_summary, code = pjdfs.run_all_tests(export="/nfs/cephfs")

    stacktrace = check_process_crash_and_backtrace(
        server,
        process_name="ganesha",
        cores_dir="/tmp/cores",
        binary_path="/usr/bin/ganesha.nfsd",
        force_check=True,
    )
    if stacktrace:
        backtrace_file = os.path.join(FAILURE_FILE, "pjdfs_cephs_ganesha_backtrace.txt")
        with open(backtrace_file, "w", encoding="utf-8") as f:
            f.write(stacktrace)
        logger.info("Ganesha backtrace written to %s", backtrace_file)
    
    if fail_found:
        pjdfs_failure_file = os.path.join(FAILURE_FILE, "pjdfs_cephs_failures.txt")
        with open(pjdfs_failure_file, "w", encoding="utf-8") as f:
            f.write(failure_summary)
        logger.info("PjdFS failure summary written to %s", pjdfs_failure_file)

    assert not fail_found and code == 0 , "PJDFS CephFS tests failed"

@pytest.mark.timeout(2400)
@pytest.mark.dependency(name="test_pynfs", depends=["test_cephfs_fsal", "test_bringup_cephfs"])
def test_pynfs(remote_sessions, reserved_nodes, cephfs_env):
    logger.info("\n" + "=" * 80 + "\n[TEST START]: PyNFS with CephFS\n" + "=" * 80)
    
    # Reuse of variables
    server = cephfs_env["server"]
    subvol_path = cephfs_env["subvol_path"]
    ceph_setup = cephfs_env["ceph_setup"]

    # Reconfigure Ganesha for pynfs
    ganesha_setup_pynfs = GaneshaManager(
        session=server,
        subvol_path=subvol_path,
        cephfs_name=ceph_setup.cephfs_name,
        test_type="pynfs"
    )
    ganesha_setup_pynfs.write_conf()
    ganesha_setup_pynfs.restart()

    server_ip = reserved_nodes["servers"][0]
    client = remote_sessions["clients"][0]
    client_ip = reserved_nodes["clients"][0]  

    setup_install_client_deps_cthon_pynfs(client)
    logger.info("Running PyNFS tests on node: %s", client_ip)
    pynfs = PyNFSManager(session=client, server_ip=server_ip, backend_type="ceph")
    fail_found, failure_summary, code = pynfs.run_all_tests(export="/nfs/cephfs")
    logger.info("PyNFS test failure summary: %s", failure_summary)

    stacktrace = check_process_crash_and_backtrace(
        server,
        process_name="ganesha",
        cores_dir="/tmp/cores",
        binary_path="/usr/bin/ganesha.nfsd",
        force_check=True,
    )
    if stacktrace:
        backtrace_file = os.path.join(FAILURE_FILE, "pynfs_cephs_ganesha_backtrace.txt")
        with open(backtrace_file, "w", encoding="utf-8") as f:
            f.write(stacktrace)
        logger.info("Ganesha backtrace written to %s", backtrace_file)
    
    if fail_found or code != 0:
        pynfs_failure_file = os.path.join(FAILURE_FILE, "pynfs_cephs_failures.txt")
        with open(pynfs_failure_file, "w", encoding="utf-8") as f:
            f.write(failure_summary)
        logger.info("PyNFS failure summary written to %s", pynfs_failure_file)

    assert code == 0 and not fail_found, "PyNFS CephFS tests failed"

# # --------------------------------
# ## Actual tests starts here - GPFS
# # --------------------------------
@pytest.mark.timeout(3600)
@pytest.mark.dependency(name="test_bringup_gpfs")
def test_bringup_gpfs(gpfs_env):
    logger.info("\n" + "=" * 80 + "\n[TEST START]: Bringup GPFS\n" + "=" * 80)
    
    ganesha_setup = gpfs_env["ganesha_setup"]
    
    # Get NFS-Ganesha version and write to file for Jenkins post section
    nfs_version = ganesha_setup.get_nfs_version()
    gpfs_setup = gpfs_env["gpfs_setup"]
    
    # Get Ceph version and write to file for Jenkins post section
    gpfs_version = gpfs_setup.get_gpfs_version()
    logger.info("GPFS version: %s", gpfs_version)
    
    # Write version to file so Jenkins can read it in post section
    with open("gpfs_version.txt", "w") as f:
        f.write(gpfs_version)
    logger.info("Written GPFS_VERSION to gpfs_version.txt: %s", gpfs_version)
    
    # Get NFS-Ganesha version and write to file for Jenkins post section
    nfs_version = ganesha_setup.get_nfs_version()
    logger.info("NFS-Ganesha version: %s", nfs_version)
    
    # Write version to file so Jenkins can read it in post section
    with open("nfs_version.txt", "w") as f:
        f.write(nfs_version)
    logger.info("Written NFS_VERSION to nfs_version.txt: %s", nfs_version)
    
    assert gpfs_env is not None


@pytest.mark.timeout(1200)
@pytest.mark.dependency(name="test_gpfs_cthon", depends=["test_bringup_gpfs"])
def test_gpfs_cthon(remote_sessions, reserved_nodes, gpfs_env):
    logger.info("\n" + "=" * 80 + "\n[TEST START]: Cthon with GPFS\n" + "=" * 80)
    
    server = gpfs_env["server"]
    vm_session = gpfs_env["vm_session"]
    vm_ip = gpfs_env["vm_ip"]
    server_ip = reserved_nodes["servers"][0]
    
    setup_install_client_deps_cthon_pynfs(server)
    logger.info("Running Cthon tests on node: %s", server_ip)
    cthon = CthonManager(session=server, server_ip=vm_ip)
    cthon.clone_and_build()
    fail_found, cthon_log, rc = cthon.run_all_cthon_test(export="/ibm/fs1", skip_v3=False)

    stacktrace = check_process_crash_and_backtrace(
        vm_session,
        process_name="ganesha",
        cores_dir="/tmp/cores",
        binary_path="/usr/bin/ganesha.nfsd",
        gdb_cmd=GPFS_GDB_CMD,
        force_check=True,
    )
    if stacktrace:
        backtrace_file = os.path.join(FAILURE_FILE, "cthon_gpfs_ganesha_backtrace.txt")
        with open(backtrace_file, "w", encoding="utf-8") as f:
            f.write(stacktrace)
        logger.info("Ganesha backtrace written to %s", backtrace_file)
    
    if fail_found:
        failure_file = os.path.join(FAILURE_FILE, "cthon_gpfs_failures.txt")
        with open(failure_file, "w", encoding="utf-8") as f:
            f.write(cthon_log)
        logger.info("Cthon failure summary written to %s", failure_file)

    assert rc == 0 and not fail_found, "Cthon GPFS tests failed"

@pytest.mark.timeout(3600)
@pytest.mark.dependency(name="test_gpfs_pjdfs", depends=["test_bringup_gpfs"])
def test_gpfs_pjdfs(remote_sessions, reserved_nodes, gpfs_env):
    logger.info("\n" + "=" * 80 + "\n[TEST START]: PJDFS with GPFS\n" + "=" * 80)
    
    server = gpfs_env["server"]
    vm_session = gpfs_env["vm_session"]
    vm_ip = gpfs_env["vm_ip"]
    server_ip = reserved_nodes["servers"][0]
    
    setup_install_client_deps_cthon_pynfs(server)
    logger.info("Running PJDFS tests on node: %s", server_ip)
    pjdfs = PJDFSManager(session=server, server_ip=vm_ip, backend_type="gpfs")
    fail_found, failure_summary, code = pjdfs.run_all_tests(export="/ibm/fs1")

    logger.info("PJDFS test failure summary: %s", failure_summary)

    stacktrace = check_process_crash_and_backtrace(
        vm_session,
        process_name="ganesha",
        cores_dir="/tmp/cores",
        binary_path="/usr/bin/ganesha.nfsd",
        gdb_cmd=GPFS_GDB_CMD,
        force_check=True,
    )
    if stacktrace:
        backtrace_file = os.path.join(FAILURE_FILE, "pjdfs_gpfs_ganesha_backtrace.txt")
        with open(backtrace_file, "w", encoding="utf-8") as f:
            f.write(stacktrace)
        logger.info("Ganesha backtrace written to %s", backtrace_file)
    
    if fail_found or code != 0 :
        failure_file = os.path.join(FAILURE_FILE, "pjdfs_gpfs_failures.txt")
        with open(failure_file, "w", encoding="utf-8") as f:
            f.write(failure_summary)
        logger.info("PJDFS failure summary written to %s", failure_file)

    assert not fail_found and code == 0 , "PJDFS GPFS tests failed"

@pytest.mark.timeout(2400)
@pytest.mark.dependency(name="test_gpfs_pynfs", depends=["test_bringup_gpfs"])
def test_gpfs_pynfs(remote_sessions, reserved_nodes, gpfs_env):
    logger.info("\n" + "=" * 80 + "\n[TEST START]: PyNFS with GPFS\n" + "=" * 80)
    
    server = gpfs_env["server"]
    vm_session = gpfs_env["vm_session"]
    vm_ip = gpfs_env["vm_ip"]
    server_ip = reserved_nodes["servers"][0]
    
    # Wait for NFS grace period
    logger.info("Waiting for 90 seconds before starting PyNFS tests as the NFS grace period is 90 seconds")
    sleep(90)
    
    logger.info("Running PyNFS tests on server node: %s", server_ip)
    pynfs = PyNFSManager(session=server, server_ip=vm_ip, backend_type="gpfs")
    fail_found, failure_summary, code = pynfs.run_all_tests(export="/ibm/fs1")
    logger.info("PyNFS test failure summary: %s", failure_summary)

    stacktrace = check_process_crash_and_backtrace(
        vm_session,
        process_name="ganesha",
        cores_dir="/tmp/cores",
        binary_path="/usr/bin/ganesha.nfsd",
        gdb_cmd=GPFS_GDB_CMD,
        force_check=True,
    )
    if stacktrace:
        backtrace_file = os.path.join(FAILURE_FILE, "pynfs_gpfs_ganesha_backtrace.txt")
        with open(backtrace_file, "w", encoding="utf-8") as f:
            f.write(stacktrace)
        logger.info("Ganesha backtrace written to %s", backtrace_file)
    
    if fail_found or code != 0 :
        failure_file = os.path.join(FAILURE_FILE, "pynfs_gpfs_failures.txt")
        with open(failure_file, "w", encoding="utf-8") as f:
            f.write(failure_summary)
        logger.info("PyNFS failure summary written to %s", failure_file)

    assert code == 0 and not fail_found, "PyNFS GPFS tests failed"
