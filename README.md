## setup
```
mkdir -p /opt/buildbot/secrets
# provide secrets/worker.pass
# provide secrets/id_rsa
# provide secrets/.htpasswd (plaintext because buildbot is broken)
chmod -R 0600 secrets
```

# master startup
```
buildbot start /opt/buildbot/master
```

# worker setup
```
#name: provided by master
#passwd: provided by master
#10.100.42.1/24 pvlan
buildbot-worker create-worker ~/bb-worker1 10.100.42.1 <name> <passwd>
```

# worker startup
```
buildbot-worker start bb-worker1
```
