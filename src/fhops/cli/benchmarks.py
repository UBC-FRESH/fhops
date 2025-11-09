"""Benchmark harness for FHOPS solvers."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from fhops.cli._utils import (
    format_operator_presets,
    operator_preset_help,
    parse_operator_weights,
    resolve_operator_presets,
)
from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics import solve_sa
from fhops.optimization.mip import build_model, solve_mip
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.telemetry import append_jsonl

console = Console()


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    path: Path


DEFAULT_SCENARIOS: tuple[BenchmarkScenario, ...] = (
    BenchmarkScenario("minitoy", Path("examples/minitoy/scenario.yaml")),
    BenchmarkScenario("med42", Path("examples/med42/scenario.yaml")),
    BenchmarkScenario("large84", Path("examples/large84/scenario.yaml")),
)


def _resolve_scenarios(user_paths: Sequence[Path] | None) -> list[BenchmarkScenario]:
    if not user_paths:
        return list(DEFAULT_SCENARIOS)

    scenarios: list[BenchmarkScenario] = []
    for idx, scenario_path in enumerate(user_paths, start=1):
        scenarios.append(BenchmarkScenario(f"user-{idx}", scenario_path))
    return scenarios


def _record_metrics(
    *,
    scenario: BenchmarkScenario,
    solver: str,
    objective: float,
    assignments: pd.DataFrame,
    kpis: Mapping[str, object],
    runtime_s: float,
    extra: dict[str, object] | None = None,
    operator_config: Mapping[str, float] | None = None,
    operator_stats: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "scenario": scenario.name,
        "scenario_path": str(scenario.path),
        "solver": solver,
        "objective": float(objective),
        "runtime_s": runtime_s,
        "assignments": len(assignments),
    }
    for key, value in kpis.items():
        payload[f"kpi_{key}"] = value
    if extra:
        payload.update(extra)
    if operator_config is not None:
        payload["operators_config"] = json.dumps(dict(sorted(operator_config.items())))
    if operator_stats is not None:
        payload["operators_stats"] = json.dumps(
            {name: dict(sorted(stats.items())) for name, stats in sorted(operator_stats.items())}
        )
    return payload


def run_benchmark_suite(
    scenario_paths: Sequence[Path] | None,
    out_dir: Path,
    *,
    time_limit: int = 300,
    sa_iters: int = 5000,
    sa_seed: int = 42,
    driver: str = "auto",
    include_mip: bool = True,
    include_sa: bool = True,
    debug: bool = False,
    operators: Sequence[str] | None = None,
    operator_weights: Mapping[str, float] | None = None,
    operator_presets: Sequence[str] | None = None,
    telemetry_log: Path | None = None,
    preset_comparisons: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Execute the benchmark suite and return the summary DataFrame."""
    scenarios = _resolve_scenarios(scenario_paths)
    if not scenarios:
        raise typer.BadParameter("No scenarios resolved for benchmarking.")

    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for bench in scenarios:
        resolved_path = bench.path.expanduser()
        if not resolved_path.exists():
            raise FileNotFoundError(f"Scenario not found: {resolved_path}")
        sc = load_scenario(str(resolved_path))
        pb = Problem.from_scenario(sc)
        scenario_out = out_dir / bench.name
        scenario_out.mkdir(parents=True, exist_ok=True)

        if include_mip:
            build_start = time.perf_counter()
            # Use builder explicitly to measure build time; solve_mip will rebuild but cost is small.
            build_model(pb)
            build_time = time.perf_counter() - build_start

            start = time.perf_counter()
            mip_res = solve_mip(pb, time_limit=time_limit, driver=driver, debug=debug)
            mip_runtime = time.perf_counter() - start
            mip_assign = cast(pd.DataFrame, mip_res["assignments"]).copy()
            mip_assign.to_csv(scenario_out / "mip_assignments.csv", index=False)
            mip_kpis = compute_kpis(pb, mip_assign)
            rows.append(
                _record_metrics(
                    scenario=bench,
                    solver="mip",
                    objective=cast(float, mip_res.get("objective", 0.0)),
                    assignments=mip_assign,
                    kpis=mip_kpis,
                    runtime_s=mip_runtime,
                    extra={"build_time_s": build_time},
                )
            )

        preset_ops, preset_weights = resolve_operator_presets(operator_presets)
        override_weights = operator_weights or {}
        explicit_ops = [op.lower() for op in operators] if operators else []

        def build_label(presets: Sequence[str] | None, has_override: bool) -> str:
            if presets:
                return "+".join(presets)
            if has_override:
                return "custom"
            return "default"

        def build_sa_config(
            presets: Sequence[str] | None,
        ) -> tuple[str, list[str] | None, dict[str, float] | None]:
            preset_ops_local, preset_weights_local = resolve_operator_presets(presets)
            combined_ops_local = list(
                dict.fromkeys((preset_ops_local or []) + explicit_ops)
            ) or None
            combined_weights_local: dict[str, float] = {}
            combined_weights_local.update(preset_weights_local)
            combined_weights_local.update(override_weights)
            label_local = build_label(presets, bool(override_weights or explicit_ops))
            return label_local, combined_ops_local, combined_weights_local or None

        runs: list[tuple[str, list[str] | None, dict[str, float] | None]] = []
        base_label, combined_ops, combined_weights = build_sa_config(operator_presets)
        runs.append((base_label, combined_ops, combined_weights))

        if preset_comparisons:
            for preset_name in preset_comparisons:
                comparison_label, comp_ops, comp_weights = build_sa_config([preset_name])
                runs.append((comparison_label, comp_ops, comp_weights))

        if include_sa:
            for preset_label, ops_config, weight_config in runs:
                start = time.perf_counter()
                sa_res = solve_sa(
                    pb,
                    iters=sa_iters,
                    seed=sa_seed,
                    operators=ops_config,
                    operator_weights=weight_config,
                )
                sa_runtime = time.perf_counter() - start
                sa_assign = cast(pd.DataFrame, sa_res["assignments"]).copy()
                output_name = (
                    f"sa_assignments_{preset_label.replace('+', '_')}.csv"
                    if preset_label not in {"default", "custom"}
                    else "sa_assignments.csv"
                )
                sa_assign.to_csv(scenario_out / output_name, index=False)
                sa_kpis = compute_kpis(pb, sa_assign)
                sa_meta = cast(dict[str, Any], sa_res.get("meta", {}))
                extra = {
                    "iters": sa_iters,
                    "seed": sa_seed,
                    "sa_initial_score": sa_meta.get("initial_score"),
                    "sa_acceptance_rate": sa_meta.get("acceptance_rate"),
                    "sa_accepted_moves": sa_meta.get("accepted_moves"),
                    "sa_proposals": sa_meta.get("proposals"),
                    "sa_restarts": sa_meta.get("restarts"),
                    "preset_label": preset_label,
                }
                operators_meta = cast(dict[str, float], sa_meta.get("operators", {}))
                operator_stats = cast(
                    dict[str, dict[str, float]], sa_meta.get("operators_stats", {})
                )
                resolved_weights = operators_meta or (weight_config or {})
                rows.append(
                    _record_metrics(
                        scenario=bench,
                        solver="sa",
                        objective=cast(float, sa_res.get("objective", 0.0)),
                        assignments=sa_assign,
                        kpis=sa_kpis,
                        runtime_s=sa_runtime,
                        extra=extra,
                        operator_config=resolved_weights,
                        operator_stats=operator_stats,
                    )
                )
                if telemetry_log:
                    log_record = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "source": "bench-suite",
                        "scenario": sc.name,
                        "scenario_path": str(resolved_path),
                        "solver": "sa",
                        "seed": sa_seed,
                        "iterations": sa_iters,
                        "objective": cast(float, sa_res.get("objective", 0.0)),
                        "kpis": sa_kpis,
                        "operators_config": resolved_weights,
                        "operators_stats": operator_stats,
                        "preset_label": preset_label,
                    }
                    append_jsonl(telemetry_log, log_record)

    summary = pd.DataFrame(rows)
    if not summary.empty:
        mip_objectives = (
            summary[summary["solver"] == "mip"].set_index("scenario")["objective"].to_dict()
        )
        summary["objective_vs_mip_gap"] = summary.apply(
            lambda row: (
                mip_objectives.get(row["scenario"], float("nan")) - row["objective"]
                if row["solver"] != "mip" and row["scenario"] in mip_objectives
                else 0.0
                if row["solver"] == "mip"
                else pd.NA
            ),
            axis=1,
        )
        summary["objective_vs_mip_ratio"] = summary.apply(
            lambda row: (
                row["objective"] / mip_objectives[row["scenario"]]
                if row["solver"] != "mip"
                and row["scenario"] in mip_objectives
                and mip_objectives[row["scenario"]] not in (0, None)
                else 1.0
                if row["solver"] == "mip"
                else pd.NA
            ),
            axis=1,
        )

    summary_csv = out_dir / "summary.csv"
    summary_json = out_dir / "summary.json"
    summary.sort_values(["scenario", "solver"]).to_csv(summary_csv, index=False)
    summary.to_json(summary_json, orient="records", indent=2)

    table = Table(title="FHOPS Benchmark Summary")
    display_columns = ["scenario", "solver"]
    if "preset_label" in summary.columns:
        display_columns.append("preset_label")
    display_columns.extend(["objective", "runtime_s", "assignments"])
    for column in display_columns:
        table.add_column(column)
    for record in summary.sort_values(["scenario", "solver"]).to_dict(orient="records"):
        row = [
            str(record["scenario"]),
            str(record["solver"]),
        ]
        if "preset_label" in summary.columns:
            row.append(str(record.get("preset_label", "")))
        row.extend(
            [
                f"{record.get('objective', 0.0):.3f}",
                f"{record.get('runtime_s', 0.0):.2f}",
                str(record.get("assignments", 0)),
            ]
        )
        table.add_row(*row)
    console.print(table)

    return summary


benchmark_app = typer.Typer(add_completion=False, help="Benchmark FHOPS solvers.")


@benchmark_app.command("suite")
def bench_suite(
    scenario: list[Path] | None = typer.Option(
        None,
        "--scenario",
        "-s",
        help="Scenario YAML path(s) to benchmark. Defaults to built-in sample scenarios.",
    ),
    out_dir: Path = typer.Option(
        Path("tmp/benchmarks"), "--out-dir", dir_okay=True, file_okay=False
    ),
    time_limit: int = typer.Option(300, help="MIP time limit (seconds)"),
    sa_iters: int = typer.Option(5000, help="Simulated annealing iterations"),
    sa_seed: int = typer.Option(42, help="Simulated annealing RNG seed"),
    driver: str = typer.Option("auto", help="HiGHS driver: auto|appsi|exec"),
    include_mip: bool = typer.Option(True, help="Include MIP solver in benchmarks"),
    include_sa: bool = typer.Option(True, help="Include simulated annealing in benchmarks"),
    debug: bool = typer.Option(False, help="Forward debug flag to solvers"),
    operator: list[str] | None = typer.Option(
        None,
        "--operator",
        "-o",
        help="Enable specific SA operators (repeatable). Defaults to all.",
    ),
    operator_weight: list[str] | None = typer.Option(
        None,
        "--operator-weight",
        "-w",
        help="Set SA operator weight as name=value (repeatable).",
    ),
    operator_preset: list[str] | None = typer.Option(
        None,
        "--operator-preset",
        "-P",
        help=f"Apply SA operator preset ({operator_preset_help()}). Repeatable.",
    ),
    list_operator_presets: bool = typer.Option(
        False, "--list-operator-presets", help="Show available operator presets and exit."
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append telemetry records for each SA run to JSONL.",
        writable=True,
        dir_okay=False,
    ),
    compare_preset: list[str] | None = typer.Option(
        None,
        "--compare-preset",
        "-C",
        help="Run additional SA passes for each preset and include them in the summary.",
    ),
):
    """Run the full benchmark suite and emit summary CSV/JSON outputs."""
    weight_config: dict[str, float]
    if list_operator_presets:
        console.print("Operator presets:")
        console.print(format_operator_presets())
        raise typer.Exit()

    try:
        _, preset_weights = resolve_operator_presets(operator_preset)
        weight_config = parse_operator_weights(operator_weight)
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise typer.BadParameter(str(exc)) from exc
    combined_weights = dict(preset_weights)
    combined_weights.update(weight_config)
    run_benchmark_suite(
        scenario_paths=scenario,
        out_dir=out_dir,
        time_limit=time_limit,
        sa_iters=sa_iters,
        sa_seed=sa_seed,
        driver=driver,
        include_mip=include_mip,
        include_sa=include_sa,
        debug=debug,
        operators=operator,
        operator_weights=combined_weights if combined_weights else None,
        operator_presets=operator_preset,
        telemetry_log=telemetry_log,
        preset_comparisons=compare_preset,
    )
