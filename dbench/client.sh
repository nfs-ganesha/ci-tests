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
echo "Install build and runtime dependencies"
yum -y install git gcc nfs-utils time automake autoconf libtool popt-devel bison flex gtk2-devel libpcap-devel c-ares-devel libsmi-devel gnutls-devel libgcrypt-devel krb5-devel GeoIP-devel ortp-devel portaudio-devel

# dbench download, install and make
echo "dbench download, install and make"
git clone git://git.samba.org/sahlberg/dbench.git dbench
cd dbench
./autogen.sh
./configure
make
make install
curl -o /usr/local/share/client.txt https://raw.githubusercontent.com/sahlberg/dbench/master/loadfiles/client.txt


# v3 mount
mkdir -p /mnt/nfsv3
mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/nfsv3

# Running dbench suite on v3 mount
echo "---------------------------------------"
echo "dbench Test Running for v3 Mount..."
echo "---------------------------------------"
/root/dbench/dbench 2 > ../dbenchTestLog.txt
tail -1 ../dbenchTestLog.txt | grep "Throughput" 
status=$?
if [ $status -eq 0 ]
then
      tail -21 ../dbenchTestLog.txt
      echo "dbench Test: SUCCESS"
else
      tail -5 ../dbenchTestLog.txt
      echo "dbench Test: FAILURE"
      exit $status
fi
umount -l /mnt/nfsv3
      
      
# v4 mount
mkdir -p /mnt/nfsv4
mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/nfsv4

# Running dbench suite on v4.0 mount
echo "---------------------------------------"
echo "dbench Test Running for v4.0 Mount..."
echo "---------------------------------------"
/root/dbench/dbench 2 > ../dbenchTestLog.txt
tail -1 ../dbenchTestLog.txt | grep "Throughput" 
status=$?
if [ $status -eq 0 ]
then
      tail -21 ../dbenchTestLog.txt
      echo "dbench Test: SUCCESS"
else
      tail -5 ../dbenchTestLog.txt
      echo "dbench Test: FAILURE"
      exit $status
fi
umount -l /mnt/nfsv4


# v4.1 mount
mkdir -p /mnt/nfsv4_1
mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/nfsv4_1


# Running dbench suite on v4.1 mount
echo "---------------------------------------"
echo "dbench Test Running for v4.1 Mount..."
echo "---------------------------------------"
/root/dbench/dbench 2 > ../dbenchTestLog.txt
tail -1 ../dbenchTestLog.txt | grep "Throughput" 
status=$?
if [ $status -eq 0 ]
then
      tail -21 ../dbenchTestLog.txt
      echo "dbench Test: SUCCESS"
else
      tail -5 ../dbenchTestLog.txt
      echo "dbench Test: FAILURE"
      exit $status
fi
umount -l /mnt/nfsv4_1
