#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../../.." && pwd)"
assets_root="${repo_root}/docs/softwarex/assets"
log_file="${assets_root}/benchmark_runs.log"
fast_mode="${FHOPS_ASSETS_FAST:-0}"

mkdir -p "${assets_root}"

start_iso="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
start_epoch="$(date +%s)"
commit_hash="$(cd "${repo_root}" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")"

echo "[benchmarks] Beginning asset regeneration (fast=${fast_mode}) at ${start_iso} (commit ${commit_hash})"

(
  cd "${repo_root}"
  FHOPS_ASSETS_FAST="${fast_mode}" bash "docs/softwarex/manuscript/scripts/generate_assets.sh"
)

end_epoch="$(date +%s)"
duration=$((end_epoch - start_epoch))

assets_hash="$(
  cd "${repo_root}"
  find docs/softwarex/assets -type f -print0 \
    | sort -z \
    | xargs -0 sha256sum \
    | sha256sum \
    | awk '{print $1}'
)"

{
  echo "run_started: ${start_iso}"
  echo "commit: ${commit_hash}"
  echo "fast_mode: ${fast_mode}"
  echo "duration_s: ${duration}"
  echo "assets_hash: ${assets_hash}"
  echo "----"
} >> "${log_file}"

echo "[benchmarks] Completed in ${duration}s (hash=${assets_hash}). Logged to ${log_file}"
