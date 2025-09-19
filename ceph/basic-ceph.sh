#!/bin/sh

# if any command fails, the script should exit
set -e

# enable some more output
set -x

# these variables need to be set
[ -n "${GERRIT_HOST}" ]
[ -n "${GERRIT_PROJECT}" ]
[ -n "${GERRIT_REFSPEC}" ]

# only use https for now
GIT_REPO="https://${GERRIT_HOST}/${GERRIT_PROJECT}"

# enable the Storage SIG Gluster and Ceph repositories
dnf -y install centos-release-ceph epel-release
dnf install dnf-plugins-core -y
dnf config-manager --set-enabled crb

BUILDREQUIRES="git bison cmake dbus-devel flex gcc-c++ krb5-devel libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build xfsprogs-devel lvm2"

BUILDREQUIRES_EXTRA="libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel"

# basic packages to install
yum install -y ${BUILDREQUIRES}
yum install --enablerepo=crb -y ${BUILDREQUIRES_EXTRA}
yum install -y libcephfs-devel


git clone --depth=1 ${GIT_REPO}
cd $(basename "${GERRIT_PROJECT}")
git fetch origin ${GERRIT_REFSPEC} && git checkout FETCH_HEAD

# update libntirpc
git submodule update --recursive --init || git submodule sync

# cleanup old build dir
[ -d build ] && rm -rf build

mkdir build
cd build

( cmake ../src -DCMAKE_BUILD_TYPE=Maintainer -DUSE_FSAL_GLUSTER=OFF -DUSE_FSAL_CEPH=ON -DUSE_FSAL_RGW=OFF -DUSE_DBUS=ON -DUSE_ADMIN_TOOLS=ON && make) || touch FAILED
make install

# dont vote if the subject of the last change includes the word "WIP"
if ( git log --oneline -1 | grep -q -i -w 'WIP' )
then
    echo "Change marked as WIP, not posting result to GerritHub."
    touch WIP
fi

# Create a virtual disk file (for OSD storage):
truncate -s 35G /tmp/ceph-disk.img
losetup -f /tmp/ceph-disk.img  # Attaches as a loop device (e.g., /dev/loop0)

pvcreate /dev/loop0
vgcreate ceph-vg /dev/loop0
lvcreate -L 10G -n osd1 ceph-vg
lvcreate -L 10G -n osd2 ceph-vg
lvcreate -L 10G -n osd3 ceph-vg

# Install and configure ceph cluster
dnf install -y cephadm
dnf install -y lua-devel
cephadm add-repo --release squid
dnf install -y ceph
cephadm bootstrap --mon-ip $(hostname -I | awk '{print $1}') --single-host-defaults --allow-fqdn-hostname
ceph auth get client.bootstrap-osd -o /var/lib/ceph/bootstrap-osd/ceph.keyring

# Attach the virtual disks
ceph-volume lvm create --data /dev/ceph-vg/osd1
ceph-volume lvm create --data /dev/ceph-vg/osd2
ceph-volume lvm create --data /dev/ceph-vg/osd3

# Verifying the disks
lvdisplay
lsblk
ceph orch device ls

# Now auto assign these lvms to the osd's
ceph orch apply osd --all-available-devices

# Wait for the osd's to be added

echo "Waiting for at least one OSD to be ready..."
TIMEOUT=300
START_TIME=$(date +%s)
while true; do
    # Check if any OSD service exists and has at least one running OSD
    OSD_STATUS=$(ceph orch ls --service-type osd --format json 2>/dev/null | \
                 jq -r '.[0].status | select(.running != null) | .running >= 1')

    # Check if the command succeeded and we got "true"
    if [ "$OSD_STATUS" = "true" ]; then
        echo "OSD is ready!"
        break
    fi

    # Check timeout if set
    if [ "$TIMEOUT" -gt 0 ]; then
        CURRENT_TIME=$(date +%s)
        ELAPSED=$((CURRENT_TIME - START_TIME))
        if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
            echo "Timeout reached while waiting for OSD to be ready"
            exit 1
        fi
    fi

    sleep 5
done

# view the osd's
ceph osd tree
# Create a cephfs volume
ceph fs volume create cephfs

# Create subvolumegroup
ceph fs subvolumegroup create cephfs ganeshagroup

# Create subvolume
ceph fs subvolume create cephfs nfs_subvol --group_name ganeshagroup --namespace-isolated

# Get subvolume path
CEPHFS_NAME="cephfs"
SUBVOLUME_NAME="nfs_subvol"
GROUP_NAME="ganeshagroup"
SUBVOL_PATH=$(ceph fs subvolume getpath "$CEPHFS_NAME" "$SUBVOLUME_NAME" --group_name "$GROUP_NAME" 2>/dev/null)

# Verify path was obtained
if [ -z "$SUBVOL_PATH" ]; then
    echo "ERROR: Failed to get subvolume path."
    exit 1
fi
echo "Subvolume path: $SUBVOL_PATH"

# create ganesha.conf file
echo "NFS_CORE_PARAM {
    Enable_NLM = false;
    Enable_RQUOTA = false;
    Protocols = 3,4;
}

EXPORT_DEFAULTS {
    Access_Type = RW;
}
EXPORT {
    Export_ID = 101;
    Path = \"$SUBVOL_PATH\";
    Pseudo = \"/nfs/cephfs\";
    Protocols = 3,4;
    mount_path_pseudo = true;
    Transports = TCP;
    Access_Type = RW;
    Squash = None;
    FSAL {
        Name = \"CEPH\";
    }
}" > /etc/ganesha/ganesha.conf

# View the ganesha conf file
cat /etc/ganesha/ganesha.conf

mkdir -p /var/run/ganesha
chmod 755 /var/run/ganesha
chown root:root /var/run/ganesha

# Creating backend recovery dir for nfs ganesha
mkdir -p /var/lib/nfs/ganesha
chmod 755 /var/lib/nfs/ganesha
chown root:root /var/lib/nfs/ganesha

ganesha.nfsd -f /etc/ganesha/ganesha.conf -L /var/log/ganesha.log
if pgrep ganesha >/dev/null; then
        echo "[OK] Service ganesha is running"
        echo $(pgrep ganesha)
    else
        echo "[ERROR] Service ganesha is NOT running" >&2
        exit 1
fi
