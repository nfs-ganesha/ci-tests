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

mkdir -p /mnt/ganesha

mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha

cd /mnt/ganesha

echo "Hello World" > testFile.txt

cd / && umount /mnt/ganesha

fstabEntry=`echo -e $SERVER:$EXPORT "\t" /mnt/ganesha "\t" nfs "\t" defaults "\t" 1 "\t" 1`

echo "FSTAB ENTRY VARIABLE"
echo "$fstabEntry"

echo "$fstabEntry" >> /etc/fstab

echo "FSTAB FILE"
cat /etc/fstab

echo "REBOOTING ... "
systemctl reboot
