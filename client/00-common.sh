#!/bin/sh
set -xe
[ -n "${SERVER}" ] || export SERVER=${SSH_CLIENT%% *}
apt install nfs-common
mkdir -p /nfs-test
mount -o remount /nfs-test || mount -t nfs -o vers=4.1 ${SERVER}:/nfs-test /nfs-test
umount /nfs-test
