#!/bin/sh
set -xe
[ -n "${SERVER}" ] || export SERVER=${SSH_CLIENT%% *}

#http://wiki.linux-nfs.org/wiki/index.php/NFStest#Installation

#nfstest does operations in the cwdir, which nfstest user needs rw access on.
cd /opt/client

#user mapping between linux and freebsd doesnt work with root/wheel, use nfstest user.
su nfstest -c "nfstest_posix --server "$SERVER" -e /nfs-test"
