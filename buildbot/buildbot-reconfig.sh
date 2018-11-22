client_ip=10.100.42.1
worker_ip=10.100.42.2
rsync -r /opt/ci-tests/server "${worker_ip}:/opt/"
rsync -r /opt/ci-tests/client "${client_ip}:/opt/"
buildbot reconfig /opt/ci-tests/buildbot
while true; do
	ssh -p29418 -i /root/.ssh/id_rsa gandi-nfs-ganesha@review.gerrithub.io gerrit stream-events
done &
disown
