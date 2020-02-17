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

# install build and runtime dependencies
yum -y install git gcc nfs-utils time

# v4.2 mount
mkdir -p /mnt/nfsv42
mount -t nfs -o vers=4.2 ${SERVER}:${EXPORT} /mnt/nfsv42

#create dir and file
mkdir /mnt/nfsv42/dir && touch /mnt/nfsv42/dir/file.txt

#change security context
cd /mnt/nfsv42/dir
flag=0

for i in u r t
do
	if [ $i == 'u' ]
	then
		chcon -$i system_u file.txt
	elif [ $i == 'r' ]
        then
                chcon -$i object_r file.txt
	else
		chcon -$i httpd_config_t file.txt
	fi

	ret=$?
	if [ $ret != 0 ]
	then
		$flag=1
		break
	fi
	restorecon -v file.txt
done

#check if test is successfull
if [ $flag -eq 0 ]
then
	echo "Success"
else
	echo "Fail"
fi
