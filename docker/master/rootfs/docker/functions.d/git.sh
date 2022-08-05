#!/bin/sh -e

git_clone_and_keep_updating() {
  REPO_URL="${1}"
  REPO_DIR="${2}"
  REPO_UPDATE_INTERVAL="${3}"
  REPO_GIT_BRANCH="${4:-master}"

  REPO_GIT_ERROR_LOG=$(mktemp)

  if [ ! -e "${REPO_DIR}/.git" ]; then
      # add --no-tags once we have a git version that supports it.
      if [ "${REPO_GIT_BRANCH}" != "*" ]; then
          git clone --single-branch -b "${REPO_GIT_BRANCH}" -- "${REPO_URL}" "${REPO_DIR}"
      else
          git clone -- "${REPO_URL}" "${REPO_DIR}"
      fi
  else
      # Lock the origin to what we are using now, and lock the fetch branches.
      # Do this regardless of how often the repo may be updated- this is to both enforce and fix
      # configuration in masters that switch from a branch to no branch (and vice versa).
      git -C "${REPO_DIR}" remote set-url origin "${REPO_URL}"
      git -C "${REPO_DIR}" remote set-branches origin "${REPO_GIT_BRANCH}"
      if [ "${REPO_GIT_BRANCH}" != "*" ]; then
          # we're locked to a specific branch; wipe the branches that are here and let the next refresh cleanup.
          git ls-remote "${REPO_DIR}" 'refs/remotes/origin/*' 'refs/tags/*' | awk '{print $2;}' | \
              xargs --no-run-if-empty -n1 git -C "${REPO_DIR}" update-ref -d
      fi
      # Also wipe tags from the repo to ensure that any old deploys don't have this still held in the refgraph.
      git -C "${REPO_DIR}" tag -l | xargs --no-run-if-empty -n1 git -C "${REPO_DIR}" tag -d
  fi
  # make git automatic git gc operations synchronous; this is to ensure we don't wind up with many backgrounded waiting on locks.
  git -C "${REPO_DIR}" config gc.autoDetach true
  # disable tag fetching since we don't actually checkout based on tags.
  git -C "${REPO_DIR}" config 'remote.origin.tagopt' '--no-tags'

  if [ "${REPO_UPDATE_INTERVAL:-0}" -eq "0" ]; then
      echo "Note: git updates are disabled."
      return 0
  fi
  # There's no need to kill this script if one iteration failed,
  # but printing out errors to stderr is useful.
  echo "Launching continous update from ${REPO_DIR}"
  echo "Checking every ${REPO_UPDATE_INTERVAL} seconds"
  (while true; do
      # force --prune to wipe any local refspecs no longer in the remote, while doing the update.
      git -C "${REPO_DIR}" remote update origin --prune > "${REPO_GIT_ERROR_LOG}" 2>&1 || cat "${REPO_GIT_ERROR_LOG}" 2>&1
      # if we're not locked to a branch, then we have nothing to enforce; it's just someone with an experimental master
      # wasting bandwidth for bitbucket...
      if [ "${REPO_GIT_BRANCH}" != "*" ]; then
          # force HEAD to point at 'master' (even if it doesn't exist- reset will fix that).
          # this ensures that we're resetting just master back to remotes/origin/master, and avoids
          # the apperance of us being on the wrong branch when in fact, we're forcing that local ref to point at the remote we want.
          git -C "${REPO_DIR}" symbolic-ref HEAD "refs/heads/${REPO_GIT_BRANCH}"
          # this code should probably force the working branch to be checked out to ${REPO_GIT_BRANCH}, but a hard reset to our target (if one is defined) accomplishes the same end result.
          # If we have a forced branch, this ensures we're always reset to that content; if not, then this ensures we're reset to at least what the current local branch is.
          git -C "${REPO_DIR}" reset --hard "remotes/origin/${REPO_GIT_BRANCH}" > "${REPO_GIT_ERROR_LOG}" 2>&1 || cat "${REPO_GIT_ERROR_LOG}" 2>&1
          git -C "${REPO_DIR}" clean -fd > "${REPO_GIT_ERROR_LOG}" 2>&1 || cat "${REPO_GIT_ERROR_LOG}" 2>&1
      fi
      # finally, do gc if needed.  This can probably be removed in light of the remote update from above.
      git -C "${REPO_DIR}" gc --auto --prune  > "${REPO_GIT_ERROR_LOG}" 2>&1 || cat "${REPO_GIT_ERROR_LOG}" 2>&1
      sleep "${REPO_UPDATE_INTERVAL}"
  done) &
}
