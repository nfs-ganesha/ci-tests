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

POSIX_HOME="/root/ntfs-3g-pjd-fstest"
POSIX_TEST_REPO="https://github.com/ffilz/ntfs-3g-pjd-fstest.git"

#Install required packages for posix compliance test suite
echo "Install required packages for posix compliance test suite"
yum -y install git gcc nfs-utils redhat-rpm-config krb5-devel perl-Test-Harness libacl-devel bc cmake

#Cloning nfs ganesha specific posix compliance test suite
echo "Cloning nfs ganesha specific posix compliance test suite"
rm -rf ${POSIX_HOME} && git clone --depth=1 ${POSIX_TEST_REPO}

#Edit conf file to set fs="ganesha"
echo "Editing tests/conf file to set fs=\"ganesha\""
CONF_FILE="${POSIX_HOME}/tests/conf"
sed -i s/'fs=.*'/'fs=\"ganesha\"'/g ${CONF_FILE}

#Build posix compliance test suite
cd ${POSIX_HOME} && make >> /tmp/output_tempfile.txt

#Mount the export with nfsv3
echo "Mount the export ${EXPORT} with nfsv3"
MOUNT_POINT="/mnt/test_posix_mnt_nfsv3"
if [ ! -d ${MOUNT_POINT} ]; then
  rm -rf 
  mkdir -p ${MOUNT_POINT}
  mount -t nfs -o vers=3 ${SERVER}:${EXPORT} ${MOUNT_POINT}
fi

set +e
#Run posix compliance test suite for nfsv3
echo "Run posix compliance test suite for nfsv3"
LOG_FILE_NFSV3="/tmp/posix_nfsv3"$(date +%s)".log"
cd ${MOUNT_POINT} && prove -rf ${POSIX_HOME}/tests > ${LOG_FILE_NFSV3}
RETURN_CODE_NFSV3=$?

echo -e "posix compliance test output for nfsv3:\n---------------------------------------"
cat ${LOG_FILE_NFSV3}

#Mount the export with nfsv4
echo "Mount the export ${EXPORT} with nfsv4"
MOUNT_POINT="/mnt/test_posix_mnt_nfsv4"
if [ ! -d ${MOUNT_POINT} ]; then
  mkdir -p ${MOUNT_POINT}
  mount -t nfs -o vers=4 ${SERVER}:${EXPORT} ${MOUNT_POINT}
fi

#Run posix compliance test suite for nfsv4
echo "Run posix compliance test suite for nfsv4"
LOG_FILE_NFSV4="/tmp/posix_nfsv4"$(date +%s)".log"
cd ${MOUNT_POINT} && prove -rf ${POSIX_HOME}/tests > ${LOG_FILE_NFSV4}
RETURN_CODE_NFSV4=$?

echo -e "posix compliance test output for nfsv4:\n---------------------------------------"
cat ${LOG_FILE_NFSV4}

#Mount the export with nfsv4.1
echo "Mount the export ${EXPORT} with nfsv4.1"
MOUNT_POINT="/mnt/test_posix_mnt_nfsv41"
if [ ! -d ${MOUNT_POINT} ]; then
  mkdir -p ${MOUNT_POINT}
  mount -t nfs -o vers=4.1 ${SERVER}:${EXPORT} ${MOUNT_POINT}
fi

#Run posix compliance test suite for nfsv4.1
echo "Run posix compliance test suite for nfsv4.1"
LOG_FILE_NFSV41="/tmp/posix_nfsv41"$(date +%s)".log"
cd ${MOUNT_POINT} && prove -rf ${POSIX_HOME}/tests > ${LOG_FILE_NFSV41}
RETURN_CODE_NFSV41=$?

echo -e "posix compliance test output for nfsv4.1:\n---------------------------------------"
cat ${LOG_FILE_NFSV41}

echo -e "posix compliance test results for nfsv3, nfsv4, and nfsv4.1\n-------------------------------------------------"
if [ $RETURN_CODE_NFSV3 == 0 ]; then
  echo "All tests passed in posix compliance test suite for nfsv3"
else
  echo -e "posix compliance test suite failures on nfsv3:\n----------------------------------------------"
  cat ${LOG_FILE_NFSV3} | grep Failed
fi

if [ $RETURN_CODE_NFSV4 == 0 ]; then
  echo "All tests passed in posix compliance test suite for nfsv4"
else
  echo -e "posix compliance test suite failures on nfsv4:\n----------------------------------------------"
  cat ${LOG_FILE_NFSV4} | grep Failed
fi

if [ $RETURN_CODE_NFSV41 == 0 ]; then
  echo "All tests passed in posix compliance test suite for nfsv4.1"
else
  echo -e "posix compliance test suite failures on nfsv4.1:\n----------------------------------------------"
  cat ${LOG_FILE_NFSV41} | grep Failed
fi

if [ $RETURN_CODE_NFSV3 != 0 ] || [ $RETURN_CODE_NFSV4 != 0 ] || [ $RETURN_CODE_NFSV41 != 0 ]; then
  EXIT_CODE=1
else
  EXIT_CODE=0
fi

exit $EXIT_CODE
