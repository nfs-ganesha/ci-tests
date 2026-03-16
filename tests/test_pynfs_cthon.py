import os
import pathlib
import re
import threading
from time import sleep

import yaml
from ci_utils.ceph.ceph_setup import CephGaneshaSetup
from ci_utils.common.remote_session import RemoteSession, RemoteSessionThroughJump
from ci_utils.cthon.cthon_setup import CthonManager
from ci_utils.gpfs.aws_setup import AWSSetupForGPFS
from ci_utils.gpfs.gpfs_setup import SpectrumScaleInstaller
from ci_utils.nfs_ganesha.gpfs_ganesha_setup import GPFSGaneshaManager
from ci_utils.nfs_ganesha.nfs_ganesha_setup import GaneshaManager
from ci_utils.nfs_ganesha.vfs_nfs_ganesha_setup import VFSGaneshaManager
from ci_utils.pynfs.pynfs_setup import PyNFSManager
from ci_utils.vfs.vfs_setup import VFSVolumeExporter
from ci_utils.virtual_machine.vm_setup import VMManager
import pytest
from ci_utils.common.logger import get_logger
from ci_utils.common.logger import set_test_name
from ci_utils.common.helpers import *


logger = get_logger(__name__)

# -----------------------
# Predefined paths
# -----------------------
WORKSPACE = os.getenv("WORKSPACE", "/tmp")
SESSION_FILE = os.path.join(WORKSPACE, "duffy_session.json")
BAREMETAL_SESSION_FILE = os.path.join(WORKSPACE, "baremetal_duffy_session.json")
FAILURE_FILE = os.path.join(WORKSPACE, "failures")
os.makedirs(FAILURE_FILE, exist_ok=True)
SUMMARY_FILE = os.path.join(WORKSPACE, "summary_cthon_pynfs.txt")
SUMMARY_STATUS = os.path.join(WORKSPACE, "summary_status.txt")

# -------------------------
# Fixtures - Sessions level
# -------------------------
@pytest.fixture(scope="session")
def all_nodes():
    session_file = SESSION_FILE
    logger.info("[Fixtures - Session]: Getting all reserved nodes from Duffy session file: %s", session_file)
    session_data = read_json_file(session_file)
    return session_data.get("nodes", [])

@pytest.fixture(scope="session")
def all_baremetal_nodes():
    if not os.path.exists(BAREMETAL_SESSION_FILE):
        return []

    with open(BAREMETAL_SESSION_FILE) as f:
        session_data = read_json_file(BAREMETAL_SESSION_FILE)
    return session_data.get("nodes", [])

@pytest.fixture(scope="session")
def cmake_config():
    # Find repo root based on THIS file's location
    this_file = pathlib.Path(__file__).resolve()

    # Navigate to ci_utils/config/cmake_flags.yml relative to this conftest
    config_path = this_file.parent.parent / "ci_utils" / "config" / "cmake_flags.yml"

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
def create_session(all_nodes, all_baremetal_nodes, request):
    logger.info("[Fixtures - Test]: Creating remote session(s)")
    
    node_param = getattr(request, "param", 0)

    if isinstance(node_param, int):
        node_param = [node_param]

    baremetal = request.node.get_closest_marker("baremetal") is not None

    sessions = []
    for idx in node_param:
        node_ip = all_nodes[idx]
        if baremetal:
            node_ip = all_baremetal_nodes[idx]
        test_name_param = request.node.name
        test_name = re.sub(r"\[.*\]$", "", test_name_param)
        default_dir = f"/root/{test_name}_{idx}"

        session = RemoteSession(node_ip=node_ip, user="root", default_dir=default_dir)
        session.connect()
        session.run(f"mkdir -p {default_dir}")
        scp_copy(node_ip, f"{WORKSPACE}/nfs-ganesha", remote_dir=default_dir)
        sessions.append((session, default_dir, node_ip))

    yield sessions if len(sessions) > 1 else sessions[0]
    
    # Teardown
    logger.info("[Fixtures - Test]: Closing remote session(s)")
    for sess, _, _ in sessions:
        sess.close()

@pytest.fixture
def cmake_flags(request, cmake_config):
    # Optional test-name override
    forced_test_name = getattr(request, "param", None)

    # Default behavior: real PyTest node name
    test_name = forced_test_name or request.node.name

    yaml_default = cmake_config.get("default", [])
    yaml_test_specific = cmake_config.get("tests", {}).get(test_name, [])
    logger.info(f"Getting default values: {os.environ}")

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

# -----------------------
# Actual Tests Starts Here
# -----------------------

# -------------------------
# Test 1: Cthon with CephFS
# Node allocation: 1 (index 1)
# -------------------------
@pytest.mark.parametrize("create_session", [1], indirect=True)
@pytest.mark.parametrize("cmake_flags", ["test_fsal_cephfs"], indirect=True)
@pytest.mark.timeout(1200) 
def test_cthon_cephfs(create_session, cmake_flags):
    try:
        logger.info("[TEST START]: Cthon with CephFS")
        
        remote_session, test_workspace, server_node = create_session

        logger.info("[TEST NODE DETAILS]: Node: %s", server_node)
        logger.info("[TEST WORKSPACE DETAILS]: Workspace: %s", test_workspace)
        logger.info("[TEST SESSION DETAILS]: Session: %s", remote_session)

        flag_str = " ".join(cmake_flags)
        logger.info("Using CMake flags: %s", flag_str)

        _, code = run_cmd(
            remote_session,
            f"cd {test_workspace}/nfs-ganesha && "
            "rm -rf build && "
            "mkdir -p build && "
            "cd build && "
            f"cmake ../src {flag_str} && "
            "make && "
            "make install"
        )

        assert code == 0, f"Cthon Make CephFS tests failed"

        logger.info("Ceph setup for Cthon tests")
        ceph_setup = CephGaneshaSetup(session=remote_session)
        subvol_path = ceph_setup.full_setup()

        logger.info("NFS Ganesha setup for Cthon tests")
        ganesha_setup = GaneshaManager(
            session=remote_session,
            subvol_path=subvol_path,
            cephfs_name=ceph_setup.cephfs_name
        )
        ganesha_setup.setup()

        logger.info("Running Cthon tests on node: %s", server_node)
        cthon = CthonManager(session=remote_session)
        cthon.clone_and_build()

        result_holder = [None]
        ganesha_died = threading.Event()
        test_done = threading.Event()

        def run_cthon():
            try:
                _, cthon_logs, rc = cthon.run_all_cthon_test(skip_v3=True)
                result_holder[0] = (cthon_logs, rc, False)
            except Exception as e:
                result_holder[0] = (str(e) or "Test aborted", 1, ganesha_died.is_set())
            finally:
                test_done.set()

        def watch_ganesha():
            while not test_done.is_set() and not ganesha_died.is_set():
                _, code = run_cmd(remote_session, "pgrep ganesha", check=False)
                if code != 0:
                    ganesha_died.set()
                    remote_session.close()
                    break
                sleep(5)

        t1 = threading.Thread(target=run_cthon)
        t2 = threading.Thread(target=watch_ganesha)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if result_holder[0] is None:
            result_holder[0] = ("Test thread failed without result", 1, False)
        cthon_logs, rc, ganesha_stopped = result_holder[0]
        if ganesha_stopped:
            logger.error("Ganesha process died during test; test run aborted.")
        logger.info("Type of rc: %s", type(rc))
        if rc != 0 or ganesha_stopped:
            # Get ganesha backtrace when session is still open (not ganesha_stopped, or session may be closed)
            stacktrace = check_process_crash_and_backtrace(
                remote_session,
                process_name="ganesha",
                cores_dir="/tmp/cores",
                binary_path="/usr/bin/ganesha.nfsd",
            )
            if stacktrace:
                backtrace_file = os.path.join(FAILURE_FILE, "cthon_cephfs_ganesha_backtrace.txt")
                with open(backtrace_file, "w", encoding="utf-8") as f:
                    f.write(stacktrace)
                logger.info("Ganesha backtrace written to %s", backtrace_file)
            cthon_log_file = os.path.join(FAILURE_FILE, "cthon_logs.txt")
            with open(cthon_log_file, "w", encoding="utf-8") as f:
                f.write(cthon_logs)
            logger.info("Cthon logs written to %s", cthon_log_file)
        else:
            logger.info("Cthon tests completed successfully")
            failure_msg = f"\n**🟢 Cthon-CephFS:** `Passed`"
            with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
                f.write(failure_msg)
            with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
                f.write("\nPassed")

        assert rc == 0 and not ganesha_stopped, (
            f"Cthon CephFS tests failed" + (" (ganesha died during test)" if ganesha_stopped else "")
        )
    except Exception as e:
        failure_msg = f"\n**🔴 Cthon-CephFS:** `Failed`"
        with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(failure_msg)
        with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
            f.write("\nFailed")


# -----------------------------------------------------------------
# Test 2: PyNFS with CephFS
# Node allocation: 2 (index 0 - client, index 2 - server)
# -----------------------------------------------------------------
@pytest.mark.parametrize("create_session", [[0, 2]], indirect=True)
@pytest.mark.parametrize("cmake_flags", ["test_fsal_cephfs"], indirect=True)
def test_pynfs_cephfs(create_session, cmake_flags):
    try:
        logger.info("[TEST START]: PyNFS with CephFS")
        (client_session, client_workspace, client_node), (server_session, server_workspace, server_node) = create_session
        failure_msg = ""

        logger.info("[TEST NODE DETAILS]: Client Node: %s, Server Node: %s", client_node, server_node)
        logger.info("[TEST WORKSPACE DETAILS]: Client Workspace: %s, Server Workspace: %s", client_workspace, server_workspace)
        logger.info("[TEST SESSION DETAILS]: Client Session: %s, Server Session: %s", client_session, server_session)

        flag_str = " ".join(cmake_flags)
        logger.info("Using CMake flags: %s", flag_str)

        _, code = run_cmd(
            server_session,
            f"cd {server_workspace}/nfs-ganesha && "
            "rm -rf build && "
            "mkdir -p build && "
            "cd build && "
            f"cmake ../src {flag_str} && "
            "make && "
            "make install"
        )

        assert code == 0, f"PyNFS Make CephFS tests failed"

        logger.info("Ceph setup for PyNFS tests")
        ceph_setup = CephGaneshaSetup(session=server_session)
        subvol_path = ceph_setup.full_setup()

        logger.info("NFS Ganesha setup for PyNFS tests")
        ganesha_setup = GaneshaManager(
            session=server_session,
            subvol_path=subvol_path,
            cephfs_name=ceph_setup.cephfs_name,
            test_type="pynfs"
        )
        ganesha_setup.setup()

        # -----------------------
        # Client Execution (thread 1: pynfs tests; thread 2: watch ganesha)
        # -----------------------
        logger.info("Running PyNFS tests on client node: %s", client_node)
        pynfs = PyNFSManager(session=client_session, server_ip=server_node, backend_type="ceph")
        result_holder = [None]
        ganesha_died = threading.Event()
        test_done = threading.Event()

        def run_pynfs():
            try:
                r = pynfs.run_all_tests(export="/nfs/cephfs")
                result_holder[0] = (r[0], r[1], r[2], False)
            except Exception as e:
                result_holder[0] = (True, str(e) or "Test aborted", 1, ganesha_died.is_set())
            finally:
                test_done.set()

        def watch_ganesha():
            while not test_done.is_set() and not ganesha_died.is_set():
                _, code = run_cmd(server_session, "pgrep ganesha", check=False)
                if code != 0:
                    ganesha_died.set()
                    client_session.close()
                    break
                sleep(5)

        t1 = threading.Thread(target=run_pynfs)
        t2 = threading.Thread(target=watch_ganesha)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if result_holder[0] is None:
            result_holder[0] = (True, "Test thread failed without result", 1, False)
        fail_found, failure_summary, code, ganesha_stopped = result_holder[0]
        if ganesha_stopped:
            logger.error("Ganesha process died during test; test run aborted.")

        logger.info("Value %s: Type of rc: %s", fail_found, type(fail_found))
        logger.info("Value %s: Type of code: %s", code, type(code))

        if fail_found or ganesha_stopped:
            stacktrace = check_process_crash_and_backtrace(
                server_session,
                process_name="ganesha",
                cores_dir="/tmp/cores",
                binary_path="/usr/bin/ganesha.nfsd",
            )
            if stacktrace:
                backtrace_file = os.path.join(FAILURE_FILE, "pynfs_cephs_ganesha_backtrace.txt")
                with open(backtrace_file, "w", encoding="utf-8") as f:
                    f.write(stacktrace)
                logger.info("Ganesha backtrace written to %s", backtrace_file)
            failure_file = os.path.join(FAILURE_FILE, "pynfs_cephs_failures.txt")
            with open(failure_file, "w", encoding="utf-8") as f:
                f.write(failure_summary)
            logger.info("PyNFS failure summary written to %s", failure_file)
        else:
            logger.info("PyNFS tests completed successfully")
            failure_msg = f"\n**🟢 PyNFS-CephFS:** `Passed`"
            with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
                f.write(failure_msg)
            with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
                f.write("\nPassed")

        assert fail_found == False and code == 0 and not ganesha_stopped, (
            "PyNFS CephFS tests failed" + (" (ganesha died during test)" if ganesha_stopped else "")
        )

    except Exception as e:
        failure_msg = f"\n**🔴 PyNFS-CephFS:** `Failed`"
        with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(failure_msg)
        with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
            f.write("\nFailed")

# -------------------------------------------------------------------
# Test 3: PyNFS-ACL with VFS
# Node allocation: 2 (index 0 - client, index 3 - server)
# -------------------------------------------------------------------
@pytest.mark.parametrize("create_session", [[0, 3]], indirect=True)
@pytest.mark.parametrize("cmake_flags", ["test_fsal_vfs"], indirect=True)
def test_pynfs_acl_vfs(create_session, cmake_flags):
    try:
        logger.info("[TEST START]: PyNFS-ACL with VFS")
        (client_session, client_workspace, client_node), (server_session, server_workspace, server_node) = create_session
        failure_msg = ""

        logger.info("[TEST NODE DETAILS]: Client Node: %s, Server Node: %s", client_node, server_node)
        logger.info("[TEST WORKSPACE DETAILS]: Client Workspace: %s, Server Workspace: %s", client_workspace, server_workspace)
        logger.info("[TEST SESSION DETAILS]: Client Session: %s, Server Session: %s", client_session, server_session)

        flag_str = " ".join(cmake_flags)
        logger.info("Using CMake flags: %s", flag_str)

        logger.info("NFS Ganesha setup for VFS tests")
        ganesha_setup = VFSGaneshaManager(
            session=server_session,
            cmake_flags=flag_str
        )
        ganesha_setup.install_ganesha(server_workspace)
        
        logger.info("VFS Exporter setup for NFS tests")
        vfs_setup = VFSVolumeExporter(server_session, vfs_volume="pynfs", enable_acl=True, security_label=False)
        vfs_setup.export_volume()

        
        # -----------------------
        # Client Execution (thread 1: pynfs tests; thread 2: watch ganesha)
        # -----------------------
        logger.info("Running PyNFS-ACL tests on client node for VFS: %s", client_node)

        pynfs = PyNFSManager(session=client_session, server_ip=server_node, backend_type="acl_vfs")
        result_holder = [None]
        ganesha_died = threading.Event()
        test_done = threading.Event()

        def run_pynfs():
            try:
                r = pynfs.run_all_tests(export="/pynfs")
                result_holder[0] = (r[0], r[1], r[2], False)
            except Exception as e:
                result_holder[0] = (True, str(e) or "Test aborted", 1, ganesha_died.is_set())
            finally:
                test_done.set()

        def watch_ganesha():
            while not test_done.is_set() and not ganesha_died.is_set():
                _, code = run_cmd(server_session, "pgrep ganesha", check=False)
                if code != 0:
                    ganesha_died.set()
                    client_session.close()
                    break
                sleep(5)

        t1 = threading.Thread(target=run_pynfs)
        t2 = threading.Thread(target=watch_ganesha)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if result_holder[0] is None:
            result_holder[0] = (True, "Test thread failed without result", 1, False)
        fail_found, failure_summary, code, ganesha_stopped = result_holder[0]
        if ganesha_stopped:
            logger.error("Ganesha process died during test; test run aborted.")

        if fail_found or ganesha_stopped:
            stacktrace = check_process_crash_and_backtrace(
                server_session,
                process_name="ganesha",
                cores_dir="/tmp/cores",
                binary_path="/usr/bin/ganesha.nfsd",
            )
            if stacktrace:
                backtrace_file = os.path.join(FAILURE_FILE, "pynfs_acl_vfs_ganesha_backtrace.txt")
                with open(backtrace_file, "w", encoding="utf-8") as f:
                    f.write(stacktrace)
                logger.info("Ganesha backtrace written to %s", backtrace_file)
            failure_file = os.path.join(FAILURE_FILE, "pynfs_acl_vfs_failures.txt")
            with open(failure_file, "w", encoding="utf-8") as f:
                f.write(failure_summary)
            logger.info("PyNFS-ACL with VFS failure summary written to %s", failure_file)
        else:
            logger.info("PyNFS-ACL with VFS tests completed successfully")
            failure_msg = f"\n**🟢 PyNFS-ACL-VFS:** `Passed`"
            with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
                f.write(failure_msg)
            with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
                f.write("\nPassed")
        
        assert fail_found == False and code == 0 and not ganesha_stopped, (
            "PyNFS CephFS tests failed" + (" (ganesha died during test)" if ganesha_stopped else "")
        )
    except Exception as e:
        failure_msg = f"\n**🔴 PyNFS-ACL-VFS:** `Failed`"
        with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(failure_msg)
        with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
            f.write("\nFailed")

# -----------------------
# Test 4: PyNFS with GPFS
# Node allocation: 2 (index 0 - baremetal client, index 1 - baremetal server)
# -----------------------
@pytest.mark.baremetal
@pytest.mark.parametrize("create_session", [0], indirect=True)
@pytest.mark.parametrize("cmake_flags", ["test_fsal_gpfs"], indirect=True)
def test_pynfs_gpfs(create_session, cmake_flags):
    try:
        logger.info("[TEST START]: PyNFS with GPFS")
        server_session, server_workspace, server_node = create_session
        failure_msg = ""

        logger.info("[TEST NODE DETAILS]: Server Node: %s", server_node)
        logger.info("[TEST WORKSPACE DETAILS]:Server Workspace: %s", server_workspace)
        logger.info("[TEST SESSION DETAILS]: Server Session: %s", server_session)

        version, _ = run_cmd(server_session, "rpm -E %{rhel}")
        version = version.strip()
        logger.info("CentOS Version for GPFS: %s", version)

        vm_name = "centos9-vm"
        username = "root"
        ssh_key = "/root/.ssh/id_rsa.pub"

        if version.startswith("9"):
            version_constraints = "5.14.0-611.16.1.el9_7" #Assuming GPFS 6.0 https://www.ibm.com/docs/en/STXKQY/gpfsclustersfaq.html#fsi
        elif version.startswith("10"):
            version_constraints = "6.12.0-124.11.1.el10_1" #Assuming GPFS 6.0 https://www.ibm.com/docs/en/STXKQY/gpfsclustersfaq.html#fsi
        else:
            version_constraints = "6.12.0-124.11.1.el10_1" #Assuming GPFS 6.0 https://www.ibm.com/docs/en/STXKQY/gpfsclustersfaq.html#fsi

        gerrit_host = os.getenv("GERRIT_HOST", "review.gerrithub.io")
        gerrit_project = os.getenv("GERRIT_PROJECT", "ffilz/nfs-ganesha")
        gerrit_refspec = os.getenv("GERRIT_REFSPEC", "")
        if not gerrit_refspec:
            logger.error("GERRIT_REFSPEC environment variable is not set. Cannot proceed.")
            assert False, "GERRIT_REFSPEC is required"

        # -----------------------
        # AWS Setup
        # -----------------------
        logger.info("AWS CLI setup on baremetal node")
        aws_setup = AWSSetupForGPFS(server_session, aws_repo="https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip")
        aws_setup.setup_aws_cli()
        verion_to_use = aws_setup.fetch_versioned_object().strip()
        logger.info("Scale version to use: %s", verion_to_use)

        # -----------------------
        # VM Setup
        # -----------------------
        image_url = identify_matching_qcow_image(server_session, "x86_64", version, f"https://cloud.centos.org/centos/{version}-stream/x86_64/images/", version_constraints=version_constraints)
        logger.info("Image URL: %s", image_url)

        logger.info("Setting up VM on baremetal node: %s", server_node)
        vm = VMManager(
            session=server_session,
            workspace=server_workspace,
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

        pubkey, _ = run_cmd(server_session, f"cat {ssh_key}")
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
      VERSION_TO_USE={verion_to_use}
      GERRIT_HOST={gerrit_host}
      GERRIT_PROJECT={gerrit_project}
      GERRIT_REFSPEC={gerrit_refspec}

  - path: /etc/profile.d/custom_vars.sh
    content: |
      export VERSION_TO_USE="{verion_to_use}"
      export GERRIT_HOST="{gerrit_host}"
      export GERRIT_PROJECT="{gerrit_project}"
      export GERRIT_REFSPEC="{gerrit_refspec}"

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
        vm.copy_file_to_vm(local_path=verion_to_use, remote_path=f"/tmp/{verion_to_use}")

        # -----------------------
        # Create Jump Session to VM
        # -----------------------
        logger.info("Creating jump session to VM")
        default_vm_dir = f"/root/test_gpfs_in_vm"
        vm_session = RemoteSessionThroughJump(
            jump_session=server_session,
            node_ip=vm_ip,
            key_file="/root/.ssh/id_rsa",
        )
        run_cmd(vm_session, f"mkdir -p {default_vm_dir}")
        run_cmd(vm_session, f"cp /tmp/{verion_to_use} {default_vm_dir}/")
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
        gpfs_installer = SpectrumScaleInstaller(node_sessions_info, username="root", vm_ip=vm_ip, path_version_to_use=f"{default_vm_dir}/{verion_to_use}", workspace=default_vm_dir, ssh_key=ssh_key, nodes=nodes)
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

        # -----------------------
        # Client Execution (thread 1: pynfs tests; thread 2: watch ganesha on VM)
        # -----------------------
        logger.info("Waiting for 90 seconds before starting PyNFS tests as the NFS grace period is 90 seconds")
        sleep(90)
        logger.info("Running PyNFS tests on barmetal node: %s", server_node)
        pynfs = PyNFSManager(session=server_session, server_ip=vm_ip, backend_type="gpfs")
        result_holder = [None]
        ganesha_died = threading.Event()
        test_done = threading.Event()

        def run_pynfs():
            try:
                r = pynfs.run_all_tests(export="/ibm/fs1")
                result_holder[0] = (r[0], r[1], r[2], False)
            except Exception as e:
                result_holder[0] = (True, str(e) or "Test aborted", 1, ganesha_died.is_set())
            finally:
                test_done.set()

        def watch_ganesha():
            while not test_done.is_set() and not ganesha_died.is_set():
                _, code = run_cmd(vm_session, "pgrep ganesha", check=False)
                if code != 0:
                    ganesha_died.set()
                    server_session.close()
                    break
                sleep(5)

        t1 = threading.Thread(target=run_pynfs)
        t2 = threading.Thread(target=watch_ganesha)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        vm_session.close()

        if result_holder[0] is None:
            result_holder[0] = (True, "Test thread failed without result", 1, False)
        fail_found, failure_summary, code, ganesha_stopped = result_holder[0]
        if ganesha_stopped:
            logger.error("Ganesha process died during test; test run aborted.")

        logger.info("Value %s: Type of rc: %s", fail_found, type(fail_found))
        logger.info("Value %s: Type of code: %s", code, type(code))

        if fail_found or ganesha_stopped:
            # Ganesha runs in VM; use vm_session for backtrace (server_session may be closed if ganesha died)
            # gdb_cmd wrapped in single quotes so it survives unpacking when run via jump host session
            gdb_cmd = (
                "'gdb -q -batch "
                "-ex \"set debuginfod enabled on\" "
                "-ex \"set pagination off\" "
                "-ex \"thread apply all bt full\" "
                "{binary_path} "
                "{core_path}'"
            )
            stacktrace = check_process_crash_and_backtrace(
                vm_session,
                process_name="ganesha",
                cores_dir="/tmp/cores",
                binary_path="/usr/bin/ganesha.nfsd",
                gdb_cmd=gdb_cmd,
            )
            if stacktrace:
                backtrace_file = os.path.join(FAILURE_FILE, "pynfs_gpfs_ganesha_backtrace.txt")
                with open(backtrace_file, "w", encoding="utf-8") as f:
                    f.write(stacktrace)
                logger.info("Ganesha backtrace written to %s", backtrace_file)
            failure_file = os.path.join(FAILURE_FILE, "pynfs_gpfs_failures.txt")
            with open(failure_file, "w", encoding="utf-8") as f:
                f.write(failure_summary)
            logger.info("PyNFS failure summary written to %s", failure_file)
        else:
            logger.info("PyNFS tests completed successfully")
            failure_msg = f"\n**🟢 PyNFS-GPFS:** `Passed`"
            with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
                f.write(failure_msg)
            with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
                f.write("\nPassed")

        assert fail_found == False and code == 0 and not ganesha_stopped, (
            "PyNFS GPFS tests failed" + (" (ganesha died during test)" if ganesha_stopped else "")
        )
    
    except Exception as e:
        failure_msg = f"\n**🔴 PyNFS-GPFS:** `Failed`"
        with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(failure_msg)
        with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
            f.write("\nFailed")
