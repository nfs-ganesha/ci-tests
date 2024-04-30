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
yum -y install nfs-utils git gcc time centos-release-gluster centos-release-ceph

# flag for commands which should run only once
once=0

#NFS-Ganesha is crashing when installing 4.0, so taking it out to see if 4.1 works

for ver in 3 4.1
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
        if [ "${CENTOS_VERSION}" == "7" ]; then
          yum -y install bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel libnfsidmap-devel libwbclient-devel libcap-devel libblkid-devel rpm-build redhat-rpm-config glusterfs-api libnsl2-devel libcephfs-devel rdma-core-devel
          yum clean all & yum clean metadata
          yum -y install userspace-rcu-devel
        elif [ "${CENTOS_VERSION}" == "8s" ]; then
          yum -y install bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel libcap-devel libblkid-devel rpm-build redhat-rpm-config glusterfs-api rdma-core-devel
          yum -y --enablerepo=powertools install libnfsidmap-devel libwbclient-devel userspace-rcu-devel userspace-rcu libnsl2-devel libcephfs-devel
        elif [ "${CENTOS_VERSION}" == "9s" ]; then
          yum -y install bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel libcap-devel libblkid-devel rpm-build redhat-rpm-config glusterfs-api rdma-core-devel
          yum -y --enablerepo=crb install libnfsidmap-devel libwbclient-devel userspace-rcu-devel userspace-rcu libnsl2-devel libcephfs-devel libuuid libuuid-devel
        fi
        timeout -s SIGKILL 600s git clone --depth=1 https://review.gerrithub.io/ffilz/nfs-ganesha
        TIMED_OUT=$?
        echo $TIMED_OUT
        #Return code will be 124 if it ends the process by using SIGTERM for not getting any response. 137 when used SIGKILL to kill the process
        if [ $TIMED_OUT == 137 ]; then
          echo -e "The process timed out after 1 minute!\nChecking the Server process to see if it has crashed!"
          exit 1
        fi
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
