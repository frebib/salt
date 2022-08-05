#!/bin/sh -e

USERLIST=/etc/salt/user-passwords

if [ ! -e "$USERLIST" ]; then
	exit 0
fi

IFS='
'
for l in `cat $USERLIST`; do
	USER=`echo $l | awk '{ print $1 }'`
	PASSWORD=`echo $l | awk '{ print $2 }'`
	if [ -n "$USER" -a -n "$PASSWORD" ]; then
		useradd "$USER" -p "$PASSWORD" -s /usr/bin/nologin
	fi
done

