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
	if [ $? -eq 0 ]
	then
		echo "SUCCESS"
	else
		echo "FAILED ON WRITING RIGHTS"
		#exit ret
	fi

	echo "Trying To Read A File"
	cat testFile.txt
	ret=$?
	if [ $? -eq 0 ]
	then
		echo "SUCCESS"
	else
		echo "FAILED ON READING RIGHTS"
		#exit ret
	fi
fi

if [ "$1" = "client_stage1" ]
then
	echo "In Client Stage 1 --- With Only RO Rights To This Client "

	echo "Trying To Write A File"
	echo " From RedHat" >> testFile.txt
	ret=$?
	if [ $? -eq 0 ]
	then
		echo "FAILURE Since Write Permissions Were Not Blocked To The CLient"
		#exit ret
	else
		echo "SUCCESS ON FAILURE"
	fi

	echo "Trying To Read A File"
	cat testFile.txt
	ret=$?
	if [ $? -eq 0 ]
	then
		echo "SUCCESS"
	else
		echo "FAILED ON READING RIGHTS"
		#exit ret
	fi

fi
