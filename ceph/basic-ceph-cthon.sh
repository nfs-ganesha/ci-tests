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

BUILDREQUIRES="git bison cmake dbus-devel flex gcc-c++ krb5-devel libacl-devel libblkid-devel libcap-devel redhat-rpm-config rpm-build xfsprogs-devel"

#BUILDREQUIRES_EXTRA="libnsl2-devel libnfsidmap-devel libwbclient-devel libcephfs-devel userspace-rcu-devel"
BUILDREQUIRES_EXTRA="libnsl2-devel libnfsidmap-devel libwbclient-devel userspace-rcu-devel"

# basic packages to install
case "${CENTOS_VERSION}" in
    7)
        yum install -y ${BUILDREQUIRES} ${BUILDREQUIRES_EXTRA} python2-devel
    ;;
    8s)
        yum install -y ${BUILDREQUIRES}
        yum install --enablerepo=powertools -y ${BUILDREQUIRES_EXTRA}
        yum install -y libcephfs-devel
    ;;
    9s)
       yum install -y ${BUILDREQUIRES}
       yum install --enablerepo=crb -y ${BUILDREQUIRES_EXTRA}
       yum install -y libcephfs-devel
    ;;
esac

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

# If failure found during build, return the status and skip proceeding
# to ceph configuration


# we accept different return values
# 0 - SUCCESS + VOTE
# 1 - FAILED + VOTE
# 10 - SUCCESS + REPORT ONLY (NO VOTE)
# 11 - FAILED + REPORT ONLY (NO VOTE)
RET=0
if [ -e FAILED ]
then
	exit ${RET}
fi
if [ -e WIP ]
then
	RET=$[RET + 10]
	exit ${RET}
fi

# Install and configure ceph cluster
dnf install -y cephadm
cephadm add-repo --release squid
dnf install -y ceph
cephadm bootstrap --mon-ip $(hostname -I | awk '{print $1}') --single-host-defaults --allow-fqdn-hostname
ceph auth get client.bootstrap-osd -o /var/lib/ceph/bootstrap-osd/ceph.keyring

# Create a virtual disk file (for OSD storage):
truncate -s 35G /tmp/ceph-disk.img
losetup -f /tmp/ceph-disk.img  # Attaches as a loop device (e.g., /dev/loop0)

pvcreate /dev/loop0
vgcreate ceph-vg /dev/loop0
lvcreate -L 10G -n osd1 ceph-vg
lvcreate -L 10G -n osd2 ceph-vg
lvcreate -L 10G -n osd3 ceph-vg

ceph-volume lvm create --data /dev/ceph-vg/osd1
ceph-volume lvm create --data /dev/ceph-vg/osd2
ceph-volume lvm create --data /dev/ceph-vg/osd3

# Now auto assign these lvms to the osd's
ceph orch apply osd --all-available-devices

sleep 20

# Create a cephfs volume
ceph fs volume create cephfs

# create ganesha.conf file
touch /etc/ganesha/ganesha.conf

# Update Ganesha.conf file
echo 'EXPORT {
    Export_ID = 1;
    Path = "/";
    Pseudo = "/nfs/cephfs";
    Protocols = 4;
    Transports = TCP;
    Access_Type = RW;
    Squash = None;
    FSAL {
        Name = "CEPH";
        User_Id = "admin";
        Secret_Access_Key = "";
    }
}' > /etc/ganesha/ganesha.conf

mkdir -p /var/run/ganesha
chmod 755 /var/run/ganesha
chown root:root /var/run/ganesha

ganesha.nfsd -f /etc/ganesha/ganesha.conf -L /var/log/ganesha.log
if pgrep ganesha >/dev/null; then
        echo "[OK] Service ganesha is running"
    else
        echo "[ERROR] Service ganesha is NOT running" >&2
        exit 1
fi



# Run Cthon post successful cluster creation

# install build and runtime dependencies
yum -y install git gcc nfs-utils time make

if [ "${CENTOS_VERSION}" == "8s" ]; then
  ENABLE_REPO="--enablerepo=powertools"
elif [ "${CENTOS_VERSION}" == "9s" ]; then
  ENABLE_REPO="--enablerepo=crb"
fi
yum ${ENABLE_REPO} install -y libtirpc-devel

#Logic to generate corefiles
echo "/tmp/cores/core.%e.%p.%h.%t" > /proc/sys/kernel/core_pattern
mkdir -p /tmp/cores

# checkout the connectathon tests
cd
git clone --depth=1 git://git.linux-nfs.org/projects/steved/cthon04.git
cd cthon04
( make all )  || true


# RUN CTHON for v3 < SKIPPING AS CURRENT RUNS FOCUS ON 4 and 4.1 >
#mkdir -p /mnt/nfs_ceph_v3
#if mount -t nfs -o vers=3 $(hostname -I | awk '{print $1}'):/nfs/cephfs /mnt/nfs_ceph_v3; then
#    echo "NFS mount successful!"
#    if mountpoint -q /mnt/nfs_ceph_v3; then
#        echo "Verification: NFS is properly mounted at /mnt/nfs_ceph_v3"
#        echo "Mounted NFS details:"
#        mount | grep /mnt/nfs_ceph_v3
#    else
#        echo "ERROR: Mount command succeeded but verification failed!" >&2
#        exit 1
#    fi
#else
#    echo "ERROR: Failed to mount NFS share!" >&2
#    touch FAILED
#    exit 1
#fi
## Run Cthon
#./server -a -p /nfs/cephfs -m /mnt/nfs_ceph_v3 $(hostname -I | awk '{print $1}')


# Run CTHON for v4.0
mkdir -p /mnt/nfs_ceph_v4
if mount -t nfs -o vers=4 $(hostname -I | awk '{print $1}'):/nfs/cephfs /mnt/nfs_ceph_v4; then
    echo "NFS mount successful!"
    if mountpoint -q /mnt/nfs_ceph_v4; then
        echo "Verification: NFS is properly mounted at /mnt/nfs_ceph_v4"
        echo "Mounted NFS details:"
        mount | grep /mnt/nfs_ceph_v4
    else
        echo "ERROR: Mount command succeeded but verification failed!" >&2
        exit 1
    fi
else
    echo "ERROR: Failed to mount NFS share!" >&2
    touch FAILED
    exit 1
fi
# Run Cthon
./server -a -p /nfs/cephfs -m /mnt/nfs_ceph_v4 $(hostname -I | awk '{print $1}')


# Run CTHON for v4.1
mkdir -p /mnt/nfs_ceph_v41
if mount -t nfs -o vers=4.1 $(hostname -I | awk '{print $1}'):/nfs/cephfs /mnt/nfs_ceph_v41; then
    echo "NFS mount successful!"
    if mountpoint -q /mnt/nfs_ceph_v41; then
        echo "Verification: NFS is properly mounted at /mnt/nfs_ceph_v41"
        echo "Mounted NFS details:"
        mount | grep /mnt/nfs_ceph_v41
    else
        echo "ERROR: Mount command succeeded but verification failed!" >&2
        exit 1
    fi
else
    echo "ERROR: Failed to mount NFS share!" >&2
    touch FAILED
    exit 1
fi
# Run Cthon
./server -a -p /nfs/cephfs -m /mnt/nfs_ceph_v41 $(hostname -I | awk '{print $1}')

exit 0

