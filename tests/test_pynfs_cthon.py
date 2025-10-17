import os
import re
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


# -----------------------
# Actual Tests Starts Here
# -----------------------

# -------------------------
# Test 1: Cthon with CephFS
# Node allocation: 1 (index 1)
# -------------------------
@pytest.mark.parametrize("create_session", [1], indirect=True)
@pytest.mark.timeout(1200) 
def test_cthon_cephfs(create_session):
    try:
        logger.info("[TEST START]: Cthon with CephFS")
        
        remote_session, test_workspace, server_node = create_session

        logger.info("[TEST NODE DETAILS]: Node: %s", server_node)
        logger.info("[TEST WORKSPACE DETAILS]: Workspace: %s", test_workspace)
        logger.info("[TEST SESSION DETAILS]: Session: %s", remote_session)

        _, code = run_cmd(
            remote_session,
            f"cd {test_workspace}/nfs-ganesha && "
            "rm -rf build && "
            "mkdir -p build && "
            "cd build && "
            "cmake ../src -DCMAKE_BUILD_TYPE=Maintainer -DUSE_FSAL_GLUSTER=OFF -DUSE_FSAL_CEPH=ON -DUSE_FSAL_RGW=OFF -DUSE_DBUS=ON -DUSE_ADMIN_TOOLS=ON && "
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
        cthon_logs, rc = cthon.run_all_cthon_test(skip_v3=True)
        logger.info("Type of rc: %s", type(rc))
        if rc != 0:
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
        
        assert rc == 0, f"Cthon CephFS tests failed"
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
def test_pynfs_cephfs(create_session):
    try:
        logger.info("[TEST START]: PyNFS with CephFS")
        (client_session, client_workspace, client_node), (server_session, server_workspace, server_node) = create_session
        failure_msg = ""

        logger.info("[TEST NODE DETAILS]: Client Node: %s, Server Node: %s", client_node, server_node)
        logger.info("[TEST WORKSPACE DETAILS]: Client Workspace: %s, Server Workspace: %s", client_workspace, server_workspace)
        logger.info("[TEST SESSION DETAILS]: Client Session: %s, Server Session: %s", client_session, server_session)

        _, code = run_cmd(
            server_session,
            f"cd {server_workspace}/nfs-ganesha && "
            "rm -rf build && "
            "mkdir -p build && "
            "cd build && "
            "cmake ../src -DCMAKE_BUILD_TYPE=Maintainer -DUSE_FSAL_GLUSTER=OFF -DUSE_FSAL_CEPH=ON -DUSE_FSAL_RGW=OFF -DUSE_DBUS=ON -DUSE_ADMIN_TOOLS=ON && "
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
            cephfs_name=ceph_setup.cephfs_name
        )
        ganesha_setup.setup()

        # -----------------------
        # Client Execution
        # -----------------------
        logger.info("Running PyNFS tests on client node: %s", client_node)
        pynfs = PyNFSManager(session=client_session, server_ip=server_node)
        fail_found, failure_summary, code = pynfs.run_all_tests(export="/nfs/cephfs")
        
        logger.info("Value %s: Type of rc: %s", fail_found, type(fail_found))
        logger.info("Value %s: Type of code: %s", code, type(code))

        if fail_found:
            failure_file = os.path.join(FAILURE_FILE, "pynfs_cephs_failures.txt")
            with open(failure_file, "w", encoding="utf-8") as f:
                f.write(failure_summary)
            logger.info("PyNFS failure summary written to %s", failure_file)
        else:
            logger.info("PyNFS tests completed successfully")
            failure_msg = f"\n**🟢 PyNFS-CephFS:** `Passed`"
            with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
                f.write(failure_msg)
        
        assert fail_found == False and code == 0, "PyNFS CephFS tests failed"

    except Exception as e:
        failure_msg = f"\n**🔴 PyNFS-CephFS:** `Failed`"
        with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(failure_msg)

# -------------------------------------------------------------------
# Test 3: PyNFS-ACL with VFS
# Node allocation: 2 (index 0 - client, index 3 - server)
# -------------------------------------------------------------------
@pytest.mark.parametrize("create_session", [[0, 3]], indirect=True)
def test_pynfs_acl_vfs(create_session):
    try:
        logger.info("[TEST START]: PyNFS-ACL with VFS")
        (client_session, client_workspace, client_node), (server_session, server_workspace, server_node) = create_session
        failure_msg = ""

        logger.info("[TEST NODE DETAILS]: Client Node: %s, Server Node: %s", client_node, server_node)
        logger.info("[TEST WORKSPACE DETAILS]: Client Workspace: %s, Server Workspace: %s", client_workspace, server_workspace)
        logger.info("[TEST SESSION DETAILS]: Client Session: %s, Server Session: %s", client_session, server_session)

        logger.info("NFS Ganesha setup for VFS tests")
        ganesha_setup = VFSGaneshaManager(
            session=server_session
        )
        ganesha_setup.install_ganesha(server_workspace)
        
        logger.info("VFS Exporter setup for NFS tests")
        vfs_setup = VFSVolumeExporter(server_session, vfs_volume="pynfs", enable_acl=True, security_label=False)
        vfs_setup.export_volume()

        
        # -----------------------
        # Client Execution
        # -----------------------
        logger.info("Running PyNFS-ACL tests on client node for VFS: %s", client_node)

        pynfs = PyNFSManager(session=client_session, server_ip=server_node)
        fail_found, failure_summary, code = pynfs.run_all_tests(export="/pynfs")
        
        if fail_found:
            failure_file = os.path.join(FAILURE_FILE, "pynfs_acl_vfs_failures.txt")
            with open(failure_file, "w", encoding="utf-8") as f:
                f.write(failure_summary)
            logger.info("PyNFS-ACL with VFS failure summary written to %s", failure_file)
        else:
            logger.info("PyNFS-ACL with VFS tests completed successfully")
            failure_msg = f"\n**🟢 PyNFS-ACL-VFS:** `Passed`"
            with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
                f.write(failure_msg)
        
        # assert return_code == 0, f"PyNFS-ACL CephFS tests failed"
        assert fail_found == False and code == 0, "PyNFS CephFS tests failed"
    except Exception as e:
        failure_msg = f"\n**🔴 PyNFS-ACL-VFS:** `Failed`"
        with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(failure_msg)

# -----------------------
# Test 4: PyNFS with GPFS
# Node allocation: 2 (index 0 - baremetal client, index 1 - baremetal server)
# -----------------------
@pytest.mark.baremetal
@pytest.mark.parametrize("create_session", [0], indirect=True)
def test_pynfs_gpfs(create_session):
    try:
        logger.info("[TEST START]: PyNFS with GPFS")
        server_session, server_workspace, server_node = create_session
        failure_msg = ""

        logger.info("[TEST NODE DETAILS]: Server Node: %s", server_node)
        logger.info("[TEST WORKSPACE DETAILS]:Server Workspace: %s", server_workspace)
        logger.info("[TEST SESSION DETAILS]: Server Session: %s", server_session)

        vm_name = "centos9-vm"
        username = "root"
        ssh_key = "/root/.ssh/id_rsa.pub"
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
        logger.info("Setting up VM on baremetal node: %s", server_node)
        vm = VMManager(
            session=server_session,
            workspace=server_workspace,
            vm_name=vm_name,
            image_url="https://cloud.centos.org/centos/9-stream/x86_64/images/CentOS-Stream-GenericCloud-9-20241028.0.x86_64.qcow2",
            image_name="CentOS-Stream-GenericCloud-9-20241028.0.x86_64.qcow2",
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
        ganesha_setup = GPFSGaneshaManager(
            session=vm_session
        )
        ganesha_setup.intall_pre_reqs_on_vm()
        ganesha_setup.install_ganesha("/root")
        ganesha_setup.export_nfs_volume()
        ganesha_setup.start_ganesha_service()

        vm_session.close()

        # -----------------------
        # Client Execution
        # -----------------------
        logger.info("Running PyNFS tests on barmetal node: %s", server_node)
        pynfs = PyNFSManager(session=server_session, server_ip=vm_ip)
        fail_found, failure_summary, code = pynfs.run_all_tests(export="/ibm/fs1")
        
        logger.info("Value %s: Type of rc: %s", fail_found, type(fail_found))
        logger.info("Value %s: Type of code: %s", code, type(code))

        if fail_found:
            failure_file = os.path.join(FAILURE_FILE, "pynfs_gpfs_failures.txt")
            with open(failure_file, "w", encoding="utf-8") as f:
                f.write(failure_summary)
            logger.info("PyNFS failure summary written to %s", failure_file)
        else:
            logger.info("PyNFS tests completed successfully")
            failure_msg = f"\n**🟢 PyNFS-GPFS:** `Passed`"
            with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
                f.write(failure_msg)
        
        assert fail_found == False and code == 0, "PyNFS GPFS tests failed"
    
    except Exception as e:
        failure_msg = f"\n**🔴 PyNFS-GPFS:** `Failed`"
        with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(failure_msg)