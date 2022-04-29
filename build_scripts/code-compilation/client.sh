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

# flag for commands which should run only once
once=0

for ver in 3 4.0 4.1
do
    echo "--------------------------------------------------"
    echo "Running test on Mount Version $ver"
    echo "--------------------------------------------------"

    mkdir -p /mnt/nfs
    # mount
    mount -t nfs -o vers=$ver ${SERVER}:${EXPORT} /mnt/nfs
    cd /mnt/nfs
    if [ $once -eq 0 ]
    then
        yum -y install bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel libnfsidmap-devel libwbclient-devel libcap-devel libblkid-devel rpm-build redhat-rpm-config
        git clone https://review.gerrithub.io/ffilz/nfs-ganesha
    fi
    cd nfs-ganesha
    git checkout next
    if [ $once -eq 0 ]
    then
        git submodule update --init || git submodule sync
        once=1
    fi
    cd ..
    mkdir ganeshaBuild
    cd ganeshaBuild
    cmake -DDEBUG_SYMS=ON -DCURSES_LIBRARY=/usr/lib64 -DCURSES_INCLUDE_PATH=/usr/include/ncurses -DCMAKE_BUILD_TYPE=Maintainer -DUSE_DBUS=ON /mnt/nfs/nfs-ganesha/src
    status=$?
    if [ $status -ne 0 ]
    then
        echo "FAILURE: cmake failed"
        exit $status
    fi
    make -j4
    make install
    cd ..
    rm -rf ganeshaBuild

    #unmount
    umount -l /mnt/nfs
done
