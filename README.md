builds data stored here: `/opt/buildbot/master/state.sqlite` be careful  
logs: `tail -f /opt/buildbot/naster/twistd.log`

## master setup

one time setup
```
git clone -b gandi-ci https://github.com/nfs-ganesha/ci-tests.git /opt/ci-tests
buildbot upgrade-master /opt/ci-tests/buildbot
# provide local.py with:
# 	id_rsa (match gerrithub key)
# 	worker password
# 	client_id for github oauath api
# 	client_secret for github oauath api
```

`. /opt/ci-tests/buildbot/buildbot-start.sh` do this for every new worker, new scripts

## new worker setup
```
# 10.100.42.1/24 pvlan
# add master's public key to authorized_keys for rsync updates
# start dbus, rpcbind
git clone -b gandi-ci https://github.com/nfs-ganesha/ci-tests /opt/ci-tests
buildbot-worker create-worker /opt/bb-worker1 <master ip (pvlan)> <name> <passwd>
# restart the master with /opt/ci-tests/buildbot/buidbot-start.sh
```
