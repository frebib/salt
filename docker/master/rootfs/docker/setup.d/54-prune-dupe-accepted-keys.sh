#!/bin/sh -e

if [ -z "${SALT_MINION_KEYS_REPO_URL}" ]; then
  exit 0
fi

prune_duplicate_keys_that_got_accepted() {
  SALT_PKI_DIR="${1}"

  # We might have an accepted key in multiple locations, this can happen when a new
  # minion connects to the master, is added to the git repo with minion keys, but is
  # never removed from pending/denied dir. This will cleanup such duplicated keys.
  # Steps:
  # 1. For every file in minions and minions_pre dir calculate sha1 sum and print it:
  #    $ d2aabf2afbfad9f7eaa236743b5a34c1bf7fd1ab  /etc/salt/pki/master/minions/36com11
  #    $ e2c7fe58f4b56f949c6cd343d4469f93588cd8cf  /etc/salt/pki/master/minions/36com36
  #    $ e2c7fe58f4b56f949c6cd343d4469f93588cd8cf  /etc/salt/pki/master/minions_pre/36com36
  # 2. Sort it and pass to uniq telling it to only print duplicated lines
  #    Dups are matched by first 40 chars of each line, since that's the length of sha1:
  #    $ e2c7fe58f4b56f949c6cd343d4469f93588cd8cf  /etc/salt/pki/master/minions/36com36
  #    $ e2c7fe58f4b56f949c6cd343d4469f93588cd8cf  /etc/salt/pki/master/minions_pre/36com36
  # 3. Then grep to only get keys in minions_pre dir, which is where pending/denied keys are
  #    $ e2c7fe58f4b56f949c6cd343d4469f93588cd8cf  /etc/salt/pki/master/minions_pre/36com36
  # 4. Remove keys that got returned by that.

  for prune_folder in minions_pre minions_denied; do
    if test -e "${SALT_PKI_DIR}/master/minions" && test -e "${SALT_PKI_DIR}/master/${prune_folder}"; then
      find -L "${SALT_PKI_DIR}/master/minions/" "${SALT_PKI_DIR}/master/${prune_folder}/" -type f -exec sha1sum '{}' ';' \
        | sort \
        | uniq --all-repeated=separate -w 40 \
        | grep "${SALT_PKI_DIR}/master/${prune_folder}/" \
        | while read SHA1 KEY_PATH ; do
          echo "Removing duplicate minion key ${KEY_PATH}, there is identical accepted key"
          rm -f "${KEY_PATH}"
        done
    fi
  done
}

(
  while sleep 10; do
    (
      prune_duplicate_keys_that_got_accepted /etc/salt/pki;
    )
  done
) &
