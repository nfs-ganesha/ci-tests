#!/bin/bash

SERVER_TEST_SCRIPT=${SERVER_TEST_SCRIPT}
CLIENT_TEST_SCRIPT=${CLIENT_TEST_SCRIPT}

server_env="export GERRIT_HOST='${GERRIT_HOST}'"
server_env+=" GERRIT_PROJECT='${GERRIT_PROJECT}'"
server_env+=" GERRIT_REFSPEC='${GERRIT_REFSPEC}'"
server_env+=" YUM_REPO='${YUM_REPO}'"

if [ $CENTOS_VERSION ]; then 
    server_env+=" CENTOS_VERSION='${CENTOS_VERSION}'"; 
fi

if [ "$JOB_NAME" == "nfs_ganesha_iozone_vfs" ] || [ "$JOB_NAME" == "nfs_ganesha_iozone_vfs_minmdcache" ]; then
    server_env+=" VFS_VOLUME='${EXPORT}'"
else
    server_env+=" GLUSTER_VOLUME='${EXPORT}'"
fi

SERVER_IP=$(cat $WORKSPACE/hosts | sed -n '1p')
CLIENT_IP=$(cat $WORKSPACE/hosts | sed -n '2p')

echo $server_env > $WORKSPACE/SERVER_ENV.txt
pwd
ls -ltr

#add the export with environment to ~/.bashrc
scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "$WORKSPACE/SERVER_ENV.txt" "root@${SERVER_IP}:./SERVER_ENV.txt"

ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@${SERVER_IP} "tee -a ~/.bashrc < ./SERVER_ENV.txt"

scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ${SERVER_TEST_SCRIPT} root@${SERVER_IP}:./$(basename ${SERVER_TEST_SCRIPT})

ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@${SERVER_IP} "ls -ltr"

ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@${SERVER_IP} "bash ./$(basename ${SERVER_TEST_SCRIPT})"
RETURN_CODE=$?

if [ $RETURN_CODE == 0 ]; then
    client_env="export SERVER='${SERVER_IP}'"
    client_env+=" EXPORT='${EXPORT}'"

    echo $client_env > $WORKSPACE/CLIENT_ENV.txt

    scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "$WORKSPACE/CLIENT_ENV.txt" "root@${CLIENT_IP}:./CLIENT_ENV.txt"

    ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@$CLIENT_IP 'tee -a ~/.bashrc < ./CLIENT_ENV.txt'

    scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ${CLIENT_TEST_SCRIPT} root@${CLIENT_IP}:./$(basename ${CLIENT_TEST_SCRIPT})

    ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@${CLIENT_IP} "bash ./$(basename ${CLIENT_TEST_SCRIPT})"
    RETURN_CODE_CLIENT=$?

fi

exit $RETURN_CODE_CLIENT
