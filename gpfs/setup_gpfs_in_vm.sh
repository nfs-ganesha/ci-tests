#!/bin/bash


set +e
set -o pipefail
set -x
dnf install unzip -y

# Download Spectrumscale Binary
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
ls -ltr
unzip -qq awscliv2.zip
chmod +x ./aws/*
./aws/install
aws --version
aws configure set aws_access_key_id ${AWS_ACCESS_KEY}
aws configure set aws_secret_access_key ${AWS_SECRET_KEY}
aws configure set default_region_name ap-south-1
aws s3api get-object --bucket centos-ci --key "version_to_use.txt" "version_to_use.txt"
VERSION_TO_USE=$(cat version_to_use.txt)
aws s3api get-object --bucket centos-ci --key "${VERSION_TO_USE}" "${VERSION_TO_USE}"

dnf install virt-install libvirt-daemon-kvm qemu-img wget -y
systemctl enable --now libvirtd
systemctl status libvirtd

# Script to create a CentOS Stream 9 VM from qcow2 image and execute commands

# Configuration variables
VM_NAME="centos9-vm"
IMAGE_URL="https://cloud.centos.org/centos/9-stream/x86_64/images/CentOS-Stream-GenericCloud-x86_64-9-20251117.0.x86_64.qcow2"
IMAGE_NAME="CentOS-Stream-GenericCloud-x86_64-9-20251117.0.x86_64.qcow2"
VM_CPU="2"
VM_RAM="8192"
VM_DISK_SIZE="30G"
SSH_KEY="${HOME}/.ssh/id_rsa.pub"
USERNAME="root"


# Check if virt-install is available
if ! command -v virt-install &> /dev/null; then
    echo "Error: virt-install is not installed. Please install libvirt and virt-install:"
    echo "sudo apt install libvirt-daemon-system virtinst (Debian/Ubuntu)"
    echo "sudo yum install libvirt virt-install (RHEL/CentOS)"
    exit 1
fi

# Check if libvirt is running
if ! systemctl is-active --quiet libvirtd; then
    echo "Warning: libvirtd is not running. Starting libvirtd..."
    sudo systemctl start libvirtd
    sudo systemctl enable libvirtd
fi

AVAILABLE_NETWORKS=$(virsh net-list --name | grep -v "^\s*$" | head -n 1)
if [[ -z "$AVAILABLE_NETWORKS" ]]; then
    echo "No networks found. Creating a new NAT network..."
    sudo virsh net-define /usr/share/libvirt/networks/default.xml 2>/dev/null || \
    cat > /tmp/default-network.xml << 'EOF'
<network>
  <name>default</name>
  <bridge name="virbr0"/>
  <forward mode="nat"/>
  <ip address="192.168.122.1" netmask="255.255.255.0">
    <dhcp>
      <range start="192.168.122.2" end="192.168.122.254"/>
    </dhcp>
  </ip>
</network>
EOF
    sudo virsh net-define /tmp/default-network.xml
    sudo virsh net-start default
    sudo virsh net-autostart default
    NETWORK="default"
else
    NETWORK="$AVAILABLE_NETWORKS"
    echo "Using network: $NETWORK"
fi

# Create directory for images if it doesn't exist
IMAGE_DIR="${HOME}/virt-images"
mkdir -p "$IMAGE_DIR"

# Download the qcow2 image if it doesn't exist
if [[ ! -f "${IMAGE_DIR}/${IMAGE_NAME}" ]]; then
    echo "Downloading CentOS Stream 9 image..."
    wget -O "${IMAGE_DIR}/${IMAGE_NAME}" "$IMAGE_URL"

    if [[ $? -ne 0 ]]; then
        echo "Error: Failed to download the image"
        exit 1
    fi
else
    echo "Image already exists, skipping download"
fi

# Resize the image to desired size
echo "Resizing image to ${VM_DISK_SIZE}..."
qemu-img resize "${IMAGE_DIR}/${IMAGE_NAME}" "$VM_DISK_SIZE"

# Generate SSH key if it doesn't exist
if [[ ! -f "${SSH_KEY}" ]]; then
    echo "Generating SSH key..."
    ssh-keygen -t rsa -b 4096 -f "${SSH_KEY%.pub}" -N ""
fi

# Create cloud-init config
echo "Creating cloud-init configuration..."
mkdir -p "${IMAGE_DIR}/cloud-init"

cat > "${IMAGE_DIR}/cloud-init/user-data" << EOF
#cloud-config
users:
  - name: ${USERNAME}
    ssh-authorized-keys:
      - $(cat "${SSH_KEY}")
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    groups: wheel
    shell: /bin/bash

# Enable passwordless sudo for the user
sudo: ['ALL=(ALL) NOPASSWD:ALL']

# Update system on first boot
package_update: true
package_upgrade: true

# Install required packages
packages:
  - qemu-guest-agent
  - cloud-utils
  - openssh-server

# Enable SSH
ssh_pwauth: false

# Write global environment variables
write_files:
  - path: /etc/environment
    append: true
    content: |
      VERSION_TO_USE=${VERSION_TO_USE}
      GERRIT_HOST=${GERRIT_HOST}
      GERRIT_PROJECT=${GERRIT_PROJECT}
      GERRIT_REFSPEC-${GERRIT_REFSPEC}

  - path: /etc/profile.d/custom_vars.sh
    content: |
      export VERSION_TO_USE="${VERSION_TO_USE}"
      export GERRIT_HOST="${GERRIT_HOST}"
      export GERRIT_PROJECT="${GERRIT_PROJECT}"
      export GERRIT_REFSPEC="${GERRIT_REFSPEC}"

# Run commands on first boot
runcmd:
  - systemctl enable qemu-guest-agent
  - systemctl start qemu-guest-agent
  - sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
  - systemctl restart sshd
  - source /etc/environment
  - source /etc/profile.d/custom_vars.sh
EOF

cat > "${IMAGE_DIR}/cloud-init/meta-data" << EOF
instance-id: ${VM_NAME}
local-hostname: ${VM_NAME}
EOF

# Create cloud-init ISO
echo "Creating cloud-init ISO..."
genisoimage -output "${IMAGE_DIR}/cloud-init.iso" -volid cidata -joliet -rock \
    "${IMAGE_DIR}/cloud-init/user-data" "${IMAGE_DIR}/cloud-init/meta-data"

# Create the VM
echo "Creating VM: ${VM_NAME}..."

mkdir -p /var/lib/libvirt/images
mv ${IMAGE_DIR}/*.qcow2 /var/lib/libvirt/images/
mv ${IMAGE_DIR}/*.iso /var/lib/libvirt/images/
chown qemu:qemu /var/lib/libvirt/images/*

virt-install \
    --name "${VM_NAME}" \
    --memory ${VM_RAM} \
    --vcpus ${VM_CPU} \
    --disk path="/var/lib/libvirt/images/${IMAGE_NAME}",format=qcow2,bus=virtio \
    --disk path="/var/lib/libvirt/images/cloud-init.iso",device=cdrom \
    --network network=${NETWORK},model=virtio \
    --os-variant centos-stream9 \
    --virt-type kvm \
    --graphics none \
    --import \
    --noautoconsole

if [[ $? -ne 0 ]]; then
    echo "Error: Failed to create VM"
    exit 1
fi

echo "VM created successfully. Waiting for VM to boot and get IP..."

# Wait for VM to get IP
MAX_WAIT=120
WAIT_TIME=0
VM_IP=""

while [[ $WAIT_TIME -lt $MAX_WAIT ]] && [[ -z "$VM_IP" ]]; do
    VM_IP=$(virsh domifaddr "${VM_NAME}" | grep ipv4 | awk '{print $4}' | cut -d'/' -f1 2>/dev/null || true)

    if [[ -n "$VM_IP" ]]; then
        break
    fi

    echo "Waiting for VM IP... (${WAIT_TIME}s/${MAX_WAIT}s)"
    sleep 5
    WAIT_TIME=$((WAIT_TIME + 5))
done

if [[ -z "$VM_IP" ]]; then
    echo "Error: Failed to get VM IP address"
    exit 1
fi

echo "VM IP address: ${VM_IP}"

# Wait for SSH to be available
echo "Waiting for SSH to be available..."
until nc -z "${VM_IP}" 22; do
    sleep 2
done

# Add VM to known hosts to avoid prompt
ssh-keyscan -H "${VM_IP}" >> ~/.ssh/known_hosts 2>/dev/null || true

# Scp the binary to vm node
scp -i "${SSH_KEY%.pub}" "${VERSION_TO_USE}" "${USERNAME}@${VM_IP}":"/tmp/${VERSION_TO_USE}"

# Execute commands on the VM
echo "Connecting to VM and executing commands..."

# Commands to execute on the VM
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -i "${SSH_KEY%.pub}" "${USERNAME}@${VM_IP}" -t << 'EOF'
  (
    set +e
    set -o pipefail
    set -x  # Print commands as they execute
    echo " === Running Spectrum Scale ==="
    ls /home
    uname -r
    WORKSPACE_PATH=$(pwd)
    WORKING_DIR="$WORKSPACE_PATH/DOWNLOAD_STORAGE_SCALE"
    mkdir -p $WORKING_DIR
    cp /tmp/${VERSION_TO_USE} $WORKING_DIR/${VERSION_TO_USE}
    cd $WORKING_DIR
    echo $PWD
    dnf install -y unzip python3-pip wget
    mkdir "$WORKING_DIR/INSTALL_PATH"
    unzip ${VERSION_TO_USE} -d INSTALLER_PATH/

    ssh-keygen -b 2048 -t rsa -f ~/.ssh/id_rsa -q -N ""
    cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
    chmod og-wx ~/.ssh/authorized_keys

    dnf clean packages
    wget https://kojihub.stream.centos.org/kojifiles/packages/kernel/5.14.0/522.el9/x86_64/kernel-devel-5.14.0-522.el9.x86_64.rpm
    wget https://kojihub.stream.centos.org/kojifiles/packages/kernel/5.14.0/522.el9/x86_64/kernel-headers-5.14.0-522.el9.x86_64.rpm
    dnf -y install ./kernel-devel-5.14.0-522.el9.x86_64.rpm ./kernel-headers-5.14.0-522.el9.x86_64.rpm
    dnf versionlock add kernel kernel-core kernel-modules kernel-headers kernel-devel


    dnf -y install cpp gcc gcc-c++ binutils numactl jre make elfutils elfutils-devel rpcbind sssd-tools openldap-clients bind-utils net-tools krb5-workstation python3 --skip-broken
    python3 -m pip install --user ansible
    python3 -m pip install cherrypy

    #Add CES IP to /etc/hosts
    ip_address=$(/sbin/ip -o -4 addr list eth0 | awk '{print $4}' | cut -d/ -f1)

    for new_ip in $(echo $ip_address | awk -F '.' '{for(i=$4+1;i<=255;i++){print $1"."$2"."$3"."i}}'); do ping -c 2 $new_ip; if [ "$?" == "1" ]; then USABLE_IP=$new_ip; break; fi; done

    echo "$USABLE_IP    cesip1 >> /etc/hosts"

    INSTALLER_VERSION=$(ls INSTALLER_PATH/  --ignore="*.md5" --ignore="*.README" --ignore="*.pgp")
    INSTALLER=$(readlink -f INSTALLER_PATH/${INSTALLER_VERSION})
    chmod +x $INSTALLER
    $INSTALLER --silent
    #
    export PATH="$PATH:$(readlink -f /usr/lpp/mmfs/*/ansible-toolkit/)"
    #
    echo " ===== Setup ===== "
    spectrumscale setup -s 127.0.0.1 --storesecret;

    echo " ===== spectrumscale node add $(hostname) -n ===== "
    spectrumscale node add $(hostname) -n;

    echo " ===== spectrumscale node add $(hostname) -p ===== "
    spectrumscale node add $(hostname) -p;
    echo "DONE"

    echo " ===== spectrumscale config protocols -e $USABLE_IP ===== "
    spectrumscale config protocols -e $USABLE_IP;

    echo " ===== spectrumscale node add -a $(hostname) ===== "
    spectrumscale node add -a $(hostname);

    echo " ===== spectrumscale config gpfs -c $(hostname)_cluster ===== "
    spectrumscale config gpfs -c $(hostname)_cluster;

    echo " ===== dd if=/dev/zero of=/home/nsd1_c84f2u09-rhel88a1 bs=1M count=8192 ===== "
    dd if=/dev/zero of=/home/nsd1_c84f2u09-rhel88a1 bs=1M count=8192;

    echo " ===== dd done ===== "
    spectrumscale nsd add -p $(hostname) -u dataAndMetadata -fs scale_volume -fg 1 /home/nsd1_c84f2u09-rhel88a1;

    echo " ===== config protocols ===== "
    spectrumscale config protocols -f scale_volume -m /ibm/scale_volume;
    spectrumscale enable nfs;
    spectrumscale enable smb;
    spectrumscale callhome disable;
    spectrumscale config perfmon -r off;
    spectrumscale node list;
    spectrumscale install --precheck;
    spectrumscale install;
    spectrumscale deploy --precheck;
    spectrumscale deploy;

    spectrumscale nsd list
    spectrumscale filesystem list

    #----------------------------------------------------------------------------------------------

    #THE FOLLOWING LINES OF CODE CLONES THE SOURCE CODE, RPMBUILD AND INSTALLS THE RPMS
    #----------------------------------------------------------------------------------------------
    # make sure rpcbind is running
    sudo dnf -y install rpcbind
    sudo systemctl start rpcbind

    echo 'TODO: this is BAD, needs a fix in the selinux-policy'
    sudo setenforce 0

    sudo systemctl stop firewalld || true

    # enable repositories
    sudo subscription-manager repos --enable codeready-builder-for-rhel-$(rpm -E %rhel)-$(uname -m)-rpms
    sudo dnf -y install yum-utils centos-release-ceph epel-release unzip --skip-broken

    if [ -n "${YUM_REPO}" ]
    then
      yum-config-manager --add-repo=http://artifacts.ci.centos.org/nfs-ganesha/nightly/libntirpc/libntirpc-latest.repo
      yum-config-manager --add-repo=${YUM_REPO}

      # install the latest version of gluster
      dnf -y install gpfs.nfs-ganesha nfs-ganesha-gluster glusterfs-ganesha

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

      dnf install -y ${BASE_PACKAGES} libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build libgfapi-devel xfsprogs-devel --skip-broken
      dnf install --enablerepo=crb -y ${BUILDREQUIRES_EXTRA} --skip-broken
      dnf -y install selinux-policy-devel sqlite --skip-broken

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
      git submodule update --recursive --init || git submodule sync

      mkdir build
      pushd build

      cmake -DCMAKE_BUILD_TYPE=Maintainer -DUSE_FSAL_GPFS=ON -DUSE_DBUS=ON -D_MSPAC_SUPPORT=OFF -DMONITORING=ON -DUSE_MONITORING=ON ../src
      # sed -i 's/^ monitoring$/%bcond_without monitoring/g' ../src/nfs-ganesha.spec
      make dist
      rpmbuild -ta --define "_srcrpmdir $PWD" --define "_rpmdir $PWD" *.tar.gz
      rpm_arch=$(rpm -E '%{_arch}')
      ganesha_version=$(rpm -q --qf '%{VERSION}-%{RELEASE}' -p *.src.rpm)

      cd nfs-ganesha/build
      if [ -e ${rpm_arch}/libntirpc-devel*.rpm ]; then
        ntirpc_version=$(rpm -q --qf '%{VERSION}-%{RELEASE}' -p ${rpm_arch}/libntirpc-devel*.rpm)
        ntirpc_rpm=${rpm_arch}/libntirpc-${ntirpc_version}.${rpm_arch}.rpm
      fi

      rpm -e gpfs.nfs-ganesha gpfs.nfs-ganesha-gpfs --nodeps
      dnf -y install {x86_64,noarch}/*.rpm

      # Test block
      ulimit -a
      ulimit -c unlimited
      ulimit -a

      # start nfs-ganesha service with an empty configuration
      echo "NFSv4 { Graceless = true; }" > /etc/ganesha/ganesha.conf

      # This block is introduced as the line creates a ambiguity as the same is used in scale implementation
      systemctl stop nfs-ganesha
      sed -i.bak -e 's/^StateDirectory/#&/' /usr/lib/systemd/system/nfs-ganesha.service
      systemctl daemon-reload

      if ! systemctl start nfs-ganesha
      then
        echo "+++ systemctl status nfs-ganesha.service +++"
        systemctl status nfs-ganesha.service
        exit 1
      fi
    fi
    ----------------------------------------------------------------------------------------------


    #EXPORT THE NFS VOLUME
    #----------------------------------------------------------------------------------------------
    /usr/lpp/mmfs/bin/mmuserauth service create --data-access-method file --type userdefined
    /usr/lpp/mmfs/bin/mmnfs export add /ibm/scale_volume -c "*(Access_Type=RW,Squash=none)"

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
) || true
EOF

SSH_EXIT_CODE=${PIPESTATUS[0]}
echo "SSH exit code: $SSH_EXIT_CODE"
echo "Checking ssh_output.log for details:"
tail -20 ssh_output.log


echo "Script completed successfully!"

# install build and runtime dependencies
dnf -y install git gcc nfs-utils time make

if [ "${CENTOS_VERSION}" == "8s" ]; then
    ENABLE_REPO="--enablerepo=powertools"
elif [ "${CENTOS_VERSION}" == "9s" ]; then
    ENABLE_REPO="--enablerepo=crb"
fi
dnf ${ENABLE_REPO} install -y libtirpc-devel

#Logic to generate corefiles
echo "/tmp/cores/core.%e.%p.%h.%t" > /proc/sys/kernel/core_pattern
mkdir -p /tmp/cores

# checkout the connectathon tests
git clone --depth=1 git://git.linux-nfs.org/projects/steved/cthon04.git
cd cthon04
make all

EXPORT="/ibm/scale_volume"
# v4 mount
mkdir -p /mnt/nfsv4
mount -t nfs -o vers=4 ${VM_IP}:${EXPORT} /mnt/nfsv4
./server -a -p ${EXPORT} -m /mnt/nfsv4 ${VM_IP}


# V3 mount
mkdir -p /mnt/nfsv3
mount -t nfs -o vers=3 ${VM_IP}:${EXPORT} /mnt/nfsv3
./server -a -p ${EXPORT} -m /mnt/nfsv3 ${VM_IP}

# VM Shutdown and Deletion
echo "Starting VM shutdown and cleanup process..."

# Shutdown the VM gracefully
echo "Shutting down VM gracefully..."
virsh shutdown "${VM_NAME}"

# Wait for VM to shutdown
echo "Waiting for VM to shutdown..."
MAX_SHUTDOWN_WAIT=60
SHUTDOWN_WAIT_TIME=0

while [[ $SHUTDOWN_WAIT_TIME -lt $MAX_SHUTDOWN_WAIT ]]; do
    VM_STATE=$(virsh domstate "${VM_NAME}" 2>/dev/null || echo "not found")
    if [[ "$VM_STATE" == "shut off" ]]; then
        echo "VM successfully shut down"
        break
    fi
    echo "Waiting for VM to shutdown... (${SHUTDOWN_WAIT_TIME}s/${MAX_SHUTDOWN_WAIT}s)"
    sleep 5
    SHUTDOWN_WAIT_TIME=$((SHUTDOWN_WAIT_TIME + 5))
done

# If VM didn't shutdown gracefully, force destroy it
if [[ "$VM_STATE" != "shut off" ]]; then
    echo "VM did not shutdown gracefully, forcing destruction..."
    virsh destroy "${VM_NAME}"
    sleep 3
fi

# Undefine the VM
echo "Undefining VM..."
virsh undefine "${VM_NAME}" --nvram --remove-all-storage

if [[ $? -eq 0 ]]; then
    echo "VM successfully undefined and storage removed"
else
    echo "Warning: Could not undefine VM with storage removal, trying without storage..."
    virsh undefine "${VM_NAME}" --nvram
fi

# Clean up cloud-init files
echo "Cleaning up cloud-init files..."
rm -rf "${IMAGE_DIR}/cloud-init" "${IMAGE_DIR}/cloud-init.iso" 2>/dev/null || true

echo "VM cleanup completed successfully!"
echo "The VM '${VM_NAME}' has been completely removed from the system."