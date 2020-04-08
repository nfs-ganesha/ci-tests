#!/bin/sh
#
# Setup a simple vfs environment and export a volume through NFS-Ganesha.
#
# This script uses the following environment variables:/
# - VFS_VOLUME: name of the volume to create
#               this name will also be used as name for the export
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

[ -n "${VFS_VOLUME}" ]

# be a little bit more verbose
set -x

# enable repositories (gluster for liburcu)
yum -y install centos-release-gluster yum-utils

# make sure rpcbind is running
yum -y install rpcbind
systemctl start rpcbind

# CentOS 7.4.1708 has an SELinux issue that prevents NFS-Ganesha from creating
# the /var/log/ganesha/ganesha.log file. Starting ganesha.nfsd fails due to
# this.
echo 'TODO: this is BAD, needs a fix in the selinux-policy'
setenforce 0

systemctl stop firewalld

if [ -n "${YUM_REPO}" ]
then
	yum-config-manager --add-repo=http://artifacts.ci.centos.org/nfs-ganesha/nightly/libntirpc/libntirpc-latest.repo
	yum-config-manager --add-repo=${YUM_REPO}

	# start nfs-ganesha service
	if ! systemctl start nfs-ganesha
	then
		echo "+++ systemctl status nfs-ganesha.service +++"
		systemctl status nfs-ganesha
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
	yum -y install git bison flex cmake gcc-c++ libacl-devel krb5-devel \
		dbus-devel libnfsidmap-devel libwbclient-devel libcap-devel \
		libblkid-devel rpm-build redhat-rpm-config userspace-rcu-devel

	git init "${GIT_REPO}"
	pushd "${GIT_REPO}"

	git fetch "${GIT_URL}" "${GERRIT_REFSPEC}"
	git checkout -b "${GERRIT_REFSPEC}" FETCH_HEAD

	# update libntirpc
	git submodule update --init || git submodule sync

	mkdir build
	pushd build

	cmake -DCMAKE_BUILD_TYPE=Maintainer ../src
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
	cat <<EOF > /etc/ganesha/ganesha.conf
NFSv4 { Graceless = true; }
EOF

	if ! systemctl start nfs-ganesha
	then
		echo "+++ systemctl status nfs-ganesha.service +++"
		systemctl status nfs-ganesha
		echo "+++ journalctl -xe +++"
		journalctl -xe
		exit 1
	fi
fi

# TODO: open only the ports needed?
# disable the firewall, otherwise the client can not connect
systemctl stop firewalld || service iptables stop

# Export the volume
mkdir -p /usr/libexec/ganesha
cd /usr/libexec/ganesha
yum -y install wget
wget https://raw.githubusercontent.com/gluster/glusterfs/release-3.10/extras/ganesha/scripts/dbus-send.sh
chmod 755 dbus-send.sh

mkdir -p /${VFS_VOLUME}
chmod ugo+w /${VFS_VOLUME}
mkdir -p /etc/ganesha/exports

cat <<EOF > /etc/ganesha/exports/export.${VFS_VOLUME}.conf
EXPORT {
    Export_Id = 2;
    Path = /${VFS_VOLUME};
    Pseudo = /${VFS_VOLUME};
    Access_type = RW;
    Disable_ACL = True;
    Protocols = "3","4";
    Transports = "UDP","TCP";
    SecType = "sys";
    Security_Lable = False;
    FSAL {
        Name = VFS;
    }
}
EOF

echo "%include \"/etc/ganesha/exports/export.${VFS_VOLUME}.conf\"" >> /etc/ganesha/ganesha.conf

/usr/libexec/ganesha/dbus-send.sh /etc/ganesha on ${VFS_VOLUME}

# wait till server comes out of grace period
sleep 5

# basic check if the export is available, some debugging if not
if ! showmount -e | grep -q -w -e "${VFS_VOLUME}"
then
	echo "+++ /var/log/ganesha/ganesha.log +++"
	cat /var/log/ganesha/ganesha.log
	echo
	echo "+++ /etc/ganesha/ganesha.conf +++"
	grep --with-filename -e '' /etc/ganesha/ganesha.conf
	echo
	echo "+++ /etc/ganesha/exports/*.conf +++"
	grep --with-filename -e '' /etc/ganesha/exports/*.conf
	echo
	exit 1
fi

#Enabling ACL for the volume if ENABLE_ACL param is set to True
if [ "${ENABLE_ACL}" == "True" ]
then
  conf_file="/etc/ganesha/exports/export."${VFS_VOLUME}".conf"
  sed -i s/'Disable_ACL = .*'/'Disable_ACL = false;'/g ${conf_file}
  cat ${conf_file}

  #Parsing export id from volume export conf file
  export_id=$(grep 'Export_Id' ${conf_file} | sed 's/^[[:space:]]*Export_Id.*=[[:space:]]*\([0-9]*\).*/\1/')

  dbus-send --type=method_call --print-reply --system  --dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr  org.ganesha.nfsd.exportmgr.UpdateExport string:${conf_file} string:"EXPORT(Export_Id = ${export_id})"
fi

#Enabling Security_Label for the volume if SECURITY_LABEL param is set to True
if [ "${SECURITY_LABEL}" == "True" ]
then
  conf_file="/etc/ganesha/exports/export."${VFS_VOLUME}".conf"
  sed -i s/'Security_Label = .*'/'Security_Label = True;'/g ${conf_file}
  cat ${conf_file}

  #Parsing export id from volume export conf file
  export_id=$(grep 'Export_Id' ${conf_file} | sed 's/^[[:space:]]*Export_Id.*=[[:space:]]*\([0-9]*\).*/\1/')

  dbus-send --type=method_call --print-reply --system  --dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr  org.ganesha.nfsd.exportmgr.UpdateExport string:${conf_file} string:"EXPORT(Export_Id = ${export_id})"
fi

