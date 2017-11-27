#!/bin/bash

artifact()
{
	[ -e ~/rsync.passwd ] || return 0
	rsync -av --password-file ~/rsync.passwd ${@} nfs-ganesha@artifacts.ci.centos.org::nfs-ganesha/
}

# if anything fails, we'll abort
set -e

# environment variables we rely on
[ -n "${TEMPLATES_URL}" ]
[ -n "${CENTOS_VERSION}" ]
[ -n "${CENTOS_ARCH}" ]

# install basic dependencies for building the tarball and srpm
yum -y install git rpm-build mock createrepo_c

# clone the repository
git clone https://github.com/nfs-ganesha/ntirpc.git
pushd ntirpc

# switch to the branch we want to build
# git checkout ${GIT_BRANCH}
# repo is configured to checkout latest devel branch, e.g. duplex-13

# generate a version based on branch.date.last-commit-hash
GIT_VERSION="$(git branch | sed 's/^\* //' | sed 's/-//')"
GIT_HASH="$(git log -1 --format=%h)"
VERSION="${GIT_VERSION}.$(date +%Y%m%d).${GIT_HASH}"

# generate the tar.gz archive
curl ${TEMPLATES_URL}/libntirpc.spec.in | sed s/XXVERSIONXX/${VERSION}/ > libntirpc.spec
tar czf ../ntirpc-${VERSION}.tar.gz --exclude-vcs ../ntirpc
popd

# build the SRPM
rm -f *.src.rpm
SRPM=$(rpmbuild --define 'dist .autobuild' --define "_srcrpmdir ${PWD}" \
	--define '_source_payload w9.gzdio' \
	--define '_source_filedigest_algorithm 1' \
	-ts ntirpc-${VERSION}.tar.gz | cut -d' ' -f 2)

# do the actual RPM build in mock
# TODO: use a CentOS Storage SIG buildroot
RESULTDIR=/srv/nightly/libntirpc/${GIT_VERSION}/${CENTOS_VERSION}/${CENTOS_ARCH}
/usr/bin/mock \
	--root epel-${CENTOS_VERSION}-${CENTOS_ARCH} \
	--resultdir ${RESULTDIR} \
	--rebuild ${SRPM}

pushd ${RESULTDIR}
createrepo_c .

# create the .repo file pointing to the just built+latest version
curl ${TEMPLATES_URL}/libntirpc.repo.in | sed s/XXVERSIONXX/${GIT_VERSION}/ > ../../../libntirpc-${GIT_VERSION}.repo
ln -sf libntirpc-${GIT_VERSION}.repo ../../../libntirpc-latest.repo
popd

pushd /srv
artifact nightly
popd

exit ${RET}
