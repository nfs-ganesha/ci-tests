#!/bin/bash
#
# Report the previous test result to Gerrit
#
# This should be a 2nd stage part of a multijob configuration in Jenkins. The
# result of the previous job is checked. Based upon the subject of the patch
# (contains the word "WIP" or not), voting is done.
#
# WARNING: Currently this script does never set Verified=-1. This is done to
# prevent incorrect negative voting. Change the part at the "TODO" for this.
#
# Environment variables used:
#  - GERRIT_HOST
#  - GERRIT_PORT
#  - GERRIT_PROJECT
#  - GERRIT_PATCHSET_REVISION: the git commit-id
#  - GERRIT_CHANGE_SUBJECT: subject of the patch (WIP?)
#  - LAST_TRIGGERED_JOB_NAME: like "nfs_ganesha_cthon04"
#  - TRIGGERED_BUILD_RESULT_${LAST_TRIGGERED_JOB_NAME}: SUCCESS/FAILURE
#  - TRIGGERED_BUILD_NUMBER_${LAST_TRIGGERED_JOB_NAME}: job number
#

# check the result of the previous job
RESULT_VAR="TRIGGERED_BUILD_RESULT_${LAST_TRIGGERED_JOB_NAME}"
RESULT="${!RESULT_VAR}"
case "${RESULT}" in
'SUCCESS')
	RET=0
	;;
'FAILURE')
	RET=1
	;;
*)
	RET=2
	;;
esac

# check if the patch subject contains the word "WIP"
if grep -q -i -w "WIP" <<< "${GERRIT_CHANGE_SUBJECT}"
then
	# add +10 for WIP patches
	RET=$[${RET} + 10]
fi

# the BUILD_URL is for this job, and not very useful in a review comment.
JOB_NUMBER_VAR="TRIGGERED_BUILD_NUMBER_${LAST_TRIGGERED_JOB_NAME}"
JOB_OUTPUT="${JENKINS_URL}/job/${LAST_TRIGGERED_JOB_NAME}/${!JOB_NUMBER_VAR}/console"

# we accept different return values
# 0 - SUCCESS + VOTE
# 1 - FAILED + VOTE
# 10 - SUCCESS + REPORT ONLY (NO VOTE)
# 11 - FAILED + REPORT ONLY (NO VOTE)

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
10)
	MESSAGE="${JOB_OUTPUT} : SUCCESS (WIP, skipping vote)"
	VERIFIED=''
	NOTIFY='--notify NONE'
	EXIT=0
	;;
11)
	MESSAGE="${JOB_OUTPUT} : FAILED (WIP, skipping vote)"
	VERIFIED=''
	NOTIFY='--notify NONE'
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
        -i ~/.ssh/gerrithub@gluster.org \
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

# mark the job as success/fail depending on the previous job
exit ${EXIT}
