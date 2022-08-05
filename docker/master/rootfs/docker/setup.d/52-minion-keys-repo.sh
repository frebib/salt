#!/bin/sh -e

if [ -z "${SALT_MINION_KEYS_REPO_URL}" ]; then
  exit 0
fi

. /docker/functions.d/git.sh
. /docker/functions.d/common.sh

set_target_subdir() {
  # SALT_REGION_NAME repos just store the minion keys in a directory named for the region,
  # thus they must be linked in differently.
  if [ -n "${SALT_REGION_NAME}" ]; then
    TARGET_SUBDIR="${TARGET_DIRECTORY}/${SALT_REGION_NAME}"
  # If COPY_REGIONAL_MINION_KEYS_TO_ROOT is set, pull all the keys from colos subfolders
  elif [ -n "${COPY_REGIONAL_MINION_KEYS_TO_ROOT}" ]; then
    TARGET_SUBDIR="${TARGET_DIRECTORY}/colos"
  # SALT_COLO_NAME just pulls keys out of a directory with the colo name
  elif [ -n "${SALT_COLO_NAME}" ]; then
    TARGET_SUBDIR="${TARGET_DIRECTORY}/colos/${SALT_COLO_NAME}"
  # for anything else there's only one dir in the repo checkout
  elif [ -z "${COPY_REGIONAL_MINION_KEYS_TO_ROOT}" ]; then
    TARGET_SUBDIR="${TARGET_DIRECTORY}/minions"
  fi
}

# This function should be run as a forked child process
symlink_keys () {
  while true; do
    # for each key file in the TARGET_SUBDIR create a symlink in the minions directory
    find "${TARGET_SUBDIR}" -type f -exec ln -sfn {} /etc/salt/pki/master/minions/ \;
    # if the key was removed from the git repo, the symlink will be invalid, so
    # clean-up invalid symlinks
    find /etc/salt/pki/master/minions -xtype l -delete
    # quit, if SALT_AUTO_PULL_INTERVAL is explicitly set to '0', otherwise loop
    # with the same interval as git_clone_and_keep_updating above
    if [ "${SALT_AUTO_PULL_INTERVAL:-15}" -eq "0" ]; then
      break
    fi
    sleep "${SALT_AUTO_PULL_INTERVAL:-15}"
  done
}

update_single_minion_key_repo() {
  TARGET_DIRECTORY="/var/tmp/minion-keys"
  set_target_subdir

  # remove "symlink"-based minions directory from previous versions
  [ -L /etc/salt/pki/master/minions ] && rm -f /etc/salt/pki/master/minions

  mkdir -p /etc/salt/pki/master/minions

  # if the target isn't a git repo, move it aside. This occurs when converting to SALT_MINION_KEYS_REPO_URL for
  # a host that tracked keys locally.
  if [ -e "${TARGET_DIRECTORY}" ] && [ ! -d "${TARGET_DIRECTORY}/.git" ]; then
    echoerr "Minion keys directory exists, but isn't a git repo.  Renaming to ${TARGET_DIRECTORY}-backup"
    mv "${TARGET_DIRECTORY}" "${TARGET_DIRECTORY}-backup"
  fi

  git_clone_and_keep_updating "${SALT_MINION_KEYS_REPO_URL}" "${TARGET_DIRECTORY}" "${SALT_AUTO_PULL_INTERVAL:-15}" "${SALT_MINION_KEYS_REPO_BRANCH:-master}"

  if [ -n "${TARGET_SUBDIR}" ]; then
      symlink_keys &
  fi
}

update_multi_minion_key_repos() {
  mkdir -p /etc/salt/pki/master/minions

  printf "${SALT_MINION_KEYS_REPO_URL}" | python3 -c 'import sys ; print("\n".join(sys.stdin.read().split()))' | while read REPO_URL ; do
    TARGET_DIRECTORY="/var/tmp/minion-keys-$(printf "${REPO_URL}" | sed -E 's~^.*/(.+)\.git~\1~')"
    set_target_subdir

    git_clone_and_keep_updating "${REPO_URL}" "${TARGET_DIRECTORY}" "${SALT_AUTO_PULL_INTERVAL:-15}" "${SALT_MINION_KEYS_REPO_BRANCH:-master}"

    if [ -n "${TARGET_SUBDIR}" ]; then
        symlink_keys &
    fi
  done
}

if printf "${SALT_MINION_KEYS_REPO_URL}" | grep -qsz -E '[[:space:]]' ; then
  update_multi_minion_key_repos
else
  update_single_minion_key_repo
fi
