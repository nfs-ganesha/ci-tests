#!/bin/sh

set -ex

# these variables need to be set
[ -n "${GERRIT_HOST}" ]
[ -n "${GERRIT_PROJECT}" ]
[ -n "${GERRIT_REFSPEC}" ]

# only use https for now
GIT_REPO="https://${GERRIT_HOST}/${GERRIT_PROJECT}"

# enable the Storage SIG Gluster and Ceph repositories
dnf -y install centos-release-gluster yum-utils centos-release-ceph epel-release

BUILDREQUIRES="git bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel rpm-build redhat-rpm-config libblkid-devel libcap-devel libgfapi-devel xfsprogs-devel"
BUILDREQUIRES_EXTRA="libnsl2-devel libnfsidmap-devel libwbclient-devel libcephfs-devel userspace-rcu-devel"

# basic packages to install
case "${CENTOS_VERSION}" in
    9s)
        dnf install -y ${BUILDREQUIRES}
        dnf install --enablerepo=crb -y ${BUILDREQUIRES_EXTRA}
    ;;
esac

git init $(basename "${GERRIT_PROJECT}")
cd $(basename "${GERRIT_PROJECT}")
git remote add origin ${GIT_REPO}
git fetch --depth=1 origin ${GERRIT_REFSPEC}
git checkout FETCH_HEAD

# update libntirpc
git submodule update --recursive --init || git submodule sync --recursive

# cleanup old build dir
[ -d build ] && rm -rf build

mkdir build
cd build

( cmake ../src -DCMAKE_BUILD_TYPE=Maintainer -DUSE_FSAL_VFS=ON -DUSE_FSAL_GLUSTER=OFF -DUSE_FSAL_CEPH=OFF -DUSE_FSAL_RGW=OFF -DUSE_FSAL_GPFS=OFF -DUSE_MONITORING=ON && make) || touch FAILED

# we accept different return values
# 0 - SUCCESS
# 1 - FAILED

if [ -e FAILED ]; then
    exit 1
else
    exit 0
fi
