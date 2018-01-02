# abort if anything fails
set -e
 
[ -n "${GLUSTER_VOLUME}" ]
 
# be a little bit more verbose
set -x
 

# starting glusterd and nfs-ganesh
systemctl start glusterd
systemctl start nfs-ganesha

# disable the firewall, otherwise the client can not connect
systemctl stop firewalld || service iptables stop

# TODO: SELinux prevents creating special files on Gluster bricks (bz#1331561)
setenforce 0
	
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
	
	
/usr/libexec/ganesha/create-export-ganesha.sh /etc/ganesha on ${GLUSTER_VOLUME}
/usr/libexec/ganesha/dbus-send.sh /etc/ganesha on ${GLUSTER_VOLUME}
	
# wait till server comes out of grace period
sleep 10

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
