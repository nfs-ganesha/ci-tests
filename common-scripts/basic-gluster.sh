#!/bin/sh
#
# Setup a simple gluster environment and export a volume through NFS-Ganesha.
#
# This script uses the following environment variables:
# - GLUSTER_VOLUME: name of the gluster volume to create
#                   this name will also be used as name for the export
#
# The YUM_REPO and GERRIT_* variables are mutually exclusive.
#
# - YUM_REPO: URL to the yum repository (.repo file) for the NFS-Ganesha
#             packages. When this option is used, libntirpc-latest is enabled
#             as well. Leave empty in case patches from Gerrit need testing.
#
# - GERRIT_HOST: when triggered from a new patch submission, this is set to the
#                git server that contains the repository to use.
#
# - GERRIT_PROJECT: project that triggered the build (like ffilz/nfs-ganesha).
#
# - GERRIT_REFSPEC: git tree-ish that can be fetched and checked-out for testing.


# abort if anything fails
set -e

[ -n "${GLUSTER_VOLUME}" ]

# be a little bit more verbose
set -x

# enable repositories
yum -y install centos-release-gluster yum-utils

# make sure rpcbind is running
yum -y install rpcbind
systemctl start rpcbind

# CentOS 7.4.1708 has an SELinux issue that prevents NFS-Ganesha from creating
# the /var/log/ganesha/ganesha.log file. Starting ganesha.nfsd fails due to
# this.
echo 'TODO: this is BAD, needs a fix in the selinux-policy'
setenforce 0

if [ -n "${YUM_REPO}" ]
then
	yum-config-manager --add-repo=http://artifacts.ci.centos.org/nfs-ganesha/nightly/libntirpc/libntirpc-latest.repo
	yum-config-manager --add-repo=${YUM_REPO}

	# install the latest version of gluster
	yum -y install nfs-ganesha nfs-ganesha-gluster glusterfs-ganesha

	# start nfs-ganesha service
	if ! systemctl start nfs-ganesha
	then
		echo "+++ systemctl status nfs-ganesha.service +++"
		systemctl status nfs-ganesha.service
		echo "+++ journalctl -xe +++"
		journalctl -xe
		exit 1
	fi
else
	[ -n "${GERRIT_HOST}" ]
	[ -n "${GERRIT_PROJECT}" ]
	[ -n "${GERRIT_REFSPEC}" ]

	GIT_REPO=$(basename "${GERRIT_PROJECT}")
	GIT_URL="https://${GERRIT_HOST}/${GERRIT_PROJECT}"

	# install NFS-Ganesha build dependencies
	yum -y --enablerepo=centos-gluster*-test install glusterfs-api-devel
	yum -y install git bison flex cmake gcc-c++ libacl-devel krb5-devel \
		dbus-devel libnfsidmap-devel libwbclient-devel libcap-devel \
		libblkid-devel rpm-build redhat-rpm-config

	git init "${GIT_REPO}"
	pushd "${GIT_REPO}"

	git fetch "${GIT_URL}" "${GERRIT_REFSPEC}"
	git checkout -b "${GERRIT_REFSPEC}" FETCH_HEAD

	# update libntirpc
	git submodule update --init || git submodule sync

	mkdir build
	pushd build

	cmake -DCMAKE_BUILD_TYPE=Maintainer -DBUILD_CONFIG=everything ../src
	make dist
	rpmbuild -ta --define "_srcrpmdir $PWD" --define "_rpmdir $PWD" *.tar.gz
	rpm_arch=$(rpm -E '%{_arch}')
	ganesha_version=$(rpm -q --qf '%{VERSION}-%{RELEASE}' -p *.src.rpm)
	if [ -e ${rpm_arch}/libntirpc-devel*.rpm ]; then
		ntirpc_version=$(rpm -q --qf '%{VERSION}-%{RELEASE}' -p ${rpm_arch}/libntirpc-devel*.rpm)
		ntirpc_rpm=${rpm_arch}/libntirpc-${ntirpc_version}.${rpm_arch}.rpm
	fi
	yum -y install ${ntirpc_rpm} ${rpm_arch}/nfs-ganesha-{,gluster-}${ganesha_version}.${rpm_arch}.rpm

	# start nfs-ganesha service with an empty configuration
	> /etc/ganesha/ganesha.conf
	if ! systemctl start nfs-ganesha
	then
		echo "+++ systemctl status nfs-ganesha.service +++"
		systemctl status nfs-ganesha.service
		echo "+++ journalctl -xe +++"
		journalctl -xe
		exit 1
	fi
fi

# create and start gluster volume
yum -y install glusterfs-server
systemctl start glusterd
mkdir -p /bricks/${GLUSTER_VOLUME}
gluster volume create ${GLUSTER_VOLUME} \
	replica 2 \
	$(hostname --fqdn):/bricks/${GLUSTER_VOLUME}/b{1,2} force

gluster volume start ${GLUSTER_VOLUME} force

#disable gluster-nfs
#gluster v set vol1 nfs.disable on
#sleep 2

#enable cache invalidation
#gluster v set vol1 cache-invalidation on

# TODO: open only the ports needed?
# disable the firewall, otherwise the client can not connect
systemctl stop firewalld || service iptables stop

# TODO: SELinux prevents creating special files on Gluster bricks (bz#1331561)
setenforce 0

# Export the volume
mkdir -p /usr/libexec/ganesha
cd /usr/libexec/ganesha
yum -y install wget
wget https://raw.githubusercontent.com/gluster/glusterfs/release-3.10/extras/ganesha/scripts/create-export-ganesha.sh
wget https://raw.githubusercontent.com/gluster/glusterfs/release-3.10/extras/ganesha/scripts/dbus-send.sh
chmod 755 create-export-ganesha.sh dbus-send.sh

/usr/libexec/ganesha/create-export-ganesha.sh /etc/ganesha on ${GLUSTER_VOLUME}
/usr/libexec/ganesha/dbus-send.sh /etc/ganesha on ${GLUSTER_VOLUME}

# wait till server comes out of grace period
sleep 90

# basic check if the export is available, some debugging if not
if ! showmount -e | grep -q -w -e "${GLUSTER_VOLUME}"
then
	echo "+++ /var/log/ganesha.log +++"
	cat /var/log/ganesha.log
	echo
	echo "+++ /etc/ganesha/ganesha.conf +++"
	grep --with-filename -e '' /etc/ganesha/ganesha.conf
	echo
	echo "+++ /etc/ganesha/exports/*.conf +++"
	grep --with-filename -e '' /etc/ganesha/exports/*.conf
	echo
	echo "Export ${GLUSTER_VOLUME} is not available"
	exit 1
fi

#Enabling ACL for the volume if ENABLE_ACL param is set to True
if [ "${ENABLE_ACL}" == "True" ]
then
  conf_file="/etc/ganesha/exports/export."${GLUSTER_VOLUME}".conf"
  sed -i s/'Disable_ACL = .*'/'Disable_ACL = false;'/g ${conf_file}
  cat ${conf_file}

  #Parsing export id from volume export conf file
  export_id=$(grep 'Export_Id' ${conf_file} | sed 's/^[[:space:]]*Export_Id.*=[[:space:]]*\([0-9]*\).*/\1/')

  dbus-send --type=method_call --print-reply --system  --dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr  org.ganesha.nfsd.exportmgr.UpdateExport string:${conf_file} string:"EXPORT(Export_Id = ${export_id})"
fi

