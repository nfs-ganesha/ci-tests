#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

if [ "$1" = "client_initialization" ]
then
	# install build and runtime dependencies
	yum -y install nfs-utils time

	mkdir -p /mnt/ganesha

	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha

	echo "Client Initial Stage --- With All Rights To All Clients ( RO & RW ) "

	cd /mnt/ganesha
	
	echo "Trying To Write A File"
	echo "Hello World" > testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "SUCCESS"
	else
		echo "FAILED ON WRITING RIGHTS"
		#exit ret
	fi

	echo "Trying To Read A File"
	cat testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "SUCCESS"
	else
		echo "FAILED ON READING RIGHTS"
		#exit ret
	fi

	cd / && umount /mnt/ganesha
fi

if [ "$1" = "client_stage1" ]
then
	echo "Client Stage 1 --- With Only RO Rights To This Client "

	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha

	cd /mnt/ganesha

	echo "Trying To Write A File"
	sed -i '1s/$/ From RedHat/' testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE Since Write Permissions Were Not Blocked To The Client"
		#exit ret
	else
		echo "SUCCESS ON WRITE PERMISSIONS FAILURE"
	fi

	echo "Trying To Read A File"
	cat testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "SUCCESS"
	else
		echo "FAILED ON READING RIGHTS"
		#exit ret
	fi
	
	cd / && umount /mnt/ganesha
fi


if [ "$1" = "client_stage2" ]
then
	echo "Client Stage 2 --- With Only Rights For v3 Mount To This Client "

	echo "Trying To Mount By vers=3"
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "SUCCESS ON v3 MOUNT BY CLIENT"
	else
		echo "FAILURE ON v3 MOUNT BY CLIENT"
		#exit ret
	fi

	cd / && umount /mnt/ganesha

	echo "Trying To Mount By vers=4.0"
	mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE Since v4.0 Permissions Were Not Given To The Client"
		#exit ret
	else
		echo "SUCCESS ON v4.0 MOUNT FAILURE"
	fi

	cd / && umount /mnt/ganesha

	echo "Trying To Mount By vers=4.1"
	mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE Since v4.1 Permissions Were Not Given To The Client"
		#exit ret
	else
		echo "SUCCESS ON v4.1 MOUNT FAILURE"
	fi

	cd / && umount /mnt/ganesha

fi

if [ "$1" = "client_stage3" ]
then
	echo "Client Stage 3 --- With Only Rights For v4.0 & v4.1 Mount To This Client "

	echo "Trying To Mount By vers=3"
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE Since v3 Permissions Were Not Given To The Client"
		#exit ret
	else
		echo "SUCCESS ON v3 MOUNT FAILURE"
	fi

	cd / && umount /mnt/ganesha

	echo "Trying To Mount By vers=4.0"
	mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "SUCCESS ON v4.0 MOUNT BY CLIENT"
	else
		echo "FAILURE ON v4.0 MOUNT BY CLIENT"
		#exit ret
	fi

	cd / && umount /mnt/ganesha

	echo "Trying To Mount By vers=4.1"
	mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "SUCCESS ON v4.1 MOUNT BY CLIENT"
	else
		echo "FAILURE ON v4.1 MOUNT BY CLIENT"
		#exit ret
	fi

	cd / && umount /mnt/ganesha

fi


if [ "$1" = "client_stage4" ]
then
	echo "Client Stage 4 --- With Squashed Root Mount To This Client "

	mount -t nfs ${SERVER}:${EXPORT} /mnt/ganesha

	echo "Creating New User : test-user"
	adduser test-user
	echo asd123 | passwd test-user --stdin

	echo "Adding test-user to sudoers file"
	echo -e 'test-user \t ALL=(ALL) \t NOPASSWD:ALL' >> /etc/sudoers

	echo "Trying To Change Ownership Of The File testFile.txt in the mount"
	sudo chown test-user /mnt/ganesha/testFile.txt

	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE Since ROOT PERMISSIONS Were Not Given To This Client"
		#exit ret
	else
		echo "SUCCESS ON chown Permission Denied"
	fi

	cd / && umount /mnt/ganesha

fi





