#!/bin/bash

# This script has the following workflow
#   1. Checkout the patch reference
#   2. Run clang format against the review.
#   3. Execute checkpatch

# It requires the following environment variables to be set
#   GERRIT_REFSPEC
#   GERRIT_PATCHSET_REVISION
#   GERRIT_PUBLISH
#   GERRITHUB_KEY
#   GERRIT_USER
#   JOB_URL

set -o pipefail 
set -x

# Avoid failures
GERRIT_PUBLISH=${GERRIT_PUBLISH:-'false'}
GERRIT_HOST=${GERRIT_HOST:-"review.gerrithub.io"}
GERRIT_PORT=${GERRIT_PORT:-"29418"}
GERRIT_PROJECT=${GERRIT_PROJECT:-"ffilz/nfs-ganesha"}

# Install the required pre-requisites
dnf -yq install git git-clang-format python3

if [[ -n "$GERRIT_REFSPEC" ]]; then
    GERRIT_PUBLISH=true
fi

# Checkout the patch
if [ ! -d nfs-ganesha ]; then
    git_project=$(basename "${GERRIT_PROJECT}")
    git_url="https://${GERRIT_HOST}/${GERRIT_PROJECT}"
    git init ${git_project}
    pushd ${git_project}
    git fetch --depth=2 "${git_url}" "${GERRIT_REFSPEC}"
    popd
fi

pushd nfs-ganesha
git checkout -b "${GERRIT_REFSPEC}" FETCH_HEAD
CLANG_OUTPUT=$(git clang-format -v \
    --diff \
    --style file:src/.clang-format \
    --extensions c,cc,cpp,h,hpp \
    HEAD~1)
CLANG_RETURN_VALUE=$?
popd

# Generate the Clang-format message based on the return value
# Here ** in the message is used to format the text in bold in Markdown
# Here \`\`\` is used to format the text in code block in Markdown
# EOF is used to end the heredoc to avoid issues with special characters and indentation
case ${CLANG_RETURN_VALUE} in
    0)
        CLANG_MSG="**🟢 Clang-format Check:** \`\`\`Passed\`\`\`"
        CLANG_FAILED=0
        ;;
    1)
        CLANG_MSG=$(cat <<EOF
**🔴 Clang-format Check:** \`\`\`Failed: Issues found\`\`\`

**Clang-failures:**
\`\`\`
${CLANG_OUTPUT}
\`\`\`

EOF
        )
        CLANG_FAILED=1
        ;;
    *)
        CLANG_MSG=$(cat <<EOF
**🔴 Clang-format Check:** \`Failed: Unknown state\`

**Clang-failures:**
\`\`\`
${CLANG_OUTPUT}
\`\`\`
EOF
        )
        CLANG_FAILED=1
        ;;
esac

# -----------------------
# Run checkpatch and capture its output
# -----------------------
pushd nfs-ganesha/src/scripts
# Making a copy of the checkpatch configuration file with leading dot as it is required by checkpatch.pl
cp checkpatch.conf .checkpatch.conf
CHECKPATCH_JSON=$(GIT_DIR=~/nfs-ganesha/.git git show --format=email | ./checkpatch.pl -q - | python3 ~/checkpatch-to-gerrit-json.py)
echo "Checkpatch JSON output: ${CHECKPATCH_JSON}"
if echo "$CHECKPATCH_JSON" | grep -q '"Checkpatch OK"'; then
    CHECKPATCH_FAILED=0
else
    echo "$CHECKPATCH_JSON" | jq -r '.comments'
    CHECKPATCH_FAILED=1
fi
popd

if [[ $CHECKPATCH_FAILED -eq 0 ]]; then
    CHECKPATCH_MSG="**🟢 Checkpatch lint:** \`\`\`Passed\`\`\`"
else
    # Generate a summary of checkpatch warnings/errors in a single-line format.
    # For each comment in the JSON:
    # - Extract the file name and (if available) the line number.
    # - Output the first line of the message (ignore multiline content).
    # - Format: <filename>[:<line>] - <message>
    # - Remove characters that could interfere with logs or shell scripts: ", `, $, \, '
    CHECKPATCH_SUMMARY=$(echo "$CHECKPATCH_JSON" | jq -r '
    .comments | to_entries[] |
    .key as $file |
    .value[] |
    "\($file)\(if .line then ":\(.line)" else "" end) - \(.message | split("\n")[0])"
    ' | sed 's/["`$\\'\'']//g')

    CHECKPATCH_MSG=$(cat <<EOF
**🔴 Checkpatch lint:** \`\`\`Failed\`\`\`

**Checkpatch-failure:**
\`\`\`
$(echo "$CHECKPATCH_SUMMARY")
\`\`\`
EOF
    )
fi

# -----------------------
# Combine messages
# -----------------------
FINAL_MESSAGE="${JOB_URL}:

${CLANG_MSG}
${CHECKPATCH_MSG}
"

# Determine Notify status
if [[ $CLANG_FAILED -eq 0 && $CHECKPATCH_FAILED -eq 0 ]]; then
    NOTIFY="--notify NONE"
    EXIT=0
else
    NOTIFY="--notify ALL"
    EXIT=1
fi

# -----------------------
# Final publish (only once)
# -----------------------
if [ "${GERRIT_PUBLISH}" == "true" ]; then
    ssh \
        -l ${GERRIT_USER} \
        -i ${GERRITHUB_KEY} \
        -o StrictHostKeyChecking=no \
        -p ${GERRIT_PORT} \
        ${GERRIT_HOST} \
        gerrit review \
            --message "'${FINAL_MESSAGE}'" \
            --project ${GERRIT_PROJECT} \
            ${NOTIFY} \
            ${GERRIT_PATCHSET_REVISION}
else
    echo "Review is not posted"
    echo "${FINAL_MESSAGE}"
fi
