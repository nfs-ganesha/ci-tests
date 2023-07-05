#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

# if any command fails, the script should exit
set -e

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
	
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	cd /mnt/ganesha
	echo "Trying To Write A File"
	echo "Hello World" > testFile.txt
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Write permissions denied"
		exit $ret
	fi
	echo "Trying To Read A File"
	cat testFile.txt
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Read permissions denied"
		exit $ret
	fi
	echo "SUCCESS: With all rights to all Clients ( RO & RW )"
	#unmount
	cd / && umount -l /mnt/ganesha
fi

if [ "$1" = "client_stage1" ]
then
	echo "------------------------------------------------------------------------"
	echo "Client Stage 1 --- With Only RO Rights To This Client "
	echo "------------------------------------------------------------------------"

	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	cd /mnt/ganesha
	echo "Trying To Write A File"
	sed -i '1s/$/ From RedHat/' testFile.txt
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: Write permissions were not blocked to the Client"
		exit 1
	fi
	echo "Trying To Read A File"
	cat testFile.txt
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Read permissions denied"
		exit $ret
	fi
	echo "SUCCESS: With Only RO Rights To This Client"
	# unmount
	cd / && umount -l /mnt/ganesha
fi


if [ "$1" = "client_stage2" ]
then
	echo "------------------------------------------------------------------------"
	echo "Client Stage 2 --- With Only Rights For v3 Mount To This Client "
	echo "------------------------------------------------------------------------"

	echo "Trying To Mount By vers=3"
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Mount v3 failed"
		exit $ret
	else
		#unmount version 3 
		cd / && umount -l /mnt/ganesha
	fi
	
	echo "Trying To Mount By vers=4.0"
	mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: Mount v4.0 Permissions were not blocked to the Client"
		exit 1
	fi

	echo "Trying To Mount By vers=4.1"
	mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: Mount v4.1 permissions were not blocked to the Client"
		exit 1
	fi
fi

if [ "$1" = "client_stage3" ]
then
	echo "-----------------------------------------------------------------------------"
	echo "Client Stage 3 --- With Only Rights For v4.0 & v4.1 Mount To This Client "
	echo "-----------------------------------------------------------------------------"

	echo "Trying To Mount By vers=3"
	mount -t nfs -o vers=3 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -eq 0 ]
	then
		echo "FAILURE: Mount v3 permissions were not blocked to the Client"
		exit 1
	fi

	echo "Trying To Mount By vers=4.0"
	mount -t nfs -o vers=4.0 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Mount v4.0 failed"
		exit $ret
	else
		#unmount version 4.0
		cd / && umount -l /mnt/ganesha
	fi

	echo "Trying To Mount By vers=4.1"
	mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} /mnt/ganesha
	ret=$?
	if [ $ret -ne 0 ]
	then
		echo "FAILURE: Mount v4.1 failed"
		exit $ret
	else
		#unmount version 4.1
		cd / && umount -l /mnt/ganesha
	fi
fi

if [ "$1" = "client_stage4" ]
then
	echo "-----------------------------------------------------------------------------"
	echo "Client Stage 4 --- With Squashed Root Mount To This Client "
	echo "-----------------------------------------------------------------------------"

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
		echo "FAILURE: ROOT permissions were not blocked the Client"
		exit 1
	fi
fi
