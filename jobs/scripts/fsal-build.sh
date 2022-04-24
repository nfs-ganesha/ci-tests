# no need for verbose output
set +x

# do not immediately fail on an error
set +e

# run the bootstrap script
python $WORKSPACE/ci-tests/build_scripts/common/bootstrap.py
RET=$?

# we accept different return values
# 0 - SUCCESS + VOTE
# 1 - FAILED + VOTE
# 10 - SUCCESS + REPORT ONLY (NO VOTE)
# 11 - FAILED + REPORT ONLY (NO VOTE)

case ${RET} in
0)
	MESSAGE="${BUILD_URL}/console : SUCCESS"
	VERIFIED='--verified +1'
	NOTIFY='--notify NONE'
	EXIT=0
	;;
1)
	MESSAGE="${BUILD_URL}/console : FAILED"
	VERIFIED='--verified -1'
	NOTIFY='--notify ALL'
	EXIT=1
	;;
10)
	MESSAGE="${BUILD_URL}/console : SUCCESS (skipping vote)"
	VERIFIED=''
	NOTIFY='--notify NONE'
	EXIT=0
	;;
11)
	MESSAGE="${BUILD_URL}/console : FAILED (skipping vote)"
	VERIFIED=''
	NOTIFY='--notify NONE'
	EXIT=1
	;;
*)
	MESSAGE="${BUILD_URL}/console : unknown return value ${RET}"
	VERIFIED=''
	NOTIFY='--notify NONE'
	EXIT=1
	;;
esac

echo "${MESSAGE}"

# Update Gerrit with the success/failure status
if [ -n "${GERRIT_PATCHSET_REVISION}" ]
then
    ssh \
        -l jenkins-glusterorg \
        -i ~/.ssh/gerrithub@gluster.org \
        -o StrictHostKeyChecking=no \
        -p 29418 \
        ${GERRIT_HOST} \
        gerrit review \
            --message "'${MESSAGE}'" \
            --project ${GERRIT_PROJECT} \
            ${VERIFIED} \
            ${NOTIFY} \
            ${GERRIT_PATCHSET_REVISION}
fi

# exit with SUCCESS or FAIL only
exit ${EXIT}
