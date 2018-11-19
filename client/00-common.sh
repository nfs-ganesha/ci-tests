#!/bin/sh
set -xe
export SERVER=${SSH_CLIENT%% *}
apt install nfs-common
mkdir -p /nfs-test
umount /nfs-test || true
mount -t nfs ${SERVER}:/nfs-test /nfs-test
