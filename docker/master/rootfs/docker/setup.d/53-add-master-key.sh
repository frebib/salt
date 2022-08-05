#!/bin/sh -e

[ -z "${SALT_MASTER_KEY}" ] && exit

TARGET_DIRECTORY="/etc/salt/pki/master"

# Ensure ${TARGET_DIRECTORY} exists. Needed for instance if
# 52-minion-keys-repo.sh did not run.
mkdir -p "${TARGET_DIRECTORY}"

cp "${SALT_MASTER_KEY}" "${TARGET_DIRECTORY}/master.pem"
chmod 400 "${TARGET_DIRECTORY}/master.pem"
