#!/bin/sh -e

. /docker/functions.d/common.sh

STATES_OWNER=$(stat -c '%U' /etc/salt/repo/states)

if [ "${STATES_OWNER}" != "root" ]; then
  # If modules are not owned by root (like in dev when you bind-mount),
  # salt tries to chown files to root. You don't want that to happen in dev.
  echoerr "/etc/salt/repo/states is not owned by root"
  echoerr "running \`salt-run saltutil.sync_all\` instead of symlinking"
  salt-run saltutil.sync_all
  exit 0
fi

if [ -e /var/cache/salt/master/extmods ]; then
  rm -r /var/cache/salt/master/extmods
fi

mkdir -p /var/cache/salt/master/extmods

for dir in /etc/salt/repo/states/_*; do
  type=${dir##*/_}
  if [ ! -e "/var/cache/salt/master/extmods/${type}" ]; then
    ln -sf "/etc/salt/repo/states/_${type}" "/var/cache/salt/master/extmods/${type}"
  fi
done
