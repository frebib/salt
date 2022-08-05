# Salt master in a docker container

This image provides ready to use extensible salt master in a docker container.

State is stored in `/etc/salt` inside of the container and it's usually
bind-mounted from the stateful storage on the host. You can also change salt
configuration externally to the container if you need to.

## Modules

This image allows extensions: all scripts from `/docker/setup.d` are executed
in order on container startup.

### Bundled modules

The following modules are enabled by default.

#### `00-ssh.sh`

This module copies ssh configs and keys from `/state/ssh` into `/root/.ssh` and
fails if `/state/ssh` is missing. This is needed to allow `git` to clone and
update salt repo.

This module only runs if `SALT_REPO_URL` is set.

#### `10-logs.sh`

This module symlinks `/var/log/salt/master` into `/dev/stderr` if the log
dir is missing. This prevents complains from `salt` tool about log file
being unavailable.

#### `40-symlinks.sh`

This module creates the following symlinks, if the targets do not yet exist:

* `/etc/salt/repo/states` -> `/srv/salt`
* `/etc/salt/repo/pillar` -> `/srv/pillar`

#### `50-repo.sh`

This module clones salt repo from `SALT_REPO_URL` (if defined)
into `/etc/salt/repo` on container startup (if the dir is missing). It also
automatically updates the repo every `SALT_AUTO_PULL_INTERVAL` seconds, which
is 15 seconds by default.

#### `54-prune-dupe-accepted-keys.sh`

This module will keep checking minion keys (every 60s) and if it finds any
key that is in more than the accepted state. This usually happens when minion
keys are managed via a git repo rather than manually. It will remove the
pending/denied key file, leaving accepted key untouched.

#### `60-module-symlinks.sh`

This module does the job of `salt-run saltutil.sync_all`. When `salt-run`
needs to be manually run to sync python modules (grains, pillars, etc)
from `/srv/salt/_{grais,pillar,etc}` to `/var/cache/salt/master/extmods`,
this module just symlinks repo dirs in their cached destinations,
removing the need to run sync manually at any point.

#### `80-ps1.sh`

This module sets bash prompt to the following:

```
[salt-master] root@dev: / $
```

Here `salt-master` part can be modified by specifying `SALT_MASTER_NAME`.

## Functions

Reusable functions can be put in `/docker/functions.d` and imported by multiple
modules during start up. Functions have to be included in modules explicitly.

### Bundled functions

#### `git.sh`: `git_clone_and_keep_updating`

This function takes git repo url, target directory and a number of seconds
to wait between updates to the local copy. It closes the repo if needed
and keeps it updated with the remote.

## Running

To run this image as is:

```
docker run --rm -it --net host \
  -v /root/.ssh:/state/ssh \
  -v /state/salt/master/mymaster:/etc/salt \
  -v /state/salt/master/mymaster-cache:/var/cache/salt/master \
  -e SALT_REPO_URL=ssh://git@stash.cfops.it:7999/devops/salt.git \
  -e SALT_LOG_LEVEL=info \
  --name salt-master \
  docker-registry.cfdata.org/stash/plat/dockerfiles/salt-bullseye-master-base/master:<version>
```

This bootstrap everything needed in `/state/salt/master/mymaster` if this is
the first time your run master with this directory. The cache directory
is mounted from `/state/salt/master/mymaster-cache`, otherwise salt master
can become very confused on restart.

If `SALT_REPO_BRANCH` env variable is passed then `git reset --hard` and
`clean -fd` will be run after every pull to ensure there are no local
modifications to any files, and to ensure we're on the correct branch.

The minion keys equivalent is `SALT_MINION_REPO_BRANCH` and has the same semantics.
