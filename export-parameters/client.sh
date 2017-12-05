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

	echo "------------------------------------------------------------------------"
	echo "Client Initial Stage --- With All Rights To All Clients ( RO & RW ) "
	echo "------------------------------------------------------------------------"
	
	#mount
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	cd /mnt/ganesha
	echo "Trying To Write A File"
	echo "Hello World" > testFile.txt
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Write permissions denied"
		exit ret
	fi
	
	echo "Trying To Read A File"
	cat testFile.txt
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Read permissions denied"
		exit ret
	fi
	
	echo "Trying To Change File Ownership For Checking ROOT Rights"
	sudo chown root testFile.txt
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Failed on Root Rights"
		exit ret
	fi
	echo "SUCCESS: With all rights to all Clients ( RO & RW )"
	#unmount
	cd / && umount /mnt/ganesha
fi


if [ "$1" = "client_stage1" ]
then
	echo "------------------------------------------------------------------------"
	echo "Client Stage 1 --- With Only RO Rights To Clients "
	echo "------------------------------------------------------------------------"
	
	#mount
	mount -t nfs ${SERVER}:${EXPORT} /mnt/ganesha
	cd /mnt/ganesha
	echo "Trying To Write A File"
	sed -i '1s/$/ From RedHat/' testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: Write permissions were not blocked to the Client"
		exit ret
	fi

	echo "Trying To Read A File"
	cat testFile.txt
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Read permissions denied"
		exit ret
	fi
	echo "SUCCESS: With Only RO Rights To This Client"
	# unmount
	cd / && umount /mnt/ganesha
fi


if [ "$1" = "client_stage2" ]
then
	echo "------------------------------------------------------------------------"
	echo "Client Stage 2 --- With Only Rights For v3 Mount To Clients "
	echo "------------------------------------------------------------------------"

	echo "Trying To Mount By vers=3"
	#mount version 3 
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Mount v3 failed"
		exit ret
	else
		#unmount version 3 
		cd / && umount /mnt/ganesha
	fi

	echo "Trying To Mount By vers=4.0"
	#mount version 4.0
	mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: Mount v4.0 Permissions were not blocked to the Client"
		exit ret
	fi

	echo "Trying To Mount By vers=4.1"
	mount version 4.1
	mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: Mount v4.1 permissions were not blocked to the Client"
		exit ret
	fi
fi


if [ "$1" = "client_stage3" ]
then
	echo "----------------------------------------------------------------------------"
	echo "Client Stage 3 --- With Only Rights For v4.0 & v4.1 Mount To This Client "
	echo "----------------------------------------------------------------------------"

	echo "Trying To Mount By vers=3"
	#mount version 3
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: Mount v3 permissions were not blocked to the Client"
		exit ret
	fi

	echo "Trying To Mount By vers=4.0 using normal path and not the pseudo path"
	#mount version 4.0 using normal path
	mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: v4 Mount not using Pseudo Path"
		exit ret
	fi

	echo "Trying To Mount By vers=4.0"
	#mount version 4.0 using pseudo path
	mount -t nfs -o vers=4.0 ${SERVER}:/ppath /mnt/ganesha
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Mount v4.0 failed"
		exit ret
	else
		#unmount version 4.0
		cd / && umount /mnt/ganesha
	fi

	echo "Trying To Mount By vers=4.1"
	#mount version 4.1 using pseudo path
	mount -t nfs -o vers=4.1 ${SERVER}:/ppath /mnt/ganesha
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Mount v4.1 failed"
		exit ret
	else
		#unmount version 4.1
		cd / && umount /mnt/ganesha
	fi
fi


if [ "$1" = "client_stage4" ]
then
	echo "------------------------------------------------------------------------"
	echo "Client Stage 4 --- With Squashed Root Mount To Clients "
	echo "------------------------------------------------------------------------"
	
	#mount
	mount -t nfs ${SERVER}:${EXPORT} /mnt/ganesha

	echo "Trying To Change Ownership Of The File testFile.txt in the mount"
	sudo chown root /mnt/ganesha/testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: Root Permissions Were Not Given To The Client"
		exit ret
	else
		cd / && umount /mnt/ganesha
	fi
fi