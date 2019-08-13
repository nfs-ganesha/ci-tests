#!/bin/sh

set -e

# these variables need to be set
[ -n "${GERRIT_HOST}" ]
[ -n "${GERRIT_PROJECT}" ]
[ -n "${GERRIT_REFSPEC}" ]

# only use https for now
GIT_REPO="https://${GERRIT_HOST}/${GERRIT_PROJECT}"

# enable the Storage SIG for lttng-{tools,ust}-devel
yum -y install centos-release-nfs-ganesha28

# basic packages to install
xargs yum -y install <<< "
git
bison
cmake
dbus-devel
flex
gcc-c++
boost-devel
doxygen
redhat-lsb
git
krb5-devel
libacl-devel
libblkid-devel
libcap-devel
libnfsidmap-devel
libwbclient-devel
redhat-rpm-config
rpm-build
xfsprogs-devel
python2-devel
userspace-rcu-devel
lttng-tools-devel
lttng-ust-devel
gperftools-devel
gtest-devel
"

git clone ${GIT_REPO}
cd $(basename "${GERRIT_PROJECT}")
git fetch origin ${GERRIT_REFSPEC} && git checkout FETCH_HEAD

# update libntirpc
git submodule update --init || git submodule sync

# cleanup old build dir
[ -d build ] && rm -rf build

mkdir build
cd build

( cmake ../src -DCMAKE_BUILD_TYPE=Maintainer -DUSE_GTEST=ON -DUSE_FSAL_GLUSTER=OFF -DUSE_FSAL_CEPH=OFF -DUSE_FSAL_RGW=OFF -DUSE_DBUS=ON -DUSE_ADMIN_TOOLS=OFF && make) || touch FAILED

# we accept different return values
# 0 - SUCCESS + VOTE
# 1 - FAILED + VOTE
# 10 - SUCCESS + REPORT ONLY (NO VOTE)
# 11 - FAILED + REPORT ONLY (NO VOTE)

RET=10
if [ -e FAILED ]
then
	RET=$[RET + 1]
fi

exit ${RET}
