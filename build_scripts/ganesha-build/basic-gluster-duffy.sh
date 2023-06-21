#!/bin/bash

TEST_SCRIPT=${TEST_SCRIPT}

CENTOS_VERSION=${CENTOS_VERSION}
CENTOS_ARCH=${CENTOS_ARCH}
TEMPLATES_URL=${TEMPLATES_URL}
TEMPLATES_FOLDER=$(basename ${TEMPLATES_URL})

SSH_OPTIONS="-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"

SERVER_IP=$(cat $WORKSPACE/hosts | sed -n '1p')

#Copy the private key to the Server and Give appropriate permission to the file
scp ${SSH_OPTIONS} /duffy-ssh-key/ssh-privatekey root@${SERVER_IP}:./ssh-private-key
ssh -t ${SSH_OPTIONS} root@${SERVER_IP} 'chmod 0600 ~/ssh-private-key'

#Copy the TEST_SCRIPT to the Server
scp ${SSH_OPTIONS} ${TEST_SCRIPT} root@${SERVER_IP}:./$(basename ${TEST_SCRIPT})

#Copy the template files
scp ${SSH_OPTIONS} -r ${TEMPLATES_URL} root@${SERVER_IP}:

#Execute the Script on the server
ssh -t ${SSH_OPTIONS} root@${SERVER_IP} "CENTOS_VERSION='${CENTOS_VERSION}' CENTOS_ARCH='${CENTOS_ARCH}' TEMPLATES_URL='/root/${TEMPLATES_FOLDER}' bash $(basename ${TEST_SCRIPT})"
RETURN_CODE=$?

exit $RETURN_CODE
