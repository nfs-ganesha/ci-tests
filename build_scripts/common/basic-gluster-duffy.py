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
ver=os.getenv("CENTOS_VERSION")
arch=os.getenv("CENTOS_ARCH")
count=2
server_script=os.getenv("SERVER_TEST_SCRIPT")
client_script=os.getenv("CLIENT_TEST_SCRIPT")
# delay for 5 minutes (duffy timeout for rate limiting)
retry_delay=300
# retry maximum 3 hours, that is 3 x 60 x 60 seconds 
max_retries=int(((3 * 60 * 60) / retry_delay))

# read the API key for Duffy from the ~/duffy.key file
api=os.environ['CICO_API_KEY']

# build the URL to request the system(s)
get_nodes_url="%s/Node/get?key=%s&ver=%s&arch=%s&count=%s" % (url_base,api,ver,arch,count)

# request the system(s)
retries=0
while retries < max_retries:
    try:
        dat=urllib.request.urlopen(get_nodes_url).read()
        b=json.loads(dat)
        # all is fine, break out of the loop
        break
    except ValueError as ve:
        print("Failed to parse Duffy response: %s" % (dat))
    except Exception as e:
        print("An unexpected error occured: %s" % (e))

    retries+=1
    print("Waiting %d seconds before retrying #%d..." % (retry_delay, retries))
    time.sleep(retry_delay)

print (b['hosts'])

# NFS-Ganesha Server (parameters need double escape, passed on ssh commandline)
server_env="export GERRIT_HOST='%s'" % os.getenv("GERRIT_HOST")
server_env+=" GERRIT_PROJECT='%s'" % os.getenv("GERRIT_PROJECT")
server_env+=" GERRIT_REFSPEC='%s'" % os.getenv("GERRIT_REFSPEC")
server_env+=" YUM_REPO='%s'" % os.getenv("YUM_REPO", "")
server_env+=" GLUSTER_VOLUME='%s'" % os.getenv("EXPORT")
server_env+=" ENABLE_ACL='%s'" % os.getenv("ENABLE_ACL", "")
server_env+=" SECURITY_LABEL='%s'" % os.getenv("SECURITY_LABEL", "")

job_name=os.environ['JOB_NAME']
if job_name == "nfs_ganesha_iozone_vfs" or job_name == "nfs_ganesha_iozone_vfs_minmdcache":
    server_env+=" VFS_VOLUME='%s'" % os.getenv("EXPORT")
else:
    server_env+=" GLUSTER_VOLUME='%s'" % os.getenv("EXPORT")

if os.getenv("CENTOS_VERSION") != "":
    server_env+=" CENTOS_VERSION='%s'" % os.getenv("CENTOS_VERSION")

# add the export with environment to ~/.bashrc
cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
tee -a ~/.bashrc' <<< "%s"
""" % (b['hosts'][0], server_env)
subprocess.call(cmd, shell=True)

copy_serverscript="""scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s root@%s:./%s
"""%(server_script, b['hosts'][0], os.path.basename(server_script))
copy_ret=subprocess.call(copy_serverscript, shell=True)
if copy_ret == 0:
    print ("Successfully copied")
else:
    print ("Copy failed")

copy_verify="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s 'ls -l'"""%(b['hosts'][0])
subprocess.call(copy_verify, shell=True)

cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s 'bash %s'""" % (b['hosts'][0], os.path.basename(server_script))
rtn_code=subprocess.call(cmd, shell=True)

# check rtn_code and skip client part after failure
if rtn_code == 0:
    # NFS-Client (parameters need double escape, passed on ssh commandline)
    client_env="export SERVER='%s'" % b['hosts'][0]
    client_env+=" EXPORT='/%s'" % os.getenv("EXPORT")
    client_env+=" TEST_PARAMETERS='%s'" % os.getenv("TEST_PARAMETERS", "")

    # add the export with environment to ~/.bashrc
    cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '
        tee -a ~/.bashrc' <<< "%s"
        """ % (b['hosts'][1], client_env)
    subprocess.call(cmd, shell=True)

    client_script = client_script.strip(" ")
    if client_script.endswith(".py"):
        interpreter_to_run = "python"
    elif client_script.endswith(".sh"):
        interpreter_to_run = "bash"
    copy_clientscript="""scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s root@%s:./%s
                      """%(client_script, b['hosts'][1], os.path.basename(client_script))
    subprocess.call(copy_clientscript, shell=True)
    cmd="""ssh -t -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s '%s %s'""" % (b['hosts'][1], interpreter_to_run, os.path.basename(client_script))
    rtn_code=subprocess.call(cmd, shell=True)

# return the system(s) to duffy
done_nodes_url="%s/Node/done?key=%s&ssid=%s" % (url_base, api, b['ssid'])
das=urllib.request.urlopen(done_nodes_url).read()

sys.exit(rtn_code)
