#
# from: https://raw.githubusercontent.com/kbsingh/centos-ci-scripts/master/build_python_script.py
#
# This script uses the Duffy node management api to get fresh machines to run
# your CI tests on. Once allocated you will be able to ssh into that machine
# as the root user and setup the environ
#
# XXX: You need to add your own api key below, and also set the right cmd= line 
#      needed to run the tests
#
# Please note, this is a basic script, there is no error handling and there are
# no real tests for any exceptions. Patches welcome!

import json, urllib.request, subprocess, sys, time, os

url_base="http://admin.ci.centos.org:8080"
# we just build on CentOS-7/x86_64, CentOS-6 does not have 'mock'?
ver=os.getenv("CENTOS_VERSION")
arch=os.getenv("CENTOS_ARCH")
count=1
script_url=os.getenv("TEST_SCRIPT")
templates_url=os.getenv("TEMPLATES_URL")

# read the API key for Duffy from the ~/duffy.key file
api=os.environ['CICO_API_KEY']

# build the URL to request the system(s)
get_nodes_url="%s/Node/get?key=%s&ver=%s&arch=%s&count=%s" % (url_base,api,ver,arch,count)

# request the system
dat=urllib.request.urlopen(get_nodes_url).read()
b=json.loads(dat)

SSID_FILE=os.getenv("WORKSPACE")+"/cico-ssid"
ff=open(SSID_FILE, "w")
ff.write(str(b['ssid'])+'\n')
ff.close()

IPS=os.getenv("WORKSPACE")+"/ip_addresses_"+os.getenv("JOB_NAME")+"_"+os.getenv("BUILD_NUMBER")+".txt"
ffd=open(IPS, "w")
ffd.write(os.getenv("JOB_NAME")+'\n'+os.getenv("BUILD_NUMBER")+'\n')
out=subprocess.getoutput("cico inventory | grep %s"%(str(b['ssid'])))
ffd.write(str(out)+'\n')
ffd.close()

# create a rsync.passwd file on the reserved system to store RPMs on artifacts.ci.centos.org
cmd="echo %s | cut -c1-13 | ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s 'cat > rsync.passwd ; chmod 0600 rsync.passwd'" % (api, b['hosts'][0])
print (cmd)
rtn_code=subprocess.call(cmd, shell=True)

scp_cmd="""scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s root@%s:./build.sh
"""%(script_url, b['hosts'][0])
subprocess.call(scp_cmd, shell=True)

cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
        CENTOS_VERSION="%s" CENTOS_ARCH="%s" TEMPLATES_URL="%s" bash build.sh'
""" % (b['hosts'][0], ver, arch, templates_url)
rtn_code=subprocess.call(cmd, shell=True)

# return the system(s) to duffy
done_nodes_url="%s/Node/done?key=%s&ssid=%s" % (url_base, api, b['ssid'])
das=urllib.request.urlopen(done_nodes_url).read()

sys.exit(rtn_code)
