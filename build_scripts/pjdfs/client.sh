#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

echo "Client Script"

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]
[ -n "${TEST_PARAMETERS}" ]

# install build and runtime dependencies
dnf -y install git gcc nfs-utils redhat-rpm-config krb5-devel python3-devel python3-gssapi python3-ply

dnf -y install wget git gcc gcc-c++ time make automake autoconf pkgconf pkgconf-pkg-config libtool bison flex perl perl-Time-HiRes python3 wget tar libaio-devel net-tools nfs-utils

cd /root;git clone https://github.com/pjd/pjdfstest.git;cd pjdfstest;autoreconf -ifs;./configure;make pjdfstest

mkdir -p /mnt/nfsv3
mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/nfsv3
export TESTDIR=/mnt/nfsv3
cd /mnt/nfsv3;prove -rv /root/pjdfstest/tests/


mkdir -p /mnt/nfsv4
mount -t nfs -o vers=4 ${SERVER}:${EXPORT} /mnt/nfsv4
export TESTDIR=/mnt/nfsv4
cd /mnt/nfsv4;prove -rv /root/pjdfstest/tests/


# v4.1 mount
mkdir -p /mnt/nfsv41
mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/nfsv41
export TESTDIR=/mnt/nfsv41
cd /mnt/nfsv41;prove -rv /root/pjdfstest/tests/

