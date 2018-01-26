#!/bin/sh

set -e

# these variables need to be set
[ -n "${GERRIT_HOST}" ]
[ -n "${GERRIT_PROJECT}" ]
[ -n "${GERRIT_REFSPEC}" ]

# only use https for now
GIT_REPO="https://${GERRIT_HOST}/${GERRIT_PROJECT}"

SHAMAN_REPO_URL="https://shaman.ceph.com/api/repos/ceph/master/latest/centos/7/flavors/default/repo"
TIME_LIMIT=1200
INTERVAL=30
REPO_FOUND=0

# poll shaman for up to 10 minutes
while [ "$SECONDS" -le "$TIME_LIMIT" ]
do
  if `curl --fail -L $SHAMAN_REPO_URL > /etc/yum.repos.d/shaman.repo`; then
    echo "Ceph repo file has been added from shaman"
    REPO_FOUND=1
    break
  else
    sleep $INTERVAL
  fi
done

if [[ "$REPO_FOUND" -eq 0 ]]; then
  echo "Ceph lib repo does NOT exist in shaman"
  exit 1
fi

# basic packages to install
xargs yum -y install <<< "
git
bison
cmake
dbus-devel
flex
gcc-c++
git
krb5-devel
libacl-devel
libblkid-devel
libcap-devel
libnfsidmap-devel
libwbclient-devel
redhat-rpm-config
rpm-build
glusterfs-api-devel
libcephfs-devel
librgw-devel
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

( cmake -DCMAKE_BUILD_TYPE=Maintainer ../src && make rpm ) || touch FAILED

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
