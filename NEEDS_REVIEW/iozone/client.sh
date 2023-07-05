#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

# install build and runtime dependencies
yum -y install nfs-utils time centos-release-gluster

mkdir -p /mnt/ganesha

yum --enablerepo=centos-gluster*test -y install iozone

mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha

cd /mnt/ganesha

echo "Running Iozone Test On NFSv3 "
echo "+++++++++++++++++++++++++++++"

iozone -a > ../ioZoneLog.txt

grep "iozone test complete" ../ioZoneLog.txt;

ret=$?

if [ $ret -eq 0 ]
then
        echo "IOZone Test Is Completed And Successful On v3";
else
        echo "IOZone Test Failed On NFSv3...";
        tail -3 ../ioZoneLog.txt;
        exit $ret;
fi

cd / && umount /mnt/ganesha

mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/ganesha

cd /mnt/ganesha

echo "Running Iozone Test On NFSv4.0 "
echo "++++++++++++++++++++++++++++++++"

iozone -a > ../ioZoneLog.txt

grep "iozone test complete" ../ioZoneLog.txt;

ret=$?

if [ $ret -eq 0 ]
then
        echo "IOZone Test Is Completed And Successful On v4.0";
else
        echo "IOZone Test Failed On NFSv4.0...";
        tail -3 ../ioZoneLog.txt;
        exit $ret;
fi

cd / && umount /mnt/ganesha

mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/ganesha

cd /mnt/ganesha

echo "Running Iozone Test On NFSv4.1 "
echo "+++++++++++++++++++++++++++++++"

iozone -a > ../ioZoneLog.txt

grep "iozone test complete" ../ioZoneLog.txt;

ret=$?

if [ $ret -eq 0 ]
then
        echo "IOZone Test Is Completed And Successful On v4.1";
else
        echo "IOZone Test Failed On NFSv4.1...";
        tail -3 ../ioZoneLog.txt;
        exit $ret;
fi

cd / && umount /mnt/ganesha

