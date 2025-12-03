#!/usr/bin/env bash
set -euo pipefail

# Resolve important directories
# Fast-mode flag (FHOPS_ASSETS_FAST=1 cuts runtimes for quick iteration)
fast_mode="${FHOPS_ASSETS_FAST:-0}"
export FHOPS_ASSETS_FAST="${fast_mode}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../../.." && pwd)"
assets_root="${repo_root}/docs/softwarex/assets"
data_dir="${assets_root}/data"
fig_dir="${assets_root}/figures"
bench_dir="${data_dir}/benchmarks"
dataset_dir="${data_dir}/datasets"
tuning_dir="${data_dir}/tuning"
playback_dir="${data_dir}/playback"
cost_dir="${data_dir}/costing"
scaling_dir="${data_dir}/scaling"

mkdir -p "${bench_dir}" "${fig_dir}" "${data_dir}"

echo "[assets] Rendering shared manuscript/doc snippets" >&2
python "${script_dir}/export_docs_assets.py" --repo-root "${repo_root}"

echo "[assets] Rendering PRISMA workflow diagram" >&2
python "${script_dir}/render_prisma_diagram.py" --repo-root "${repo_root}"

echo "[assets] Summarizing datasets into ${dataset_dir}" >&2
python "${script_dir}/run_dataset_inspection.py" --repo-root "${repo_root}" --out-dir "${dataset_dir}"

synthetic_scenario="${dataset_dir}/synthetic_small/scenario.yaml"
if [[ ! -f "${synthetic_scenario}" ]]; then
  echo "[assets] ERROR: synthetic scenario not found at ${synthetic_scenario}" >&2
  exit 1
fi

default_time_limit="180"
default_sa_iters="2500"
default_ils_iters="400"
default_tabu_iters="2500"
default_ils_batch="1"
default_tabu_batch="1"
default_ils_workers="4"
default_tabu_workers="4"

if [[ "${fast_mode}" == "1" ]]; then
  default_time_limit="90"
  default_sa_iters="1200"
  default_ils_iters="220"
  default_tabu_iters="1400"
  default_ils_batch="1"
  default_tabu_batch="1"
  default_ils_workers="2"
  default_tabu_workers="2"
  echo "[assets] FAST mode enabled (FHOPS_ASSETS_FAST=1): lighter benchmark budgets." >&2
fi

echo "[assets] Regenerating FHOPS benchmark summaries into ${bench_dir}" >&2
rm -rf "${bench_dir}" && mkdir -p "${bench_dir}"

scenario_specs=(
  "${repo_root}/examples/tiny7/scenario.yaml|tiny7|Tiny7 reference scenario"
  "${repo_root}/examples/med42/scenario.yaml|med42|Med42 reference scenario"
  "${synthetic_scenario}|synthetic_small|Synthetic tier (small)"
)

declare -a bench_pids=()

for spec in "${scenario_specs[@]}"; do
  IFS="|" read -r scenario_path slug label <<< "${spec}"
  if [[ ! -f "${scenario_path}" ]]; then
    echo "[assets] WARN: skipping ${slug}; missing scenario ${scenario_path}" >&2
    continue
  fi

  (
    out_dir="${bench_dir}/${slug}"
    rm -rf "${out_dir}"
    mkdir -p "${out_dir}"

    telemetry="${out_dir}/telemetry.jsonl"
    printf "%s\n" "${label}" > "${out_dir}/label.txt"
    printf "%s\n" "${scenario_path}" > "${out_dir}/scenario_path.txt"

    case "${slug}" in
      tiny7)
        time_limit="${default_time_limit}"
        sa_local="${default_sa_iters}"
        ils_local="${default_ils_iters}"
        tabu_local="${default_tabu_iters}"
        ils_batch="${default_ils_batch}"
        tabu_batch="${default_tabu_batch}"
        ils_workers="${default_ils_workers}"
        tabu_workers="${default_tabu_workers}"
        if [[ "${fast_mode}" != "1" ]]; then
          time_limit="900"
          sa_local="8000"
          ils_local="1500"
          tabu_local="20000"
          ils_batch="4"
          tabu_batch="4"
          ils_workers="12"
          tabu_workers="12"
        fi
        ;;
      med42)
        time_limit="${default_time_limit}"
        sa_local="${default_sa_iters}"
        ils_local="${default_ils_iters}"
        tabu_local="${default_tabu_iters}"
        ils_batch="${default_ils_batch}"
        tabu_batch="${default_tabu_batch}"
        ils_workers="${default_ils_workers}"
        tabu_workers="${default_tabu_workers}"
        if [[ "${fast_mode}" != "1" ]]; then
          time_limit="2400"
          sa_local="20000"
          ils_local="4000"
          tabu_local="40000"
          ils_batch="6"
          tabu_batch="6"
          ils_workers="24"
          tabu_workers="24"
        fi
        ;;
      synthetic_small)
        time_limit="${default_time_limit}"
        sa_local="${default_sa_iters}"
        ils_local="${default_ils_iters}"
        tabu_local="${default_tabu_iters}"
        ils_batch="${default_ils_batch}"
        tabu_batch="${default_tabu_batch}"
        ils_workers="${default_ils_workers}"
        tabu_workers="${default_tabu_workers}"
        if [[ "${fast_mode}" != "1" ]]; then
          time_limit="600"
          sa_local="6000"
          ils_local="1200"
          tabu_local="15000"
          ils_batch="4"
          tabu_batch="4"
          ils_workers="12"
          tabu_workers="12"
        fi
        ;;
      *)
        time_limit="${default_time_limit}"
        sa_local="${default_sa_iters}"
        ils_local="${default_ils_iters}"
        tabu_local="${default_tabu_iters}"
        ils_batch="${default_ils_batch}"
        tabu_batch="${default_tabu_batch}"
        ils_workers="${default_ils_workers}"
        tabu_workers="${default_tabu_workers}"
        ;;
    esac

    if [[ "${fast_mode}" == "1" ]]; then
      case "${slug}" in
        tiny7)
          time_limit="450"
          sa_local="3000"
          ils_local="600"
          tabu_local="6000"
          ;;
        med42)
          time_limit="900"
          sa_local="6000"
          ils_local="1200"
          tabu_local="8000"
          ;;
        synthetic_small)
          time_limit="300"
          sa_local="2500"
          ils_local="500"
          tabu_local="4000"
          ;;
      esac
    fi

    echo "[assets] Running benchmark suite for ${slug} -> ${out_dir} (time=${time_limit}s, sa=${sa_local}, ils=${ils_local}, tabu=${tabu_local})" >&2
    bench_args=(
      "bench"
      "suite"
      "--scenario" "${scenario_path}"
      "--out-dir" "${out_dir}"
      "--telemetry-log" "${telemetry}"
      "--time-limit" "${time_limit}"
      "--sa-iters" "${sa_local}"
      "--driver" "auto"
      "--no-include-mip"
      "--include-ils"
      "--ils-iters" "${ils_local}"
      "--ils-batch-neighbours" "${ils_batch}"
      "--ils-workers" "${ils_workers}"
      "--include-tabu"
      "--tabu-iters" "${tabu_local}"
      "--tabu-stall-limit" "${tabu_local}"
      "--tabu-batch-neighbours" "${tabu_batch}"
      "--tabu-workers" "${tabu_workers}"
      "--compare-preset" "diversify"
      "--compare-preset" "mobilisation"
    )

    pushd "${repo_root}" >/dev/null
    python -m fhops.cli.main "${bench_args[@]}"
    popd >/dev/null
  ) &
  bench_pids+=("$!")
done

for pid in "${bench_pids[@]}"; do
  if ! wait "${pid}"; then
    echo "[assets] ERROR: benchmark worker ${pid} failed" >&2
    exit 1
  fi
done

python - <<'PY' "${bench_dir}"
import json
import sys
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit("Bench directory argument missing.")
bench_dir = Path(sys.argv[1])

index = []
for summary_path in sorted(bench_dir.glob("*/summary.json")):
    parent = summary_path.parent
    slug = parent.name
    telemetry = parent / "telemetry.jsonl"
    label_file = parent / "label.txt"
    label = label_file.read_text(encoding="utf-8").strip() if label_file.exists() else slug
    scenario_file = parent / "scenario_path.txt"
    scenario_path = scenario_file.read_text(encoding="utf-8").strip() if scenario_file.exists() else ""
    index.append(
        {
            "slug": slug,
            "label": label,
            "summary": str(summary_path.relative_to(bench_dir)),
            "telemetry": str(telemetry.relative_to(bench_dir)) if telemetry.exists() else "",
            "scenario": scenario_path,
        }
    )

with (bench_dir / "index.json").open("w", encoding="utf-8") as fh:
    json.dump({"benchmarks": index}, fh, indent=2)
print(f"[assets] Wrote benchmark index with {len(index)} entries to {bench_dir/'index.json'}")
PY

echo "[assets] Running tuning harness into ${tuning_dir}" >&2
python "${script_dir}/run_tuner.py" --repo-root "${repo_root}" --out-dir "${tuning_dir}" --tier "short"

echo "[assets] Running playback analysis into ${playback_dir}" >&2
python "${script_dir}/run_playback_analysis.py" --repo-root "${repo_root}" --out-dir "${playback_dir}"
echo "[assets] Rendering playback robustness figure" >&2
python "${script_dir}/plot_playback_variability.py" --repo-root "${repo_root}" --playback-dir "${playback_dir}" --out-path "${playback_dir}/utilisation_robustness.png"

echo "[assets] Running costing demo into ${cost_dir}" >&2
python "${script_dir}/run_costing_demo.py" --repo-root "${repo_root}" --out-dir "${cost_dir}"

echo "[assets] Running synthetic scaling sweep into ${scaling_dir}" >&2
python "${script_dir}/run_synthetic_sweep.py" --repo-root "${repo_root}" --out-dir "${scaling_dir}"

echo "[assets] Building solver/tuning tables" >&2
python "${script_dir}/build_tables.py" --repo-root "${repo_root}"
