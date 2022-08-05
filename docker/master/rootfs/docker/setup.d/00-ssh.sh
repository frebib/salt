#!/bin/sh -e

. /docker/functions.d/common.sh

if [ "${SALT_REPO_URL}" = "" ] &&
   [ "${SALT_EDGE_PILLAR_REPO_URL}" = "" ] &&
   [ "${SALT_MINION_KEYS_REPO_URL}" = "" ]; then
  exit 0
fi

if [ ! -e /state/ssh ]; then
  echoerr "/state/ssh does not exist!"
  exit 1
fi

mkdir -p /root/.ssh
cp -a /state/ssh/* /root/.ssh
chown -R root:root /root/.ssh
chmod -R go-rwx /root/.ssh
