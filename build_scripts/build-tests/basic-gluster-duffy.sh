#!/bin/bash

TEST_SCRIPT=${TEST_SCRIPT}

server_env="export GERRIT_HOST='${GERRIT_HOST}'"
server_env+=" GERRIT_PROJECT='${GERRIT_PROJECT}'"
server_env+=" GERRIT_REFSPEC='${GERRIT_REFSPEC}'"
server_env+=" CENTOS_VERSION='${CENTOS_VERSION}'"
server_env+=" CENTOS_ARCH='${CENTOS_ARCH}'"
server_env+=" YUM_REPO='${YUM_REPO}'"

SERVER_IP=$(cat $WORKSPACE/hosts | sed -n '1p')

echo $server_env > $WORKSPACE/SERVER_ENV.txt

SSH_OPTIONS="-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"

#add the export with environment to ~/.bashrc
scp ${SSH_OPTIONS} "$WORKSPACE/SERVER_ENV.txt" "root@${SERVER_IP}:./SERVER_ENV.txt"

ssh -t ${SSH_OPTIONS} root@${SERVER_IP} "tee -a ~/.bashrc < ./SERVER_ENV.txt"

scp ${SSH_OPTIONS} ${TEST_SCRIPT} root@${SERVER_IP}:./$(basename ${TEST_SCRIPT})

ssh -t ${SSH_OPTIONS} root@${SERVER_IP} "bash ./$(basename ${TEST_SCRIPT})"
RETURN_CODE=$?

if [ $RETURN_CODE != 0 ]; then
    echo "The SERVER script failed!"
    exit $RETURN_CODE
fi
