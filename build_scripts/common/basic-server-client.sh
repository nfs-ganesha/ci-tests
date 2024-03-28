#!/bin/bash

function server_run()
{
  if [ "$JOB_NAME" == "iozone-vfs" ] || [ "$JOB_NAME" == "iozone-vfs-minmdcache" ]; then
    VOLUME_TYPE="VFS"
  elif [ "$JOB_NAME" == "storage-scale" ]; then
    VOLUME_TYPE="STORAGE_SCALE"
  else
    VOLUME_TYPE="GLUSTER"
  fi

  if [ "$JOB_NAME" == "pynfs-acl" ]; then
    INCLUDE_ACL_PARAM=" ENABLE_ACL='${ENABLE_ACL}'"
  fi

  scp ${SSH_OPTIONS} ${2} root@${1}:./$(basename ${2})

  if [ "$JOB_NAME" == "storage-scale" ]; then
    ssh -t ${SSH_OPTIONS} root@${1} "AWS_ACCESS_KEY='${AWS_ACCESS_KEY}' AWS_SECRET_KEY='${AWS_SECRET_KEY}' GERRIT_HOST='${GERRIT_HOST}' GERRIT_PROJECT='${GERRIT_PROJECT}' GERRIT_REFSPEC='${GERRIT_REFSPEC}' CENTOS_VERSION='${CENTOS_VERSION}' CENTOS_ARCH='${CENTOS_ARCH}' ${VOLUME_TYPE}_VOLUME='${EXPORT}' YUM_REPO='${YUM_REPO}' ${INCLUDE_TEMPLATE_URL} ${INCLUDE_ACL_PARAM} bash ./$(basename ${2})"
  else
    ssh -t ${SSH_OPTIONS} root@${1} "GERRIT_HOST='${GERRIT_HOST}' GERRIT_PROJECT='${GERRIT_PROJECT}' GERRIT_REFSPEC='${GERRIT_REFSPEC}' CENTOS_VERSION='${CENTOS_VERSION}' CENTOS_ARCH='${CENTOS_ARCH}' ${VOLUME_TYPE}_VOLUME='${EXPORT}' YUM_REPO='${YUM_REPO}' ${INCLUDE_TEMPLATE_URL} ${INCLUDE_ACL_PARAM} bash ./$(basename ${2})"
  fi

  #RETURN_CODE=$?

  #return $RETURN_CODE
}

function client_run()
{
  scp ${SSH_OPTIONS} ${2} root@${1}:./$(basename ${2})

  if [ "${JOB_NAME}" == "pynfs" ] || [ "${JOB_NAME}" == "pynfs-acl" ]; then
    INCLUDE_TEST_PARAMS="TEST_PARAMETERS='${TEST_PARAMETERS}'"
  fi

  if [ "$JOB_NAME" == "storage-scale" ]; then
    ssh -t ${SSH_OPTIONS} root@${1} "SERVER='${3}' EXPORT='/ibm/${EXPORT}' CENTOS_VERSION='${CENTOS_VERSION}' ${INCLUDE_TEST_PARAMS} bash ./$(basename ${2})"
    RETURN_CODE_CLIENT=$?
  else
    ssh -t ${SSH_OPTIONS} root@${1} "SERVER='${3}' EXPORT='/${EXPORT}' CENTOS_VERSION='${CENTOS_VERSION}' ${INCLUDE_TEST_PARAMS} bash ./$(basename ${2})"
    RETURN_CODE_CLIENT=$?
  fi

  return $RETURN_CODE_CLIENT
}

SSH_OPTIONS="-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
SERVER_IP=$(cat $WORKSPACE/hosts | sed -n '1p')

if [ "${TEST_SCRIPT}" ]; then
  if [ "${TEMPLATES_URL}" ]; then
    TEMPLATES_FOLDER=$(basename ${TEMPLATES_URL})
    #Copy the private key to the Server and Give appropriate permission to the file
    scp ${SSH_OPTIONS} /duffy-ssh-key/ssh-privatekey root@${SERVER_IP}:./ssh-private-key
    ssh -t ${SSH_OPTIONS} root@${SERVER_IP} 'chmod 0600 ~/ssh-private-key'
    scp ${SSH_OPTIONS} -r ${TEMPLATES_URL} root@${SERVER_IP}:
    INCLUDE_TEMPLATE_URL="TEMPLATES_URL='/root/${TEMPLATES_FOLDER}'"
  fi
  server_run ${SERVER_IP} ${TEST_SCRIPT}
  FINAL_RESULT=$?
elif [ "${SERVER_TEST_SCRIPT}" ] && [ "${CLIENT_TEST_SCRIPT}" ]; then
  CLIENT_IP=$(cat $WORKSPACE/hosts | sed -n '2p')
  server_run ${SERVER_IP} ${SERVER_TEST_SCRIPT}
  SERVER_SCRIPT_RESULT=$?
  echo "SERVER_SCRIPT_RESULT = $SERVER_SCRIPT_RESULT"
  if [ "${SERVER_SCRIPT_RESULT}" == "0" ]; then
    echo "Server script success!"
    client_run ${CLIENT_IP} ${CLIENT_TEST_SCRIPT} ${SERVER_IP}
    FINAL_RESULT=$?
    echo "Client script status = $FINAL_RESULT"
  else
    scp root@${SERVER_IP}:/root/rpmbuild/BUILD/nfs-ganesha-5.4/CMakeFiles/CMakeOutput.log $WORKSPACE
    scp root@${SERVER_IP}:/root/rpmbuild/BUILD/nfs-ganesha-5.4/CMakeFiles/CMakeError.log $WORKSPACE
    ls -ltr $WORKSPACE
    FINAL_RESULT=${SERVER_SCRIPT_RESULT}
  fi
fi

exit ${FINAL_RESULT}
