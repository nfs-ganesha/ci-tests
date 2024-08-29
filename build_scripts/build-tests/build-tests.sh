#!/bin/sh

set -e

# these variables need to be set
[ -n "${GERRIT_HOST}" ]
[ -n "${GERRIT_PROJECT}" ]
[ -n "${GERRIT_REFSPEC}" ]

# only use https for now
GIT_REPO="https://${GERRIT_HOST}/${GERRIT_PROJECT}"

# enable the Storage SIG for lttng-{tools,ust}-devel
yum -y install centos-release-gluster yum-utils centos-release-ceph epel-release 

BASE_PACKAGES="git bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel rpm-build redhat-rpm-config libacl-devel libblkid-devel libcap-devel gperftools-devel gtest-devel rdma-core-devel"
BUILDREQUIRES_EXTRA="libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel  boost-devel doxygen xfsprogs-devel lttng-tools-devel lttng-ust-devel"

if [ "${CENTOS_VERSION}" = "7" ]; then
  yum -y install libgfapi-devel
  yum -y install ${BASE_PACKAGES} libnfsidmap-devel libwbclient-devel libcap-devel libblkid-devel userspace-rcu-devel userspace-rcu python2-devel
elif [ "${CENTOS_VERSION}" = "8s" ]; then
  yum install -y ${BASE_PACKAGES} libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build libgfapi-devel xfsprogs-devel
  yum install --enablerepo=powertools -y ${BUILDREQUIRES_EXTRA}
  yum -y install selinux-policy-devel sqlite libcephfs-devel
elif [ "${CENTOS_VERSION}" = "9s" ]; then
  yum install -y ${BASE_PACKAGES} libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build libgfapi-devel xfsprogs-devel
  yum install --enablerepo=crb -y ${BUILDREQUIRES_EXTRA}
  yum -y install selinux-policy-devel sqlite libcephfs-devel
fi

git clone --depth=1 ${GIT_REPO}
cd $(basename "${GERRIT_PROJECT}")
git fetch --depth=1 origin ${GERRIT_REFSPEC} && git checkout FETCH_HEAD

# update libntirpc
git submodule update --init || git submodule sync

# cleanup old build dir
[ -d build ] && rm -rf build

mkdir build
cd build

#( cmake ../src -DCMAKE_BUILD_TYPE=Maintainer -DUSE_GTEST=ON -DUSE_FSAL_GLUSTER=OFF -DUSE_FSAL_CEPH=OFF -DUSE_FSAL_RGW=OFF -DUSE_DBUS=ON -DUSE_ADMIN_TOOLS=OFF && make) || touch FAILED

cmake ../src -DCMAKE_BUILD_TYPE=Maintainer -DUSE_GTEST=ON -DUSE_FSAL_GLUSTER=OFF -DUSE_FSAL_CEPH=OFF -DUSE_FSAL_RGW=OFF -DUSE_DBUS=ON -DUSE_ADMIN_TOOLS=OFF && make
RET=$?

# we accept different return values
# 0 - SUCCESS + VOTE
# 1 - FAILED + VOTE
# 10 - SUCCESS + REPORT ONLY (NO VOTE)
# 11 - FAILED + REPORT ONLY (NO VOTE)

#RET=10
#if [ -e FAILED ]
#then
#	RET=$[RET + 1]
#fi

exit ${RET}
