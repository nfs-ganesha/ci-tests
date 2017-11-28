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
echo "Install build and runtime dependencies"
yum -y install nfs-utils git gcc time

echo "--------------------------------------------------"
echo "Running test on Mount Version 3"
echo "--------------------------------------------------"

# mount
mkdir -p /mnt/nfs
mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/nfs
cd /mnt/nfs
yum -y install bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel libnfsidmap-devel libwbclient-devel libcap-devel libblkid-devel rpm-build redhat-rpm-config
git clone https://review.gerrithub.io/ffilz/nfs-ganesha
cd nfs-ganesha
git checkout next
git submodule update --init || git submodule sync
cd ..
mkdir ganeshaBuild
cd ganeshaBuild
cmake -DDEBUG_SYMS=ON -DUSE_FSAL_GLUSTER=ON -DCURSES_LIBRARY=/usr/lib64 -DCURSES_INCLUDE_PATH=/usr/include/ncurses -DCMAKE_BUILD_TYPE=Maintainer -DUSE_DBUS=ON /mnt/nfs/nfs-ganesha/src
make -j4
make install
cd ..
rm -rf ganeshaBuild

#unmount
umount -l /mnt/nfs


echo "--------------------------------------------------"
echo "Running test on Mount Version 4.0"
echo "--------------------------------------------------"

# mount
mkdir -p /mnt/nfs
mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/nfs
cd /mnt/nfs
cd nfs-ganesha
git checkout next
git submodule update --init || git submodule sync
cd ..
mkdir ganeshaBuild
cd ganeshaBuild
cmake -DDEBUG_SYMS=ON -DUSE_FSAL_GLUSTER=ON -DCURSES_LIBRARY=/usr/lib64 -DCURSES_INCLUDE_PATH=/usr/include/ncurses -DCMAKE_BUILD_TYPE=Maintainer -DUSE_DBUS=ON /mnt/nfs/nfs-ganesha/src
make -j4
make install
cd ..
rm -rf ganeshaBuild

#unmount
umount -l /mnt/nfs


echo "--------------------------------------------------"
echo "Running test on Mount Version 4.1"
echo "--------------------------------------------------"

# mount
mkdir -p /mnt/nfs
mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/nfs
cd /mnt/nfs
cd nfs-ganesha
git checkout next
git submodule update --init || git submodule sync
cd ..
mkdir ganeshaBuild
cd ganeshaBuild
cmake -DDEBUG_SYMS=ON -DUSE_FSAL_GLUSTER=ON -DCURSES_LIBRARY=/usr/lib64 -DCURSES_INCLUDE_PATH=/usr/include/ncurses -DCMAKE_BUILD_TYPE=Maintainer -DUSE_DBUS=ON /mnt/nfs/nfs-ganesha/src
make -j4
make install

#unmount
umount -l /mnt/nfs
