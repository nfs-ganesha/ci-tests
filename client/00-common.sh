#!/bin/sh
set -xe
export SERVER=${SSH_CLIENT%% *}
apt install nfs-common
mkdir -p /nfs-test
mount -o remount /nfs-test || mount -t nfs ${SERVER}:/nfs-test /nfs-test
umount /nfs-test
