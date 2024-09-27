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

import json, urllib, subprocess, sys, os, time

url_base="http://admin.ci.centos.org:8080"
ver=os.getenv("CENTOS_VERSION")
arch=os.getenv("CENTOS_ARCH")
count=4
server_script=os.getenv("SERVER_TEST_SCRIPT")
client_script=os.getenv("CLIENT_TEST_SCRIPT")

# delay for 5 minutes (duffy timeout for rate limiting)
retry_delay=300
# retry maximum 3 hours, that is 3 x 60 x 60 seconds 
max_retries=((3 * 60 * 60) / retry_delay)

# read the API key for Duffy from the ~/duffy.key file
fo=open("/home/nfs-ganesha/duffy.key")
api=fo.read().strip()
fo.close()

# build the URL to request the system(s)
get_nodes_url="%s/Node/get?key=%s&ver=%s&arch=%s&count=%s" % (url_base,api,ver,arch,count)

# request the system(s)
retries=0
while retries < max_retries:
    try:
        dat=urllib.urlopen(get_nodes_url).read()
        b=json.loads(dat)
        # all is fine, break out of the loop
        break
    except ValueError, ve:
        print("Failed to parse Duffy response: %s" % (dat))
    except Error, e:
        print("An unexpected error occured: %s" % (e))

    retries+=1
    print("Waiting %d seconds before retrying #%d..." % (retry_delay, retries))
    time.sleep(retry_delay)


# NFS-Ganesha Server (parameters need double escape, passed on ssh commandline)
server_env="export GERRIT_HOST='%s'" % os.getenv("GERRIT_HOST")
server_env+=" GERRIT_PROJECT='%s'" % os.getenv("GERRIT_PROJECT")
server_env+=" GERRIT_REFSPEC='%s'" % os.getenv("GERRIT_REFSPEC")
server_env+=" YUM_REPO='%s'" % os.getenv("YUM_REPO", "")
server_env+=" GLUSTER_VOLUME='%s'" % os.getenv("EXPORT")
server_env+=" ENABLE_ACL='%s'" % os.getenv("ENABLE_ACL", "")

# add the export with environment to ~/.bashrc for server-1
cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
tee -a ~/.bashrc' <<< "%s"
""" % (b['hosts'][0], server_env)
subprocess.call(cmd, shell=True)

cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
	yum -y install curl &&
	curl -o server1 %s && bash server1 0
'""" % (b['hosts'][0], server_script)
rtn_code=subprocess.call(cmd, shell=True)

# add the export with environment to ~/.bashrc for server-2
if rtn_code == 0:
    cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
    tee -a ~/.bashrc' <<< "%s"
    """ % (b['hosts'][1], server_env)
    subprocess.call(cmd, shell=True)

    cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
    	    yum -y install curl &&
	    curl -o server2 %s && bash server2 0 0 0 %s
    '""" % (b['hosts'][1], server_script, b['hosts'][0])
    rtn_code=subprocess.call(cmd, shell=True)

# check rtn_code and skip resume client-1 part after failure
if rtn_code == 0:
    cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
	    yum -y install curl &&
	    curl -o server1 %s && bash server1 - - 0
    '""" % (b['hosts'][0], server_script)
    rtn_code=subprocess.call(cmd, shell=True)

# check rtn_code and skip client environment part after failure
if rtn_code == 0:
    # NFS-Client (parameters need double escape, passed on ssh commandline)
    client_env="export SERVER='%s'" % b['hosts'][0]
    client_env+=" EXPORT='/%s'" % os.getenv("EXPORT")
    client_env+=" TEST_PARAMETERS='%s'" % os.getenv("TEST_PARAMETERS", "")

    # add the export with environment to ~/.bashrc for client-1
    cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
        tee -a ~/.bashrc' <<< "%s"
        """ % (b['hosts'][2], client_env)
    rtn_code=subprocess.call(cmd, shell=True)

    # NFS-Client (parameters need double escape, passed on ssh commandline)
    client_env="export SERVER='%s'" % b['hosts'][1]
    client_env+=" EXPORT='/%s'" % os.getenv("EXPORT")
    client_env+=" TEST_PARAMETERS='%s'" % os.getenv("TEST_PARAMETERS", "")

    # add the export with environment to ~/.bashrc for client-2
    cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
        tee -a ~/.bashrc' <<< "%s"
        """ % (b['hosts'][3], client_env)
    rtn_code=subprocess.call(cmd, shell=True)

 # check rtn_code and skip rest test part after failure
if rtn_code == 0:
    versions = [3 , 4.0, 4.1]
    for version in versions:
    	# running client-1 script
    	client_script = client_script.strip(" ")
    	cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
	      curl -o client1  %s && bash client1 1 %.1f
        '""" % (b['hosts'][2], client_script, version)
    	rtn_code=subprocess.call(cmd, shell=True)
	
    	# check rtn_code and skip client-2 part after failure
    	if rtn_code == 0:
    	# running client-2 script
            client_script = client_script.strip(" ")
            cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
	          curl -o client2 %s && bash client2 1 %.1f
            '""" % (b['hosts'][3], client_script, version)
            rtn_code=subprocess.call(cmd, shell=True)

    	# check rtn_code and skip client-1 write to a file part after failure
    	if rtn_code == 0:
            cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
	          curl -o client1 %s && bash client1 2
            '""" % (b['hosts'][2], client_script)
            rtn_code=subprocess.call(cmd, shell=True)

    	# check rtn_code and skip client-2 read and write to the file part after failure
    	if rtn_code == 0:
            cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
	          curl -o client2 %s && bash client2 3
            '""" % (b['hosts'][3], client_script)
            rtn_code=subprocess.call(cmd, shell=True)

    	# check rtn_code and skip client-1 write to a file part after failure
    	if rtn_code == 0:
            cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
	          curl -o client1 %s && bash client1 4
            '""" % (b['hosts'][2], client_script)
            rtn_code=subprocess.call(cmd, shell=True)
	
# return the system(s) to duffy
done_nodes_url="%s/Node/done?key=%s&ssid=%s" % (url_base, api, b['ssid'])
das=urllib.urlopen(done_nodes_url).read()

sys.exit(rtn_code)
