import os
import subprocess
import time
import json
from pathlib import Path
from ci_utils.common.logger import get_logger
logger = get_logger(__name__)

class DuffySession:
    def __init__(self, workspace=None, centos_version=None, centos_arch=None, metal_only=False, node_count=None):
        """
        Initialize Duffy client and configuration.
        Args:
            workspace (str): Base folder for saving session info. Defaults to /tmp.
            centos_version (str): CentOS version filter for pools. Defaults to "9".
            centos_arch (str): CentOS architecture filter for pools. Defaults to "x86_64".
            metal_only (bool): If True, only consider metal pools. Defaults to False.
        """
        self.workspace = Path(workspace or os.getenv("WORKSPACE", "/tmp"))
        self.centos_version = centos_version or os.getenv("CENTOS_VERSION", "9")
        self.centos_arch = centos_arch or os.getenv("CENTOS_ARCH", "x86_64")
        self.metal_only = metal_only
        self.node_count = node_count or int(os.getenv("NODE_COUNT", "1"))  # default = 1
        self.session_id = None
        self.nodes = []

        self.client_bin = "duffy client"
        self._write_config()

    # -----------------------
    # Duffy Writing Config
    # -----------------------
    def _write_config(self):
        logger.info("[STEP]: Writing Duffy client config")
        cfg_dir = Path.home() / ".config"
        cfg_dir.mkdir(parents=True, exist_ok=True)

        config_file = cfg_dir / "duffy"
        api_key = os.getenv("CICO_API_KEY", "")
        content = f"""client:
  url: https://duffy.ci.centos.org/api/v1
  auth:
    name: nfs-ganesha
    key: {api_key}
"""
        config_file.write_text(content)

    # -----------------------
    # List all pools
    # -----------------------
    def _list_all_pools(self):
        logger.info("[STEP]: Listing available Duffy pools")
        result = subprocess.check_output(f"{self.client_bin} list-pools", shell=True, universal_newlines=True)
        pools = json.loads(result)["pools"]
        return [p["name"] for p in pools if f"{self.centos_version}" in p["name"] and "x86_64" in p["name"]]

    # -----------------------
    # List matching pools
    # -----------------------
    def _list_pools(self):
        """Return Duffy pools filtered by CENTOS_VERSION and CENTOS_ARCH."""
        logger.info("[STEP]: Listing matching Duffy pools")
        all_pools = self._list_all_pools()
        filtered = [
            p for p in all_pools
            if f"{self.centos_version}-{self.centos_arch}" in p
            and (not self.metal_only or "metal" in p)
        ]
        logger.info(
            "Filtered pools for CENTOS_VERSION=%s, CENTOS_ARCH=%s: %s",
            self.centos_version, self.centos_arch, filtered
        )
        return filtered

    # -----------------------
    # Validate pool readiness
    # -----------------------
    def _pool_ready_count(self, pool):
        logger.info(f"[STEP]: Checking ready nodes in pool: {pool}")
        result = subprocess.check_output(f"{self.client_bin} show-pool {pool}", shell=True, universal_newlines=True)
        return json.loads(result)["pool"]["levels"]["ready"]

    # -----------------------
    # Request session
    # -----------------------
    def _request_session(self, pool):
        logger.info(f"[STEP]: Requesting session from pool: {pool} with {self.node_count} nodes")
        result = subprocess.check_output(
            f'{self.client_bin} request-session pool="{pool}",quantity={self.node_count}',
            shell=True,
            universal_newlines=True,
        )
        return json.loads(result)

    # -----------------------
    # Create session
    # -----------------------
    def create(self):
        logger.info("[STEP]: Starting Duffy session reservation...")
        retry = True

        while retry:
            for pool in self._list_pools():
                logger.info(f"Checking pool: {pool}")
                ready = self._pool_ready_count(pool)
                logger.info(f"Ready nodes in pool '{pool}': {ready}")
                if ready >= self.node_count:
                    logger.info(f"Enough ready nodes in pool '{pool}'")
                    session = self._request_session(pool)
                    if "error" in session and session["error"]["detail"] != "null":
                        logger.info("Failed to reserve node: %s", session["error"]["detail"])
                        time.sleep(60)
                        continue
                    
                    logger.info("Session response: %s", session)
                    self.session_id = session["session"]["id"]
                    self.nodes = [n["ipaddr"] for n in session["session"]["nodes"]]

                    logger.info(f"Saving session info to workspace: {self.workspace}")
                    # Save hosts + session_id in workspace
                    hosts_file = self.workspace / "hosts"
                    session_file = self.workspace / "session_id"
                    hosts_file.write_text("\n".join(self.nodes))
                    session_file.write_text(str(self.session_id))


                    logger.info(f"Session ID: {self.session_id}")
                    logger.info("Node(s) reserved successfully!")
                    retry = False
                    break
            if retry:
                logger.info("Retrying in 60s...")
                time.sleep(60)

        return self.nodes

    # -----------------------
    # Delete session
    # -----------------------
    def delete(self):
        logger.info("[STEP]: Releasing Duffy session...")
        if self.session_id:
            subprocess.run(f"{self.client_bin} retire-session {self.session_id}", shell=True)
            logger.info(f"Session {self.session_id} released.")
