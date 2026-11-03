#!/usr/bin/env bash
# Idempotently start the detached public-demo supervisor in tmux.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="${FHOPS_PUBLIC_DEMO_TMUX_SESSION:-fhops-public-demo}"
LOG="${FHOPS_PUBLIC_DEMO_SUPERVISOR_LOG:-/tmp/opencode/fhops-public-demo-supervisor.log}"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  exit 0
fi

mkdir -p "$(dirname "$LOG")"
tmux new-session -d -s "$SESSION" \
  "FHOPS_PUBLIC_DEMO_SUPERVISOR_LOG='$LOG' '$ROOT/scripts/public_demo_supervisor.sh'"
