# cico-node-done-from-ansible.sh
# A script that releases nodes from a SSID file written by
set +x
SSID_FILE=${SSID_FILE:-$WORKSPACE/cico-ssid}

scp -q -o StrictHostKeyChecking=no -i /duffy-ssh-key/ssh-privatekey -r $WORKSPACE/ip_address*.txt nfs-ganesha@artifacts.ci.centos.org:/srv/artifacts/nfs-ganesha/

for ssid in $(cat ${SSID_FILE})
do
    cico -q node done $ssid
done
