export CENTOS_VERSION=7
export CENTOS_ARCH=x86_64
export GERRIT_HOST=${GERRIT_HOST}
export GERRIT_PROJECT=${GERRIT_PROJECT}
export GERRIT_REFSPEC=${GERRIT_REFSPEC}
export LAST_TRIGGERED_JOB_NAME=nfs_ganesha_code_compilation
export BUILD_NUMBER=${BUILD_NUMBER}

python $WORKSPACE/ci-tests/build_scripts/common/basic-gluster-duffy.py 
RET=$?

JOB_OUTPUT="${JENKINS_URL}/job/${LAST_TRIGGERED_JOB_NAME}/${BUILD_NUMBER}/console"

case ${RET} in
0)
	MESSAGE="${JOB_OUTPUT} : SUCCESS"
	VERIFIED='--verified +1'
	NOTIFY='--notify NONE'
	EXIT=0
	;;
1)
	MESSAGE="${JOB_OUTPUT} : FAILED"
	# TODO: Enable voting if tests are stable. Env parameter?
	#VERIFIED='--verified -1'
	VERIFIED=''
	NOTIFY='--notify ALL'
	EXIT=1
	;;
*)
	MESSAGE="${JOB_OUTPUT} : unknown return value ${RET}"
	VERIFIED=''
	NOTIFY='--notify NONE'
	EXIT=1
	;;
esac

# show the message on the console, it helps users looking the output
echo "${MESSAGE}"

# Update Gerrit with the success/failure status
if [ -n "${GERRIT_PATCHSET_REVISION}" ]
then
    ssh \
        -l jenkins-glusterorg \
        -i $GERRITHUB_KEY \
        -o StrictHostKeyChecking=no \
        -p ${GERRIT_PORT} \
        ${GERRIT_HOST} \
        gerrit review \
            --message "'${MESSAGE}'" \
            --project ${GERRIT_PROJECT} \
            ${VERIFIED} \
            ${NOTIFY} \
            ${GERRIT_PATCHSET_REVISION}
fi
