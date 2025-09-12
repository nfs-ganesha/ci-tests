#!/bin/sh

# if any command fails, the script should exit
set -e

# enable some more output
set -x

# Run basic ceph deployment and ganesha service
sh $WORKSPACE/ci-tests/ceph/basic-ceph.sh

# install build and runtime dependencies
yum -y install git gcc nfs-utils time make


ENABLE_REPO="--enablerepo=crb"
yum ${ENABLE_REPO} install -y libtirpc-devel

#Logic to generate corefiles
echo "/tmp/cores/core.%e.%p.%h.%t" > /proc/sys/kernel/core_pattern
mkdir -p /tmp/cores

# checkout the PJDFS tests
dnf install -y autoconf automake clang gcc perl perl-TAP-Harness --skip-broken
git clone --depth=1 https://github.com/pjd/pjdfstest.git
autoreconf -ifs
make pjdfstest
cd pjdfstest

# Run PJDFS for v4.0
mkdir -p /mnt/nfs_ceph_v4
if mount -t nfs -o vers=4 $(hostname -I | awk '{print $1}'):/nfs/cephfs /mnt/nfs_ceph_v4; then
    echo "NFS mount successful!"
    if mountpoint -q /mnt/nfs_ceph_v4; then
        echo "Verification: NFS is properly mounted at /mnt/nfs_ceph_v4"
        echo "Mounted NFS details:"
        mount | grep /mnt/nfs_ceph_v4
    else
        echo "ERROR: Mount command succeeded but verification failed!" >&2
        exit 1
    fi
else
    echo "ERROR: Failed to mount NFS share!" >&2
    cat /var/log/ganesha.log
    touch FAILED
    exit 1
fi
# Run PJDFS
prove -rv  /mnt/nfs_ceph_v4

# Run PJDFS for v4.2
mkdir -p /mnt/nfs_ceph_v42
if mount -t nfs -o vers=4.2 $(hostname -I | awk '{print $1}'):/nfs/cephfs /mnt/nfs_ceph_v42; then
    echo "NFS mount successful!"
    if mountpoint -q /mnt/nfs_ceph_v42; then
        echo "Verification: NFS is properly mounted at /mnt/nfs_ceph_v42"
        echo "Mounted NFS details:"
        mount | grep /mnt/nfs_ceph_v42
    else
        echo "ERROR: Mount command succeeded but verification failed!" >&2
        exit 1
    fi
else
    echo "ERROR: Failed to mount NFS share!" >&2
    cat /var/log/ganesha.log
    touch FAILED
    exit 1
fi
# Run PJDFS
prove -rv  /mnt/nfs_ceph_v42


# Run PJDFS for v3
mkdir -p /mnt/nfs_ceph_v3
if mount -t nfs -o vers=3 $(hostname -I | awk '{print $1}'):/nfs/cephfs /mnt/nfs_ceph_v3; then
    echo "NFS mount successful!"
    if mountpoint -q /mnt/nfs_ceph_v3; then
        echo "Verification: NFS is properly mounted at /mnt/nfs_ceph_v3"
        echo "Mounted NFS details:"
        mount | grep /mnt/nfs_ceph_v3
    else
        echo "ERROR: Mount command succeeded but verification failed!" >&2
        exit 1
    fi
else
    echo "ERROR: Failed to mount NFS share!" >&2
    cat /var/log/ganesha.log
    touch FAILED
    exit 1
fi
# Run PJDFS
prove -rv /mnt/nfs_ceph_v3

exit 0

