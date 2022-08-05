#!/bin/sh -e

for script in /docker/setup.d/*; do
  echo "running $script.."
  $script
done

# console log default is warning, but log-file-level default is info.
# honor those defaults unless explicitly overridden.
exec salt-master \
  --log-level="${SALT_MASTER_LOG_LEVEL:-${SALT_LOG_LEVEL:-warning}}" \
  --log-file-level="${SALT_MASTER_LOG_LEVEL:-${SALT_LOG_LEVEL:-info}}"
