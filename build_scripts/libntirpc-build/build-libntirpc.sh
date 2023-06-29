#!/bin/bash

artifact()
{
    rm -rf ${RESULTDIR}/*.log
    [ -e ~/ssh-private-key ] || return 0
    scp -q -o StrictHostKeyChecking=no -i ~/ssh-private-key -r "${@}" nfs-ganesha@artifacts.ci.centos.org:/srv/artifacts/nfs-ganesha/
    #rsync -av --password-file ~/ssh-private-key --exclude='*.log' ${@} nfs-ganesha@artifacts.ci.centos.org::nfs-ganesha/
}


# if anything fails, we'll abort
set -e

set -x

# environment variables we rely on
[ -n "${TEMPLATES_URL}" ]
[ -n "${CENTOS_VERSION}" ]
[ -n "${CENTOS_ARCH}" ]

yum -y install yum-utils
yum -y install centos-release-gluster epel-release centos-release-ceph

BASE_PACKAGES="git bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel rpm-build redhat-rpm-config createrepo_c python3 cmake"
BUILDREQUIRES_EXTRA="libnsl2-devel libnfsidmap-devel libwbclient-devel libcephfs-devel userspace-rcu-devel"
if [ "${CENTOS_VERSION}" = "7" ]; then
  yum -y install libgfapi-devel mock
  yum -y install ${BASE_PACKAGES} libnfsidmap-devel libwbclient-devel libcap-devel libblkid-devel userspace-rcu-devel userspace-rcu
elif [ "${CENTOS_VERSION}" = "8s" ]; then
  yum install -y ${BASE_PACKAGES} libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build libgfapi-devel xfsprogs-devel python2-devel
  yum install --enablerepo=powertools -y ${BUILDREQUIRES_EXTRA} mock
  yum -y install selinux-policy-devel sqlite
elif [ "${CENTOS_VERSION}" = "9s" ]; then
  yum install -y ${BASE_PACKAGES} libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build libgfapi-devel xfsprogs-devel
  yum install --enablerepo=crb -y ${BUILDREQUIRES_EXTRA} mock
  yum -y install selinux-policy-devel sqlite
fi

# clone the repository
git clone --depth=1 https://github.com/nfs-ganesha/ntirpc.git
pushd ntirpc

# switch to the branch we want to build
# git checkout ${GIT_BRANCH}
# repo is configured to checkout latest devel branch, e.g. duplex-13

# generate a version based on branch.date.last-commit-hash
GIT_VERSION="$(git branch | sed 's/^\* //' | sed 's/-//')"
GIT_HASH="$(git log -1 --format=%h)"
VERSION="${GIT_VERSION}.$(date +%Y%m%d).${GIT_HASH}"

# generate the tar.gz archive
if [ "${CENTOS_VERSION}" == "7" ]; then
  sed s/XXVERSIONXX/${VERSION}/ ${TEMPLATES_URL}/libntirpc_centos7.spec.in > libntirpc.spec
else
  sed s/XXVERSIONXX/${VERSION}/ ${TEMPLATES_URL}/libntirpc.spec.in > libntirpc.spec
fi
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


case "${CENTOS_VERSION}" in
7)
  MOCK_CHROOT=epel-${CENTOS_VERSION}-${CENTOS_ARCH}
;;
8s)
  MOCK_CHROOT=centos-stream+epel-next-8-x86_64
;;
9s)
  MOCK_CHROOT=centos-stream+epel-next-9-x86_64
;;
esac

RESULTDIR="/srv/nightly/libntirpc/${GIT_VERSION}/${CENTOS_VERSION//s}/${CENTOS_ARCH}"
/usr/bin/mock \
    --root ${MOCK_CHROOT} \
    --resultdir ${RESULTDIR} \
    --rebuild ${SRPM}
RET=$?

pushd ${RESULTDIR}
createrepo_c .

# create the .repo file pointing to the just built+latest version
sed s/XXVERSIONXX/${GIT_VERSION}/ ${TEMPLATES_URL}/libntirpc.repo.in > ../../../libntirpc-${GIT_VERSION}.repo
ln -sf libntirpc-${GIT_VERSION}.repo ../../../libntirpc-latest.repo
popd

pushd /srv
artifact nightly
popd

exit ${RET}
