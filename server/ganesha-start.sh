#!/bin/sh
set -xe
rpcbind 2>&- || true
pkill ganesha.nfsd || true
sleep 1
ganesha.nfsd -f /opt/server/ganesha.conf -L /var/log/ganesha.log
