# Prepare a NFS-client for posix compliance testing
# - install needed tools and libs
# - checkout posix compliance from git
# - build posix compliance test suite
# - run the NFSv4.0 tests
#

import os
import subprocess
import time
import sys
import logging

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s')

#get the environment variables
server=os.getenv("SERVER")
export=os.getenv("EXPORT")

posix_home = "/root/ntfs-3g-pjd-fstest/"
posix_test_repo = "https://github.com/ffilz/ntfs-3g-pjd-fstest.git"

#Install required packages for posix compliance test suite
logging.info("Install required packages for posix compliance test suite")
cmd = "yum -y install git gcc nfs-utils redhat-rpm-config python-devel krb5-devel perl-Test-Harness libacl-devel bc"
logging.info("Executing cmd: %s" % cmd)
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    logging.error("Failed to install packages required to run posix compliance test suite")
    sys.exit(1)

#Cloning nfs ganesha specific posix compliance test suite
logging.info("Cloning nfs ganesha specific posix compliance test suite")
cmd = "rm -rf %s && git clone %s" % (posix_home, posix_test_repo)
logging.info("Executing cmd: %s" % cmd)
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    logging.error("Failed to clone posix compliance test suite")
    sys.exit(1)

#Edit conf file to set fs="ganesha"
logging.info("Editing tests/conf file to set fs=\"ganesha\"")
conf_file = "%s/tests/conf" % posix_home
cmd = "sed -i s/'fs=.*'/'fs=\"ganesha\"'/g %s" % conf_file
logging.info("Executing cmd: %s" % cmd)
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    logging.error("Failed to edit conf file to set fs=\"ganesha\"")
    sys.exit(1)

#Build posix compliance test suite
logging.info("Build posix compliance test suite")
cmd = "cd %s && make" % posix_home
logging.info("Executing cmd: %s" % cmd)
fh = open("/tmp/output_tempfile.txt","w")
p = subprocess.Popen(cmd, shell=True, stdout=fh, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code = p.returncode
fh.close()

if rtn_code != 0:
    logging.error("Building posix compliance test suite failed")
    sys.exit(1)

#Mount the export with nfsv3
logging.info("Mount the export %s with nfsv3" % export)
mountpoint = "/mnt/test_posix_mnt_nfsv3"
cmd = "[ -d %s ] || mkdir %s && mount -t nfs -o vers=3 %s:%s %s" % (mountpoint, mountpoint, server, export, mountpoint)
logging.info("Executing cmd: %s" % cmd)
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    logging.error("Failed to mount nfsv3 export %s:%s" % (server, export))
    sys.exit(1)

#Run posix compliance test suite for nfsv3
logging.info("Run posix compliance test suite for nfsv3")
log_file_nfsv3 = "/tmp/posix_nfsv3" + str(int(time.time())) + ".log"
cmd = "cd %s && prove -rf %s/tests > %s" % (mountpoint, posix_home, log_file_nfsv3)
logging.info("Executing cmd: %s" % cmd)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code_nfsv3 = p.returncode

logging.info("posix compliance test output for nfsv3:")
logging.info("---------------------------------------")
cmd = "cat %s" % log_file_nfsv3
logging.info("Executing cmd: %s" % cmd)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout_nfsv3, perr = p.communicate()
logging.info(pout_nfsv3)

#Mount the export with nfsv4
logging.info("Mount the export %s with nfsv4" % export)
mountpoint = "/mnt/test_posix_mnt_nfsv4"
cmd = "[ -d %s ] || mkdir %s && mount -t nfs -o vers=4 %s:%s %s" % (mountpoint, mountpoint, server, export, mountpoint)
logging.info("Executing cmd: %s" % cmd)
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    logging.error("Failed to mount nfsv4 export %s:%s" % (server, export))
    sys.exit(1)

#Run posix compliance test suite for nfsv4
logging.info("Run posix compliance test suite for nfsv4")
log_file_nfsv4 = "/tmp/posix_nfsv4" + str(int(time.time())) + ".log"
cmd = "cd %s && prove -rf %s/tests > %s" % (mountpoint, posix_home, log_file_nfsv4)
logging.info("Executing cmd: %s" % cmd)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code_nfsv4 = p.returncode

logging.info("posix compliance test output for nfsv4:")
logging.info("---------------------------------------")
cmd = "cat %s" % log_file_nfsv4
logging.info("Executing cmd: %s" % cmd)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout_nfsv4, perr = p.communicate()
logging.info(pout_nfsv4)

#Mount the export with nfsv4.1
logging.info("Mount the export %s with nfsv4.1" % export)
mountpoint = "/mnt/test_posix_mnt_nfsv41"
cmd = "[ -d %s ] || mkdir %s && mount -t nfs -o vers=4.1 %s:%s %s" % (mountpoint, mountpoint, server, export, mountpoint)
logging.info("Executing cmd: %s" % cmd)
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    logging.error("Failed to mount nfsv4.1 export %s:%s" % (server, export))
    sys.exit(1)

#Run posix compliance test suite for nfsv4
logging.info("Run posix compliance test suite for nfsv4.1")
log_file_nfsv41 = "/tmp/posix_nfsv41" + str(int(time.time())) + ".log"
cmd = "cd %s && prove -rf %s/tests > %s" % (mountpoint, posix_home, log_file_nfsv41)
logging.info("Executing cmd: %s" % cmd)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code_nfsv41 = p.returncode

logging.info("posix compliance test output for nfsv4.1:")
logging.info("---------------------------------------")
cmd = "cat %s" % log_file_nfsv41
logging.info("Executing cmd: %s" % cmd)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout_nfsv41, perr = p.communicate()
logging.info(pout_nfsv41)


logging.info("posix compliance test results for nfsv3, nfsv4, and nfsv4.1")
logging.info("-------------------------------------------------")
if rtn_code_nfsv3 == 0:
    logging.info("All tests passed in posix compliance test suite for nfsv3")
else:
    cmd = "cat %s | grep Failed" % log_file_nfsv3
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pout_nfsv3, perr = p.communicate()
    logging.info("posix compliance test suite failures on nfsv3:")
    logging.info("----------------------------------------------")
    logging.error(pout_nfsv3)

if rtn_code_nfsv4 == 0:
    logging.info("All tests passed in posix compliance test suite for nfsv4")
else:
    cmd = "cat %s | grep Failed" % log_file_nfsv4
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pout_nfsv4, perr = p.communicate()
    logging.info("posix compliance test suite failures on nfsv4:")
    logging.info("----------------------------------------------")
    logging.error(pout_nfsv4)

if rtn_code_nfsv41 == 0:
    logging.info("All tests passed in posix compliance test suite for nfsv4.1")
else:
    cmd = "cat %s | grep Failed" % log_file_nfsv41
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pout_nfsv41, perr = p.communicate()
    logging.info("posix compliance test suite failures on nfsv4.1:")
    logging.info("----------------------------------------------")
    logging.error(pout_nfsv41)

rtn_code = rtn_code_nfsv3 or rtn_code_nfsv4 or rtn_code_nfsv41
sys.exit(rtn_code)
