#!/bin/sh -e

if [ -z "${SALT_TYPE}" ]; then
  echo 'SALT_TYPE is not defined' 1>&2
  exit 1
fi

# systemd ¯\_(ツ)_/¯
export container=docker

# Highstate on boot
[ "${SALT_NO_HIGHSTATE}" ] || systemctl enable salt-highstate

[ -s /etc/salt/minion_id ] || hostname > /etc/salt/minion_id

if [ ! -s /etc/salt/grains ]; then
    echo "environment: dev" > /etc/salt/grains
    echo "type: ${SALT_TYPE}" >> /etc/salt/grains
fi

# Concatenate grains files in /etc/salt/grains.d/ in numerical order.
# If a grain is found in multiple files, Salt will use the value from the last file
# that includes the grain.
if [ -d "/etc/salt/grains.d" ]; then
    cat $(find /etc/salt/grains.d/ -type f | sort -g) >> /etc/salt/grains
fi

if ! grep -q '^log_level' /etc/salt/minion; then
    echo "log_level: ${SALT_MINION_LOG_LEVEL:-${SALT_LOG_LEVEL:-info}}" \
         >> /etc/salt/minion
fi

# Remove all lists to enforce apt management from salt on the first run.
if [ ! -e /.salt-dev-not-first-run ]; then
    rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*
    touch /.salt-dev-not-first-run
fi

exec /sbin/init
