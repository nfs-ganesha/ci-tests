#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

if [ "$1" = "initialization" ]
then
	echo "In Client Initialization Stage"
	# install build and runtime dependencies
	yum -y install nfs-utils time

	mkdir -p /mnt/ganesha

	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha

elif [ "$1" = "stage1" ]
then
	
	echo "In Client Stage 1 --- With All Rights To All Clients ( RO & RW ) "

	cd /mnt/ganesha

	echo "Hello World" > testFile.txt

	cat testFile.txt	

fi
