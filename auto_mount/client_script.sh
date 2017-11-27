#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

if [ "$1" = "initial_stage" ]
then

	# install build and runtime dependencies
	yum -y install nfs-utils time

	mkdir -p /mnt/nfs3
	mkdir -p /mnt/nfs4

	mount -t nfs ${SERVER}:${EXPORT} /mnt/nfs3

	echo "Hello World" > /mnt/nfs3/testFile.txt

	cd / && umount /mnt/nfs3

	fstabEntry=`echo -e $SERVER:$EXPORT "\t" /mnt/nfs3 "\t" nfs "\t" defaults "\t" 1 "\t" 1`

	echo "$fstabEntry" >> /etc/fstab

	fstabEntry=`echo -e $SERVER:$EXPORT "\t" /mnt/nfs4 "\t" nfs4 "\t" defaults "\t" 1 "\t" 1`

	echo "$fstabEntry" >> /etc/fstab	

	echo "FSTAB FILE"
	cat /etc/fstab

	echo "REBOOTING ... "
	systemctl reboot

elif [ "$1" = "after_reboot" ]
then
	cat /mnt/nfs3/testFile.txt | grep "Hello World"

	ret=$?

	if [ $ret -eq 0 ]
	then
		echo "=======||  Auto Remount Works Succesfully On v3 Mount ||======="
	else
		echo "*******||  Auto Remount Failed on v3 Mount ||*******"
		exit $ret
	fi

	cat /mnt/nfs4/testFile.txt | grep "Hello World"

	ret=$?

	if [ $ret -eq 0 ]
	then
		echo "=======||  Auto Remount Works Succesfully On v4.0 Mount ||======="
	else
		echo "*******||  Auto Remount Failed on v4.0 Mount ||*******"
		exit $ret
	fi

	cd / && umount /mnt/nfs4
	cd / && umount /mnt/nfs3
	
fi

