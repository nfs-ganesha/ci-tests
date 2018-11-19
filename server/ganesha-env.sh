#!/bin/sh
pkg install nfs-ganesha-kmod cmake bison python27 devel/dbus
kldload fhlink fhreadlink getfhat setthreadgid setthreadgroups setthreaduid
#dbus script for ganesha
cd /usr/local/share/dbus-1/system.d/ && wget https://raw.githubusercontent.com/nfs-ganesha/nfs-ganesha/next/src/scripts/ganeshactl/org.ganesha.nfsd.conf
service dbus onestart
