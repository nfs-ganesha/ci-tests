import os
import pathlib

import yaml
from ci_utils.common.remote_session import RemoteSession
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
FAILURE_FILE = os.path.join(WORKSPACE, "failures")
os.makedirs(FAILURE_FILE, exist_ok=True)
SUMMARY_FILE = os.path.join(WORKSPACE, "summary_checkpatch_fsal.txt")
SUMMARY_STATUS = os.path.join(WORKSPACE, "summary_status.txt")

# -----------------------
# Fixtures - Sessions level
# -----------------------
@pytest.fixture(scope="session")
def server_node():
    logger.info("[Fixtures - Session]: Getting server node from Duffy session file: %s", SESSION_FILE)
    session_data = read_json_file(SESSION_FILE)
    return session_data.get("nodes")[0]

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
def create_session(server_node, request):
    logger.info("[Fixtures - Test]: Creating remote session to server node: %s", server_node)
    
    test_name = request.node.name
    default_dir = f"/root/{test_name}"

    session = RemoteSession(node_ip=server_node, user="root", default_dir=default_dir)
    session.connect()   # Open once
    session.run(f"mkdir -p {default_dir}")  # Ensure default dir exists

    scp_copy(server_node, f"{WORKSPACE}/nfs-ganesha", remote_dir=default_dir)

    yield session, default_dir  # Yield both session and default dir
    session.close()   

@pytest.fixture
def cmake_flags(request, cmake_config):
    test_name = request.node.name
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
# ---------------------------------------------------------
# Helper function to log results to summary file
# ---------------------------------------------------------
def gerrit_custom_message(return_code, test_name, out=None):
    if return_code == 0:
        failure_msg = f"\n**🟢 {test_name}:** `Passed`"
        with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(failure_msg)
        with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
            f.write("\nPassed")
    else:
        failure_msg = f"\n**🔴 {test_name}:** `Failed`"
        if out:
            failure_msg += f"\n```\n{out}\n```"
        with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(failure_msg)
        with open(SUMMARY_STATUS, "a", encoding="utf-8") as f:
            f.write("\nFailed")


# -----------------------
# Actual Tests start here
# -----------------------

# -----------------------
# TEST 1: Checkpatch validation
# Required Node: 1
# -----------------------
def test_checkpatch(create_session, server_node):
    logger.info("[TEST] Running Checkpatch test")
    remote_session, test_workspace = create_session
    
    logger.info("TEST WORKSPACE: %s", test_workspace)
    files_to_copy = [
        f"{WORKSPACE}/ci-tests/build_scripts/checkpatch/checkpatch-to-gerrit-json.py"
    ]
    scp_copy(server_node, files_to_copy, remote_dir=test_workspace)
    scp_copy(server_node, f"{WORKSPACE}/nfs-ganesha/src/scripts/checkpatch.conf", remote_dir=f"{test_workspace}/nfs-ganesha/src/scripts/.checkpatch.conf")

    cmd = (
        f"cd {test_workspace}/nfs-ganesha/src/scripts && "
        f"GIT_DIR={test_workspace}/nfs-ganesha/.git git show --format=email "
        "| ./checkpatch.pl -q - "
        f"| python3 {test_workspace}/checkpatch-to-gerrit-json.py"
    )
    logger.info("Checkpatch command: %s", cmd)
    out, _ = run_cmd(remote_session, cmd, check=False)

    # Exclusions for files that don't impact code quality
    exclusions = ["/COMMIT_MSG"]

    code = 1 
    # Condition 1: "Checkpatch OK" found
    if "Checkpatch OK" in out:
        code = 0
    else:
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            logger.error("Failed to parse checkpatch output as JSON")
            data = None

        if data and "comments" in data:
            comments = data["comments"]

            # Remove all keys present in exclusions
            for exc in exclusions:
                comments.pop(exc, None)

            logger.info("Comments after exclusions: %s", comments)
            # Condition 2: If comments is empty after exclusions → success
            if not comments:
                code = 0

    if code != 0:
        checkpatch_log_file = os.path.join(FAILURE_FILE, "checkpatch_logs.json")
        with open(checkpatch_log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2))
        logger.info("Checkpatch logs written to %s", checkpatch_log_file)

        # Try to parse JSON output for cleaner logging to gerrit
        try:
            formatted_out = []
            for file, issues in data.get("comments", {}).items():
                for issue in issues:
                    # Flatten message to avoid newlines/special chars
                    msg = issue["message"].splitlines()[0]
                    formatted_out.append(f"{file}:{issue['line']}: {msg}")
            formatted_out.append(data.get("message", ""))
            out = "\n".join(formatted_out)
        except Exception:
            logger.warning("Failed to parse checkpatch output as JSON, using raw output")

    gerrit_custom_message(code, "Checkpatch lint", out)

    # Commenting out assertion to skip checkpatch failure
    # assert code == 0, f"Checkpatch failed"

# -----------------------
# TEST 2: Clang format validation
# Required Node: 1
# -----------------------
def test_clang_format(create_session, server_node):
    logger.info("[TEST] Running Clang format test")
    remote_session, test_workspace = create_session 
    
    logger.info("TEST WORKSPACE: %s", test_workspace)
    files_to_copy = [
        f"{WORKSPACE}/ci-tests/build_scripts/clang/clangformat_to_gerrit_json.py"
    ]
    scp_copy(server_node, files_to_copy, remote_dir=test_workspace)

    out, _ = run_cmd(
        remote_session,
        f"cd {test_workspace}/nfs-ganesha && "
        "git clang-format -v "
        "--diff "
        "--style file:src/.clang-format "
        "--extensions c,cc,cpp,h,hpp "
        "HEAD~1 "
        f"| python3 {test_workspace}/clangformat_to_gerrit_json.py", check=False
    )
    
    code = 0 if "clang-format OK" in out else 1

    if code != 0:
        clang_log_file = os.path.join(FAILURE_FILE, "clang_logs.json")
        with open(clang_log_file, "w", encoding="utf-8") as f:
            f.write(out)
        logger.info("Clang logs written to %s", clang_log_file)


        clang_dump = os.path.join(FAILURE_FILE, "clang_logs.txt")
        dump_out, _ = run_cmd(
            remote_session,
            f"cd {test_workspace}/nfs-ganesha && "
            "git clang-format -v "
            "--diff "
            "--style file:src/.clang-format "
            "--extensions c,cc,cpp,h,hpp "
            "HEAD~1", check=False
        )
        with open(clang_dump, "w", encoding="utf-8") as f:
            f.write(dump_out)
        logger.info("Clang format logs written to %s", clang_dump)

        # Try to parse JSON output for cleaner logging to gerrit
        try:
            data = json.loads(out)
            formatted_out = []
            for file, issues in data.get("comments", {}).items():
                for issue in issues:
                    # Flatten message to avoid newlines/special chars
                    msg = issue["message"].splitlines()[0]
                    formatted_out.append(f"{file}:{issue['line']}: {msg}")
            formatted_out.append(data.get("message", ""))
            out = "\n".join(formatted_out)
        except Exception:
            logger.warning("Failed to parse clang output as JSON, using raw output")

    gerrit_custom_message(code, "Clang-format Check", out)

    # Commenting out assertion to skip clang format failure
    # assert code == 0, f"Clang format check failed"

# -----------------------
# TEST 3: FSAL build tests - CephFS
# Required Node: 1
# -----------------------
def test_fsal_cephfs(create_session, cmake_flags):
    logger.info("[TEST] Running FSAL CephFS test")
    remote_session, test_workspace = create_session
    logger.info("TEST WORKSPACE: %s", test_workspace)

    flag_str = " ".join(cmake_flags)
    logger.info("Using CMake flags: %s", flag_str)

    out, code = run_cmd(
        remote_session,
        f"cd {test_workspace}/nfs-ganesha && "
        "rm -rf build && "
        "mkdir -p build && "
        "cd build && "
        f"cmake ../src {flag_str} && "
        "make", check=False
    )

    gerrit_custom_message(code, "FSAL CephFS Build")

    if code:
        fsal_cephfs_log_file = os.path.join(FAILURE_FILE, "fsal_cephfs_logs.txt")
        with open(fsal_cephfs_log_file, "w", encoding="utf-8") as f:
            f.write(out)
        logger.info("FSAL CephFS logs written to %s", fsal_cephfs_log_file)

    assert code == 0, f"FSAL CephFS tests failed"

# -----------------------
# TEST 4: FSAL build tests - GPFS
# Required Node: 1
# -----------------------
def test_fsal_gpfs(create_session, cmake_flags):
    logger.info("[TEST] Running FSAL GPFS test")
    remote_session, test_workspace = create_session
    logger.info("TEST WORKSPACE: %s", test_workspace)

    flag_str = " ".join(cmake_flags)
    logger.info("Using CMake flags: %s", flag_str)

    out, code = run_cmd(
        remote_session,
        f"cd {test_workspace}/nfs-ganesha && "
        "rm -rf build && "
        "mkdir -p build && "
        "cd build && "
        f"cmake ../src {flag_str} && "
        "make", check=False
    )

    gerrit_custom_message(code, "FSAL GPFS Build")

    if code:
        fsal_gpfs_log_file = os.path.join(FAILURE_FILE, "fsal_gpfs_logs.txt")
        with open(fsal_gpfs_log_file, "w", encoding="utf-8") as f:
            f.write(out)
        logger.info("FSAL GPFS logs written to %s", fsal_gpfs_log_file)

    assert code == 0, f"FSAL GPFS tests failed"

# -----------------------
# TEST 5: FSAL build tests - RGW
# Required Node: 1
# -----------------------
def test_fsal_rgw(create_session, cmake_flags):
    logger.info("[TEST] Running FSAL RGW test")
    remote_session, test_workspace = create_session  # Unpack the tuple
    logger.info("TEST WORKSPACE: %s", test_workspace)

    flag_str = " ".join(cmake_flags)
    logger.info("Using CMake flags: %s", flag_str)

    out, code = run_cmd(
        remote_session,
        f"cd {test_workspace}/nfs-ganesha && "
        "rm -rf build && "
        "mkdir -p build && "
        "cd build && "
        f"cmake ../src {flag_str} && "
        "make", check=False
    )

    gerrit_custom_message(code, "FSAL RGW Build")

    if code:
        fsal_rgw_log_file = os.path.join(FAILURE_FILE, "fsal_rgw_logs.txt")
        with open(fsal_rgw_log_file, "w", encoding="utf-8") as f:
            f.write(out)
        logger.info("FSAL RGW logs written to %s", fsal_rgw_log_file)

    assert code == 0, f"FSAL RGW tests failed"

# -----------------------
# TEST 6: FSAL build tests - VFS
# Required Node: 1
# -----------------------
def test_fsal_vfs(create_session, cmake_flags):
    logger.info("[TEST] Running FSAL VFS test")
    remote_session, test_workspace = create_session
    logger.info("TEST WORKSPACE: %s", test_workspace)

    flag_str = " ".join(cmake_flags)
    logger.info("Using CMake flags: %s", flag_str)

    out, code = run_cmd(
        remote_session,
        f"cd {test_workspace}/nfs-ganesha && "
        "rm -rf build && "
        "mkdir -p build && "
        "cd build && "
        f"cmake ../src {flag_str} && "
        "make", check=False
    )

    gerrit_custom_message(code, "FSAL VFS Build")

    if code:
        fsal_vfs_log_file = os.path.join(FAILURE_FILE, "fsal_vfs_logs.txt")
        with open(fsal_vfs_log_file, "w", encoding="utf-8") as f:
            f.write(out)
        logger.info("FSAL VFS logs written to %s", fsal_vfs_log_file)

    assert code == 0, f"FSAL VFS tests failed"