#!/usr/bin/env python3
"""Summarize reference datasets for the SoftwareX manuscript assets."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DatasetTarget:
    slug: str
    scenario_path: Path
    label: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate dataset summaries + synthetic bundle for SoftwareX assets."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="Path to FHOPS repository root.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for dataset summaries (defaults to docs/softwarex/assets/data/datasets).",
    )
    parser.add_argument(
        "--synth-tier",
        default="small",
        help="Synthetic tier passed to `fhops synth generate`.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def inspect_table(csv_path: Path) -> dict[str, Any]:
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    return {
        "path": str(csv_path),
        "row_count": len(rows),
        "columns": fieldnames,
    }


def summarize_dataset(target: DatasetTarget) -> dict[str, Any]:
    data = load_yaml(target.scenario_path)
    base_dir = target.scenario_path.parent
    tables = {}
    machine_roles: dict[str, int] = {}

    table_keys = {
        "blocks": "blocks",
        "machines": "machines",
        "landings": "landings",
        "calendar": "calendar",
        "prod_rates": "prod_rates",
    }

    for key, csv_key in table_keys.items():
        rel = data.get("data", {}).get(csv_key)
        if rel:
            table_path = (base_dir / rel).resolve()
            tables[key] = inspect_table(table_path)
            if key == "machines":
                with table_path.open("r", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        role = (row.get("role") or "unassigned").strip() or "unassigned"
                        machine_roles[role] = machine_roles.get(role, 0) + 1
        else:
            tables[key] = {"path": None, "row_count": 0, "columns": []}

    start_date = data.get("start_date")
    if start_date is not None:
        start_date = str(start_date)

    summary = {
        "slug": target.slug,
        "label": target.label,
        "scenario_path": str(target.scenario_path),
        "name": data.get("name"),
        "num_days": data.get("num_days"),
        "start_date": start_date,
        "schema_version": data.get("schema_version", "1.0.0"),
        "objective_weights": data.get("objective_weights", {}),
        "tables": tables,
        "machine_roles": machine_roles,
    }
    return summary


def run_synth_bundle(repo_root: Path, tier: str, dest_dir: Path) -> Path:
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    cmd = [
        "python",
        "-m",
        "fhops.cli.main",
        "synth",
        "generate",
        str(dest_dir),
        "--tier",
        tier,
        "--overwrite",
    ]
    subprocess.run(cmd, cwd=repo_root, check=True)
    scenario_path = dest_dir / "scenario.yaml"
    if not scenario_path.exists():
        raise FileNotFoundError(f"Synthetic scenario not found at {scenario_path}")
    return scenario_path


def main() -> int:
    args = parse_args()
    repo_root: Path = args.repo_root.resolve()
    datasets_dir = (
        args.out_dir
        if args.out_dir is not None
        else repo_root / "docs" / "softwarex" / "assets" / "data" / "datasets"
    ).resolve()
    datasets_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        DatasetTarget(
            slug="minitoy",
            scenario_path=repo_root / "examples" / "minitoy" / "scenario.yaml",
            label="FHOPS MiniToy (examples/minitoy)",
        ),
        DatasetTarget(
            slug="med42",
            scenario_path=repo_root / "examples" / "med42" / "scenario.yaml",
            label="FHOPS Med42 (examples/med42)",
        ),
    ]

    synth_dir = datasets_dir / "synthetic_small"
    synth_scenario = run_synth_bundle(repo_root, args.synth_tier, synth_dir)
    targets.append(
        DatasetTarget(
            slug="synthetic_small",
            scenario_path=synth_scenario,
            label=f"Synthetic tier: {args.synth_tier}",
        )
    )

    summaries = []
    for target in targets:
        summary = summarize_dataset(target)
        summary_path = datasets_dir / f"{target.slug}_summary.json"
        with summary_path.open("w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        summaries.append(summary)
        print(f"[dataset] Wrote summary for {target.slug}: {summary_path}")

    index_path = datasets_dir / "index.json"
    with index_path.open("w", encoding="utf-8") as fh:
        json.dump({"datasets": summaries}, fh, indent=2)
    print(f"[dataset] Wrote dataset index: {index_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
