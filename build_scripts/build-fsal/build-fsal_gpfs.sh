#!/bin/sh

set -e

# these variables need to be set
[ -n "${GERRIT_HOST}" ]
[ -n "${GERRIT_PROJECT}" ]
[ -n "${GERRIT_REFSPEC}" ]

# only use https for now
GIT_REPO="https://${GERRIT_HOST}/${GERRIT_PROJECT}"

# enable the Storage SIG Gluster and Ceph repositories
yum -y install centos-release-gluster

BUILDREQUIRES="git bison cmake dbus-devel flex gcc-c++ krb5-devel libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build libgfapi-devel xfsprogs-devel rdma-core-devel"

BUILDREQUIRES_EXTRA="libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel"

# basic packages to install
case "${CENTOS_VERSION}" in
    7)
        yum install -y ${BUILDREQUIRES} ${BUILDREQUIRES_EXTRA} python2-devel
    ;;
    8s)
        yum install -y ${BUILDREQUIRES}
        yum install --enablerepo=powertools -y ${BUILDREQUIRES_EXTRA}
    ;;
    9s)
        yum install -y ${BUILDREQUIRES}
        yum install --enablerepo=crb -y ${BUILDREQUIRES_EXTRA}
    ;;
esac

git clone --depth=1 ${GIT_REPO}
cd $(basename "${GERRIT_PROJECT}")
git fetch origin ${GERRIT_REFSPEC} && git checkout FETCH_HEAD

# update libntirpc
git submodule update --init || git submodule sync

# cleanup old build dir
[ -d build ] && rm -rf build

mkdir build
cd build

( cmake ../src -DCMAKE_BUILD_TYPE=Maintainer -DUSE_FSAL_GLUSTER=OFF -DUSE_FSAL_CEPH=OFF -DUSE_FSAL_RGW=OFF -DUSE_FSAL_GPFS=ON -DUSE_DBUS=ON -DUSE_ADMIN_TOOLS=ON && make) || touch FAILED

# dont vote if the subject of the last change includes the word "WIP"
if ( git log --oneline -1 | grep -q -i -w 'WIP' )
then
    echo "Change marked as WIP, not posting result to GerritHub."
    touch WIP
fi

# we accept different return values
# 0 - SUCCESS + VOTE
# 1 - FAILED + VOTE
# 10 - SUCCESS + REPORT ONLY (NO VOTE)
# 11 - FAILED + REPORT ONLY (NO VOTE)

RET=0
if [ -e FAILED ]
then
	RET=$[RET + 1]
fi
if [ -e WIP ]
then
	RET=$[RET + 10]
fi

exit ${RET}
