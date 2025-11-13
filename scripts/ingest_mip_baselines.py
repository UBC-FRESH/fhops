#!/usr/bin/env python
"""Solve MIP baselines for scenarios and log results into the telemetry store."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from fhops.cli.main import _collect_tuning_scenarios
from fhops.evaluation.metrics.kpis import compute_kpis
from fhops.optimization.mip import solve_mip
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario
from fhops.telemetry.run_logger import RunTelemetryLogger


def _scenario_label(scenario_path: Path, scenario_obj: Any) -> str:
    return (
        getattr(scenario_obj, "name", None)
        or scenario_path.parent.name
        or scenario_path.stem
    )


def _scenario_features(scenario_obj: Any) -> dict[str, Any]:
    return {
        "num_days": getattr(scenario_obj, "num_days", None),
        "num_blocks": len(getattr(scenario_obj, "blocks", []) or []),
        "num_machines": len(getattr(scenario_obj, "machines", []) or []),
        "num_landings": len(getattr(scenario_obj, "landings", []) or []),
        "num_shift_calendar_entries": len(getattr(scenario_obj, "shift_calendar", []) or []),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        action="append",
        default=None,
        help="Scenario bundle alias or path (repeatable).",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        type=Path,
        help="Explicit scenario YAML paths (repeatable).",
    )
    parser.add_argument(
        "--telemetry-log",
        type=Path,
        required=True,
        help="Telemetry JSONL that will receive the MIP run records.",
    )
    parser.add_argument(
        "--tier-label",
        help="Optional tier label stored in telemetry context (e.g., long).",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=900,
        help="HiGHS time limit in seconds (default: 900).",
    )
    parser.add_argument(
        "--driver",
        default="auto",
        help="HiGHS driver override (auto|appsi|exec).",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to the telemetry log if it already exists (default is append).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress messages.",
    )
    return parser.parse_args(argv)


def ensure_log_ready(log_path: Path, append: bool) -> None:
    if append:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return
    if log_path.exists():
        log_path.unlink()
    sqlite_path = log_path.with_suffix(".sqlite")
    if sqlite_path.exists():
        sqlite_path.unlink()
    steps_dir = log_path.parent / "steps"
    if steps_dir.exists():
        for child in steps_dir.iterdir():
            if child.is_file():
                child.unlink()
        steps_dir.rmdir()
    log_path.parent.mkdir(parents=True, exist_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    telemetry_log = args.telemetry_log
    ensure_log_ready(telemetry_log, append=args.append)

    scenario_paths: list[Path] = list(args.scenario or [])
    bundle_specs: list[str] = list(args.bundle or [])

    resolved_scenarios: list[Path] = []
    bundle_map: dict[Path, dict[str, str]] = {}

    if scenario_paths:
        for scenario_path in scenario_paths:
            resolved_scenarios.append(scenario_path)

    if bundle_specs:
        bundle_scenarios, bundle_meta = _collect_tuning_scenarios([], bundle_specs)
        for scenario_path in bundle_scenarios:
            resolved_scenarios.append(scenario_path)
        bundle_map.update(bundle_meta)

    if not resolved_scenarios:
        raise SystemExit("No scenarios provided via --scenario or --bundle.")

    seen: set[Path] = set()
    for scenario_path in resolved_scenarios:
        scenario_resolved = scenario_path.resolve()
        if scenario_resolved in seen:
            continue
        seen.add(scenario_resolved)

        scenario_obj = load_scenario(str(scenario_path))
        if args.verbose:
            print(f"[MIP] Solving {scenario_path}")
        problem = Problem.from_scenario(scenario_obj)

        result = solve_mip(
            problem,
            time_limit=args.time_limit,
            driver=args.driver,
        )
        objective = float(result.get("objective", 0.0))
        assignments = pd.DataFrame(result["assignments"])
        kpis = compute_kpis(problem, assignments).to_dict()

        bundle_meta = bundle_map.get(scenario_resolved)
        scenario_label = _scenario_label(scenario_path, scenario_obj)
        features = _scenario_features(scenario_obj)
        context = {
            "source": "benchmark.mip",
            "scenario_features": features,
        }
        if args.tier_label:
            context["tier"] = args.tier_label
        if bundle_meta:
            context["bundle"] = bundle_meta.get("bundle")
            context["bundle_member"] = bundle_meta.get("bundle_member", scenario_label)

        with RunTelemetryLogger(
            log_path=telemetry_log,
            solver="mip",
            scenario=scenario_label,
            scenario_path=str(scenario_path),
            config={
                "time_limit": args.time_limit,
                "driver": args.driver,
            },
            context=context,
            step_interval=None,
        ) as run_logger:
            run_logger.finalize(
                status="ok",
                metrics={"objective": objective},
                extra={"status": "optimal"},
                kpis=kpis,
            )
        if args.verbose:
            print(
                f"[MIP] objective={objective:.3f} telemetry_run_id={run_logger.run_id}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
