#!/bin/bash

SERVER_TEST_SCRIPT=${SERVER_TEST_SCRIPT}
CLIENT_TEST_SCRIPT=${CLIENT_TEST_SCRIPT}
GERRIT_HOST=${GERRIT_HOST}
GERRIT_PROJECT=${GERRIT_PROJECT}
GERRIT_REFSPEC=${GERRIT_REFSPEC}
CENTOS_VERSION=${CENTOS_VERSION}
CENTOS_ARCH=${CENTOS_ARCH}
GLUSTER_VOLUME=${EXPORT}

SERVER_IP=$(cat $WORKSPACE/hosts | sed -n '1p')
CLIENT_IP=$(cat $WORKSPACE/hosts | sed -n '2p')

SSH_OPTIONS="-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"

scp ${SSH_OPTIONS} ${SERVER_TEST_SCRIPT} root@${SERVER_IP}:./$(basename ${SERVER_TEST_SCRIPT})

ssh -t ${SSH_OPTIONS} root@${SERVER_IP} "GERRIT_HOST='${GERRIT_HOST}' GERRIT_PROJECT='${GERRIT_PROJECT}' GERRIT_REFSPEC='${GERRIT_REFSPEC}' CENTOS_VERSION='${CENTOS_VERSION}' GLUSTER_VOLUME='${EXPORT}' YUM_REPO='${YUM_REPO}' bash ./$(basename ${SERVER_TEST_SCRIPT})"

RETURN_CODE=$?

if [ $RETURN_CODE == 0 ]; then
    client_env="export SERVER='${SERVER_IP}'"
    client_env+=" EXPORT='/${EXPORT}'"
    client_env+=" CENTOS_VERSION='${CENTOS_VERSION}'"

    scp ${SSH_OPTIONS} /duffy-ssh-key/ssh-privatekey root@${CLIENT_IP}:./ssh-privatekey

    ssh -t ${SSH_OPTIONS} root@${CLIENT_IP} 'chmod 0600 ./ssh-privatekey'

    scp ${SSH_OPTIONS} ${CLIENT_TEST_SCRIPT} root@${CLIENT_IP}:./$(basename ${CLIENT_TEST_SCRIPT})

    set +x
    ssh -t ${SSH_OPTIONS} root@${CLIENT_IP} "SERVER='${SERVER_IP}' EXPORT='/${EXPORT}' CENTOS_VERSION='${CENTOS_VERSION}' bash ./$(basename ${CLIENT_TEST_SCRIPT})"
    RETURN_CODE_CLIENT=$?

    echo "Checking if the process had crashed!"
    CHECK_SERVER_PROCESS=$(ssh -t ${SSH_OPTIONS} root@${SERVER_IP} "ps ax | grep ganesha | grep -v grep")
    if [ -z "${CHECK_SERVER_PROCESS}" ]; then
        echo "No process was found"
    fi

    exit $RETURN_CODE_CLIENT
else
    echo "The SERVER script failed!"
    exit $RETURN_CODE
fi
