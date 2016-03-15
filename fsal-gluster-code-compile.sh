#!/bin/sh
#
# Environment variables used:
#  - GERRIT_HOST
#  - GERRIT_PROJECT
#  - GERRIT_REFSPEC

set -e

GIT_REPO=$(basename "${GERRIT_PROJECT}")
GIT_URL="https://${GERRIT_HOST}/${GERRIT_PROJECT}"

# install NFS-Ganesha build dependencies
yum -y install git bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel libnfsidmap-devel libwbclient-devel libcap-devel libblkid-devel rpm-build redhat-rpm-config

# install the latest version of gluster
yum -y install centos-release-gluster
yum -y install glusterfs-api-devel

[ -d "${GIT_REPO}" ] && rm -rf "${GIT_REPO}"
git init "${GIT_REPO}"
pushd "${GIT_REPO}"

git fetch "${GIT_URL}" "${GERRIT_REFSPEC}"
git checkout -b "${GERRIT_REFSPEC}" FETCH_HEAD

# update libntirpc
git submodule update --init || git submodule sync

mkdir build
pushd build

cmake -DCMAKE_BUILD_TYPE=Maintainer ../src && make rpm
