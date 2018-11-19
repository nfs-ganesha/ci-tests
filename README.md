builds data stored here: `/opt/buildbot/master/state.sqlite` be careful  
logs: `tail -f /opt/buildbot/naster/twistd.log`

## master setup
```
git clone -b gandi-ci https://github.com/nfs-ganesha/ci-tests.git /opt/buildbot/master
buildbot upgrade-master /opt/buildbot/master
# provide local.py with:
# 	id_rsa (match gerrithub key)
# 	worker password
# 	client_id for github oauath api
# 	client_secret for github oauath api
#start the buildbot webpage
buildbot start /opt/buildbot/master
```

## worker setup
```
#name: provided by master
#passwd: provided by master
#10.100.42.1/24 pvlan
buildbot-worker create-worker ~/bb-worker1 10.100.42.1 <name> <passwd>
# start the worker, only needs to be restarted when the master is restarted
buildbot-worker start bb-worker1
```
