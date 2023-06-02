#!/bin/bash

SERVER_TEST_SCRIPT=${SERVER_TEST_SCRIPT}
CLIENT_TEST_SCRIPT=${CLIENT_TEST_SCRIPT}

server_env="export GERRIT_HOST='${GERRIT_HOST}'"
server_env+=" GERRIT_PROJECT='${GERRIT_PROJECT}'"
server_env+=" GERRIT_REFSPEC='${GERRIT_REFSPEC}'"
server_env+=" GLUSTER_VOLUME='${EXPORT}'"
server_env+=" YUM_REPO='${YUM_REPO}'"

if [ $CENTOS_VERSION ]; then 
    server_env+=" CENTOS_VERSION='${CENTOS_VERSION}'"; 
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

RETURN_CODE=$(ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@${SERVER_IP} "bash ./$(basename ${SERVER_TEST_SCRIPT})")
echo $RETURN_CODE

if [ $RETURN_CODE == 0 ]; then
    client_env="export SERVER='$SERVER_IP'"
    client_env+=" EXPORT='/$EXPORT'"

    echo $client_env > CLIENT_ENV.txt

    ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@$CLIENT_IP 'tee -a ~/.bashrc < ./CLIENT_ENV.txt'

    FILE_ENDS_WITH=$(echo $CLIENT_TEST_SCRIPT | cut -d "." -f2)
    echo $FILE_ENDS_WITH
    
    if [ $FILE_ENDS_WITH == "py" ]; then
        interpreter_to_run="python"
    elif [ $FILE_ENDS_WITH == "sh" ]; then
        interpreter_to_run="bash"
    fi

    scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ${CLIENT_TEST_SCRIPT} root@${CLIENT_IP}:./$(basename ${CLIENT_TEST_SCRIPT})

    RETURN_CODE_CLIENT=$(ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@${CLIENT_IP} "$interpreter_to_run ./$(basename ${CLIENT_TEST_SCRIPT})")

fi

exit $RETURN_CODE_CLIENT
