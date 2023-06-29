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

if [ "$CENTOS_VERSION" == "7" ]; then
  yum --enablerepo=centos-gluster*test -y install iozone
elif [ "$CENTOS_VERSION" == "8s" ]; then
  curl -o /etc/yum.repos.d/iozone.repo https://copr.fedorainfracloud.org/coprs/aflyhorse/iozone/repo/centos-stream-8/aflyhorse-iozone-centos-stream-8.repo
  yum install -y iozone
elif [ "$CENTOS_VERSION" == "9s" ]; then
  curl -o /etc/yum.repos.d/iozone.repo https://copr.fedorainfracloud.org/coprs/aflyhorse/iozone/repo/centos-stream-9/aflyhorse-iozone-centos-stream-9.repo
  yum install -y iozone
fi

mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha

cd /mnt/ganesha

echo "Running Iozone Test On NFSv3 "
echo "+++++++++++++++++++++++++++++"

#timeout -s SIGKILL 240s iozone -a > ../ioZoneLog.txt
#TIMED_OUT=$?
#Return code will be 124 if it ends the process by using SIGTERM for not getting any response. 137 when used SIGKILL to kill the process
#if [ $TIMED_OUT == 137 ]; then
#  echo -e "The process timed out after 4 minute!\nLooks like the Server process to see if it has crashed!"
#  exit 1
#fi

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

