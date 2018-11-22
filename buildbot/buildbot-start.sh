set -x
client_ip=10.100.42.1
worker_ip=10.100.42.2
rsync -r /opt/ci-tests/server "${worker_ip}:/opt/"
rsync -r /opt/ci-tests/client "${client_ip}:/opt/"
buildbot restart /opt/ci-tests/buildbot
sleep 3
ssh root@${worker_ip} buildbot-worker restart /opt/bb-worker1
