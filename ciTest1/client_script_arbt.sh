#!/bin/sh

# enable some more output
set -x
echo "+++++++++++++CLIENT SCRIPT AFTER REBOOTING++++++++++++++++++"

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

cat /mnt/nfs3/testFile.txt | grep "Hello World NFS3"

ret=$?

if [ $ret -eq 0 ]
then
	echo "=======||  Auto Remount Works Succesfully On v3 Mount ||======="
else
	echo "*******||  Auto Remount Failed on v3 Mount ||*******"
	exit $ret
fi

cd / && umount /mnt/nfs3


cat /mnt/nfs4/testFile.txt | grep "Hello World NFS4.0"

ret=$?

if [ $ret -eq 0 ]
then
	echo "=======||  Auto Remount Works Succesfully On v4.0 Mount ||======="
else
	echo "*******||  Auto Remount Failed on v4.0 Mount ||*******"
	exit $ret
fi

cd / && umount /mnt/nfs4
