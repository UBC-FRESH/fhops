#!/usr/bin/env bash
# Keep the FHOPS public demo origin alive on 127.0.0.1:8780.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${FHOPS_PUBLIC_DEMO_SUPERVISOR_LOG:-/tmp/opencode/fhops-public-demo-supervisor.log}"
HEALTH="${ROOT}/scripts/public_demo_health.sh"
PORT="${PORT:-8780}"
APP_PATTERN="uvicorn demo_app:app --host 127.0.0.1 --port ${PORT}"

mkdir -p "$(dirname "$LOG")"

is_healthy() {
  PORT="$PORT" "$HEALTH" >/dev/null 2>&1
}

start_app() {
  # A hung origin can still own the port; clear it before rebinding.
  pkill -f "$APP_PATTERN" 2>/dev/null || true
  sleep 1
  (
    cd "$ROOT"
    PORT="$PORT" nohup ./run_public_demo.sh >>"$LOG" 2>&1 &
  )
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) started public demo on 127.0.0.1:${PORT}" >>"$LOG"
}

while true; do
  if ! is_healthy; then
    start_app
  fi
  sleep 5
done
