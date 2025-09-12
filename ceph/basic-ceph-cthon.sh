#!/bin/sh

# if any command fails, the script should exit
set -e

# enable some more output
set -x

# Run basic ceph deployment and ganesha service
sh $WORKSPACE/ci-tests/ceph/basic-ceph.sh

# Run Cthon post successful cluster creation

# install build and runtime dependencies
yum -y install git gcc nfs-utils time make

if [ "${CENTOS_VERSION}" == "8s" ]; then
  ENABLE_REPO="--enablerepo=powertools"
elif [ "${CENTOS_VERSION}" == "9s" ]; then
  ENABLE_REPO="--enablerepo=crb"
fi
yum ${ENABLE_REPO} install -y libtirpc-devel

#Logic to generate corefiles
echo "/tmp/cores/core.%e.%p.%h.%t" > /proc/sys/kernel/core_pattern
mkdir -p /tmp/cores

# checkout the connectathon tests
cd
git clone --depth=1 git://git.linux-nfs.org/projects/steved/cthon04.git
cd cthon04
( make all )  || true


# RUN CTHON for v3 < SKIPPING AS CURRENT RUNS FOCUS ON 4 and 4.1 >
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
    touch FAILED
    exit 1
fi
# Run Cthon
./server -a -p /nfs/cephfs -m /mnt/nfs_ceph_v3 $(hostname -I | awk '{print $1}')
./test $(hostname -I | awk '{print $1}'):/nfs/cephfs /mnt/nfs_ceph_v3

# Run CTHON for v4.0
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
# Run Cthon

if [ "${CONCURRENT_JOBS}" == "True" ]; then
  ./server -c 100000 /nfs/cephfs -m /mnt/nfs_ceph_v4 $(hostname -I | awk '{print $1}')
else
  ./server -a -p /nfs/cephfs -m /mnt/nfs_ceph_v4 $(hostname -I | awk '{print $1}')
fi

# Run CTHON for v4.2
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
# Run Cthon
if [ "${CONCURRENT_JOBS}" == "True" ]; then
  ./server -c 100000 /nfs/cephfs -m /mnt/nfs_ceph_v4 $(hostname -I | awk '{print $1}')
else
  ./server -a -p /nfs/cephfs -m /mnt/nfs_ceph_v4 $(hostname -I | awk '{print $1}')
fi

exit 0
