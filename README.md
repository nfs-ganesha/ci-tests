builds data sotred here: `/opt/buildbot/master/state.sqlite` be careful  
logs: `tail -f /opt/buildbot/naster/twistd.log`

## master setup

`local.py` should contain all relevant secrets, see `master.cfg`

```
git clone -b gandi-ci https://github.com/nfs-ganesha/ci-tests.git /opt/buildbot/master
buildbot upgrade-master /opt/buildbot/master
```

## master startup
```
buildbot start /opt/buildbot/master
```

## worker setup
```
#name: provided by master
#passwd: provided by master
#10.100.42.1/24 pvlan
buildbot-worker create-worker ~/bb-worker1 10.100.42.1 <name> <passwd>
```

## worker startup
workers need to be restarted after a master `restart` (use master `reconfig` instead)
```
buildbot-worker start bb-worker1
```
