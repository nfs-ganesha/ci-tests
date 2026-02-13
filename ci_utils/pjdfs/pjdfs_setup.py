# Generated using IBM Bob

import os
from time import sleep
from typing import List, Tuple, Optional

from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger
logger = get_logger(__name__)


class PJDFSManager:
    def __init__(self, session, server_ip, repo_url="https://github.com/pjd/pjdfstest.git", backend_type=None):
        """
        Manage PJDFS test runs on a remote session.

        Args:
            session: RemoteSession instance for running commands.
            server_ip: NFS server IP/hostname.
            repo_url: PJDFS repository URL.
            backend_type: Type of backend storage (e.g., 'ceph', 'acl_vfs', 'gpfs')
        """
        self.session = session
        self.repo_url = repo_url
        self.repo_dir = "/root/pjdfstest"
        self.server_ip = server_ip
        self.failure_log = f"{self.repo_dir }/pjdfs_failed_tests_all.txt"
        self.verbose_log = f"{self.repo_dir }/pjdfs_verbose_failures_all.log"
        self.backend_type = backend_type

    # ----------------------------
    # Install dependencies
    # ----------------------------
    def install_dependencies(self) -> None:
        logger.info("[TEST]: Installing PJDFS dependencies...")
        run_cmd(
            self.session,
            "dnf -y install wget git gcc gcc-c++ time make automake autoconf "
            "pkgconf pkgconf-pkg-config libtool bison flex perl perl-Time-HiRes "
            "perl-TAP-Harness python3 tar libaio-devel net-tools nfs-utils --skip-broken"
        )
        
        # Enable CRB repo and install libtirpc-devel
        run_cmd(self.session, "dnf install -y libtirpc-devel --enablerepo=crb", check=False)
        sleep(2)

    # ----------------------------
    # Clone and build PJDFS
    # ----------------------------
    def clone_and_build(self) -> None:
        logger.info("[TEST]: Cloning and building PJDFS...")
        run_cmd(self.session, f"rm -rf {self.repo_dir}")
        run_cmd(self.session, f"git clone --depth=1 {self.repo_url} {self.repo_dir}")
        run_cmd(self.session, f"cd {self.repo_dir} && autoreconf -ifs")
        run_cmd(self.session, f"cd {self.repo_dir} && ./configure")
        run_cmd(self.session, f"cd {self.repo_dir} && make pjdfstest")
        sleep(5)

    # ----------------------------
    # Mount NFS share
    # ----------------------------
    def mount_nfs(self, version: str, server: str, export: str, mount_point: str) -> bool:
        """
        Mount NFS share with specified version.

        Args:
            version: NFS version (e.g., "3", "4", "4.1", "4.2").
            server: NFS server IP/hostname.
            export: Export path.
            mount_point: Local mount point.

        Returns:
            bool: True if mount successful, False otherwise.
        """
        logger.info(f"[TEST]: Mounting NFS v{version} at {mount_point}...")
        
        # Create mount point
        run_cmd(self.session, f"mkdir -p {mount_point}")
        
        # Attempt mount
        mount_cmd = f"mount -t nfs -o vers={version} {server}:{export} {mount_point}"
        out, code = run_cmd(self.session, mount_cmd, check=False)
        
        if code != 0:
            logger.error(f"Failed to mount NFS v{version}: {out}")
            run_cmd(self.session, "cat /var/log/ganesha.log", check=False)
            return False
        
        # Verify mount
        verify_cmd = f"mountpoint -q {mount_point}"
        out, code = run_cmd(self.session, verify_cmd, check=False)
        
        if code == 0:
            logger.info(f"NFS v{version} successfully mounted at {mount_point}")
            run_cmd(self.session, f"mount | grep {mount_point}", check=False)
            return True
        else:
            logger.error(f"Mount verification failed for {mount_point}")
            return False

    # ----------------------------
    # Run PJDFS test for a specific version
    # ----------------------------
    def run_test(
        self,
        version: str,
        server: str,
        export: str = "/nfs/cephfs",
    ) -> Tuple[str, str, int]:
        """
        Run PJDFS test for a specific NFS version.

        Args:
            version: NFS version ("3", "4", "4.1", "4.2").
            server: NFS server IP/hostname.
            export: Export path (e.g., /nfs/cephfs).

        Returns:
            Tuple of (version, output, return_code).
        """
        logger.info("[TEST]: Running PJDFS tests for NFSv%s...", version)
        
        # Determine mount point based on version
        version_safe = version.replace(".", "")
        mount_point = f"/mnt/nfs_pjdfs_v{version_safe}"
        
        # Mount NFS
        if not self.mount_nfs(version, server, export, mount_point):
            error_msg = f"Failed to mount NFS v{version}"
            logger.error(error_msg)
            return version, error_msg, 1
        
        # Log name
        log_path = f"{self.repo_dir}/log_pjdfs_nfsv{version}.log"

        # Run PJDFS tests
        test_cmd = f"cd {mount_point} && prove -r {self.repo_dir}/tests/ | tee {log_path}"
        
        max_retries = 3
        wait_secs = 10
        
        out = ""
        code = 1
        
        for attempt in range(1, max_retries + 1):
            logger.info(f"PJDFS v{version} attempt {attempt}/{max_retries}...")
            
            out, code = run_cmd(self.session, test_cmd, check=False)
            
            # Check if tests ran successfully
            if "All tests successful" in out or "Result: PASS" in out:
                logger.info(f"PJDFS v{version} tests completed successfully")
                return version, out, code
            elif "Files=" in out and "Tests=" in out:
                # Tests ran but some may have failed
                logger.info(f"PJDFS v{version} tests finished with results")
                self.rerun_failed_tests_with_verbose(mount_point, log_path, version)
                return version, out, code
            else:
                logger.warning(f"PJDFS v{version} tests may not have completed properly")
                if attempt < max_retries:
                    logger.info(f"Retrying after {wait_secs} seconds...")
                    sleep(wait_secs)
                else:
                    logger.error("All retries exhausted")
                    return version, out, code
        
        return version, out, code

    # ----------------------------
    # Collect and summarize failures
    # ----------------------------
    def collect_failures(self, outputs):
        """
        Collect pjdfstest failures from aggregated failure file.
        """

        logger.info("[TEST]: Collecting PJDFS failures...")

        # Read failure file
        failed_content, _ = run_cmd(self.session, f"cat {self.failure_log}", check=False)

        # Read verbose log
        verbose_content, _ = run_cmd(self.session, f"cat {self.verbose_log}", check=False)

        fail_found = False
        return_code = 0
        version_summary = ""

        for version, out, code in outputs:
            if code != 0 or ("Files=" in out and "Tests=" in out):
                fail_found = True
                return_code = code
                version_summary += f"\npjdfs v{version} test: Failed\n"
                logger.error("Return code %s detected in pjdfs %s", code, version)
            else:
                version_summary += f"\npjdfs v{version} test: Passed\n"

        summary_text = (
            f"{version_summary}\n"
            "\nPJDFS FAILURE TESTS\n"
            "-------------------\n"
            f"{failed_content}\n\n"
            "PJDFS VERBOSE FAILURE LOGS\n"
            "--------------------------\n"
            f"{verbose_content}"
        )


        return fail_found, summary_text, return_code
    # ----------------------------
    # Cleanup mounts
    # ----------------------------
    def cleanup_mounts(self) -> None:
        """Unmount all PJDFS test mount points."""
        logger.info("[TEST]: Cleaning up PJDFS mounts...")
        mount_points = [
            "/mnt/nfs_pjdfs_v3",
            "/mnt/nfs_pjdfs_v4",
            "/mnt/nfs_pjdfs_v41",
            "/mnt/nfs_pjdfs_v42"
        ]
        
        for mount_point in mount_points:
            run_cmd(self.session, f"umount {mount_point}", check=False)
            run_cmd(self.session, f"rm -rf {mount_point}", check=False)

    def rerun_failed_tests_with_verbose(self, mount_point: str, log_path: str, version: str):
        """
        Extract failed tests from pjdfstest log and rerun them with verbose output.
        """

        # Extract failures from the CURRENT version log
        extract_cmd = (
            f"grep -B1 'Failed tests:' {log_path} | "
            f"grep '/tests/' | "
            f"awk '{{print $1}}'"
        )

        failed_tests, _ = run_cmd(self.session, extract_cmd, check=False)
        logger.debug(f"Failed tests: {failed_tests}")

        failed_list = [t.strip() for t in failed_tests.splitlines() if t.strip()]
        logger.debug(f"Failed list: {failed_list}")

        if not failed_list:
            logger.info(f"NFSv{version}: No individual failing tests detected")
            return

        # Append failures to aggregated file
        append_cmd = (
            f"echo '\n===== NFSv{version} =====' >> {self.failure_log} && "
            f"echo '{failed_tests}' >> {self.failure_log}"
        )
        run_cmd(self.session, append_cmd, check=False)

        logger.warning(f"NFSv{version}: Re-running {len(failed_list)} failed tests in verbose mode")

        tests = " ".join(failed_list)

        verbose_cmd = (
            f"echo '\n===== VERBOSE NFSv{version} =====' >> {self.verbose_log} && "
            f"cd {mount_point} && "
            f"prove -v {tests} >> {self.verbose_log} 2>&1"
        )

        run_cmd(self.session, verbose_cmd, check=False)

    # ----------------------------
    # Run all PJDFS tests
    # ----------------------------
    def run_all_tests(self, export, export_v3=""):
        """
        Run all PJDFS test suites for specified NFS versions.

        Args:
            export: NFS export path.
            versions: List of NFS versions to test (default: ["3", "4", "4.1", "4.2"]).

        Returns:
            Tuple of (fail_found, summary_text, return_code).
        """
        logger.info("[TEST]: Running all PJDFS test suites")
        
        self.install_dependencies()
        self.clone_and_build()

        results = [
            self.run_test("3", self.server_ip, export_v3),
            self.run_test("4.0", self.server_ip, export),          
            self.run_test("4.2", self.server_ip, export)
        ]
        # Cleanup
        self.cleanup_mounts()

        return self.collect_failures(results)

