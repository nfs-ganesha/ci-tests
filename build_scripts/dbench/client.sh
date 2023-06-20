#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

echo "Client Script"

# if any command fails, the script should exit
set -e

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

# install build and runtime dependencies
echo "Install runtime dependencies"
yum -y install nfs-utils

# dbench is available from the testing repositories in the CentOS Storage SIG
if [ "$CENTOS_VERSION" == "7" ]; then
  yum -y install centos-release-gluster
  yum --enablerepo=centos-gluster*-test -y install dbench
elif [ "$CENTOS_VERSION" == "8s" ]; then
  yum -y install epel-release
  yum -y install dbench
else
  echo "Please check the CENTOS_VERSION! The build implementation for this version=${CENTOS_VERSION} is in progress!"
fi

# place all used files in ${WORKDIR}
WORKDIR=/var/tmp/dbench.d
mkdir ${WORKDIR}

curl -o ${WORKDIR}/client.txt https://raw.githubusercontent.com/sahlberg/dbench/master/loadfiles/client.txt


# v3 mount
mkdir -p /mnt/nfsv3
mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/nfsv3
mkdir /mnt/nfsv3/v3

# Running dbench suite on v3 mount
echo "---------------------------------------"
echo "dbench Test Running for v3 Mount..."
echo "---------------------------------------"
dbench --directory=/mnt/nfsv3/v3 --loadfile=${WORKDIR}/client.txt 2 > ${WORKDIR}/dbenchTestLog.txt
tail -1 ${WORKDIR}/dbenchTestLog.txt | grep "Throughput"
status=$?
if [ $status -eq 0 ]
then
      tail -21 ${WORKDIR}/dbenchTestLog.txt
      echo "dbench Test: SUCCESS"
else
      tail -5 ${WORKDIR}/dbenchTestLog.txt
      echo "dbench Test: FAILURE"
      exit $status
fi
umount -l /mnt/nfsv3
      
      
# v4 mount
mkdir -p /mnt/nfsv4
mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/nfsv4
mkdir /mnt/nfsv4/v4

# Running dbench suite on v4.0 mount
echo "---------------------------------------"
echo "dbench Test Running for v4.0 Mount..."
echo "---------------------------------------"
dbench --directory=/mnt/nfsv4/v4 --loadfile=${WORKDIR}/client.txt 2 > ${WORKDIR}/dbenchTestLog.txt
tail -1 ${WORKDIR}/dbenchTestLog.txt | grep "Throughput"
status=$?
if [ $status -eq 0 ]
then
      tail -21 ${WORKDIR}/dbenchTestLog.txt
      echo "dbench Test: SUCCESS"
else
      tail -5 ${WORKDIR}/dbenchTestLog.txt
      echo "dbench Test: FAILURE"
      exit $status
fi
umount -l /mnt/nfsv4


# v4.1 mount
mkdir -p /mnt/nfsv4_1
mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/nfsv4_1
mkdir /mnt/nfsv4_1/v41

# Running dbench suite on v4.1 mount
echo "---------------------------------------"
echo "dbench Test Running for v4.1 Mount..."
echo "---------------------------------------"
dbench --directory=/mnt/nfsv4_1/v41 --loadfile=${WORKDIR}/client.txt 2 > ${WORKDIR}/dbenchTestLog.txt
tail -1 ${WORKDIR}/dbenchTestLog.txt | grep "Throughput"
status=$?
if [ $status -eq 0 ]
then
      tail -21 ${WORKDIR}/dbenchTestLog.txt
      echo "dbench Test: SUCCESS"
else
      tail -5 ${WORKDIR}/dbenchTestLog.txt
      echo "dbench Test: FAILURE"
      exit $status
fi
umount -l /mnt/nfsv4_1
