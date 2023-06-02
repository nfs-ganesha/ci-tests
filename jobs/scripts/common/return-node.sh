#!/bin/bash
# A script that releases nodes from session ids

set +x

SESSION_ID=$(cat "${WORKSPACE}"/session_id)

duffy client retire-session "${SESSION_ID}" > /dev/null

duffy client list-sessions
