# no need for verbose output
set +x

# do not immediately fail on an error
set +e

export CENTOS_VERSION=${CENTOS_VERSION}
export CENTOS_ARCH=${CENTOS_ARCH}
export GERRIT_HOST=${GERRIT_HOST}
export GERRIT_PROJECT=${GERRIT_PROJECT}
export GERRIT_REFSPEC=${GERRIT_REFSPEC}
export LAST_TRIGGERED_JOB_NAME=$JOB_NAME
export BUILD_NUMBER=${BUILD_NUMBER}

if [ "$JOB_NAME" == "storage-scale" ]; then
  export AWS_ACCESS_KEY=${ACCESS_KEY}
  export AWS_SECRET_KEY=${SECRET_KEY}
fi

bash $WORKSPACE/ci-tests/build_scripts/common/basic-server-client.sh
RET=$?

case ${RET} in
0)
	MESSAGE="**🟢 $TEST_NAME:** \`Passed\`"
	EXIT=0
	;;
1)
	MESSAGE="**🔴 $TEST_NAME:** \`Failed\`"
	EXIT=1
	;;
*)
	MESSAGE="**🔴 $TEST_NAME:** \`unknown return value\` ${RET}"
	EXIT=1
	;;
esac

# Append failures.txt content if it exists and is non-empty
FAILURE_LOG=$WORKSPACE/failures.txt
if [[ -s "$FAILURE_LOG" ]]; then
    MESSAGE+="\n\`\`\`\n$(cat "$FAILURE_LOG")\n\`\`\`"
fi

# show the message on the console, it helps users looking the output
echo -e "${MESSAGE}"

echo -e "${MESSAGE}" >> result_message.txt

exit ${EXIT}
