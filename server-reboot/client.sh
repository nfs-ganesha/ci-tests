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
yum -y install nfs-utils time

echo "--------------------------------------------------"
echo "Running test on Mount Version $1"
echo "--------------------------------------------------"

# mount
mkdir -p /mnt/nfs
mount -t nfs -o vers=$1 ${SERVER}:${EXPORT} /mnt/nfs
status=$?
if [ $status -eq 0 ]
then
    # creating and performing io operation on file
    touch test_file.txt
    for ((i=1;i<=100;i++)); 
    do 
        echo "$i " >> test_file.txt
        sleep 1
    done
    cat test_file.txt
    #unmount
    umount -l /mnt/nfs
else
   echo "Failed Mounting for version $1"
   echo "Server Reboot Test: FAILURE"
   exit $status
fi
