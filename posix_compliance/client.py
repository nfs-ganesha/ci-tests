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

#get the environment variables
server=os.getenv("SERVER")
export=os.getenv("EXPORT")

posix_home = "/root/ntfs-3g-pjd-fstest/"
posix_test_repo = "https://github.com/ffilz/ntfs-3g-pjd-fstest.git"

#Install required packages for posix compliance test suite
cmd = "yum -y install git gcc nfs-utils redhat-rpm-config python-devel krb5-devel perl-Test-Harness libacl-devel"
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    print "Failed to install packages required to run posix compliance test suite"
    sys.exit(1)

#Cloning nfs ganesha specific posix compliance test suite
cmd = "rm -rf %s && git clone %s" % (posix_home, posix_test_repo)
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    print "Failed to clone posix compliance test suite"
    sys.exit(1)

#Edit conf file to set fs="ganesha"
conf_file = "%s/tests/conf" % posix_home
cmd = "sed -i s/'fs=.*'/'fs=\"ganesha\"'/g %s" % conf_file
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    print "Failed to edit conf file to set fs=\"ganesha\""
    sys.exit(1)

#Build posix compliance test suite
cmd = "cd %s && make" % posix_home
fh = open("/tmp/output_tempfile.txt","w")
p = subprocess.Popen(cmd, shell=True, stdout=fh, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code = p.returncode
fh.close()

if rtn_code != 0:
    print "Building posix compliance test suite failed"
    sys.exit(1)

#Mount the export with nfsv3
mountpoint = "/mnt/test_posix_mnt_nfsv3"
cmd = "[ -d %s ] || mkdir %s && mount -t nfs -o vers=3 %s:%s %s" % (mountpoint, mountpoint, server, export, mountpoint)
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    print "Failed to mount nfsv3 export %s:%s" % (server, export)
    sys.exit(1)

#Run posix compliance test suite for nfsv3
log_file_nfsv3 = "/tmp/posix_nfsv3" + str(int(time.time())) + ".log"
cmd = "cd %s && prove -rf %s/tests > %s" % (mountpoint, posix_home, log_file_nfsv3)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code_nfsv3 = p.returncode

print "posix compliance test output for nfsv3:"
print "---------------------------------------"
cmd = "cat %s" % log_file_nfsv3
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout_nfsv3, perr = p.communicate()
print pout_nfsv3

#Mount the export with nfsv4
mountpoint = "/mnt/test_posix_mnt_nfsv4"
cmd = "[ -d %s ] || mkdir %s && mount -t nfs -o vers=4 %s:%s %s" % (mountpoint, mountpoint, server, export, mountpoint)
rtn_code = subprocess.call(cmd, shell=True)
if rtn_code != 0:
    print "Failed to mount nfsv4 export %s:%s" % (server, export)
    sys.exit(1)

#Run posix compliance test suite for nfsv4
log_file_nfsv4 = "/tmp/posix_nfsv4" + str(int(time.time())) + ".log"
cmd = "cd %s && prove -rf %s/tests > %s" % (mountpoint, posix_home, log_file_nfsv4)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code_nfsv4 = p.returncode

print "posix compliance test output for nfsv4:"
print "---------------------------------------"
cmd = "cat %s" % log_file_nfsv4
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout_nfsv4, perr = p.communicate()
print pout_nfsv4


print "posix compliance test results for nfsv3 and nfsv4"
print "-------------------------------------------------"
if rtn_code_nfsv3 == 0:
    print "All tests passed in posix compliance test suite for nfsv3"
else:
    cmd = "cat %s | grep Failed" % log_file_nfsv3
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pout_nfsv3, perr = p.communicate()
    print "posix compliance test suite failures on nfsv3:"
    print "----------------------------------------------"
    print pout_nfsv3

if rtn_code_nfsv4 == 0:
    print "All tests passed in posix compliance test suite for nfsv4"
else:
    cmd = "cat %s | grep Failed" % log_file_nfsv4
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pout_nfsv4, perr = p.communicate()
    print "posix compliance test suite failures on nfsv4:"
    print "----------------------------------------------"
    print pout_nfsv4


rtn_code = rtn_code_nfsv3 or rtn_code_nfsv4
sys.exit(rtn_code)
