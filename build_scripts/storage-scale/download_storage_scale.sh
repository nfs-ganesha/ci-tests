#!/bin/bash

set -x

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
aws s3api get-object --bucket nfsganesha-ci --key "version_to_use.txt" "version_to_use.txt"
VERSION_TO_USE=$(cat version_to_use.txt)
echo ${VERSION_TO_USE}
aws s3api get-object --bucket nfsganesha-ci --key "${VERSION_TO_USE}" "Storage_Scale_Developer-5.1.9.0-x86_64-Linux-install.zip"
unzip Storage_Scale_Developer-5.1.9.0-x86_64-Linux-install.zip

ssh-keygen -b 2048 -t rsa -f ~/.ssh/id_rsa -q -N ""
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
chmod og-wx ~/.ssh/authorized_keys

yum -y install kernel-devel cpp gcc gcc-c++ binutils numactl jre make elfutils elfutils-devel rpcbind sssd-tools openldap-clients bind-utils net-tools krb5-workstation python3
python3 -m pip install --user ansible
yum install -y kernel-devel-4.18.0-499.el8.x86_64 kernel-headers-4.18.0-499.el8.x86_64

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
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale nsd add -p $(hostname) -u dataAndMetadata -fs fs1 -fg 1 /home/nsd1_c84f2u09-rhel88a1; 
/usr/lpp/mmfs/5.1.9.0/ansible-toolkit/spectrumscale config protocols -f fs1 -m /ibm/fs1; 
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

sleep 6000
