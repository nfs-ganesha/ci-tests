# no need for verbose output
set +x

# do not immediately fail on an error
set +e

# run the bootstrap script
bash $WORKSPACE/ci-tests/build_scripts/common/basic-server-client.sh
RET=$?

# we accept different return values
# 0 - SUCCESS + VOTE
# 1 - FAILED + VOTE
# 10 - SUCCESS + REPORT ONLY (NO VOTE)
# 11 - FAILED + REPORT ONLY (NO VOTE)

case ${RET} in
0)
	MESSAGE="**🟢 $JOB_NAME:** \`SUCCESS\` - ${BUILD_URL}/console"
	EXIT=0
	;;
1)
	MESSAGE="**🔴 $JOB_NAME:** \`FAILED\` - ${BUILD_URL}/console"
	EXIT=1
	;;
10)
	MESSAGE="**🟢 $JOB_NAME:** \`SUCCESS - WIP\` - ${BUILD_URL}/console"
	EXIT=0
	;;
11)
	MESSAGE="**🔴 $JOB_NAME:** \`FAILED - WIP\` - ${BUILD_URL}/console"
	EXIT=1
	;;
*)
	MESSAGE="**🔴 $JOB_NAME:** \`FAILED : unknown return value ${RET}\` - ${BUILD_URL}/console"
	EXIT=1
	;;
esac

echo "${MESSAGE}"
echo "${MESSAGE}" > result_message.txt

# exit with SUCCESS or FAIL only
exit ${EXIT}
