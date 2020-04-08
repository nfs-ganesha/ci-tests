# Prepare a NFS-client for pynfs testing
# - install needed tools and libs
# - checkout pynfs from git
# - build pynfs
# - run the NFSv4.0 tests
#

import os
import subprocess
import time
import sys

#get the environment variables
server=os.getenv("SERVER")
export=os.getenv("EXPORT")
test_parameters=os.getenv("TEST_PARAMETERS")

#Install required packages for pynfs test suite
cmd = "yum -y install git gcc nfs-utils redhat-rpm-config python-devel krb5-devel"
subprocess.call(cmd, shell=True)

#install pynfs test suite
print "cloning pynfs.git"
cmd = "rm -rf /root/pynfs && git clone git://linux-nfs.org/~bfields/pynfs.git"
subprocess.call(cmd, shell=True)

#Build pynfs
print "building pynfs"
cmd = "cd /root/pynfs && yes | python setup.py build"
fh = open("/tmp/output_tempfile.txt","w")
p = subprocess.Popen(cmd, shell=True, stdout=fh, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code = p.returncode
fh.close()

if rtn_code != 0:
    print "Building pynfs test suite failed"
    sys.exit(1)

#Run pynfs test suite
print "running pynfs 4.0"
log_file40 = "/tmp/pynfs" + str(int(time.time())) + ".log"
cmd = "cd /root/pynfs/nfs4.0 && ./testserver.py %s:%s --verbose --maketree --showomit --rundeps all ganesha %s > %s" %(server, export, test_parameters, log_file40)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code40 = p.returncode

print "pynfs 4.0 test output:"
print "------------------"
cmd = "cat %s" % log_file40
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout, perr = p.communicate()
print pout

print "running pynfs 4.1"
log_file41 = "/tmp/pynfs" + str(int(time.time())) + ".log"
cmd = "cd /root/pynfs/nfs4.0 && ./testserver.py %s:%s --verbose --maketree --showomit --rundeps all ganesha %s > %s" %(server, export, test_parameters, log_file41)
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout, perr = p.communicate()
rtn_code41 = p.returncode

print "pynfs 4.1 test output:"
print "------------------"
cmd = "cat %s" % log_file41
p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pout, perr = p.communicate()
print pout

if rtn_code40 == 0:
    print "All tests passed in pynfs 4.0 test suite"

if rtn_code41 == 0:
    print "All tests passed in pynfs 4.1 test suite"

if rtn_code40 != 0 or rtn_code41 != 0:
    cmd = "cat %s | grep FAILURE" % log_file
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pout, perr = p.communicate()
    print "pynfs test suite failures:"
    print "--------------------------"
    print pout
    sys.exit(1)

sys.exit(0)

