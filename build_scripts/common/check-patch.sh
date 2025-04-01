#!/bin/bash

# This script has the following workflow
#   1. Checkout the patch reference
#   2. Run clang format against the review.
#   3. Execute checkpatch

# It requires the following environment variables to be set
#   GERRIT_REFSPEC
#   GERRIT_PATCHSET_REVISION
#   GERRIT_PUBLISH
#   GERRITHUB_KEY
#   GERRIT_USER
#   JOB_URL

set -o pipefail 
set -x

# Avoid failures
GERRIT_PUBLISH=${GERRIT_PUBLISH:-'false'}
GERRIT_HOST=${GERRIT_HOST:-"review.gerrithub.io"}
GERRIT_PORT=${GERRIT_PORT:-"29418"}
GERRIT_PROJECT=${GERRIT_PROJECT:-"ffilz/nfs-ganesha"}

# Install the required pre-requisites
dnf -yq install git git-clang-format python3

if [[ -n "$GERRIT_REFSPEC" ]]; then
    GERRIT_PUBLISH=true
fi

# Checkout the patch
if [ ! -d nfs-ganesha ]; then
    git_project=$(basename "${GERRIT_PROJECT}")
    git_url="https://${GERRIT_HOST}/${GERRIT_PROJECT}"
    git init ${git_project}
    pushd ${git_project}
    git fetch --depth=2 "${git_url}" "${GERRIT_REFSPEC}"
    popd
fi

pushd nfs-ganesha
git checkout -b "${GERRIT_REFSPEC}" FETCH_HEAD
git clang-format -v \
    --diff \
    --style file:src/.clang-format \
    --extensions c,cc,cpp,h,hpp \
    HEAD~1
RETURN_VALUE=$?
popd

# Post message
case ${RETURN_VALUE} in
    0)
        MESSAGE="${JOB_URL}: Success."
        VERIFIED="--verified +1"
        NOTIFY="--notify NONE"
        EXIT=0
        ;;
    1)
        MESSAGE="${JOB_URL}: Failed"
        VERIFIED='--verified -1'
        NOTIFY="--notify all"
        EXIT=1
        ;;
    *)
        MESSAGE="${job_url}: UNKNOWN"
        VERIFIED=''
        NOTIFY="--notify NONE"
        EXIT=1
        ;;
esac

if [ "${GERRIT_PUBLISH}" == "true" ]; then
    ssh \
        -l ${GERRIT_USER} \
        -i ${GERRITHUB_KEY} \
        -o StrictHostKeyChecking=no \
        -p ${GERRIT_PORT} \
        ${GERRIT_HOST} \
        gerrit review \
            --message "'${MESSAGE}'" \
            --project ${GERRIT_PROJECT} \
            ${VERIFIED} \
            ${NOTIFY} \
            ${GERRIT_PATCHSET_REVISION}
else
    echo "Clang format review is not posted"
fi

publish_checkpatch() {
    local SSH_GERRIT="ssh -p 29418 -i $GERRITHUB_KEY $GERRIT_USER@review.gerrithub.io"

    if [[ "$GERRIT_PUBLISH" == "true" ]]; then
        tee /proc/$$/fd/1 | \
        $SSH_GERRIT "gerrit review --json --project ffilz/nfs-ganesha $GERRIT_PATCHSET_REVISION"
    else
        echo "Would have submit:"
        echo -n "echo '"
        cat
        echo "' | $SSH_GERRIT \"gerrit review --json --project ffilz/nfs-ganesha $GERRIT_PATCHSET_REVISION\""
  fi 
}

pushd nfs-ganesha/src/scripts
# cd to ~/checkpatch for checkpatch.pl as a hack to get config without modifying $HOME
GIT_DIR=~/nfs-ganesha/.git git show --format=email  | \
    ./checkpatch.pl -q - | \
    python3 ~/checkpatch-to-gerrit-json.py | \
    publish_checkpatch
popd
