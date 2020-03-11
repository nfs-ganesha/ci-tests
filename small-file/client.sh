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
yum -y install git gcc nfs-utils time

# Cloning the small file test repo
git clone https://github.com/distributed-system-analysis/smallfile.git
cd smallfile

# v3 mount
mkdir -p /mnt/nfsv3
mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/nfsv3
./smallfile_cli.py --files 100000 --threads 10 --file-size 4 --hash-into-dirs Y --top /mnt/nfsv3 --operation create

# v4 mount
mkdir -p /mnt/nfsv4
mount -t nfs -o vers=4 ${SERVER}:${EXPORT} /mnt/nfsv4
./smallfile_cli.py --files 100000 --threads 10 --file-size 4 --hash-into-dirs Y --top /mnt/nfsv4 --operation create

# v4.1 mount
mkdir -p /mnt/nfsv41
mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/nfsv41
./smallfile_cli.py --files 100000 --threads 10 --file-size 4 --hash-into-dirs Y --top /mnt/nfsv41 --operation create


