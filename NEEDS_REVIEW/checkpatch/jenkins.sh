# actual script used in jenkins
# currently assumes the content of this folder is available at ~/checkpatch,
# will eventually clone this repo

# variables availables:
# GERRIT_PUBLISH (false): Whether to submit checkpatch result
# GERRIT_REF (next): Reference used to push to gerrit e.g. 243215/3
# REVISION (next): git commit revision to check
# GERRIT_USER (): your gerrit username. Access is provided through either ssh key or jenkins user agent

set -o pipefail

# gerrit plugin sets a number of variable, use them
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
