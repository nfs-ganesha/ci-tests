set -o pipefail 
set -x

if [[ -n "$GERRIT_REFSPEC" ]]; then
  GERRIT_REF="$GERRIT_REFSPEC"
  REVISION="$GERRIT_PATCHSET_REVISION"
  GERRIT_PUBLISH=true
fi

if ! [ -d nfs-ganesha ]; then
  GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -i $GERRITHUB_KEY" git clone --depth=1 -o gerrit ssh://$GERRIT_USER@review.gerrithub.io:29418/ffilz/nfs-ganesha.git -v
fi

( cd nfs-ganesha && git fetch gerrit $GERRIT_REF && git checkout $REVISION )

publish_checkpatch() {
  local SSH_GERRIT="ssh -p 29418 -i $GERRITHUB_KEY $GERRIT_USER@review.gerrithub.io"
  if [[ "$GERRIT_PUBLISH" == "true" ]]; then
    tee /proc/$$/fd/1 | $SSH_GERRIT "gerrit review --json --project ffilz/nfs-ganesha $REVISION"
  else
    echo "Would have submit:"
    echo -n "echo '"
    cat
    echo "' | $SSH_GERRIT \"gerrit review --json --project ffilz/nfs-ganesha $REVISION\""
  fi 
}

# cd to ~/checkpatch for checkpatch.pl as a hack to get config without modifying $HOME
GIT_DIR=nfs-ganesha/.git git show --format=email      | \
  ( cd $WORKSPACE/ci-tests/build_scripts/checkpatch && ./checkpatch.pl -q - || true ) | \
  python $WORKSPACE/ci-tests/build_scripts/checkpatch/checkpatch-to-gerrit-json.py    | \
  publish_checkpatch


