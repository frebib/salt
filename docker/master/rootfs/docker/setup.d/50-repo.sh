#!/bin/sh -e

. /docker/functions.d/common.sh

if [ -z "${SALT_REPO_URL}" ]; then
  echoerr "Salt repo URL not set, exiting..."
  exit 0
fi

. /docker/functions.d/git.sh

# note the SALT_REPO_BRANCH:-*; if no branch is specified, it's a personal (or at least, not under our enforced control)
# thus just pull all branches rather than locking to master.
git_clone_and_keep_updating "${SALT_REPO_URL}" "/etc/salt/repo" "${SALT_AUTO_PULL_INTERVAL:-15}" "${SALT_REPO_BRANCH:-*}"
