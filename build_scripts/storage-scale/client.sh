#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

# if any command fails, the script should exit
set -e

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

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
git clone --depth=1 git://git.linux-nfs.org/projects/steved/cthon04.git
cd cthon04
make all

# v3 mount
#mkdir -p /mnt/nfsv3
#mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/nfsv3
#./server -a -p ${EXPORT} -m /mnt/nfsv3 ${SERVER}

# v4 mount
mkdir -p /mnt/nfsv4
mount -t nfs -o vers=4 ${SERVER}:${EXPORT} /mnt/nfsv4
./server -a -p ${EXPORT} -m /mnt/nfsv4 ${SERVER}

# v4.1 mount
#mkdir -p /mnt/nfsv41
#mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/nfsv41
#./server -a -p ${EXPORT} -m /mnt/nfsv41 ${SERVER}
