builds data stored here: `/opt/buildbot/master/state.sqlite` be careful  
logs: `tail -f /opt/buildbot/naster/twistd.log`

## master setup
```
git clone -b gandi-ci https://github.com/nfs-ganesha/ci-tests.git /opt/buildbot/ci-tests
buildbot upgrade-master /opt/ci-tests/buildbot
# provide local.py with:
# 	id_rsa (match gerrithub key)
# 	worker password
# 	client_id for github oauath api
# 	client_secret for github oauath api
#start the buildbot webpage
# _NEVER_ `buildbot reconfig` because the gerrit streams events never restarts after that...
./opt/ci-tests/buildbot-start.sh
```

## worker setup
```
#10.100.42.1/24 pvlan
# add master's public key to authorized_keys for rsync updates
git clone -b gandi-ci https://github.com/nfs-ganesha/ci-tests /opt/ci-tests
buildbot-worker create-worker /opt/bb-worker1 <master ip (pvlan)> <name> <passwd>
# start the worker, only needs to be restarted when the master is restarted
buildbot-worker start bb-worker1
```
