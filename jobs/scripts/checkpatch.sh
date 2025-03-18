#!/bin/bash

# This script has the following workflow
#   1. Checkout the patch reference
#   2. Run clang format against the review.
#   3. Execute checkpatch
set -o pipefail 
set -x

if [[ -n "$GERRIT_REFSPEC" ]]; then
    GERRIT_REF="$GERRIT_REFSPEC"
    REVISION="$GERRIT_PATCHSET_REVISION"
    GERRIT_PUBLISH=true
fi

if [ ! -d nfs-ganesha ]; then
    GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -i $GERRITHUB_KEY" git \
        clone --depth=1 \
        -o gerrit \
        ssh://$GERRIT_USER@review.gerrithub.io:29418/ffilz/nfs-ganesha.git -v
fi

( cd nfs-ganesha && git fetch gerrit $GERRIT_REF && git checkout $REVISION )

job_url="${JENKINS_URL}/job/checkpatch/${BUILD_NUMBER}/console"

# Install git-clang-format
sudo dnf -qy git-clang-format

pushd nfs-ganesha
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
        MESSAGE="${job_url}: Success."
        VERIFIED="--verified +1"
        NOTIFY="--notify NONE"
        EXIT=0
        ;;
    1)
        MESSAGE="${job_url}: Failed"
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
        $SSH_GERRIT "gerrit review --json --project ffilz/nfs-ganesha $REVISION"
    else
        echo "Would have submit:"
        echo -n "echo '"
        cat
        echo "' | $SSH_GERRIT \"gerrit review --json --project ffilz/nfs-ganesha $REVISION\""
  fi 
}

# cd to ~/checkpatch for checkpatch.pl as a hack to get config without modifying $HOME
GIT_DIR=nfs-ganesha/.git git show --format=email  | \
    (cd $WORKSPACE/ci-tests/build_scripts/checkpatch && ./checkpatch.pl -q - || true ) | \
    python $WORKSPACE/ci-tests/build_scripts/checkpatch/checkpatch-to-gerrit-json.py    | \
    publish_checkpatch
