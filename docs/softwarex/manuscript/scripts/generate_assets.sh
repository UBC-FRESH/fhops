#!/usr/bin/env bash
set -euo pipefail

# Resolve important directories
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../../.." && pwd)"
assets_root="${repo_root}/docs/softwarex/assets"
data_dir="${assets_root}/data"
fig_dir="${assets_root}/figures"
bench_dir="${data_dir}/benchmarks"
dataset_dir="${data_dir}/datasets"

mkdir -p "${bench_dir}" "${fig_dir}" "${data_dir}"

echo "[assets] Regenerating FHOPS benchmark summaries into ${bench_dir}" >&2
rm -rf "${bench_dir}" && mkdir -p "${bench_dir}"

bench_args=(
  "bench"
  "suite"
  "--scenario" "examples/minitoy/scenario.yaml"
  "--out-dir" "${bench_dir}"
  "--telemetry-log" "${bench_dir}/telemetry.jsonl"
  "--time-limit" "60"
  "--sa-iters" "1000"
  "--driver" "auto"
  "--no-include-mip"
)

pushd "${repo_root}" >/dev/null
python -m fhops.cli.main "${bench_args[@]}"
popd >/dev/null

echo "[assets] Benchmarks ready. Summary CSV/JSON live under ${bench_dir}" >&2

echo "[assets] Rendering shared manuscript/doc snippets" >&2
python "${script_dir}/export_docs_assets.py" --repo-root "${repo_root}"

echo "[assets] Summarizing datasets into ${dataset_dir}" >&2
python "${script_dir}/run_dataset_inspection.py" --repo-root "${repo_root}" --out-dir "${dataset_dir}"
