#!/bin/sh
#
# Prepare a NFS-client for pynfs testing
# - install needed tools and libs
# - checkout pynfs from git
# - build pynfs
# - run the NFSv4.0 tests
#

# bail out if there is an error
set -e

# enable some debugging
set -x

# variables we expect
[ -n "${SERVER}" ]
[ -n "${EXPORT}" ]

yum -y install git gcc nfs-utils redhat-rpm-config python-devel krb5-devel

#install pynfs test suite
git clone git://linux-nfs.org/~bfields/pynfs.git
cd pynfs
yes  | python setup.py build
cd nfs4.0
./testserver.py \
	${SERVER}:${EXPORT} \
	--verbose \
	--maketree \
	--showomit \
	--rundeps \
	all \
	ganesha \
	${TEST_PARAMETERS}

# implicit exit status from ./testserver.py
