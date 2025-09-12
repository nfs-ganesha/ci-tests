#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

echo "Client Script for executing LTP"

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

# install build and runtime dependencies
dnf install -y git gcc gcc-c++ make automake autoconf pkgconf pkgconf-pkg-config libtool bison flex perl perl-Time-HiRes python3 wget tar libaio-devel net-tools nfs-utils

git clone https://github.com/linux-test-project/ltp.git

cd ltp;make autotools;./configure;make -j$(nproc); make install

# Mount nfs
# v3 mount
mkdir -p /mnt/nfsv3
mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/nfsv3

# v4 mount
mkdir -p /mnt/nfsv4
mount -t nfs -o vers=4 ${SERVER}:${EXPORT} /mnt/nfsv4

# v4.2 mount
mkdir -p /mnt/nfsv42
mount -t nfs -o vers=4.2 ${SERVER}:${EXPORT} /mnt/nfsv42

# Run ltp on v3 mount
cd /opt/ltp; sudo ./runltp -d /mnt/nfsv3 -f fs -o /tmp/ltp_output_nfsv3.log -l /tmp/ltp_run_nfsv3.log -p

# Run ltp on v4.2 mount
cd /opt/ltp; sudo ./runltp -d /mnt/nfsv42 -f fs -o /tmp/ltp_output_nfsv42.log -l /tmp/ltp_run_nfsv42.log -p

# Run ltp on v4 mount
cd /opt/ltp; sudo ./runltp -d /mnt/nfsv4 -f fs -o /tmp/ltp_output_nfsv4.log -l /tmp/ltp_run_nfsv4.log -p
