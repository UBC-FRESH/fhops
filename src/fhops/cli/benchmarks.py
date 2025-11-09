"""Benchmark harness for FHOPS solvers."""

from __future__ import annotations

import json
import math
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

from fhops.cli._utils import format_operator_presets, operator_preset_help, parse_operator_weights
from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics import solve_ils, solve_sa, solve_tabu
from fhops.optimization.mip import build_model, solve_mip
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.telemetry import append_jsonl
from fhops.cli.profiles import (
    Profile,
    combine_solver_configs,
    format_profiles as format_profile_list,
    get_profile,
    merge_profile_with_cli,
)

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
    time_limit: int = 1800,
    sa_iters: int = 5000,
    sa_seed: int = 42,
    include_ils: bool = False,
    ils_iters: int | None = None,
    ils_seed: int | None = None,
    ils_batch_neighbours: int = 1,
    ils_workers: int = 1,
    ils_perturbation_strength: int = 3,
    ils_stall_limit: int = 10,
    ils_hybrid_use_mip: bool = False,
    ils_hybrid_mip_time_limit: int = 60,
    include_tabu: bool = False,
    tabu_iters: int | None = None,
    tabu_seed: int | None = None,
    tabu_tenure: int | None = None,
    tabu_stall_limit: int = 200,
    tabu_batch_neighbours: int = 1,
    tabu_workers: int = 1,
    driver: str = "auto",
    include_mip: bool = True,
    include_sa: bool = True,
    debug: bool = False,
    operators: Sequence[str] | None = None,
    operator_weights: Mapping[str, float] | None = None,
    operator_presets: Sequence[str] | None = None,
    telemetry_log: Path | None = None,
    preset_comparisons: Sequence[str] | None = None,
    profile: Profile | None = None,
) -> pd.DataFrame:
    """Execute the benchmark suite and return the summary DataFrame."""
    scenarios = _resolve_scenarios(scenario_paths)
    if not scenarios:
        raise typer.BadParameter("No scenarios resolved for benchmarking.")

    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    profile_sa_config = combine_solver_configs(profile.bench if profile else None, profile.sa if profile else None) if profile else None
    profile_ils_config = combine_solver_configs(profile.bench if profile else None, profile.ils if profile else None) if profile else None
    profile_tabu_config = combine_solver_configs(profile.bench if profile else None, profile.tabu if profile else None) if profile else None

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

        override_weights = operator_weights or {}
        explicit_ops = [op.lower() for op in operators] if operators else []

        def build_label(presets: Sequence[str] | None, has_override: bool) -> str:
            if presets:
                return "+".join(presets)
            if has_override:
                return "custom"
            return "default"

        def build_sa_run(
            presets: Sequence[str] | None,
        ) -> tuple[str, Sequence[str] | None]:
            label_local = build_label(presets, bool(override_weights or explicit_ops))
            return label_local, presets

        runs: list[tuple[str, Sequence[str] | None]] = []
        base_label, base_presets = build_sa_run(operator_presets)
        runs.append((base_label, base_presets))

        if preset_comparisons:
            for preset_name in preset_comparisons:
                comparison_label, comp_presets = build_sa_run([preset_name])
                runs.append((comparison_label, comp_presets))

        if include_sa:
            for preset_label, run_presets in runs:
                combined_ops, combined_weights, batch_arg, worker_arg, multistart_arg, extra_kwargs = merge_profile_with_cli(
                    profile_sa_config,
                    run_presets,
                    override_weights,
                    explicit_ops,
                    None,
                    None,
                    None,
                )
                sa_kwargs = {
                    "iters": sa_iters,
                    "seed": sa_seed,
                    "operators": combined_ops,
                    "operator_weights": combined_weights if combined_weights else None,
                    "batch_size": batch_arg if batch_arg and batch_arg > 1 else None,
                    "max_workers": worker_arg if worker_arg and worker_arg > 1 else None,
                }
                sa_kwargs.update(extra_kwargs)
                start = time.perf_counter()
                sa_res = solve_sa(pb, **sa_kwargs)
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
                if profile:
                    sa_meta["profile"] = profile.name
                    sa_meta["profile_version"] = profile.version
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
                if profile:
                    extra["profile"] = profile.name
                    extra["profile_version"] = profile.version
                operators_meta = cast(dict[str, float], sa_meta.get("operators", {}))
                operator_stats = cast(
                    dict[str, dict[str, float]], sa_meta.get("operators_stats", {})
                )
                resolved_weights = operators_meta or (combined_weights or {})
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
                    if profile:
                        log_record["profile"] = profile.name
                        log_record["profile_version"] = profile.version
                    append_jsonl(telemetry_log, log_record)

        if include_ils:
            ils_ops, ils_weight_config, ils_batch_override, ils_worker_override, _, ils_extra_kwargs = merge_profile_with_cli(
                profile_ils_config,
                operator_presets,
                override_weights,
                explicit_ops,
                ils_batch_neighbours,
                ils_workers,
                None,
            )
            ils_batch_final = ils_batch_override if ils_batch_override is not None else ils_batch_neighbours
            ils_worker_final = ils_worker_override if ils_worker_override is not None else ils_workers
            if ils_extra_kwargs:
                if "perturbation_strength" in ils_extra_kwargs and ils_perturbation_strength == 3:
                    ils_perturbation_strength = int(ils_extra_kwargs.pop("perturbation_strength"))
                if "stall_limit" in ils_extra_kwargs and ils_stall_limit == 10:
                    ils_stall_limit = int(ils_extra_kwargs.pop("stall_limit"))
                if "hybrid_use_mip" in ils_extra_kwargs and not ils_hybrid_use_mip:
                    ils_hybrid_use_mip = bool(ils_extra_kwargs.pop("hybrid_use_mip"))
                if (
                    "hybrid_mip_time_limit" in ils_extra_kwargs
                    and ils_hybrid_mip_time_limit == 60
                ):
                    ils_hybrid_mip_time_limit = int(ils_extra_kwargs.pop("hybrid_mip_time_limit"))
            start = time.perf_counter()
            ils_res = solve_ils(
                pb,
                iters=ils_iters or sa_iters,
                seed=ils_seed or sa_seed,
                operators=ils_ops,
                operator_weights=ils_weight_config if ils_weight_config else None,
                batch_size=ils_batch_final if ils_batch_final and ils_batch_final > 1 else None,
                max_workers=ils_worker_final if ils_worker_final and ils_worker_final > 1 else None,
                perturbation_strength=ils_perturbation_strength,
                stall_limit=ils_stall_limit,
                hybrid_use_mip=ils_hybrid_use_mip,
                hybrid_mip_time_limit=ils_hybrid_mip_time_limit,
                **ils_extra_kwargs,
            )
            ils_runtime = time.perf_counter() - start
            ils_assign = cast(pd.DataFrame, ils_res["assignments"]).copy()
            ils_assign.to_csv(scenario_out / "ils_assignments.csv", index=False)
            ils_kpis = compute_kpis(pb, ils_assign)
            ils_meta = cast(dict[str, Any], ils_res.get("meta", {}))
            if profile:
                ils_meta["profile"] = profile.name
                ils_meta["profile_version"] = profile.version
            ils_weights = cast(dict[str, float], ils_meta.get("operators", {}))
            ils_stats = cast(dict[str, dict[str, float]], ils_meta.get("operators_stats", {}))
            extra_ils = {
                "iters": ils_iters or sa_iters,
                "seed": ils_seed or sa_seed,
                "perturbation_strength": ils_perturbation_strength,
                "stall_limit": ils_stall_limit,
                "hybrid_use_mip": ils_hybrid_use_mip,
                "hybrid_mip_time_limit": ils_hybrid_mip_time_limit,
                "improvement_steps": ils_meta.get("improvement_steps"),
            }
            if profile:
                extra_ils["profile"] = profile.name
                extra_ils["profile_version"] = profile.version
            rows.append(
                _record_metrics(
                    scenario=bench,
                    solver="ils",
                    objective=cast(float, ils_res.get("objective", 0.0)),
                    assignments=ils_assign,
                    kpis=ils_kpis,
                    runtime_s=ils_runtime,
                    extra=extra_ils,
                    operator_config=ils_weights or ils_weight_config or {},
                    operator_stats=ils_stats,
                )
            )
            if telemetry_log:
                record = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "bench-suite",
                    "scenario": sc.name,
                    "scenario_path": str(resolved_path),
                    "solver": "ils",
                    "seed": ils_seed or sa_seed,
                    "iterations": ils_iters or sa_iters,
                    "objective": cast(float, ils_res.get("objective", 0.0)),
                    "kpis": ils_kpis,
                    "operators_config": ils_weights or ils_weight_config,
                    "operators_stats": ils_stats,
                    "perturbation_strength": ils_perturbation_strength,
                    "stall_limit": ils_stall_limit,
                    "hybrid_use_mip": ils_hybrid_use_mip,
                    "hybrid_mip_time_limit": ils_hybrid_mip_time_limit,
                }
                if profile:
                    record["profile"] = profile.name
                    record["profile_version"] = profile.version
                append_jsonl(telemetry_log, record)

        if include_tabu:
            tabu_ops, tabu_weight_config, tabu_batch_override, tabu_worker_override, _, tabu_extra_kwargs = merge_profile_with_cli(
                profile_tabu_config,
                operator_presets,
                override_weights,
                explicit_ops,
                tabu_batch_neighbours,
                tabu_workers,
                None,
            )
            tabu_batch_final = tabu_batch_override if tabu_batch_override is not None else tabu_batch_neighbours
            tabu_worker_final = tabu_worker_override if tabu_worker_override is not None else tabu_workers
            if tabu_extra_kwargs:
                if "tabu_tenure" in tabu_extra_kwargs and (tabu_tenure is None or tabu_tenure == 0):
                    tabu_tenure = int(tabu_extra_kwargs.pop("tabu_tenure"))
                if "stall_limit" in tabu_extra_kwargs and tabu_stall_limit == 200:
                    tabu_stall_limit = int(tabu_extra_kwargs.pop("stall_limit"))
            start = time.perf_counter()
            tabu_res = solve_tabu(
                pb,
                iters=tabu_iters or sa_iters,
                seed=tabu_seed or sa_seed,
                operators=tabu_ops,
                operator_weights=tabu_weight_config if tabu_weight_config else None,
                batch_size=tabu_batch_final if tabu_batch_final and tabu_batch_final > 1 else None,
                max_workers=tabu_worker_final if tabu_worker_final and tabu_worker_final > 1 else None,
                tabu_tenure=tabu_tenure,
                stall_limit=tabu_stall_limit,
                **tabu_extra_kwargs,
            )
            tabu_runtime = time.perf_counter() - start
            tabu_assign = cast(pd.DataFrame, tabu_res["assignments"]).copy()
            tabu_assign.to_csv(scenario_out / "tabu_assignments.csv", index=False)
            tabu_kpis = compute_kpis(pb, tabu_assign)
            tabu_meta = cast(dict[str, Any], tabu_res.get("meta", {}))
            if profile:
                tabu_meta["profile"] = profile.name
                tabu_meta["profile_version"] = profile.version
            extra_tabu = {
                "iters": tabu_iters or sa_iters,
                "seed": tabu_seed or sa_seed,
                "tabu_tenure": tabu_meta.get("tabu_tenure"),
                "tabu_stall_limit": tabu_stall_limit,
            }
            if profile:
                extra_tabu["profile"] = profile.name
                extra_tabu["profile_version"] = profile.version
            rows.append(
                _record_metrics(
                    scenario=bench,
                    solver="tabu",
                    objective=cast(float, tabu_res.get("objective", 0.0)),
                    assignments=tabu_assign,
                    kpis=tabu_kpis,
                    runtime_s=tabu_runtime,
                    extra=extra_tabu,
                    operator_config=tabu_meta.get("operators", tabu_weight_config),
                    operator_stats=cast(dict[str, dict[str, float]], tabu_meta.get("operators_stats", {})),
                )
            )
            if telemetry_log:
                record = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "bench-suite",
                    "scenario": sc.name,
                    "scenario_path": str(resolved_path),
                    "solver": "tabu",
                    "seed": tabu_seed or sa_seed,
                    "iterations": tabu_iters or sa_iters,
                    "objective": cast(float, tabu_res.get("objective", 0.0)),
                    "kpis": tabu_kpis,
                    "operators_config": tabu_meta.get("operators", tabu_weight_config),
                    "operators_stats": tabu_meta.get("operators_stats"),
                    "tabu_tenure": tabu_meta.get("tabu_tenure"),
                    "tabu_stall_limit": tabu_stall_limit,
                }
                if profile:
                    record["profile"] = profile.name
                    record["profile_version"] = profile.version
                append_jsonl(telemetry_log, record)

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

        heuristic_mask = summary["solver"] != "mip"
        summary["solver_category"] = summary["solver"].map(
            lambda solver: "exact" if solver == "mip" else "heuristic"
        )
        best_solver_by_scenario: dict[str, str] = {}
        best_objective_by_scenario: dict[str, float] = {}
        best_runtime_by_scenario: dict[str, float] = {}
        if heuristic_mask.any():
            heuristics = summary[heuristic_mask]
            idx = heuristics.groupby("scenario")["objective"].idxmax()
            for scenario, index in idx.items():
                row = summary.loc[index]
                best_solver_by_scenario[scenario] = str(row["solver"])
                best_objective_by_scenario[scenario] = float(row["objective"])
                best_runtime_by_scenario[scenario] = float(row.get("runtime_s", float("nan")))
            summary["best_heuristic_solver"] = summary["scenario"].map(best_solver_by_scenario)
            summary["best_heuristic_objective"] = summary["scenario"].map(
                best_objective_by_scenario
            )
            summary["best_heuristic_runtime_s"] = summary["scenario"].map(
                best_runtime_by_scenario
            )
            summary["objective_gap_vs_best_heuristic"] = summary[
                "best_heuristic_objective"
            ] - summary["objective"]

            def _runtime_ratio(row: pd.Series) -> float | pd.NA:
                best_runtime = row.get("best_heuristic_runtime_s")
                runtime = row.get("runtime_s")
                if isinstance(best_runtime, (int, float)) and isinstance(runtime, (int, float)):
                    if best_runtime == 0 or math.isnan(best_runtime):
                        return pd.NA
                    return runtime / best_runtime
                return pd.NA

            summary["runtime_ratio_vs_best_heuristic"] = summary.apply(
                _runtime_ratio, axis=1
            )
        else:
            summary["best_heuristic_solver"] = pd.NA
            summary["best_heuristic_objective"] = pd.NA
            summary["best_heuristic_runtime_s"] = pd.NA
            summary["objective_gap_vs_best_heuristic"] = pd.NA
            summary["runtime_ratio_vs_best_heuristic"] = pd.NA

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
    time_limit: int = typer.Option(1800, help="MIP time limit (seconds, default 30 minutes)"),
    sa_iters: int = typer.Option(5000, help="Simulated annealing iterations"),
    sa_seed: int = typer.Option(42, help="Simulated annealing RNG seed"),
    include_ils: bool = typer.Option(False, help="Include Iterated Local Search in benchmarks"),
    ils_iters: int = typer.Option(250, help="Iterated Local Search iterations"),
    ils_seed: int = typer.Option(42, help="Iterated Local Search RNG seed"),
    ils_batch_neighbours: int = typer.Option(1, help="Neighbours sampled per ILS local search step"),
    ils_workers: int = typer.Option(1, help="Worker threads for ILS batched evaluation"),
    ils_perturbation_strength: int = typer.Option(3, help="ILS perturbation strength"),
    ils_stall_limit: int = typer.Option(10, help="ILS stall limit before restart/perturbation"),
    ils_hybrid_use_mip: bool = typer.Option(False, help="Enable hybrid MIP warm start in ILS"),
    ils_hybrid_mip_time_limit: int = typer.Option(60, help="Time limit (s) for hybrid MIP warm start"),
    include_tabu: bool = typer.Option(False, help="Include Tabu Search in benchmarks"),
    tabu_iters: int = typer.Option(5000, help="Tabu Search iterations"),
    tabu_seed: int = typer.Option(42, help="Tabu Search RNG seed"),
    tabu_tenure: int = typer.Option(0, help="Tabu tenure override (0=auto)"),
    tabu_stall_limit: int = typer.Option(200, help="Tabu stall limit"),
    tabu_batch_neighbours: int = typer.Option(1, help="Neighbours sampled per Tabu iteration"),
    tabu_workers: int = typer.Option(1, help="Worker threads for Tabu batched evaluation"),
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
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Apply a solver profile combining presets and advanced options.",
    ),
    list_profiles: bool = typer.Option(
        False, "--list-profiles", help="Show available solver profiles and exit."
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
        weight_config = parse_operator_weights(operator_weight)
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise typer.BadParameter(str(exc)) from exc
    if list_profiles:
        console.print("Solver profiles:")
        console.print(format_profile_list())
        raise typer.Exit()
    profile_obj: Profile | None = None
    if profile:
        try:
            profile_obj = get_profile(profile)
        except KeyError as exc:  # pragma: no cover - CLI validation
            raise typer.BadParameter(str(exc)) from exc
    run_benchmark_suite(
        scenario_paths=scenario,
        out_dir=out_dir,
        time_limit=time_limit,
        sa_iters=sa_iters,
        sa_seed=sa_seed,
        include_ils=include_ils,
        ils_iters=ils_iters,
        ils_seed=ils_seed,
        ils_batch_neighbours=ils_batch_neighbours,
        ils_workers=ils_workers,
        ils_perturbation_strength=ils_perturbation_strength,
        ils_stall_limit=ils_stall_limit,
        ils_hybrid_use_mip=ils_hybrid_use_mip,
        ils_hybrid_mip_time_limit=ils_hybrid_mip_time_limit,
        include_tabu=include_tabu,
        tabu_iters=tabu_iters,
        tabu_seed=tabu_seed,
        tabu_tenure=tabu_tenure if tabu_tenure > 0 else None,
        tabu_stall_limit=tabu_stall_limit,
        tabu_batch_neighbours=tabu_batch_neighbours,
        tabu_workers=tabu_workers,
        driver=driver,
        include_mip=include_mip,
        include_sa=include_sa,
        debug=debug,
        operators=operator,
        operator_weights=weight_config if weight_config else None,
        operator_presets=operator_preset,
        telemetry_log=telemetry_log,
        preset_comparisons=compare_preset,
        profile=profile_obj,
    )
