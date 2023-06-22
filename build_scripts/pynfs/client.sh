#!/bin/sh
#
# Environment variables used:
#  - SERVER: hostname or IP-address of the NFS-server
#  - EXPORT: NFS-export to test (should start with "/")

echo "Client Script"

# if any command fails, the script should exit
set -e

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]
[ -n "${TEST_PARAMETERS}" ]

# install build and runtime dependencies
yum -y install git gcc nfs-utils redhat-rpm-config krb5-devel python3

rm -rf /root/pynfs && git clone git://linux-nfs.org/~bfields/pynfs.git

cd /root/pynfs && yes | python3 setup.py build > /tmp/output_tempfile.txt
echo $?

set +e

LOG_FILE40="/tmp/pynfs"$(date +%s)".log"
cd /root/pynfs/nfs4.0
timeout --preserve-status -s SIGKILL 240s ./testserver.py ${SERVER}:${EXPORT} --verbose --maketree --showomit --rundeps all ganesha ${TEST_PARAMETERS} >> "${LOG_FILE40}" 
TIMED_OUT=$?
#Return code will be 124 if it ends the process by using SIGTERM for not getting any response. 137 when used SIGKILL to kill the process
if [ $TIMED_OUT == 137 ]; then
  echo -e "The process timed out after 4 minute!\nLooks like the Server process to see if it has crashed!"
  exit 1
fi
#cd /root/pynfs/nfs4.0 && ./testserver.py ${SERVER}:${EXPORT} --verbose --maketree --showomit --rundeps all ganesha ${TEST_PARAMETERS} >> "${LOG_FILE40}"
RETURN_CODE40=$?

echo "pynfs 4.0 test output:"
cat $LOG_FILE40

LOG_FILE41="/tmp/pynfs"$(date +%s)".log"
cd /root/pynfs/nfs4.1
timeout --preserve-status -s SIGKILL 240s ./testserver.py ${SERVER}:${EXPORT} all ganesha --verbose --maketree --showomit --rundeps >> "${LOG_FILE41}" 
TIMED_OUT=$?
#Return code will be 124 if it ends the process by using SIGTERM for not getting any response. 137 when used SIGKILL to kill the process
if [ $TIMED_OUT == 137 ]; then
  echo -e "The process timed out after 4 minute!\nLooks like the Server process to see if it has crashed!"
  exit 1
fi 
#cd /root/pynfs/nfs4.1 && ./testserver.py ${SERVER}:${EXPORT} all ganesha --verbose --maketree --showomit --rundeps >> "${LOG_FILE41}"
RETURN_CODE41=$?

set -e

echo "pynfs 4.1 test output:"
cat $LOG_FILE41

if [ $RETURN_CODE40 == 0 ]; then
    echo "All tests passed in pynfs 4.0 test suite"
fi

if [ $RETURN_CODE41 == 0 ]; then
    echo "All tests passed in pynfs 4.1 test suite"
fi

if [ $RETURN_CODE40 != 0 ] || [ $RETURN_CODE40 != 0 ]; then
    echo "pynfs 4.0 test suite failures:"
    echo "--------------------------"
    cat $LOG_FILE40 | grep FAILURE

    echo "pynfs 4.1 test suite failures:"
    echo "--------------------------"
    cat $LOG_FILE41 | grep FAILURE

    exit 1
fi

exit 0 
