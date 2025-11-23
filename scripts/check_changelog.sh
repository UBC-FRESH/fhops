#!/usr/bin/env bash
set -euo pipefail

STAGED=$(git diff --cached --name-only)

if [ -n "$STAGED" ]; then
  if echo "$STAGED" | grep -q '^CHANGE_LOG\.md$'; then
    exit 0
  fi
else
  # When pre-commit runs with --all-files (e.g., in CI), nothing is staged.
  DIFF_FILES=""
  if PARENTS=$(git rev-list --parents -n 1 HEAD 2>/dev/null | cut -d' ' -f2-); then
    for parent in $PARENTS; do
      BASE=$(git merge-base HEAD "$parent")
      DIFF_FILES+=$'\n'"$(git diff --name-only "$BASE" HEAD)"
    done
  else
    DIFF_FILES=$(git show --name-only --pretty='' HEAD)
  fi

  if echo "$DIFF_FILES" | grep -q '^CHANGE_LOG\.md$'; then
    exit 0
  fi
fi

echo "CHANGE_LOG.md missing from this commit. Please add an entry before committing." >&2
exit 1
