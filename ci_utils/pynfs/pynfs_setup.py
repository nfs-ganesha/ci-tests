from time import sleep
from typing import List, Tuple

from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger
logger = get_logger(__name__)


class PyNFSManager:
    def __init__(self, session, server_ip, repo_url="git://git.linux-nfs.org/projects/cdmackay/pynfs.git", backend_type=None):
        """
        Manage PyNFS test runs on a remote session.

        Args:
            session: RemoteSession instance for running commands.
            server_ip: NFS server IP/hostname.
            backend_type: Type of backend storage (e.g., 'ceph', 'acl_vfs', 'gpfs')
        """
        self.session = session
        self.repo_url = repo_url
        self.repo_dir = "pynfs"
        self.server_ip = server_ip
        self.failure_log = "/root/pynfs_failures.txt"
        self.backend_type = backend_type

    # ----------------------------
    # Clone and build pynfs
    # ----------------------------
    def clone_and_build(self) -> None:
        logger.info("[TEST]: Cloning and building pynfs...")
        run_cmd(self.session, f"rm -rf {self.repo_dir}")
        run_cmd(self.session, f"git clone --depth=1 {self.repo_url} {self.repo_dir}")
        run_cmd(self.session, f"cd {self.repo_dir} && python3 setup.py build")
        sleep(5)
    # ----------------------------
    # Run pynfs test for a specific version
    # ----------------------------
    def run_test(
        self,
        version: str,
        server: str,
        export: str = "/nfs/cephfs",
    ):
        """
        Run pynfs test for a specific version.

        Args:
            version: "4.0" or "4.1".
            server: NFS server IP/hostname.
            export: Export path (e.g., /nfs/cephfs).
            test_parameters: Extra args for testserver.py.

        Returns:
            Path to the log file.
        """
        logger.info("[TEST]: Running pynfs tests for NFSv%s...", version)
        known_failures = []

        if version == "4.0":
            cmd = (
                f"cd {self.repo_dir}/nfs4.0 && "
                f"./testserver.py {server}:{export} "
                f"--secure --verbose --maketree --showomit --rundeps all ganesha"
            )

            if self.backend_type == "ceph":
                # BZ-2415387
                known_failures = [
                    "WRT17",
                    "MKLINK",
                    "WRT16",
                    "PUTFH3",
                    "LOCK20",
                    "RNM20"
                ]
            elif self.backend_type == "acl_vfs":
                # BZ-2415390
                known_failures = [
                    "WRT17",
                    "WRT16",
                    "WRT18",
                    "LOOKCHAR",
                    "LOOKBLK",
                    "SATT18",
                    "LOCK20",
                ]
            elif self.backend_type == "gpfs":
                # BZ-2416755
                known_failures = [
                    "WRT17",
                    "WRT16",
                    "SATT12x",
                    "LOCK20",
                ]

        elif version == "4.1":
            cmd = (
                f"cd {self.repo_dir}/nfs4.1 && "
                f"./testserver.py {server}:{export} all ganesha "
                f"--secure --verbose --maketree --showomit --rundeps"
            )

            if self.backend_type == "ceph":
                # BZ-2415388
                known_failures = [
                    "ALLOC1",
                    "ALLOC2",
                    "ALLOC3",
                    "RNM20",
                    "DELEG2",
                    "DELEG23",
                    "DELEG8",
                    "DELEG25",
                    "DELEG24",
                    "DELEG7",
                    "SEQ6",
                    "CSESS21",
                    "CSESS20",
                ]
            elif self.backend_type == "acl_vfs":
                ## Adding no-deleg option to skip delegation tests for VFS backends BZ-2415392
                cmd = (
                    f"cd {self.repo_dir}/nfs4.1 && "
                    f"./testserver.py {server}:{export} all ganesha nodeleg"
                    f" --secure --verbose --maketree --showomit --rundeps"
                )
                known_failures = [
                    "PUTFH1c",
                    "PUTFH1b",
                    "RNM1c",
                    "RNM1b",
                    "RNM2c",
                    "RNM2b",
                    "RNM3c",
                    "RNM3b",
                    "LKPP1c",
                    "LKPP1b",
                    "SEQ6",
                    "CSESS21",
                    "CSESS20",
                ]
            elif self.backend_type == "gpfs":
                # BZ-2416757
                known_failures = [
                    "XATT5",
                    "XATT7",
                    "XATT8",
                    "XATT9",
                    "XATT10",
                    "XATT11",
                    "XATT2",
                    "XATT6",
                    "XATT4",
                    "XATT3",
                    "DELEG2",
                    "DELEG23",
                    "DELEG1",
                    "DELEG8",
                    "DELEG25",
                    "DELEG24",
                    "DELEG6",
                    "DELEG7",
                    "DELEG5",
                    "DELEG3",
                    "SEQ6",
                    "CSESS21",
                    "CSESS20",
                    "EID9"
                ]
        else:
            raise ValueError(f"Unsupported NFS version: {version}")

        max_retries = 10
        wait_secs = 15
        out = ""
        code = 1
        for attempt in range(1, max_retries + 1):
            logger.info(f"PyNFS attempt {attempt}/{max_retries}...")

            out, code = run_cmd(self.session, cmd, check=False)

            # Detect initialization failure
            if "Initialization failed" not in out:
                logger.info("pynfs %s test finished. Log:\n %s", version, out)

                # --- Filter known failures ---
                if known_failures:
                    filtered_lines = []
                    ignored_failures = []
                    ignored_count = 0
                    for line in out.splitlines():
                        parts = line.split()
                        if len(parts) > 0 and parts[0] in known_failures and ": FAILURE" in line:
                            ignored_count += 1
                            ignored_failures.append(line)
                            logger.debug("Ignoring known failure: %s", line.strip())
                            continue
                        filtered_lines.append(line)
                    if ignored_count:
                        logger.info(
                            "Filtered %d known failures from pynfs output.", ignored_count
                        )
                        failure_out = "\n".join(ignored_failures)
                        logger.info("Ignored failures for version %s:\n%s", version, failure_out)
                    out = "\n".join(filtered_lines)
                # --- End filtering ---

                return version, out, code

            logger.warning("PyNFS initialization failed — possibly NFS not ready yet.")
            run_cmd(self.session, f"showmount -e {server}", check=False)
            if attempt < max_retries:
                logger.info(f"Retrying after {wait_secs} seconds...")
                sleep(wait_secs)
            else:
                logger.error("All retries exhausted, giving up.")

        return version, out, code

    # ----------------------------
    # Collect and summarize failures
    # ----------------------------
    def collect_failures(self, outputs):
        logger.info("[TEST]: Collecting pynfs failures...")
        fail_found = False
        failure_summary = []
        summary_text = ""
        return_code = 0

        for version, out, code in outputs:
            failures = [line for line in out.splitlines() if ": FAILURE" in line]
            if failures:
                fail_found = True
                logger.warning("Failures detected in pynfs %s", version)
                failure_summary.append(f"pynfs {version} test suite failures:")
                failure_summary.append("------------------------------")
                failure_summary.extend(failures)
                failure_summary.append("")  # blank line
            if code != 0:
                return_code = code
                fail_found = True
                logger.error("Return code %s detected in pynfs %s", code, version)

        if failure_summary:
            summary_text = "\n".join(failure_summary)
            logger.error("Failure summary:\n%s", summary_text)

        return fail_found, summary_text, return_code
    
    # ----------------------------
    # Run all pynfs tests
    # ----------------------------
    def run_all_tests(self, export):
        logger.info("[TEST]: Running all pynfs test suites")
        self.clone_and_build()

        results = [
            self.run_test("4.0", self.server_ip, export),
            self.run_test("4.1", self.server_ip, export)
        ]

        return self.collect_failures(results)
