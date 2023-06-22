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

Vers_List=" 3 4 4.1"
Operation_List=" create read chmod stat append rename delete-renamed mkdir rmdir "
var="/mnt/nfsv"

# install build and runtime dependencies
yum -y install git gcc nfs-utils time python3

# Cloning the small file test repo
git clone https://github.com/distributed-system-analysis/smallfile.git
cd smallfile


for i in $Vers_List
do
	mount_pt=$var$i
	mkdir -p $mount_pt
	mount -t nfs -o vers=$i ${SERVER}:${EXPORT} $mount_pt

	for j in $Operation_List
	do
          timeout -s SIGKILL 240s ./smallfile_cli.py --files 200 --threads 20 --file-size 64 --hash-into-dirs Y --top $mount_pt --operation $j 
          TIMED_OUT=$?
          if [ $TIMED_OUT == 137 ]; then
            echo -e "The process timed out after 4 minute!\nLooks like the Server process to see if it has crashed!"
            exit 1
          fi
          #./smallfile_cli.py --files 200 --threads 20 --file-size 64 --hash-into-dirs Y --top $mount_pt --operation $j
	done
done

