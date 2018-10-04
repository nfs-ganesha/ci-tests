set -o pipefail

GERRIT_REF=${GERRIT_REFSPEC:-next}
REVISION=${GERRIT_PATCHSET_REVISION:-next}
PUBLISH=${JENKINS_GERRIT_PUBLISH:-false}
TEST_9P_VFS=${JENKINS_TEST_9P_VFS:-false}
TEST_PROXY=${JENKINS_TEST_PROXY:-true}
CMAKE_OPTS_9P_VFS=${JENKINS_CMAKE_OPTS_9P_VFS:--DBUILD_CONFIG=everything -DCMAKE_CXX_COMPILER=clang -DCMAKE_C_COMPILER=clang -DCMAKE_LINKER=clang -DSANITIZE_ADDRESS=ON -DUSE_9P_RDMA=ON}
SIGMUND_BEHAVIOUR_9P_VFS=${JENKINS_SIGMUND_BEHAVIOUR_9P_VFS:-9p_plus_pynfs}
SIGMUND_SPEED=${JENKINS_SIGMUND_SPEED:-fast}
PCOCC_TEMPLATE_GANESHA_CI_PROXY=${JENKINS_PCOCC_TEMPLATE_GANESHA_CI_OCEAN:-ocean2.5_ganesha-ci}
PCOCC_TEMPLATE_GANESHA_CI_9P=${JENKINS_PCOCC_TEMPLATE_GANESHA_CI_FEDORA:-fedora28_ganesha-ci}
export PCOCC_USER_CONF_DIR=${JENKINS_PCOCC_USER_CONF_DIR:-/ccc/home/cont001/s8open/s8open/pcocc_images}
PCOCC_PARTITION=${JENKINS_PCOCC_PARTITION:-haswell}


SSH_GERRIT="socksify ssh -vvv -p 29418 cea-gerrithub-hpc@review.gerrithub.io"

#VERF corresponds to gerrit status, +1, 0 or -1.
#All status are published on gerrit but only -1 is notified to patch submitter.
#Only VERF=+1 returns a jenkins success script value of 0, else 1 is returned.

gerrit_publish() {
  local   NOTIFY="ALL"

  [[ "$VERF" != "-1" ]] && NOTIFY="NONE"

  if [[ "$PUBLISH" == "true" ]]; then
    echo '{"message": "'"$MESSAGE"'", "labels": { "Verified": '"$VERF"' }, "notify": '"$NOTIFY"' }' | \
      $SSH_GERRIT "gerrit review --json --project ffilz/nfs-ganesha $REVISION"
  else
    echo "echo '{\"message\": \"$MESSAGE\", \"labels\": { \"Verified\": \"$VERF\" }, \"notify\": \"$NOTIFY\" }' | \\
      $SSH_GERRIT \\
        \"gerrit review --json --project ffilz/nfs-ganesha $REVISION\""
  fi
}

exit_test_status() {
  if [[ "$VERF" != "1" ]]; then
    echo "VERF : $VERF"
    exit 1
  else
    exit 0
  fi
}

gerrit_publish_exit() {
  gerrit_publish
  exit_test_status
}

gerrit_publish_clean_exit() {
  local CLEANUP_FUNC=$1

  gerrit_publish

  #call clean function
  $CLEANUP_FUNC

  exit_test_status
}

get_back_test_report () {
  local P_ID=$1
  local TEST_NAME=$2
  local SERVER_LOG=$3
  local  TESTS_LOG=$4
  local CLEANUP_FUNC=$5
  local VM=$6

  if ! pcocc scp -j $P_ID root@$VM:/tmp/test_report.xml .; then
    VERF="-1"
    MESSAGE="Build OK - tests $TEST_NAME didn't finish?\nganesha server logs:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' $SERVER_LOG)\ntest logs:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' $TESTS_LOG)"
    gerrit_publish_clean_exit $CLEANUP_FUNC
  fi
}

#return in string the number of total tests
analyse_report_result() {
  local TEST_NAME=$1
  local SERVER_LOG=$2
  local CLEANUP_FUNC=$3

  local TEST_TOTAL=$(grep -c '<testcase' test_report.xml) || true
  local TEST_SKIPPED=$(grep -c '<skipped' test_report.xml) || true
  local TEST_TOTAL=$((TEST_TOTAL-TEST_SKIPPED))
  local TEST_FAILED=$(grep -c '<failure' test_report.xml) || true
  if [[ "$TEST_FAILED" != "0" ]]; then
    local FAILURES=$(grep -B1 '<failure' test_report.xml | sed -ne 's/.*name="\([^"]*\)".*/\1/p' || true)
    VERF="-1"
    MESSAGE="Build OK - $TEST_NAME tests failures ($TEST_FAILED/$TEST_TOTAL failed):"$'\n'"$FAILURES"$'\n'"ganesha server log:"$'\n'"$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' $SERVER_LOG)"
    gerrit_publish_clean_exit $CLEANUP_FUNC
  fi

  echo $TEST_TOTAL
}



# make test_report current. keep old one because jenkins doesn't like if there's none...
touch test_report.xml
rm -f pcocc_*.{err,out}

###############
# Fetch sources
###############
#fetch nfs-ganesha from gerrithub
if ! [ -d nfs-ganesha/.git ]; then
  socksify git clone ssh://cea-gerrithub-hpc@review.gerrithub.io:29418/ffilz/nfs-ganesha.git
fi

( cd nfs-ganesha && socksify git fetch origin $GERRIT_REF )

#fetch libntirpc from github
if ! [ -d nfs-ganesha/src/libntirpc/.git ]; then
  ( cd nfs-ganesha/src && rm -rf libntirpc && socksify git clone https://github.com/nfs-ganesha/ntirpc.git libntirpc )
else
  ( cd nfs-ganesha/src/libntirpc && socksify git fetch --all )
fi

#update working directory with current tested patch
( cd nfs-ganesha && git checkout $REVISION && socksify git submodule update --init )

#skip commits with WIP/RFC
if GIT_DIR=nfs-ganesha/.git git show --format=oneline --quiet | grep -qE "^WIP|^RFC|^FYI"; then
  exit 0
fi

#check empty build directory
if [[ ! -d nfs-ganesha/build ]]; then
  mkdir nfs-ganesha/build
else
  rm -rf nfs-ganesha/build/*
fi

#######################
# TEST_9P_VFS
#######################
cleanup_9P_VFS() {
  pcocc ssh -j $PCOCC_ID vm0 -- sudo poweroff || true
  pcocc ssh -j $PCOCC_ID vm1 -- sudo poweroff || true
  rm -rf $HOME/.pcocc/job_$PCOCC_ID
}

if [[ $TEST_9P_VFS == "true" ]] ; then

  rm -f server_logs mount_logs test_logs

  #####################
  # LAUNCH PCOCC VM
  #####################
  PCOCC_ID=$(pcocc batch -p $PCOCC_PARTITION -c 4 -N 1 ${PCOCC_TEMPLATE_GANESHA_CI_9P}:2 | awk '{print $NF}')

  PCOCC_FILE='~/.pcocc/pcocc_${PCOCC_ID}_vm_0'

  #####################
  # Test with ssh if the pcocc vm is successfully started
  #####################
  # VM sometimes refuse first ssh, try twice:
  pcocc ssh -j $PCOCC_ID -o ConnectTimeout=600 vm0 -- "echo VM started" || { sleep 10; pcocc ssh -j $PCOCC_ID -o ConnectTimeout=600 vm0 -- "echo VM started"; }


  #####################
  # Copy ganesha source
  #####################
  pcocc scp -j $PCOCC_ID -r nfs-ganesha root@vm0:/opt/nfs-ganesha
  pcocc scp -j $PCOCC_ID -r nfs-ganesha root@vm1:/opt/nfs-ganesha

  #####################
  # CONFIG GANESHA ON vm0
  #####################

  if ! pcocc ssh -j $PCOCC_ID root@vm0 -- "cd /opt/nfs-ganesha/build && cmake /opt/nfs-ganesha/src/ $CMAKE_OPTS_9P_VFS"; then
      VERF="-1"
      MESSAGE="Cmake failed:"$'\n'$(pcocc ssh -j $PCOCC_ID root@vm0 -- "cd /opt/nfs-ganesha/build && cmake /opt/nfs-ganesha/src/ $CMAKE_OPTS_9P_VFS 2>&1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' || true)
      gerrit_publish_clean_exit cleanup_9P_VFS
  fi

  #####################
  # BUILD GANESHA ON vm0
  #####################
  if ! pcocc ssh -j $PCOCC_ID root@vm0 "cd /opt/nfs-ganesha/build && make -j8 -k"; then
      VERF="-1"
      MESSAGE="Build failed:"$'\n'$(pcocc ssh -j $PCOCC_ID root@vm0 -- "cd /opt/nfs-ganesha/build && make -k 2>&1 >/dev/null" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' || true)
      gerrit_publish_clean_exit cleanup_9P_VFS
  fi

  #####################
  # LAUNCH GANESHA SERVER ON vm0
  #####################
  timeout 30m pcocc ssh -j $PCOCC_ID vm0 -- "sudo ASAN_OPTIONS='detect_leaks=0:detect_stack_use_after_return=1' gdb --batch --ex 'b __sanitizer::Die' --ex r --ex bt --args /opt/nfs-ganesha/build/MainNFSD/ganesha.nfsd -L STDOUT -F -f /opt/ganesha.conf.9p_vfs" 2>&1 | tee server_logs&
  SERVER=$!

  #####################
  # WAIT server is started on vm0
  #####################
  sleep 10

  #####################
  # 9P mount on /mnt on vm1
  #####################

  #TESTING IB between vm0 and vm1
  if ! pcocc ssh -j $PCOCC_ID vm1 -- "sudo ping -c 4 -W 1 10.251.0.1 -q >/dev/null" ; then
    #MOUNT ON TCP
    echo "WITH TCP"
    if ! pcocc ssh -j $PCOCC_ID vm1 "sudo mount -vvv -t 9p -o aname=tmp,cache=mmap,privport=1,posixacl,msize=1048576,trans=tcp 10.200.0.1 /mnt" | tee mount_logs; then
        VERF="-1"
        MESSAGE="Build OK - 9p mount failed on TCP\n\nmount:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' mount_logs)\nserver:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' server_logs)"
        gerrit_publish_clean_exit cleanup_9P_VFS
    fi
    else
    #MOUNT ON IB
    echo "WITH IB"
    if ! pcocc ssh -j $PCOCC_ID vm1 "sudo modprobe 9pnet_rdma; sleep 8; sudo mount -vvv -t 9p -o aname=tmp,cache=mmap,privport=1,posixacl,msize=1048576,trans=rdma,port=5640 10.251.0.1 /mnt" | tee mount_logs; then
        VERF="-1"
        MESSAGE="Build OK - 9p mount failed on IB RDMA\n\nmount:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' mount_logs)\nserver:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' server_logs)"
        gerrit_publish_clean_exit cleanup_9P_VFS
    fi
  fi

  #####################
  # SIGMUND TEST on vm1
  #####################
  timeout 30m pcocc ssh -j $PCOCC_ID vm1 -- sudo /opt/sigmund/sigmund.sh $SIGMUND_BEHAVIOUR_9P_VFS -j -q -s $SIGMUND_SPEED 2>&1 | tee test_logs || true


  #####################
  # umount on vm0 and stop server on vm1
  #####################
  timeout 1m pcocc ssh -j $PCOCC_ID vm1 -- sudo umount /mnt || true
  pcocc ssh -j $PCOCC_ID vm0 -- sudo pkill ganesha.nfsd || true

  if ! wait $SERVER || ! grep -q "exited normally" server_logs; then
    VERF="-1"
    MESSAGE="Build OK - server crashed/hang:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' server_logs)\ntest logs:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' test_logs)"
    gerrit_publish_clean_exit cleanup_9P_VFS
  fi

  #####################
  # Get back test_report.xml from vm1
  #####################
  get_back_test_report $PCOCC_ID "9P on VFS" server_logs test_logs cleanup_9P_VFS vm1

  #####################
  # Analyze and report result
  #####################
  TEST_TOTAL_9P=$(analyse_report_result "9P on VFS" server_logs cleanup_9P_VFS)

  # kill old VMs, we no longer need them.
  cleanup_9P_VFS
fi

#########################
# TEST_PROXY
# vm0:client , vm1:ganesha proxy , vm2:nfs-server
#########################
cleanup_proxy() {
  pcocc ssh -j $PCOCC_ID_PROXY -l root vm0 -- poweroff || true
  pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 -- poweroff || true
  pcocc ssh -j $PCOCC_ID_PROXY -l root vm2 -- poweroff || true
  rm -rf $HOME/.pcocc/job_$PCOCC_ID_PROXY
}


if [[ "$TEST_PROXY" == "true" ]]; then
  rm -f server_logs_proxy

  #####################
  # LAUNCH PCOCC VM
  #####################
  PCOCC_ID_PROXY=$(pcocc batch -p $PCOCC_PARTITION -c 2 -N 1 ${PCOCC_TEMPLATE_GANESHA_CI_PROXY}:3 | awk '{print $NF}')

  #####################
  # Test with ssh if the pcocc vm is successfully started
  #####################
  ## VM sometimes refuse first ssh, try twice:
  pcocc ssh -j $PCOCC_ID_PROXY -l root -o ConnectTimeout=600 vm0 -- "echo VM0 started" || { sleep 30; pcocc ssh -j $PCOCC_ID_PROXY -l root -o ConnectTimeout=600 vm0 -- "echo VM0 started"; }
  pcocc ssh -j $PCOCC_ID_PROXY -l root -o ConnectTimeout=600 vm1 -- "echo VM1 started" || { sleep 30; pcocc ssh -j $PCOCC_ID_PROXY -l root -o ConnectTimeout=600 vm1 -- "echo VM1 started"; }
  pcocc ssh -j $PCOCC_ID_PROXY -l root -o ConnectTimeout=600 vm2 -- "echo VM2 started" || { sleep 30; pcocc ssh -j $PCOCC_ID_PROXY -l root -o ConnectTimeout=600 vm2 -- "echo VM2 started"; }


  #####################
  # Copy ganesha source
  #####################
  pcocc scp -j $PCOCC_ID_PROXY -r nfs-ganesha root@vm0:/opt/nfs-ganesha
  pcocc scp -j $PCOCC_ID_PROXY -r nfs-ganesha root@vm1:/opt/nfs-ganesha


  #####################
  # CONFIG GANESHA ON vm1
  #####################

  if ! pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 -- "mkdir -p /opt/nfs-ganesha/build && cd /opt/nfs-ganesha/build && cmake -DCMAKE_BUILD_TYPE=Debug /opt/nfs-ganesha/src/"; then
      VERF="-1"
      MESSAGE="Cmake proxy failed:"$'\n'$(pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 -- "cd /opt/nfs-ganesha/build && cmake -DCMAKE_BUILD_TYPE=Debug /opt/nfs-ganesha/src/ 2>&1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' || true)
      gerrit_publish_clean_exit cleanup_proxy
  fi

  #####################
  # BUILD GANESHA ON vm1
  #####################
  if ! pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 "cd /opt/nfs-ganesha/build && make -j8 -k"; then
      VERF="-1"
      MESSAGE="Build proxy failed:"$'\n'$(pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 -- "cd /opt/nfs-ganesha/build && make -k 2>&1 >/dev/null" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' || true)
      gerrit_publish_clean_exit cleanup_proxy
  fi

  ######################
  # INSTALL GANESHA on vm1
  ######################
  if ! pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 "cd /opt/nfs-ganesha/build && make install"; then
      VERF="-1"
      MESSAGE="Install proxy failed:"$'\n'$(pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 -- "cd /opt/nfs-ganesha/build && make install 2>&1 >/dev/null" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' || true)
      gerrit_publish_clean_exit cleanup_proxy
  fi

  ########################
  # start nfs-server on vm2
  ########################
  timeout --preserve-status 2m pcocc ssh -j $PCOCC_ID_PROXY -l root vm2 -o ConnectTimeout=10 -- "systemctl start nfs-server"

  #####################
  # LAUNCH GANESHA SERVER ON vm1
  #####################
  # If you reenable this, remove grep exited normally below!
  #timeout 30m pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 -- "/usr/bin/ganesha.nfsd -L STDOUT -F -f /opt/ganesha.conf.fsal_proxy" 2>&1 | tee server_logs_proxy&
  timeout 30m pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 -- "gdb --batch --ex r --ex bt --args /usr/bin/ganesha.nfsd -L STDOUT -F -f /opt/ganesha.conf.fsal_proxy" 2>&1 | tee server_logs_proxy&
  SERVER_PROXY=$!

  NFS_VERS="4.1"

  #cleaning file
  rm -f mount_logs_proxy_$NFS_VERS test_logs_proxy_$NFS_VERS

  #####################
  # nfs mount on /mnt on vm0
  #####################
  if ! pcocc ssh -j $PCOCC_ID_PROXY -l root vm0 "mount -t nfs -o vers=$NFS_VERS vm1:/tmp_proxy /mnt" | tee mount_logs_proxy_$NFS_VERS; then
      VERF="-1"
      MESSAGE="Build OK - NFSv$NFS_VERS proxy mount failed\n\nmount proxy:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' mount_logs_proxy_$NFS_VERS)\nserver proxy:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' server_logs_proxy)"
      gerrit_publish_clean_exit cleanup_proxy
  fi

  #####################
  # SIGMUND TEST on vm0
  #####################
  timeout 30m pcocc ssh -j $PCOCC_ID_PROXY -l root vm0 -- /opt/sigmund/sigmund.sh allfs -j -q -s $SIGMUND_SPEED 2>&1 | tee test_logs_proxy_$NFS_VERS || true


  #####################
  # umount on vm0
  #####################
  timeout 1m pcocc ssh -j $PCOCC_ID_PROXY -l root vm0 -- umount /mnt || true

  #####################
  # Get back test_report.xml from vm0
  #####################
  get_back_test_report $PCOCC_ID_PROXY "PROXY NFSv$NFS_VERS" server_logs_proxy test_logs_proxy_$NFS_VERS cleanup_proxy vm0

  #####################
  # Analyze and report result
  #####################
  TEST_TOTAL_PROXY_41=$(analyse_report_result "client NFSv$NFS_VERS on FSAL_Proxy" server_logs_proxy cleanup_proxy)

  #We focus on NFSv4.1 and comment NFSv4.0
  TEST_TOTAL_PROXY_40="0"
  #NFSv3 tests are not yet stables.
  TEST_TOTAL_PROXY_3="0"

  #####################
  # stop servers ganesha and nfs
  #####################
  pcocc ssh -j $PCOCC_ID_PROXY -l root vm1 -- pkill ganesha.nfsd || true
  pcocc ssh -j $PCOCC_ID_PROXY -l root vm2 -- systemctl stop nfs-server || true

  if ! wait $SERVER_PROXY || ! grep -q "exited normally" server_logs_proxy; then
    # TEMP KLUDGE: ignore shutdown crash
    if ! grep -q "FSAL system destroyed" server_logs_proxy; then
      VERF="-1"
      MESSAGE="Build OK - ganesha server proxy crashed/hang:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' server_logs_proxy)\ntest logs:\n$(sed -e 's/\\/\\\\/g' -e 's/\"/\\\"/g' test_logs_proxy)"
      gerrit_publish_clean_exit cleanup_proxy
    fi
  fi

  cleanup_proxy
fi

#PUBLISH FINAL SUCCESS AND EXIT
VERF="1"
if [[ "$TEST_9P_VFS" == "true" && "$TEST_PROXY" != "true" ]]; then
  MESSAGE="Build OK - tests OK ($TEST_TOTAL_9P 9P tests)"
elif [[ "$TEST_9P_VFS" == "true" && "$TEST_PROXY" == "true" ]]; then
  MESSAGE="Build OK - tests OK ($TEST_TOTAL_9P 9P tests and $TEST_TOTAL_PROXY_41 NFSv4.1 / $TEST_TOTAL_PROXY_40 NFSv4.0 / $TEST_TOTAL_PROXY_3 NFSv3 proxy tests)"
elif [[ "$TEST_9P_VFS" != "true" && "$TEST_PROXY" == "true" ]]; then
  MESSAGE="Build OK - tests OK ($TEST_TOTAL_PROXY_41 NFSv4.1 / $TEST_TOTAL_PROXY_40 NFSv4.0 / $TEST_TOTAL_PROXY_3 NFSv3 proxy tests)"
fi

gerrit_publish_exit
