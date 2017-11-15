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
	echo "In Client Initialization Stage"
	# install build and runtime dependencies
	yum -y install nfs-utils time

	mkdir -p /mnt/ganesha

	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha

	echo "In Client Initial Stage --- With All Rights To All Clients ( RO & RW ) "

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
	echo "In Client Stage 1 --- With Only RO Rights To This Client "

	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha

	cd /mnt/ganesha

	echo "Trying To Write A File"
	sed -i '1s/$/ From RedHat/' testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE Since Write Permissions Were Not Blocked To The CLient"
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
	echo "In Client Stage 2 --- With Only Rights For v3 Mount To This Client "

	echo "Trying To Mount By vers=3"
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	echo "Hello From v3_Mount" > /mnt/ganesha/testFile.txt
	cat /mnt/ganesha/testFile.txt
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
	echo "Hello From v4.0_Mount" > /mnt/ganesha/testFile.txt
	cat /mnt/ganesha/testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE Since v4.0 Permissions Were Not Given To The CLient"
		#exit ret
	else
		echo "SUCCESS ON v4.0 MOUNT FAILURE"
	fi

	cd / && umount /mnt/ganesha

	echo "Trying To Mount By vers=4.1"
	mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/ganesha
	echo "Hello From v4.1_Mount" > /mnt/ganesha/testFile.txt
	cat /mnt/ganesha/testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE Since v4.1 Permissions Were Not Given To The CLient"
		#exit ret
	else
		echo "SUCCESS ON v4.1 MOUNT FAILURE"
	fi

	cd / && umount /mnt/ganesha

fi

if [ "$1" = "client_stage3" ]
then
	echo "In Client Stage 3 --- With Only Rights For v4.0 & v4.1 Mount To This Client "

	echo "Trying To Mount By vers=3"
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	echo "Hello From v3_Mount" > /mnt/ganesha/testFile.txt
	cat /mnt/ganesha/testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE Since v3 Permissions Were Not Given To The CLient"
		#exit ret
	else
		echo "SUCCESS ON v3 MOUNT FAILURE"
	fi

	cd / && umount /mnt/ganesha

	echo "Trying To Mount By vers=4.0"
	mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/ganesha
	echo "Hello From v4.0_Mount" > /mnt/ganesha/testFile.txt
	cat /mnt/ganesha/testFile.txt
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
	echo "Hello From v4.1_Mount" > /mnt/ganesha/testFile.txt
	cat /mnt/ganesha/testFile.txt
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



