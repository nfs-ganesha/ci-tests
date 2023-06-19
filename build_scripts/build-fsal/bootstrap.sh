#!/bin/bash

echo "Hello from bootstrap.sh"

TEST_SCRIPT=${TEST_SCRIPT}

SERVER_IP=$(cat $WORKSPACE/hosts | sed -n '1p')

server_env="export CENTOS_VERSION='${CENTOS_VERSION}'"
server_env+=" CENTOS_ARCH='${CENTOS_ARCH}'"
server_env+=" GERRIT_HOST='${GERRIT_HOST}'"
server_env+=" GERRIT_PROJECT='${GERRIT_PROJECT}'"
server_env+=" GERRIT_REFSPEC='${GERRIT_REFSPEC}'"

echo $server_env > $WORKSPACE/SERVER_ENV.txt

scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "$WORKSPACE/SERVER_ENV.txt" "root@${SERVER_IP}:./SERVER_ENV.txt"

ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@${SERVER_IP} "tee -a ~/.bashrc < ./SERVER_ENV.txt"

scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "$TEST_SCRIPT" root@${SERVER_IP}:./build.sh

ssh -tt -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@${SERVER_IP} 'bash build.sh'
