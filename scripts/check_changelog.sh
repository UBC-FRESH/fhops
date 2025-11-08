#!/usr/bin/env bash
set -euo pipefail

if ! git diff --cached --name-only | grep -q '^CHANGE_LOG\.md$'; then
  echo "CHANGE_LOG.md missing from this commit. Please add an entry before committing." >&2
  exit 1
fi
