set -o pipefail

if [[ -n "$GERRIT_REFSPEC" ]]; then
  GERRIT_REF="$GERRIT_REFSPEC"
  REVISION="$GERRIT_PATCHSET_REVISION"
  GERRIT_PUBLISH=true
fi

if ! [ -d nfs-ganesha ]; then
  git clone -o gerrit ssh://$GERRIT_USER@review.gerrithub.io:29418/ffilz/nfs-ganesha.git
fi

( cd nfs-ganesha && git fetch gerrit $GERRIT_REF && git checkout $REVISION )

publish_checkpatch() {
  local SSH_GERRIT="ssh -p 29418 $GERRIT_USER@review.gerrithub.io"
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
  ( cd ~/checkpatch && ./checkpatch.pl -q - || true ) | \
  python ~/checkpatch/checkpatch-to-gerrit-json.py    | \
  publish_checkpatch
