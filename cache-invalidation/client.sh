#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

# if any command fails, the script should exit
set -e

# enable some more output
set -x

if [ $1 -eq 1 ]
then
    [ -n "${SERVER}" ]
    [ -n "${EXPORT}" ]
    
    # install build and runtime dependencies
    echo "Install build and runtime dependencies"
    yum -y install nfs-utils time

    echo "--------------------------------------------------"
    echo "Running test on Mount Version $2"
    echo "--------------------------------------------------"

    # mount
    mkdir -p /mnt/nfs
    mount -t nfs -o vers=$2 ${SERVER}:${EXPORT} /mnt/nfs
    status=$?
    if [ $status -ne 0 ]
    then
        echo "Failed Mounting for version $2 on client-2"
        echo "Cache Invalidation Test: FAILURE"
        exit $status
    fi

elif [ $1 -eq 2 ]
then
    touch /mnt/nfs/file1.txt
    > /mnt/nfs/file1.txt
    echo "We Are" >> /mnt/nfs/file1.txt

elif [ $1 -eq 3 ]
then
    content=$(cat /mnt/nfs/file1.txt)
    if [ "$content" == "We Are" ]
    then
        echo "REDHAT" >> /mnt/nfs/file1.txt
    else
        echo "Cache Invalidation Test: FAILURE"
        exit -1
    fi
    #unmount on client-2
    umount /mnt/nfs

elif [ $1 -eq 4 ]
then
    content=$(cat /mnt/nfs/file1.txt)
    if [ "$content" != "We Are
REDHAT" ]
    then
        echo "Cache Invalidation Test: FAILURE"
        exit -1
    fi
    #unmount on client-1
    umount /mnt/nfs
fi
