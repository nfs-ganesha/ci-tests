#!/bin/sh
rpcbind 2>&-
pkill ganesha.nfsd
sleep 1
ganesha.nfsd -f ganesha.conf -L /var/log/ganesha.log
