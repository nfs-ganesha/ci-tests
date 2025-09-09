import os
import json
import subprocess
from typing import Dict, Any

from ci_utils.common.logger import get_logger

logger = get_logger(__name__)

# -----------------------
# Common Helpers
# -----------------------


# ---------------------------------------
# SCP Copy from Workspace to Remote Node
# ---------------------------------------
def scp_copy(node_ip, files, remote_dir="/root", user="root", key_file=None):
    """Copy files or directories to a remote node using SCP.
    Args:
        node_ip (str): Remote node IP address.
        files (str or List[str]): File or list of files/directories to copy.
        remote_dir (str): Destination directory on the remote node.
        user (str): SSH user for the remote node.
        key_file (str): Path to SSH private key file.
    Raises:
        FileNotFoundError: If any of the specified files/directories do not exist.
    """
    logger.info(f"[STEP]: Copying files to remote node {node_ip}")
    ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if key_file:
        ssh_opts.extend(["-i", key_file])

    if not isinstance(files, list):
        files = [files]

    for path in files:
        if not os.path.exists(path):
            raise FileNotFoundError(f"File or directory does not exist: {path}")

        # Add -r only for directories
        scp_cmd = ["scp"] + ssh_opts
        if os.path.isdir(path):
            scp_cmd.append("-r")

        scp_cmd += [path, f"{user}@{node_ip}:{remote_dir}"]

        logger.info(f"Copying {path} -> {user}@{node_ip}:{remote_dir}")
        logger.info(f"Running command: {' '.join(scp_cmd)}")
        subprocess.check_call(scp_cmd)
        list_all_contents(remote_dir, node_ip)

# -----------------------
# List all contents of a directory (local or remote)
# -----------------------    
def list_all_contents(path=".", node_ip=None, user="root", key_file=None):
    """
    Run `ls -la` locally or on a remote node.

    Args:
        path (str): Directory to list (default ".").
        node_ip (str, optional): Remote node IP. If None, runs locally.
        user (str): SSH user for remote node.
        key_file (str): Path to SSH private key.

    Returns:
        str: Raw `ls -la` output.
    """
    logger.info(f"[STEP]: Listing contents of {path} on {'remote node ' + node_ip if node_ip else 'local machine'}")
    if node_ip:
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no"]
        if key_file:
            ssh_cmd.extend(["-i", key_file])
        ssh_cmd.append(f"{user}@{node_ip}")
        ssh_cmd.append(f"ls -la {path}")
        logger.info(f"[INFO] Running command: {' '.join(ssh_cmd)}")
        output = subprocess.check_output(ssh_cmd, universal_newlines=True)
    else:
        output = subprocess.check_output(["ls", "-la", path], universal_newlines=True)

    return output

# -----------------------
# Read JSON file
# -----------------------
def read_json_file(json_path: str) -> Dict[str, Any]:
    """
    Read a JSON file and return its contents as a dictionary.

    Args:
        json_path (str): Path to the JSON file.

    Returns:
        Dict[str, Any]: Parsed JSON content.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file content is not valid JSON.
    """
    logger.info("[STEP]: Reading JSON file: %s", json_path)

    try:
        with open(json_path, "r") as f:
            data = json.load(f)
        logger.info("Successfully read JSON file: %s", json_path)
        return data
    except FileNotFoundError:
        logger.error("JSON file not found: %s", json_path)
        raise
    except json.JSONDecodeError as e:
        logger.error("Failed to parse JSON file %s: %s", json_path, e)
        raise

# -----------------------
# Run remote commands
# -----------------------
def run_cmd(session, cmd, check=True, timeout=3600, source_bashrc=False):
    """Run remote command on session and return stdout.
    Args:
        session (RemoteSession): Active RemoteSession instance.
        cmd (str): Command to run.
        check (bool): If True, raise RuntimeError on non-zero exit code.
        timeout (int): Command timeout in seconds.
    Returns:
        str: Command stdout output.
    Raises:
        RuntimeError: If command fails and check is True.
    """
    cmd_to_run = f'source ~/.bashrc && {cmd}' if source_bashrc else cmd
    logger.info(f"[STEP]: Running remote command: {cmd_to_run}")
    out, err, code = session.run(cmd_to_run, timeout)
    if code != 0 and check:
        logger.error(f"Command failed: {cmd_to_run}\n{err}")
        raise RuntimeError(err)
    logger.info(f"[REMOTE] Command output for {cmd_to_run} with return code {code}:\n {out.strip()}")
    return out.strip(), code