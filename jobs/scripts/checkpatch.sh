#!/bin/bash

# This script executes the linter scripts against the given patchset
set -o pipefail 
set -x

JOB_URL="${JENKINS_URL}/job/checkpatch/${BUILD_NUMBER}/console"
SSH_OPTIONS="-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
SERVER_IP=$(cat ${WORKSPACE}/hosts | sed -n '1p')

# Copy checkpatch-to-gerrit-json file and check-patch
scp ${SSH_OPTIONS} \
    ${WORKSPACE}/ci-tests/build_scripts/common/checkpatch-to-gerrit-json.py \
    root@${SERVER_IP}:checkpatch-to-gerrit-json.py
scp ${SSH_OPTIONS} ${WORKSPACE}/ci-tests/build_scripts/common/check-patch.sh \
    root@${SERVER_IP}:check-patch.sh
scp ${SSH_OPTIONS} ${GERRITHUB_KEY} root@${SERVER_IP}:gerrit-key
ssh -t ${SSH_OPTIONS} -l root ${SERVER_IP} 'chmod 0600 ~/gerrit-key'

# Execute check-patch on the reserved node
# Indentation is not applied on purpose due to use of double quotes
ssh -t ${SSH_OPTIONS} \
    -l root \
    ${SERVER_IP} \
    "GERRIT_HOST='${GERRIT_HOST}' \
GERRIT_PROJECT='${GERRIT_PROJECT}' \
GERRIT_REFSPEC='${GERRIT_REFSPEC}' \
GERRIT_PATCHSET_REVISION='${GERRIT_PATCHSET_REVISION}' \
GERRIT_PUBLISH='${GERRIT_PUBLISH}' \
GERRITHUB_KEY='/root/gerrit-key' \
GERRIT_USER='${GERRIT_USER}' \
JOB_URL='${JOB_URL}' \
bash -x check-patch.sh"
