#!/usr/bin/env python3
"""Generate machine cost estimates for the SoftwareX manuscript."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
from typing import Any

MACHINES = ["H1", "H2", "H3", "H4"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="FHOPS repository root.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Costing asset directory (defaults to docs/softwarex/assets/data/costing).",
    )
    return parser.parse_args()


def run_estimate(
    repo_root: Path,
    scenario_path: Path,
    machine_id: str,
    telemetry: Path,
    metrics: dict[str, float],
) -> None:
    cmd = [
        "python",
        "-m",
        "fhops.cli.main",
        "dataset",
        "estimate-cost",
        "--dataset",
        str(scenario_path),
        "--machine",
        machine_id,
        "--telemetry-log",
        str(telemetry),
        "--avg-stem-size",
        f"{metrics['avg_stem_size']}",
        "--volume-per-ha",
        f"{metrics['volume_per_ha']}",
        "--stem-density",
        f"{metrics['stem_density']}",
        "--ground-slope",
        f"{metrics['ground_slope']}",
        "--avg-stem-size-sigma",
        f"{metrics['avg_stem_size_sigma']}",
        "--volume-per-ha-sigma",
        f"{metrics['volume_per_ha_sigma']}",
        "--stem-density-sigma",
        f"{metrics['stem_density_sigma']}",
        "--ground-slope-sigma",
        f"{metrics['ground_slope_sigma']}",
    ]
    subprocess.run(cmd, cwd=repo_root, check=True)


def load_telemetry(log_path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not log_path.exists():
        return entries
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def summarize(entries: list[dict[str, Any]], dest: Path) -> None:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        inputs = entry.get("inputs", {})
        outputs = entry.get("outputs", {})
        rental_breakdown = outputs.get("rental_breakdown") or {}
        road_info = outputs.get("road") or {}
        rows.append(
            {
                "dataset": inputs.get("dataset"),
                "scenario_name": inputs.get("scenario_name"),
                "machine_id": inputs.get("machine_id"),
                "machine_role": inputs.get("machine_role"),
                "usage_hours": inputs.get("usage_hours"),
                "include_repair": inputs.get("include_repair"),
                "utilisation": outputs.get("utilisation"),
                "productivity_m3_per_pmh": outputs.get("productivity_m3_per_pmh"),
                "productivity_method": outputs.get("productivity_method"),
                "rental_rate_smh": outputs.get("rental_rate_smh"),
                "cost_per_m3": outputs.get("cost_per_m3"),
                "owning_cost_smh": rental_breakdown.get("ownership"),
                "operating_cost_smh": rental_breakdown.get("operating"),
                "repair_cost_smh": rental_breakdown.get("repair_maintenance"),
                "road_machine": road_info.get("machine_slug") if road_info else None,
                "road_length_m": road_info.get("road_length_m") if road_info else None,
                "road_total_cad": road_info.get("total_cost_target_cad") if road_info else None,
            }
        )
    if not rows:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    (dest.with_suffix(".json")).write_text(json.dumps(rows, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = (
        args.out_dir
        if args.out_dir is not None
        else repo_root / "docs" / "softwarex" / "assets" / "data" / "costing"
    ).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    telemetry = out_dir / "telemetry.jsonl"
    if telemetry.exists():
        telemetry.unlink()
    scenario_dir = repo_root / "examples" / "med42"
    scenario_path = scenario_dir / "scenario.yaml"
    blocks_path = scenario_dir / "data" / "blocks.csv"
    if not blocks_path.exists():
        raise FileNotFoundError(blocks_path)
    import pandas as pd  # local import to avoid hard dependency when unused

    blocks = pd.read_csv(blocks_path)
    metrics = {
        "avg_stem_size": float(blocks["avg_stem_size_m3"].mean()),
        "volume_per_ha": float(blocks["volume_per_ha_m3"].mean()),
        "stem_density": float(blocks["stem_density_per_ha"].mean()),
        "ground_slope": float(blocks["ground_slope_percent"].mean()),
        "avg_stem_size_sigma": 0.05,
        "volume_per_ha_sigma": float(blocks["volume_per_ha_m3_sigma"].mean()),
        "stem_density_sigma": float(blocks["stem_density_per_ha_sigma"].mean()),
        "ground_slope_sigma": 2.0,
    }

    for machine_id in MACHINES:
        print(f"[costing] {machine_id}")
        run_estimate(repo_root, scenario_path, machine_id, telemetry, metrics)
    entries = load_telemetry(telemetry)
    summarize(entries, out_dir / "cost_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
