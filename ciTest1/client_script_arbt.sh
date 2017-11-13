#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

# enable some more output
# set -x
echo "+++++++++++++CLIENT SCRIPT AFTER REBOOTING++++++++++++++++++"

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

cat /mnt/ganesha/testFile.txt | grep "Hello World"

ret=$?

if [ $ret -eq 0 ]
then
	echo "=======||  Auto Remount Works Succesfully ||======="
else
	echo "*******||  Auto Remount Failed ||*******"
	exit $ret
fi


cd / && umount /mnt/ganesha
