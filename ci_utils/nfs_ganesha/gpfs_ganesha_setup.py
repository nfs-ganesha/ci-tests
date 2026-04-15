import os
import re
import time

from ci_utils.common.helpers import run_cmd
from ci_utils.common.logger import get_logger
logger = get_logger(__name__)


class GPFSGaneshaManager:
    def __init__(self, session, export="/ibm/fs1", system_type="centos", cmake_flags=None):
        """Handles GPFS and NFS-Ganesha installation and setup on a VM.
        Args:
            session (RemoteSession): Remote session to the VM.
        """
        self.session = session
        self.export = export
        self.system_type = system_type
        self.cmake_flags = cmake_flags

    # -------------------------------
    # Helpers
    # -------------------------------
    def wait_for_ces_healthy(self, timeout=600, interval=10):
        logger.info("Waiting for CES to be healthy...")
        end = time.time() + timeout
        while time.time() < end:
            out, rc = run_cmd(self.session, "/usr/lpp/mmfs/bin/mmhealth node show CES", check=False)
            if rc == 0:
                statuses = dict(re.findall(r"^\s*([A-Z_]+)\s+([A-Z]+)\s+", out, re.M))
                logger.info(f"CES statuses: {statuses}")
                if statuses.get("CES") == "HEALTHY":
                    logger.info("CES is healthy")
                    return True
                else:
                    logger.info(f"Retrying after {interval} seconds")
            time.sleep(interval)
        raise TimeoutError("CES did not become healthy within the timeout period")
    
    # -------------------------------
    # Install pre-requisites on VM
    # -------------------------------
    def intall_pre_reqs_on_vm(self):
        logger.info("[STEP]: Installing pre-requisite packages for GPFS and Ganesha on the VM")
        run_cmd(self.session, "dnf install -y rpcbind yum-utils centos-release-ceph epel-release unzip --skip-broken")
        run_cmd(self.session, "systemctl start rpcbind")
        run_cmd(self.session, " sudo setenforce 0")
        run_cmd(self.session, "sudo systemctl stop firewalld", check=False)

    # -------------------------------
    # Install Ganesha with GPFS support
    # -------------------------------
    def install_ganesha(self, test_workspace: str):
        logger.info("[STEP]: Installing NFS-Ganesha with GPFS support on the VM")
        yum_repo = os.getenv("GPFS_YUM_REPO", "")
        if yum_repo:
            self._install_from_repo(yum_repo)
        else:
            self._build_from_source(test_workspace)

        self.coredump_setup()
        self.start_ganesha_service()

    # -------------------------------
    # Install Ganesha from repo or build from source
    # -------------------------------
    def _install_from_repo(self, yum_repo: str):
        logger.info("[STEP]: Installing Ganesha from yum repo...")
        run_cmd(self.session, "yum-config-manager --add-repo=http://artifacts.ci.centos.org/nfs-ganesha/nightly/libntirpc/libntirpc-latest.repo")
        run_cmd(self.session, f"yum-config-manager --add-repo={yum_repo}")
        run_cmd(self.session, "dnf -y install gpfs.nfs-ganesha nfs-ganesha-gluster glusterfs-ganesha")

    def _build_from_source(self, test_workspace: str):
        logger.info("[STEP]: Building Ganesha from source...")

        BASE_PACKAGES="git bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel rpm-build redhat-rpm-config gdb"
        BUILDREQUIRES_EXTRA="libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel libcephfs-devel python3-devel"
        ADDITIONAL_PACKAGES=""
    
        if self.system_type == "centos":
            repo_name = "crb"
            version, _ = run_cmd(self.session, "rpm -E %{rhel}")
            version = version.strip()
            logger.info("CentOS Version for GPFS: %s", version)
            if version.startswith("10"):
                ADDITIONAL_PACKAGES = "python3-build python3-wheel python3-installer"
        elif self.system_type == "baremetal" or self.system_type == "openstack":
            # Detect RHEL version and arch
            release_out, _ = run_cmd(self.session, "cat /etc/redhat-release")
            arch, _ = run_cmd(self.session, "arch")

            match = re.search(r"release\s+(\d+)", release_out)
            if not match:
                raise RuntimeError("Unable to detect RHEL version")
            rhel_major = match.group(1)

            # Build repo name dynamically
            repo_name = f"codeready-builder-for-rhel-{rhel_major}-{arch.strip()}-rpms"
            run_cmd(self.session, f"subscription-manager repos --enable={repo_name}")

        dnf_cmd = f"dnf install --enablerepo={repo_name} -y {BASE_PACKAGES} {BUILDREQUIRES_EXTRA} {ADDITIONAL_PACKAGES} libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build libgfapi-devel xfsprogs-devel selinux-policy-devel sqlite --skip-broken"
        max_attempts = 3
        retry_delay = 30
        for attempt in range(1, max_attempts + 1):
            try:
                run_cmd(self.session, dnf_cmd)
                break
            except RuntimeError as e:
                if attempt == max_attempts:
                    raise
                logger.warning("dnf install failed (attempt %d/%d): %s. Cleaning cache and retrying in %ds ...", attempt, max_attempts, e, retry_delay)
                run_cmd(self.session, "dnf clean all", check=False)
                time.sleep(retry_delay)

        cmake_binary, _ = run_cmd(self.session, "which cmake")
        build_dir = f"{test_workspace}/nfs-ganesha/build"
        src_dir = f"{test_workspace}/nfs-ganesha"

        logger.info("Disabling GPFS NFS service to avoid conflicts during Ganesha build")
        run_cmd(self.session, f"/usr/lpp/mmfs/bin/mmces service disable nfs --force")
        out, code = run_cmd(self.session, [
            f"bash -c 'cd {src_dir} && rm -rf {build_dir} && "
            f"mkdir -p {build_dir} && cd {build_dir} && "
            f"{cmake_binary} {src_dir}/src {self.cmake_flags} && make dist'"
        ])

        logger.info("GPFS Make CephFS output: %s", out)
        logger.info("GPFS Make CephFS exit code: %d", code)
        assert code == 0, f"GPFS Make CephFS tests failed"
        
        run_cmd(self.session, f"ls -la {src_dir}")
        run_cmd(self.session, f"ls -la {build_dir}")

        out, code = run_cmd(self.session, f"ls {build_dir}/nfs-ganesha-*.tar.gz")
        logger.info("Tarball ls output: %s", out)
        tarball = out.strip().splitlines()[0]

        run_cmd(
            self.session,
            f"bash -c 'cd {build_dir} && "
            f"rpmbuild -ta --define \"_srcrpmdir {build_dir}\" "
            f"--define \"_rpmdir {build_dir}\" {tarball}'"
        )
        
        # Get RPM arch
        rpm_arch, _ = run_cmd(self.session, "rpm -E '%{_arch}'")
        logger.info("RPM Arch: %s", rpm_arch)

        ganesha_version, _ = run_cmd(
            self.session,
            f"bash -c 'cd {build_dir} && rpm -q --qf '%{{VERSION}}-%{{RELEASE}}' -p *.src.rpm'"
        )
        logger.info("Ganesha Version: %s", ganesha_version)

        # Check for NTIRPC
        ntirpc_check_cmd = f"bash -c 'cd {build_dir} && ls {rpm_arch}/libntirpc-devel*.rpm || true'"
        ntirpc_files, _ = run_cmd(self.session, ntirpc_check_cmd)

        if ntirpc_files.strip():
            ntirpc_version, _ = run_cmd(
                self.session,
                f"bash -c 'cd {build_dir} && rpm -q --qf '%{{VERSION}}-%{{RELEASE}}' -p {rpm_arch}/libntirpc-devel*.rpm'"
            )
            ntirpc_rpm = f"{rpm_arch}/libntirpc-{ntirpc_version}.{rpm_arch}.rpm"
            logger.info("NTIRPC Version: %s", ntirpc_version)
            logger.info("NTIRPC RPM: %s", ntirpc_rpm)

        run_cmd(
            self.session,
            '\"bash -c \'rpm -e --nodeps \$(rpm -qa | grep \"^gpfs\\.nfs-ganesha\")\'\"',
            check=False
        )

        run_cmd(self.session, f"\"bash -c 'rpm -qa | grep gpfs.nfs-ganesha'\"", check=False)
        out, _ = run_cmd(self.session, f"ls {build_dir}/x86_64/*.rpm")
        rpm_files_x86 = out.strip().splitlines()

        out, _ = run_cmd(self.session, f"ls {build_dir}/noarch/*.rpm")
        rpm_files_noarch = out.strip().splitlines()

        all_rpms = rpm_files_x86 + rpm_files_noarch
        rpm_list = " ".join(all_rpms)

        logger.info("List of RPMs: %s", rpm_list)

        run_cmd(self.session,
            f"bash -c 'cd {build_dir} && dnf -y install {rpm_list}'"
        )

        logger.info("Test block")
        run_cmd(self.session, "ulimit -a")
        run_cmd(self.session, "ulimit -c unlimited")
        run_cmd(self.session, "ulimit -a")

        run_cmd(self.session, "cat /etc/ganesha/ganesha.conf")

        run_cmd(self.session, "systemctl stop nfs-ganesha")
        if self.system_type == "centos":
            # Enclosed with  double quotes to handle special chars in bash since for centos this runs on vm from barmetal
            run_cmd(self.session, "sed -i.bak -e \"'s/^StateDirectory/#&/'\" /usr/lib/systemd/system/nfs-ganesha.service")
        else:
            run_cmd(self.session, "sed -i.bak -e 's/^StateDirectory/#&/' /usr/lib/systemd/system/nfs-ganesha.service")
        run_cmd(self.session, "systemctl daemon-reload")

        logger.info("NFS-Ganesha build, install, and minimal config complete.")
    # -------------------------------
    # Setup coredump configuration
    # -------------------------------
    def coredump_setup(self):
        logger.info("[STEP]: Setting up coredump configuration")
        run_cmd(self.session, "sysctl -w kernel.core_pattern=/tmp/cores/core.%e.%p.%h.%t")
        run_cmd(self.session, "mkdir -p /tmp/cores")
        run_cmd(self.session, "cat /proc/sys/kernel/core_pattern")
        logger.info("Coredump setup complete.")
        
    # -------------------------------
    # Start Ganesha service
    # -------------------------------
    def start_ganesha_service(self):
        logger.info("[STEP]: Starting NFS-Ganesha service...")
        out, rc = run_cmd(self.session, "systemctl enable --now nfs-ganesha.service", check=False)
        out, rc = run_cmd(self.session, "systemctl start nfs-ganesha.service", check=False)
        run_cmd(self.session, "systemctl status nfs-ganesha.service", check=False)
        run_cmd(self.session, "cat /etc/ganesha/ganesha.conf")
        if rc != 0:
            logger.error("Failed to start nfs-ganesha: %s", out)
            run_cmd(self.session, "journalctl -xe", check=False)
            assert False, "Failed to start nfs-ganesha service"
        logger.info("NFS-Ganesha started successfully.")

    # -------------------------------
    # Get NFS version
    # -------------------------------
    def get_nfs_version(self):
        """
        Get the NFS-Ganesha version.
        
        Returns:
            str: NFS-Ganesha version string (first line only) or "Unknown" if unable to retrieve.
        """
        logger.info("[STEP]: Getting NFS-Ganesha version")
        output, code = run_cmd(self.session, "ganesha.nfsd -v", check=False)
        
        if code == 0 and output:
            # Parse only the first line to get the version
            first_line = output.strip().split('\n')[0]
            logger.info(f"[OK] NFS-Ganesha version: {first_line}")
            return first_line
        
        logger.warning("Failed to get NFS-Ganesha version")
        return "Unknown"
    # -------------------------------
    # Setup and export NFS volume
    # -------------------------------
    def export_nfs_volume(self):
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmces service enable nfs")
        run_cmd(self.session, "cat /etc/ganesha/ganesha.conf")

        logger.info("[STEP]: Exporting NFS volume...")
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmuserauth service create --data-access-method file --type userdefined")
        if self.system_type == "centos":
            # Enclosed with  double quotes to handle special chars in bash since for centos this runs on vm from barmetal
            run_cmd(
                self.session,
                f"/usr/lpp/mmfs/bin/mmnfs export add {self.export} -c \"'*(Access_Type=RW,Squash=none)'\"",
            )
        else:
            run_cmd(
                self.session,
                f"/usr/lpp/mmfs/bin/mmnfs export add {self.export} -c '*(Access_Type=RW,Squash=none)'",
            )
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmnfs export list")

        logger.info("Restarting NFS-Ganesha to apply changes for Minor versions and UTF8 enforcement")
        run_cmd(self.session, "cat /var/mmfs/ces/nfs-config/gpfs.ganesha.main.conf")
        run_cmd(self.session, "systemctl stop nfs-ganesha", check=False)
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmnfs config list |grep MINOR")
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmnfs config change MINOR_VERSIONS=0,1,2")
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmnfs config list |grep ENFORCE")
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmnfs config change ENFORCE_UTF8_VALIDATION=true")
        time.sleep(20)
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmnfs config list |grep MINOR")
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmnfs config list |grep ENFORCE")
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmnfs config list")
        run_cmd(self.session, "systemctl daemon-reload")
        run_cmd(self.session, "cat /var/mmfs/ces/nfs-config/gpfs.ganesha.main.conf")
        
        # Validate enforce_utf8_validation and reload if false
        logger.info("Checking enforce_utf8_validation value")
        _, rc = run_cmd(self.session, "grep -i 'enforce_utf8_validation.*false' /var/mmfs/ces/nfs-config/gpfs.ganesha.main.conf", check=False)
        if rc == 0:
            logger.warning("enforce_utf8_validation is false, performing daemon-reload")
            run_cmd(self.session, "systemctl daemon-reload")
            time.sleep(20)
            run_cmd(self.session, "cat /var/mmfs/ces/nfs-config/gpfs.ganesha.main.conf")
        
        self.start_ganesha_service()

        run_cmd(self.session, "cat /var/mmfs/ces/nfs-config/gpfs.ganesha.main.conf")
        logger.info("Validating health of CES and NFS services")
        run_cmd(self.session, "systemctl status nfs-ganesha.service", check=False)
        run_cmd(self.session, "cat /etc/ganesha/ganesha.conf", check=False)
        self.wait_for_ces_healthy()
        run_cmd(self.session, "/usr/lpp/mmfs/bin/mmhealth cluster show CES")

        logger.info("Listing NFS exports configured in Ganesha")
        run_cmd(self.session, "cat /var/mmfs/ces/nfs-config/gpfs.ganesha.exports.conf")
        
        logger.info("NFS volume exported successfully.")
