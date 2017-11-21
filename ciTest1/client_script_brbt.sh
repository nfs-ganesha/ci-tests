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
yum -y install nfs-utils time

mkdir -p /mnt/nfs3
mkdir -p /mnt/nfs4

mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/nfs3
mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/nfs4

echo "Hello World NFS3" > /mnt/nfs3/testFile.txt
echo "Hello World NFS4.0" > /mnt/nfs4/testFile.txt

cd / && umount /mnt/nfs3
cd / && umount /mnt/nfs4

fstabEntry=`echo -e $SERVER:$EXPORT "\t" /mnt/nfs3 "\t" nfs "\t" defaults "\t" 1 "\t" 1`

echo "FSTAB ENTRY VARIABLE"
echo "$fstabEntry"

echo "$fstabEntry" >> /etc/fstab

fstabEntry=`echo -e $SERVER:$EXPORT "\t" /mnt/nfs4 "\t" nfs4 "\t" defaults "\t" 1 "\t" 1`

echo "FSTAB ENTRY VARIABLE"
echo "$fstabEntry"

echo "$fstabEntry" >> /etc/fstab

echo "FSTAB FILE"
cat /etc/fstab

echo "REBOOTING ... "
systemctl reboot
