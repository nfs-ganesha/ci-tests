#!/bin/bash

artifact()
{
	[ -e ~/rsync.passwd ] || return 0
	rsync -av --password-file ~/rsync.passwd ${@} nfs-ganesha@artifacts.ci.centos.org::nfs-ganesha/
}

# if anything fails, we'll abort
set -e

# be a little more verbose
set -x

# variables that we need
[ -n "${TEMPLATES_URL}" ]
[ -n "${CENTOS_VERSION}" ]
[ -n "${CENTOS_ARCH}" ]

# weĺl need yum-utils for yum-config-manager
yum -y install yum-utils

# enable the libntirpc repository (latest builds)
yum-config-manager --add-repo=http://artifacts.ci.centos.org/nfs-ganesha/nightly/libntirpc/libntirpc-latest.repo

# enable the glusterfs repository (latest released version)
yum -y install centos-release-gluster

# install basic dependencies for building the tarball and srpm
yum -y install git rpm-build gcc gcc-c++ mock createrepo_c

# clone the repository, github is faster than our Gerrit
#git clone https://review.gluster.org/glusterfs
# git clone https://github.com/gluster/glusterfs
git clone https://github.com/nfs-ganesha/nfs-ganesha.git
pushd nfs-ganesha

# switch to the branch we want to build
# git checkout ${GERRIT_BRANCH}
#
# repo is configured to checkout latest devel branch, i.e. "next"
# TODO: use (and make sure to export) GERRIT_BRANCH

# generate a version based on branch.date.last-commit-hash
GIT_VERSION="$(git branch | sed 's/^\* //')"
GIT_HASH="$(git log -1 --format=%h)"
VERSION="${GIT_VERSION}.$(date +%Y%m%d).${GIT_HASH}"

# generate the tar.gz archive
# TODO: uses a patched spec file, it would be better to use the one included in the git repo
curl ${TEMPLATES_URL}/nfs-ganesha.spec.in | sed s/XXVERSIONXX/${VERSION}/ > nfs-ganesha.spec
tar czf ../nfs-ganesha-${VERSION}.tar.gz --exclude-vcs ../nfs-ganesha
popd

# build the SRPM (TODO: run "cmake" and then "make srpm")
rm -f *.src.rpm
SRPM=$(rpmbuild --define 'dist .autobuild' --define "_srcrpmdir ${PWD}" \
	--define '_source_payload w9.gzdio' \
	--define '_source_filedigest_algorithm 1' \
	-ts nfs-ganesha-${VERSION}.tar.gz | cut -d' ' -f 2)

echo "SRPM: ${SRPM}"

# do the actual RPM build in mock
# TODO: use a CentOS Storage SIG buildroot
RESULTDIR=/srv/nfs-ganesha/nightly/${GIT_VERSION}/${CENTOS_VERSION}/${CENTOS_ARCH}
mkdir -p ${RESULTDIR}

# TODO: we should use mock, but we need additional repositories
#       the CentOS CI installs systems cleanly anyway, similar to a mock-chroot
#/usr/bin/mock \
#	--root epel-${CENTOS_VERSION}-${CENTOS_ARCH} \
#	--resultdir ${RESULTDIR} \
#	--enablerepo=http://artifacts.ci.centos.org/srv/gluster/nightly/master.repo \
#	--rebuild ${SRPM}

# install missing build dependencies
yum-builddep -y ${SRPM}
rpmbuild \
	--define "_srcrpmdir ${RESULTDIR}" \
	--define "_rpmdir ${RESULTDIR}" \
	--rebuild ${SRPM} \
	2>&1 | tee ${RESULTDIR}/build.log

# generate the local repository
pushd ${RESULTDIR}
createrepo_c .

# update/create a .repo file that can be used by yum
curl ${TEMPLATES_URL}/nfs-ganesha.repo.in | sed s/XXVERSIONXX/${GIT_VERSION}/ > ../../../nfs-ganesha-${GIT_VERSION}.repo
popd

# rsync the new repo and .repo file to to the public server
pushd /srv/nfs-ganesha
artifact nightly
popd

exit ${RET}
