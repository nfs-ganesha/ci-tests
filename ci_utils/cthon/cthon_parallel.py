#!/usr/bin/env python3
############# CTHON Parallel Test Runner##################################
# This script sets up and runs multiple instances of CTHON tests in parallel
# using Podman containers, each mounting an NFS export.
# It handles NFS mounting and container management
# This can run independently on any machine with Podman and NFS access.
# Sample usage:
# python3 cthon-script.py --server 10.8.130.240 --export /ibm/fs1 --instances 20 --log-dir /tmp --nfs-version 4 --repeat 1000 --timeout 86400

# This command runs 20 parallel CTHON instances against NFSv4 export /ibm/fs1 on server for 1000 iterations each, 
# logging to /tmp, with a timeout of 24 hours per instance.
#################################################################
import os
import subprocess
import time
import argparse
import tempfile
import shutil
import concurrent.futures

DOCKERFILE_CONTENT = r"""
FROM centos:9
RUN dnf -y install dnf-plugins-core && \
    dnf config-manager --set-enabled crb && \
    dnf -y install \
      nfs-utils \
      git make gcc automake autoconf \
      libtirpc libtirpc-devel \
      util-linux \
      hostname \
      time \
    && dnf clean all
WORKDIR /root
RUN git clone --depth=1 git://git.linux-nfs.org/projects/steved/cthon04.git && \
    cd cthon04 && \
    make
WORKDIR /root/cthon04
ENTRYPOINT ["bash", "./server"]
"""

def parse_args():
    parser = argparse.ArgumentParser(description="Run CTHON tests inside Podman with NFS mount handling")
    parser.add_argument("--server", required=True, help="NFS server IP/hostname")
    parser.add_argument("--export", required=True, help="NFS export path (real or pseudo)")
    parser.add_argument("--nfs-version", required=True, choices=["3", "4", "4.1"], help="NFS version")
    parser.add_argument("--instances", type=int, default=1, help="Number of parallel instances")
    parser.add_argument("--base-dir", default="/mnt/test", help="Base mount directory")
    parser.add_argument("--log-dir", default="/tmp", help="Directory to store logs")
    parser.add_argument("--repeat", default=1, help="Number of times the script to be run continuosly")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds for each test instance")
    return parser.parse_args()

def build_image():
    tmpdir = tempfile.mkdtemp()
    dockerfile_path = os.path.join(tmpdir, "Dockerfile")
    with open(dockerfile_path, "w") as f:
        f.write(DOCKERFILE_CONTENT)
    print("[INFO] Building cthon-client image...")
    subprocess.run(["podman", "build", "-t", "cthon-client", tmpdir], check=True)
    shutil.rmtree(tmpdir)

def mount_nfs(server, export, mount_point, nfs_version):
    os.makedirs(mount_point, exist_ok=True)
    res = subprocess.run(["mountpoint", "-q", mount_point])
    if res.returncode != 0:
        print(f"[INFO] Mounting {server}:{export} on {mount_point} (NFSv{nfs_version})")
        subprocess.run([
            "mount", "-t", "nfs",
            "-o", f"vers={nfs_version}",
            f"{server}:{export}", mount_point
        ], check=True)

def unmount_nfs(mount_point):
    print(f"[INFO] Unmounting {mount_point}")
    subprocess.run(["umount", "-f", mount_point], check=False)

def run_instance(i, server, export, mount_point, log_dir, repeat):
    log_file = os.path.join(log_dir, f"cthon-{i}.log")
    f = open(log_file, "w")
    print(f"[INFO] Launching cthon instance {i}, logs -> {log_file}")
    p = subprocess.Popen([
        "podman", "run", "--rm", "--replace",
        "--name", f"cthon{i}",
        "--privileged", "--cap-add=SYS_ADMIN", "--device", "/dev/fuse",
        "-v", f"{mount_point}:{mount_point}",
        "cthon-client",
        "-a", "-p", export, "-m", mount_point, "-N", repeat, server
    ], stdout=f, stderr=subprocess.STDOUT)
    return p, f, time.time()

def main():
    args = parse_args()
    build_image()
    processes = {}
    try:
        # Step 1: mount NFS for each instance
        for i in range(1, args.instances + 1):
            mnt = f"{args.base_dir}-{i}"
            mount_nfs(args.server, args.export, mnt, args.nfs_version)
        # Step 2: launch containers
        for i in range(1, args.instances + 1):
            mnt = f"{args.base_dir}-{i}"
            processes[i] = run_instance(i, args.server, args.export, mnt, args.log_dir, args.repeat)
        # Step 3: wait and report
        results = {}

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_i = {
                executor.submit(p.wait, args.timeout): (i, p, f, start_time)
                for i, (p, f, start_time) in processes.items()
            }
            for future in concurrent.futures.as_completed(future_to_i):
                i, p, f, start_time = future_to_i[future]
                try:
                    rc = future.result()
                    status = "✅ SUCCESS" if rc == 0 else f"❌ FAILED (exit code {rc})"
                except subprocess.TimeoutExpired:
                    print(f"[WARN] Instance {i} timed out, killing container cthon{i}")
                    p.kill()
                    subprocess.run(["podman", "rm", "-f", f"cthon{i}"], check=False)
                    rc = -1
                    status = "⚠️ HUNG (timeout)"
                finally:
                    f.close()
                    duration = time.time() - start_time
                    results[i] = (rc, duration, status)
        print("\n===== TEST SUMMARY =====")
        for i, (rc, duration, status) in results.items():
            log_file = os.path.join(args.log_dir, f"cthon-{i}.log")
            print(f"Instance {i}: {status} (Duration: {duration:.2f}s) - log: {log_file}")

    finally:
        # Always unmount on exit
        for i in range(1, args.instances + 1):
            mnt = f"{args.base_dir}-{i}"
            unmount_nfs(mnt)

if __name__ == "__main__":
    main()
