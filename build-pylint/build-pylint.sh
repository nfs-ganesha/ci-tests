#!/bin/sh

set -e

# these variables need to be set
[ -n "${GERRIT_HOST}" ]
[ -n "${GERRIT_PROJECT}" ]
[ -n "${GERRIT_REFSPEC}" ]

# only use https for now
GIT_REPO="https://${GERRIT_HOST}/${GERRIT_PROJECT}"

# enable the Storage SIG for pylint
yum -y install centos-release-nfs-ganesha28

# basic packages to install
xargs yum -y install <<< "
git
pylint
"

git clone ${GIT_REPO}
cd $(basename "${GERRIT_PROJECT}")
git fetch origin ${GERRIT_REFSPEC} && git checkout FETCH_HEAD

pushd src/scripts/ganeshactl

for p in *.py */*.py */*/*.py
do
    pylint $p
done

popd

# we accept different return values
# 0 - SUCCESS + VOTE
# 1 - FAILED + VOTE
# 10 - SUCCESS + REPORT ONLY (NO VOTE)
# 11 - FAILED + REPORT ONLY (NO VOTE)

exit 10
