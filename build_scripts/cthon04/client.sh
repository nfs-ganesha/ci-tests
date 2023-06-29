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

# checkout the connectathon tests
git clone --depth=1 git://git.linux-nfs.org/projects/steved/cthon04.git
cd cthon04
make all

# v3 mount
mkdir -p /mnt/nfsv3
mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/nfsv3
timeout -s SIGKILL 240s ./server -a -p ${EXPORT} -m /mnt/nfsv3 ${SERVER} 
TIMED_OUT=$?
#Return code will be 124 if it ends the process by using SIGTERM for not getting any response. 137 when used SIGKILL to kill the process
if [ $TIMED_OUT == 137 ]; then
  echo -e "The process timed out after 4 minute!\nLooks like the Server process to see if it has crashed!"
  exit 1
fi

# v4 mount
mkdir -p /mnt/nfsv4
mount -t nfs -o vers=4 ${SERVER}:${EXPORT} /mnt/nfsv4
./server -a -p ${EXPORT} -m /mnt/nfsv4 ${SERVER}

# v4.1 mount
mkdir -p /mnt/nfsv41
mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/nfsv41
./server -a -p ${EXPORT} -m /mnt/nfsv41 ${SERVER}

# implicit exit status from the last command
