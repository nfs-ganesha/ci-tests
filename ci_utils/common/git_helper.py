# utils/git_helper.py
import os
from pathlib import Path
from git import Repo, GitCommandError
from ci_utils.common.logger import get_logger

logger = get_logger(__name__)

class GitWorkspace:
    def __init__(self, workspace: str, gerrit_host: str, gerrit_project: str, gerrit_refspec: str):
        """
        Initialize GitWorkspace.

        :param workspace: Base folder where the repo will be cloned/fetched.
        :param gerrit_host: Gerrit host (e.g., review.gerrithub.io)
        :param gerrit_project: Project path in Gerrit (e.g., ffilz/nfs-ganesha)
        :param gerrit_refspec: Patch/branch refspec to fetch
        """
        self.workspace = Path(workspace)
        self.gerrit_host = gerrit_host
        self.gerrit_project = gerrit_project
        self.gerrit_refspec = gerrit_refspec
        self.repo_path = self.workspace / Path(gerrit_project).name
        self.repo = None
        self.clone_depth = os.getenv("GIT_CLONE_DEPTH", "1")

    # -----------------------
    # Prepare repo
    # -----------------------
    def prepare_repo(self):
        logger.info("[STEP]: Preparing Git repo in workspace: %s", self.workspace)
        if not self.repo_path.exists():
            logger.info("Initializing repo at: %s", self.repo_path)
            self.repo_path.mkdir(parents=True, exist_ok=True)
            self.repo = Repo.init(self.repo_path)
        else:
            logger.info("Using existing repo at: %s", self.repo_path)
            self.repo = Repo(self.repo_path)

        git_url = f"https://{self.gerrit_host}/{self.gerrit_project}"
        try:
            # logger.info("Fetching refspec %s from %s", self.gerrit_refspec, git_url)
            # self.repo.git.fetch(git_url, self.gerrit_refspec, depth=self.clone_depth)
            # self.repo.git.checkout("-b", self.gerrit_refspec, "FETCH_HEAD")
            
            # Check if branch already exists
            branches = [b.name for b in self.repo.branches]
            if self.gerrit_refspec in branches:
                logger.info("Branch %s already exists, checking it out", self.gerrit_refspec)
                self.repo.git.checkout(self.gerrit_refspec)
            else:
                logger.info("Creating new branch %s from FETCH_HEAD", self.gerrit_refspec)
                self.repo.git.fetch(git_url, self.gerrit_refspec, depth=self.clone_depth)
                self.repo.git.checkout("-b", self.gerrit_refspec, "FETCH_HEAD")
            logger.info("Checked out branch %s", self.gerrit_refspec)
            
            # Handle submodules only for nfs-ganesha
            if self.gerrit_project.endswith("nfs-ganesha"):
                try:
                    logger.info("Updating submodules recursively")
                    self.repo.git.submodule("update", "--recursive", "--init")
                except GitCommandError:
                    logger.warning("Submodule update failed, trying sync...")
                    self.repo.git.submodule("sync", "--recursive")
        except GitCommandError as e:
            logger.error("Git command failed: %s", e)
            raise

    # -----------------------
    # Check if repo exists
    # -----------------------
    def repo_exists(self) -> bool:
        logger.info("[STEP]: Checking if repo exists at: %s", self.repo_path)
        return self.repo_path.exists() and (self.repo_path / ".git").exists()
