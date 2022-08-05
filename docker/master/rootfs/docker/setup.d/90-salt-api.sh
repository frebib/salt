#!/bin/bash -e
# Use env variables for log level
# Defaults are set in salt config file
# log-level default is "warning"
# log-file-level is "info"
# see https://docs.saltstack.com/en/latest/ref/configuration/logging/ for reference
if [ -n "${SALT_MASTER_LOG_LEVEL}" ]; then
	OPTION=("--log-level=${SALT_MASTER_LOG_LEVEL}" "--log-file-level=${SALT_MASTER_LOG_LEVEL}")
elif [ -n "${SALT_LOG_LEVEL}" ]; then
	OPTION=("--log-level=${SALT_LOG_LEVEL}" "--log-file-level=${SALT_LOG_LEVEL}")
fi

if [ -n "${SALT_API_ENABLED}" ]; then
	salt-api --daemon "${OPTION[@]}"
fi
