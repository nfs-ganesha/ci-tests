#!/bin/sh

# if any command fails, the script should exit
set -e

# enable some more output
set -x

[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]
[ -n "${TEST_PARAMETERS}" ]

# install build and runtime dependencies
dnf -y install git gcc nfs-utils redhat-rpm-config krb5-devel python3-devel python3-gssapi python3-ply

rm -rf /root/pynfs && git clone git://git.linux-nfs.org/projects/cdmackay/pynfs.git

cd /root/pynfs && yes | python3 setup.py build > /tmp/output_tempfile.txt
echo $?

LOG_FILE40="/tmp/pynfs"$(date +%s)".log"
cd /root/pynfs/nfs4.0
COMMAND='./testserver.py ${SERVER}:${EXPORT} --verbose --maketree --showomit --rundeps all ganesha ${TEST_PARAMETERS} >> "${LOG_FILE40}"'
TARGET_USER="testuser"

# Create user if not exists
if id "$TARGET_USER" &>/dev/null; then
    echo "User $TARGET_USER already exists."
else
    echo "Creating user $TARGET_USER ..."
    useradd -m "$TARGET_USER"
fi

# Run the command as non-root user
echo "Running command as $TARGET_USER ..."
sudo -u "$TARGET_USER" bash -c "$COMMAND"
RETURN_CODE40=$?

echo "pynfs 4.0 test output:"
cat $LOG_FILE40

LOG_FILE41="/tmp/pynfs"$(date +%s)".log"
cd /root/pynfs/nfs4.1
COMMAND='./testserver.py ${SERVER}:${EXPORT} all ganesha --verbose --maketree --showomit --rundeps >> "${LOG_FILE41}"'

# Run the command as non-root user
echo "Running command as $TARGET_USER ..."
sudo -u "$TARGET_USER" bash -c "$COMMAND"
RETURN_CODE41=$?

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
