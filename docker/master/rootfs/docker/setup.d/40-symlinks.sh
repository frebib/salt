#!/bin/sh -e

if [ ! -e /srv/salt ]; then
  ln -sf /etc/salt/repo/states /srv/salt
fi

if [ ! -e /srv/pillar ]; then
  ln -sf /etc/salt/repo/pillar /srv/pillar
fi
