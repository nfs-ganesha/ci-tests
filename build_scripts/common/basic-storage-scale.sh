#!/bin/sh
#
# Setup a simple gluster environment and export a volume through NFS-Ganesha.
#
# This script uses the following environment variables:/
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

set -x

#THE FOLLOWING LINES OF CODE DOWNLOADS STORAGE SCALE, INSTALLS IT AND CREATES A CLUSTER
#----------------------------------------------------------------------------------------------
WORKING_DIR="DOWNLOAD_STORAGE_SCALE"
mkdir -p $WORKING_DIR
cd $WORKING_DIR
echo $PWD
yum install -y unzip
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
ls -ltr
unzip -qq awscliv2.zip
chmod +x ./aws/*
./aws/install
aws --version
aws configure set aws_access_key_id ${AWS_ACCESS_KEY}
aws configure set aws_secret_access_key ${AWS_SECRET_KEY}
aws s3api get-object --bucket centos-ci --key "version_to_use.txt" "version_to_use.txt"
VERSION_TO_USE=$(cat version_to_use.txt)
echo ${VERSION_TO_USE}
aws s3api get-object --bucket centos-ci --key "${VERSION_TO_USE}" "Storage_Scale_Developer-5.1.9.0-x86_64-Linux-install.zip"
unzip Storage_Scale_Developer-5.1.9.0-x86_64-Linux-install.zip

ssh-keygen -b 2048 -t rsa -f ~/.ssh/id_rsa -q -N ""
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
chmod og-wx ~/.ssh/authorized_keys

yum -y install kernel-devel-$(uname -r) kernel-headers-$(uname -r) cpp gcc gcc-c++ binutils numactl jre make elfutils elfutils-devel rpcbind sssd-tools openldap-clients bind-utils net-tools krb5-workstation python3
python3 -m pip install --user ansible

#Add CES IP to /etc/hosts
ip_address=$(/sbin/ip -o -4 addr list eth0 | awk '{print $4}' | cut -d/ -f1)

for new_ip in $(echo $ip_address | awk -F '.' '{for(i=$4+1;i<=255;i++){print $1"."$2"."$3"."i}}'); do ping -c 2 $new_ip; if [ "$?" == "1" ]; then USABLE_IP=$new_ip; break; fi; done

echo "$USABLE_IP    cesip1" >> /etc/hosts

INSTALLER_VERSION=$(echo ${VERSION_TO_USE/.zip/})
chmod +x $INSTALLER_VERSION
./$INSTALLER_VERSION --silent

/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale setup -s 127.0.0.1 --storesecret;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale node add $(hostname) -n;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale node add $(hostname) -p;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale config protocols -e $USABLE_IP;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale node add -a $(hostname);
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale config gpfs -c $(hostname)_cluster;
dd if=/dev/zero of=/home/nsd1_c84f2u09-rhel88a1 bs=1M count=8192;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale nsd add -p $(hostname) -u dataAndMetadata -fs ${STORAGE_SCALE_VOLUME} -fg 1 /home/nsd1_c84f2u09-rhel88a1;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale config protocols -f ${STORAGE_SCALE_VOLUME} -m /ibm/${STORAGE_SCALE_VOLUME};
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale enable nfs;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale enable smb;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale callhome disable;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale config perfmon -r off;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale node list;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale install --precheck;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale install;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale deploy --precheck;
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale deploy;

/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale nsd list
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale filesystem list
#----------------------------------------------------------------------------------------------

#THE FOLLOWING LINES OF CODE CLONES THE SOURCE CODE, RPMBUILD AND INSTALLS THE RPMS
#----------------------------------------------------------------------------------------------
# make sure rpcbind is running
yum -y install rpcbind
systemctl start rpcbind

echo 'TODO: this is BAD, needs a fix in the selinux-policy'
sudo etenforce 0

systemctl stop firewalld || true

# enable repositories
yum -y install centos-release-gluster yum-utils centos-release-ceph epel-release unzip

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

        BASE_PACKAGES="git bison flex cmake gcc-c++ libacl-devel krb5-devel dbus-devel rpm-build redhat-rpm-config gdb"
        BUILDREQUIRES_EXTRA="libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel libcephfs-devel"
        if [ "${CENTOS_VERSION}" = "7" ]; then
            yum -y install libgfapi-devel
            yum -y install ${BASE_PACKAGES} libnfsidmap-devel libwbclient-devel libcap-devel libblkid-devel userspace-rcu-devel userspace-rcu python2-devel
        elif [ "${CENTOS_VERSION}" = "8s" ]; then
            yum install -y ${BASE_PACKAGES} libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build libgfapi-devel xfsprogs-devel
            yum install --enablerepo=powertools -y ${BUILDREQUIRES_EXTRA}
            yum -y install selinux-policy-devel sqlite 
        elif [ "${CENTOS_VERSION}" = "9s" ]; then
            yum install -y ${BASE_PACKAGES} libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build libgfapi-devel xfsprogs-devel
            yum install --enablerepo=crb -y ${BUILDREQUIRES_EXTRA}
            yum -y install selinux-policy-devel sqlite
        fi

	git init "${GIT_REPO}"
	pushd "${GIT_REPO}"

        #Its observed that fetch is failing so this little hack is added! Will delete in future if it turns out useless!
	git fetch --depth=1 "${GIT_URL}" "${GERRIT_REFSPEC}" > /dev/null
        if [ $? = 0 ]; then
            echo "Fetch succeeded"
        else
            sleep 2
            git fetch "${GIT_URL}" "${GERRIT_REFSPEC}"
        fi       

	git checkout -b "${GERRIT_REFSPEC}" FETCH_HEAD

	# update libntirpc
	git submodule update --init || git submodule sync

	mkdir build
	pushd build

	cmake -DCMAKE_BUILD_TYPE=Maintainer -DUSE_FSAL_GPFS=ON -DUSE_DBUS=ON -D_MSPAC_SUPPORT=OFF ../src
	make dist
	rpmbuild -ta --define "_srcrpmdir $PWD" --define "_rpmdir $PWD" *.tar.gz
	rpm_arch=$(rpm -E '%{_arch}')
	ganesha_version=$(rpm -q --qf '%{VERSION}-%{RELEASE}' -p *.src.rpm)
	if [ -e ${rpm_arch}/libntirpc-devel*.rpm ]; then
		ntirpc_version=$(rpm -q --qf '%{VERSION}-%{RELEASE}' -p ${rpm_arch}/libntirpc-devel*.rpm)
		ntirpc_rpm=${rpm_arch}/libntirpc-${ntirpc_version}.${rpm_arch}.rpm
	fi
        rpm -e gpfs.nfs-ganesha gpfs.nfs-ganesha-gpfs --nodeps
	yum -y install {x86_64,noarch}/*.rpm

        #Test block
        ulimit -a
        ulimit -c unlimited
        ulimit -a

	# start nfs-ganesha service with an empty configuration
	echo "NFSv4 { Graceless = true; }" > /etc/ganesha/ganesha.conf
     
        #This block is introduced as the line creates a ambiguity as the same is used in scale implementation
        systemctl stop nfs-ganesha
        sed -i.bak -e 's/^StateDirectory/#&/' /usr/lib/systemd/system/nfs-ganesha.service
        systemctl daemon-reload

	if ! systemctl start nfs-ganesha
	then
		echo "+++ systemctl status nfs-ganesha.service +++"
		systemctl status nfs-ganesha.service
		echo "+++ journalctl -xe +++"
		journalctl -xe
		exit 1
	fi
fi
#----------------------------------------------------------------------------------------------


#EXPORT THE NFS VOLUME
#----------------------------------------------------------------------------------------------
/usr/lpp/mmfs/bin/mmuserauth service create --data-access-method file --type userdefined
/usr/lpp/mmfs/bin/mmnfs export add /ibm/${STORAGE_SCALE_VOLUME} -c "*(Access_Type=RW,Squash=none)"

#CHECKS TO SEE IF THE VOLUME IS WORKING
#----------------------------------------------------------------------------------------------

#There's a duplicate line in the file - /var/mmfs/ces/nfs-config/gpfs.ganesha.main.conf which fails to restart
systemctl stop nfs-ganesha
/usr/lpp/mmfs/bin/mmnfs config change MINOR_VERSIONS=0,1
sleep 20
sed -i.bak -e '41d' /var/mmfs/ces/nfs-config/gpfs.ganesha.main.conf
sleep 5
systemctl daemon-reload
if ! systemctl start nfs-ganesha
then
    echo "+++ systemctl status nfs-ganesha.service +++"
    systemctl status nfs-ganesha.service
    echo "+++ journalctl -xe +++"
    journalctl -xe
    exit 1
fi

systemctl status nfs-ganesha
