#!/bin/bash

set +x

mkdir -p ~/.config

cat > ~/.config/duffy <<EOF
client:
  url: https://duffy.ci.centos.org/api/v1
  auth:
    name: nfs-ganesha
    key: ${CICO_API_KEY}
EOF

readarray -t POOLS < <(duffy client list-pools | jq -r '.pools[].name')

LIST_POOLS=()
for i in "${POOLS[@]}"
do
        if [[ $i =~ ${CENTOS_VERSION}(s)*-x86_64 ]]; then
                LIST_POOLS+=($i)
        fi
done

if [[ $JOB_NAME =~ fsal-* ]] || [ "$JOB_NAME" == "pylint" ] || [ "$JOB_NAME" == "ganesha-build" ]; then
    node_count=1
else
    node_count=2
fi

for my_pool in ${LIST_POOLS[@]};
do
        if [[ $(duffy client show-pool $my_pool | jq -r '.pool.levels.ready') -gt 1 ]]; then
                SESSION=$(duffy client request-session pool="${my_pool}",quantity=$node_count)
                CHECK_ERR=$(echo ${SESSION} | jq -r '.error.detail')
                echo $CHECK_ERR
                if [ "${CHECK_ERR}" == "null" ]; then
                  echo "${SESSION}" | jq -r '.session.nodes[].ipaddr' > "${WORKSPACE}"/hosts
                  echo "${SESSION}" | jq -r '.session.id' > "${WORKSPACE}"/session_id
                  break
                else
                  echo -e "Failed to reserve node for the following reasons!\n-------------------------------------------------\n${CHECK_ERR}"
                fi
        fi
        sleep 60
        echo -n "."
done
