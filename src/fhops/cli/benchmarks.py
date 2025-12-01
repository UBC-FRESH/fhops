"""Benchmark harness for FHOPS solvers.

This module powers the ``fhops bench`` Typer app.  It orchestrates benchmark runs across the
built-in sample scenarios (or user-provided bundles), persists solver assignments/KPIs, and emits
summary CSV/JSON tables that can be plotted or ingested into telemetry dashboards.  The docstrings
here intentionally mirror the CLI help text so the Sphinx API pages expose comparable guidance.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from fhops.cli._utils import (
    format_operator_presets,
    operator_preset_help,
    parse_objective_weight_overrides,
    parse_operator_weights,
)
from fhops.cli.profiles import (
    Profile,
    combine_solver_configs,
    format_profiles,
    get_profile,
    merge_profile_with_cli,
)
from fhops.cli.watch_dashboard import LiveWatch
from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics import solve_ils, solve_sa, solve_tabu
from fhops.optimization.mip import build_model, solve_mip
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.telemetry import append_jsonl
from fhops.telemetry.machine_costs import build_machine_cost_snapshots, summarize_machine_costs
from fhops.telemetry.watch import WatchConfig

console = Console()


@dataclass(frozen=True)
class BenchmarkScenario:
    """Scenario path paired with a friendly label.

    Attributes
    ----------
    name:
        Identifier used in summary tables and telemetry rows.
    path:
        Filesystem path to the ``scenario.yaml`` bundle.
    """

    name: str
    path: Path


DEFAULT_SCENARIOS: tuple[BenchmarkScenario, ...] = (
    BenchmarkScenario("tiny7", Path("examples/tiny7/scenario.yaml")),
    BenchmarkScenario("med42", Path("examples/med42/scenario.yaml")),
    BenchmarkScenario("large84", Path("examples/large84/scenario.yaml")),
    BenchmarkScenario("synthetic-small", Path("examples/synthetic/small/scenario.yaml")),
)


def _resolve_scenarios(user_paths: Sequence[Path] | None) -> list[BenchmarkScenario]:
    """Coerce user-provided scenario paths into BenchmarkScenario objects (or fall back to defaults)."""

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
    machine_costs_summary: str | None = None,
) -> dict[str, object]:
    """Serialise solver metrics (objective/KPIs/runtime) for the benchmark summary frame."""
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
    if machine_costs_summary:
        payload["machine_costs_summary"] = machine_costs_summary
    return payload


def run_benchmark_suite(
    scenario_paths: Sequence[Path] | None,
    out_dir: Path,
    *,
    time_limit: int = 1800,
    sa_iters: int = 5000,
    sa_seed: int = 42,
    sa_cooling_rate: float = 0.999,
    sa_restart_interval: int | None = None,
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
    objective_weight_overrides: Mapping[str, float] | None = None,
    telemetry_log: Path | None = None,
    preset_comparisons: Sequence[str] | None = None,
    profile: Profile | None = None,
    watch: bool = False,
    watch_refresh: float = 0.5,
) -> pd.DataFrame:
    """Execute the benchmark suite and return the summary DataFrame.

    Parameters
    ----------
    scenario_paths : Sequence[pathlib.Path] | None
        Optional list of scenario YAML paths to benchmark. ``None`` defaults to the bundled
        scenarios (tiny7 → med42 → large84 → synthetic-small).
    out_dir : pathlib.Path
        Directory that will contain per-scenario outputs, summary CSV/JSON, telemetry logs, and
        solver-specific assignment CSVs.
    time_limit : int, default=1800
        Time limit (seconds) for the MIP solve.
    sa_iters : int, default=5000
        Iteration budget for simulated annealing runs.
    sa_seed : int, default=42
        RNG seed for simulated annealing.
    sa_cooling_rate : float, default=0.999
        Cooling rate multiplier (closer to 1 slows cooling).
    sa_restart_interval : int | None, default=None
        Non-accepting iteration interval before SA restarts (``None`` auto-scales with iters).
    include_ils : bool, default=False
        When ``True`` run Iterated Local Search in addition to SA/MIP.
    ils_iters : int | None, default=None
        Iteration budget per ILS run (falls back to ``sa_iters`` when ``None``).
    ils_seed : int | None, default=None
        RNG seed for ILS (falls back to ``sa_seed`` when ``None``).
    ils_batch_neighbours : int, default=1
        Number of neighbours sampled per ILS local-search step.
    ils_workers : int, default=1
        Thread pool size for evaluating batched ILS neighbours.
    ils_perturbation_strength : int, default=3
        Count of perturbation steps applied during diversification.
    ils_stall_limit : int, default=10
        Non-improving ILS iterations before forcing perturbation/restarter logic.
    ils_hybrid_use_mip : bool, default=False
        When ``True`` fire a short MIP warm start if ILS stalls persist.
    ils_hybrid_mip_time_limit : int, default=60
        Time limit (seconds) for the hybrid MIP warm start.
    include_tabu : bool, default=False
        When ``True`` include Tabu Search runs.
    tabu_iters : int | None, default=None
        Iteration budget for Tabu Search (falls back to ``sa_iters`` when ``None``).
    tabu_seed : int | None, default=None
        RNG seed for Tabu Search (falls back to ``sa_seed`` when ``None``).
    tabu_tenure : int | None, default=None
        Override for Tabu tenure (``None`` lets the solver auto-tune based on problem size).
    tabu_stall_limit : int, default=200
        Non-improving Tabu iterations before diversification.
    tabu_batch_neighbours : int, default=1
        Number of neighbours evaluated per Tabu iteration.
    tabu_workers : int, default=1
        Thread pool size for evaluating batched Tabu neighbours.
    driver : str, default="auto"
        MIP driver (``auto | highs-appsi | highs-exec | gurobi*``) passed to
        :func:`fhops.optimization.mip.solve_mip`.
    include_mip : bool, default=True
        Toggle the exact MIP run (when ``False`` only heuristics are executed).
    include_sa : bool, default=True
        Toggle simulated annealing runs.
    debug : bool, default=False
        Enable additional solver logging (forwarded to :func:`solve_mip` and heuristics).
    operators : Sequence[str] | None, default=None
        Subset of SA operators to enable (defaults to registry defaults when ``None``).
    operator_weights : Mapping[str, float] | None, default=None
        Weight overrides for SA operators. Zero/negative values effectively disable the operator.
    operator_presets : Sequence[str] | None, default=None
        List of preset names to merge into the SA configuration (mirrors CLI ``--operator-preset``).
    objective_weight_overrides : Mapping[str, float] | None, default=None
        Optional objective weight overrides forwarded to SA/ILS/Tabu runs.
    telemetry_log : pathlib.Path | None, default=None
        Optional JSONL log file used to append run metadata per solver execution.
    preset_comparisons : Sequence[str] | None, default=None
        Additional SA presets to run for side-by-side comparisons (records carry ``preset_label``).
    profile : fhops.cli.profiles.Profile | None, default=None
        Optional solver profile object combining preset/operator/advanced overrides.
    watch : bool, default=False
        Enable live dashboard updates (requires interactive terminal).
    watch_refresh : float, default=0.5
        Refresh interval (seconds) for the live dashboard when ``watch`` is enabled.

    Returns
    -------
    pandas.DataFrame
        Summary table concatenating KPI/objective/runtime rows for every scenario/solver run.

    Notes
    -----
    The function writes the following assets inside ``out_dir``:

    * ``summary.csv`` and ``summary.json``: aggregated KPI/objective/runtime metrics.
    * ``<scenario>/<solver>_assignments.csv``: per-solver assignment matrices.
    * Optional telemetry JSONL entries (when ``telemetry_log`` is provided).
    """
    scenarios = _resolve_scenarios(scenario_paths)
    if not scenarios:
        raise typer.BadParameter("No scenarios resolved for benchmarking.")

    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    profile_sa_config = (
        combine_solver_configs(profile.bench if profile else None, profile.sa if profile else None)
        if profile
        else None
    )
    profile_ils_config = (
        combine_solver_configs(profile.bench if profile else None, profile.ils if profile else None)
        if profile
        else None
    )
    profile_tabu_config = (
        combine_solver_configs(
            profile.bench if profile else None, profile.tabu if profile else None
        )
        if profile
        else None
    )

    watch_runner: LiveWatch | None = None
    if watch:
        if console.is_terminal:
            watch_runner = LiveWatch(WatchConfig(refresh_interval=watch_refresh), console=console)
            watch_runner.start()
        else:
            console.print("[yellow]Watch mode disabled: not running in an interactive terminal.[/]")

    def _run_benchmark_scenarios() -> None:
        for bench in scenarios:
            resolved_path = bench.path.expanduser()
            if not resolved_path.exists():
                raise FileNotFoundError(f"Scenario not found: {resolved_path}")
            sc = load_scenario(str(resolved_path))
            machine_cost_dicts = [
                snapshot.to_dict() for snapshot in build_machine_cost_snapshots(sc.machines)
            ]
            machine_costs_summary = summarize_machine_costs(machine_cost_dicts)
            pb = Problem.from_scenario(sc)
            scenario_out = out_dir / bench.name
            scenario_out.mkdir(parents=True, exist_ok=True)

            scenario_mip_objective: float | None = None
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
                scenario_mip_objective = cast(float, mip_res.get("objective", 0.0))
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
                        machine_costs_summary=machine_costs_summary,
                    )
                )

            sc_name = getattr(sc, "name", bench.name)
            watch_sink = watch_runner.sink if watch_runner else None

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
                    resolved_sa = merge_profile_with_cli(
                        profile_sa_config,
                        run_presets,
                        override_weights,
                        explicit_ops,
                        None,
                        None,
                        None,
                    )
                    sa_kwargs: dict[str, Any] = {
                        "iters": sa_iters,
                        "seed": sa_seed,
                        "operators": resolved_sa.operators,
                        "operator_weights": (
                            resolved_sa.operator_weights if resolved_sa.operator_weights else None
                        ),
                        "batch_size": resolved_sa.batch_neighbours,
                        "max_workers": resolved_sa.parallel_workers,
                        "cooling_rate": sa_cooling_rate,
                        "restart_interval": sa_restart_interval,
                        "objective_weight_overrides": objective_weight_overrides,
                        "milp_objective": scenario_mip_objective,
                    }
                    if resolved_sa.extra_kwargs:
                        sa_kwargs.update(resolved_sa.extra_kwargs)
                    if watch_sink:
                        sa_kwargs["watch_sink"] = watch_sink
                        sa_kwargs["watch_interval"] = max(1, sa_iters // 200 or 1)
                        sa_kwargs["watch_metadata"] = {
                            "scenario": sc_name,
                            "solver": f"sa[{preset_label}]" if preset_label else "sa",
                        }
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
                    resolved_weights = operators_meta or (
                        resolved_sa.operator_weights if resolved_sa.operator_weights else {}
                    )
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
                            machine_costs_summary=machine_costs_summary,
                        )
                    )
                    if telemetry_log:
                        log_record = {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "source": "bench-suite",
                            "scenario": sc.name,
                            "scenario_path": str(resolved_path),
                            "solver": "sa",
                            "seed": sa_seed,
                            "iterations": sa_iters,
                            "objective": cast(float, sa_res.get("objective", 0.0)),
                            "kpis": sa_kpis.to_dict(),
                            "operators_config": resolved_weights,
                            "operators_stats": operator_stats,
                            "preset_label": preset_label,
                            "machine_costs": machine_cost_dicts,
                        }
                        if scenario_mip_objective is not None:
                            log_record["milp_objective"] = float(scenario_mip_objective)
                        if profile:
                            log_record["profile"] = profile.name
                            log_record["profile_version"] = profile.version
                        append_jsonl(telemetry_log, log_record)

            if include_ils:
                resolved_ils = merge_profile_with_cli(
                    profile_ils_config,
                    operator_presets,
                    override_weights,
                    explicit_ops,
                    ils_batch_neighbours,
                    ils_workers,
                    None,
                )
                ils_batch_arg = resolved_ils.batch_neighbours
                if ils_batch_arg is None and ils_batch_neighbours > 1:
                    ils_batch_arg = ils_batch_neighbours
                ils_worker_arg = resolved_ils.parallel_workers
                if ils_worker_arg is None and ils_workers > 1:
                    ils_worker_arg = ils_workers
                ils_weight_config = (
                    resolved_ils.operator_weights if resolved_ils.operator_weights else None
                )
                ils_extra_kwargs: dict[str, Any] = dict(resolved_ils.extra_kwargs)
                perturbation_strength_val = ils_perturbation_strength
                stall_limit_val = ils_stall_limit
                hybrid_use_mip_val = ils_hybrid_use_mip
                hybrid_mip_time_limit_val = ils_hybrid_mip_time_limit

                value = ils_extra_kwargs.pop("perturbation_strength", None)
                if isinstance(value, int | float):
                    perturbation_strength_val = int(value)
                value = ils_extra_kwargs.pop("stall_limit", None)
                if isinstance(value, int | float):
                    stall_limit_val = int(value)
                value = ils_extra_kwargs.pop("hybrid_use_mip", None)
                if isinstance(value, bool):
                    hybrid_use_mip_val = value
                value = ils_extra_kwargs.pop("hybrid_mip_time_limit", None)
                if isinstance(value, int | float):
                    hybrid_mip_time_limit_val = int(value)

                ils_run_iters = ils_iters if ils_iters is not None else sa_iters
                ils_run_seed = ils_seed if ils_seed is not None else sa_seed
                ils_kwargs: dict[str, Any] = {
                    "iters": ils_run_iters,
                    "seed": ils_run_seed,
                    "operators": resolved_ils.operators,
                    "operator_weights": ils_weight_config,
                    "batch_size": ils_batch_arg,
                    "max_workers": ils_worker_arg,
                    "perturbation_strength": perturbation_strength_val,
                    "stall_limit": stall_limit_val,
                    "hybrid_use_mip": hybrid_use_mip_val,
                    "hybrid_mip_time_limit": hybrid_mip_time_limit_val,
                    "objective_weight_overrides": objective_weight_overrides,
                    "milp_objective": scenario_mip_objective,
                }
                ils_kwargs.update(ils_extra_kwargs)
                if watch_sink:
                    ils_kwargs["watch_sink"] = watch_sink
                    ils_kwargs["watch_interval"] = max(1, ils_run_iters // 50 or 1)
                    ils_kwargs["watch_metadata"] = {
                        "scenario": sc_name,
                        "solver": "ils",
                    }

                start = time.perf_counter()
                ils_res = solve_ils(pb, **ils_kwargs)
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
                    "iters": ils_run_iters,
                    "seed": ils_run_seed,
                    "perturbation_strength": perturbation_strength_val,
                    "stall_limit": stall_limit_val,
                    "hybrid_use_mip": hybrid_use_mip_val,
                    "hybrid_mip_time_limit": hybrid_mip_time_limit_val,
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
                        operator_config=ils_weights or (ils_weight_config or {}),
                        operator_stats=ils_stats,
                        machine_costs_summary=machine_costs_summary,
                    )
                )
                if telemetry_log:
                    record = {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "source": "bench-suite",
                        "scenario": sc.name,
                        "scenario_path": str(resolved_path),
                        "solver": "ils",
                        "seed": ils_run_seed,
                        "iterations": ils_run_iters,
                        "objective": cast(float, ils_res.get("objective", 0.0)),
                        "kpis": ils_kpis.to_dict(),
                        "operators_config": ils_weights or ils_weight_config,
                        "operators_stats": ils_stats,
                        "perturbation_strength": perturbation_strength_val,
                        "stall_limit": stall_limit_val,
                        "hybrid_use_mip": hybrid_use_mip_val,
                        "hybrid_mip_time_limit": hybrid_mip_time_limit_val,
                        "machine_costs": machine_cost_dicts,
                    }
                    if scenario_mip_objective is not None:
                        record["milp_objective"] = float(scenario_mip_objective)
                    if profile:
                        record["profile"] = profile.name
                        record["profile_version"] = profile.version
                    append_jsonl(telemetry_log, record)

            if include_tabu:
                resolved_tabu = merge_profile_with_cli(
                    profile_tabu_config,
                    operator_presets,
                    override_weights,
                    explicit_ops,
                    tabu_batch_neighbours,
                    tabu_workers,
                    None,
                )
                tabu_batch_arg = resolved_tabu.batch_neighbours
                if tabu_batch_arg is None and tabu_batch_neighbours > 1:
                    tabu_batch_arg = tabu_batch_neighbours
                tabu_worker_arg = resolved_tabu.parallel_workers
                if tabu_worker_arg is None and tabu_workers > 1:
                    tabu_worker_arg = tabu_workers
                tabu_weight_config = (
                    resolved_tabu.operator_weights if resolved_tabu.operator_weights else None
                )
                tabu_extra_kwargs: dict[str, Any] = dict(resolved_tabu.extra_kwargs)
                tabu_tenure_val = tabu_tenure
                tabu_stall_limit_val = tabu_stall_limit
                value = tabu_extra_kwargs.pop("tabu_tenure", None)
                if isinstance(value, int | float):
                    tabu_tenure_val = int(value)
                value = tabu_extra_kwargs.pop("stall_limit", None)
                if isinstance(value, int | float):
                    tabu_stall_limit_val = int(value)

                tabu_run_iters = tabu_iters if tabu_iters is not None else sa_iters
                tabu_run_seed = tabu_seed if tabu_seed is not None else sa_seed
                tabu_kwargs: dict[str, Any] = {
                    "iters": tabu_run_iters,
                    "seed": tabu_run_seed,
                    "operators": resolved_tabu.operators,
                    "operator_weights": tabu_weight_config,
                    "batch_size": tabu_batch_arg,
                    "max_workers": tabu_worker_arg,
                    "tabu_tenure": tabu_tenure_val,
                    "stall_limit": tabu_stall_limit_val,
                    "objective_weight_overrides": objective_weight_overrides,
                    "milp_objective": scenario_mip_objective,
                }
                tabu_kwargs.update(tabu_extra_kwargs)
                if watch_sink:
                    tabu_kwargs["watch_sink"] = watch_sink
                    tabu_kwargs["watch_interval"] = max(1, tabu_run_iters // 50 or 1)
                    tabu_kwargs["watch_metadata"] = {
                        "scenario": sc_name,
                        "solver": "tabu",
                    }

                start = time.perf_counter()
                tabu_res = solve_tabu(pb, **tabu_kwargs)
                tabu_runtime = time.perf_counter() - start
                tabu_assign = cast(pd.DataFrame, tabu_res["assignments"]).copy()
                tabu_assign.to_csv(scenario_out / "tabu_assignments.csv", index=False)
                tabu_kpis = compute_kpis(pb, tabu_assign)
                tabu_meta = cast(dict[str, Any], tabu_res.get("meta", {}))
                if profile:
                    tabu_meta["profile"] = profile.name
                    tabu_meta["profile_version"] = profile.version
                tabu_weights = cast(dict[str, float], tabu_meta.get("operators", {}))
                tabu_stats = cast(dict[str, dict[str, float]], tabu_meta.get("operators_stats", {}))
                extra_tabu = {
                    "iters": tabu_run_iters,
                    "seed": tabu_run_seed,
                    "tabu_tenure": tabu_meta.get("tabu_tenure", tabu_tenure_val),
                    "tabu_stall_limit": tabu_stall_limit_val,
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
                        operator_config=tabu_weights or (tabu_weight_config or {}),
                        operator_stats=tabu_stats,
                        machine_costs_summary=machine_costs_summary,
                    )
                )
                if telemetry_log:
                    record = {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "source": "bench-suite",
                        "scenario": sc.name,
                        "scenario_path": str(resolved_path),
                        "solver": "tabu",
                        "seed": tabu_run_seed,
                        "iterations": tabu_run_iters,
                        "objective": cast(float, tabu_res.get("objective", 0.0)),
                        "kpis": tabu_kpis.to_dict(),
                        "operators_config": tabu_weights or tabu_weight_config,
                        "operators_stats": tabu_stats,
                        "tabu_tenure": tabu_meta.get("tabu_tenure", tabu_tenure_val),
                        "tabu_stall_limit": tabu_stall_limit_val,
                        "machine_costs": machine_cost_dicts,
                    }
                    if scenario_mip_objective is not None:
                        record["milp_objective"] = float(scenario_mip_objective)
                    if profile:
                        record["profile"] = profile.name
                        record["profile_version"] = profile.version
                    append_jsonl(telemetry_log, record)

    try:
        _run_benchmark_scenarios()
    finally:
        if watch_runner:
            watch_runner.stop()
    summary = pd.DataFrame(rows)
    if not summary.empty:
        summary = summary.copy()
        summary["scenario_key"] = summary["scenario"].astype(str)
        raw_objectives = summary[summary["solver"] == "mip"].set_index("scenario_key")["objective"]
        mip_objectives: dict[str, float] = {}
        for key, value in raw_objectives.items():
            try:
                mip_objectives[str(key)] = float(value)
            except (TypeError, ValueError):
                continue

        def _coerce_float(value: object) -> float | None:
            if isinstance(value, int | float):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return None
            return None

        def _objective_gap(row: pd.Series) -> object:
            scenario_key = str(row.get("scenario_key", ""))
            mip_value = mip_objectives.get(scenario_key)
            if row.get("solver") == "mip":
                return 0.0
            if mip_value is None:
                return pd.NA
            objective_val = _coerce_float(row.get("objective", 0.0))
            if objective_val is None:
                return pd.NA
            return mip_value - objective_val

        def _objective_ratio(row: pd.Series) -> object:
            scenario_key = str(row.get("scenario_key", ""))
            mip_value = mip_objectives.get(scenario_key)
            if row.get("solver") == "mip":
                return 1.0
            if mip_value is None:
                return pd.NA
            if mip_value == 0:
                return pd.NA
            objective_val = _coerce_float(row.get("objective", 0.0))
            if objective_val is None:
                return pd.NA
            mip_value_float = mip_value
            return objective_val / mip_value_float

        summary["objective_vs_mip_gap"] = summary.apply(_objective_gap, axis=1)
        summary["objective_vs_mip_ratio"] = summary.apply(_objective_ratio, axis=1)

        heuristic_mask = summary["solver"] != "mip"
        summary["solver_category"] = summary["solver"].map(
            lambda solver: "exact" if solver == "mip" else "heuristic"
        )
        best_solver_by_scenario: dict[str, str] = {}
        best_objective_by_scenario: dict[str, float] = {}
        best_runtime_by_scenario: dict[str, float] = {}
        if heuristic_mask.any():
            heuristics = summary[heuristic_mask]
            idx = heuristics.groupby("scenario_key")["objective"].idxmax()
            for scenario_key, index in idx.items():
                row = summary.loc[index]
                key_str = str(scenario_key)
                best_solver_by_scenario[key_str] = str(row["solver"])
                objective_val = _coerce_float(row.get("objective", 0.0))
                if objective_val is not None:
                    best_objective_by_scenario[key_str] = objective_val
                runtime_val = _coerce_float(row.get("runtime_s", float("nan")))
                if runtime_val is not None:
                    best_runtime_by_scenario[key_str] = runtime_val
            summary["best_heuristic_solver"] = summary["scenario_key"].map(best_solver_by_scenario)
            summary["best_heuristic_objective"] = summary["scenario_key"].map(
                best_objective_by_scenario
            )
            summary["best_heuristic_runtime_s"] = summary["scenario_key"].map(
                best_runtime_by_scenario
            )
            gap_vs_best = summary["best_heuristic_objective"] - summary["objective"]
            summary["objective_gap_vs_best_heuristic"] = gap_vs_best
            exact_mask = summary["solver_category"] == "exact"
            summary.loc[exact_mask, "objective_gap_vs_best_heuristic"] = (
                summary.loc[exact_mask, "objective"]
                - summary.loc[exact_mask, "best_heuristic_objective"]
            )

            def _runtime_ratio(row: pd.Series) -> object:
                best_runtime_val = _coerce_float(row.get("best_heuristic_runtime_s"))
                runtime_val = _coerce_float(row.get("runtime_s"))
                if best_runtime_val is None or runtime_val is None:
                    return pd.NA
                if best_runtime_val == 0 or math.isnan(best_runtime_val):
                    return pd.NA
                return runtime_val / best_runtime_val

            summary["runtime_ratio_vs_best_heuristic"] = summary.apply(_runtime_ratio, axis=1)
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
    for record_obj in summary.sort_values(["scenario", "solver"]).to_dict(orient="records"):
        record = cast(dict[str, object], record_obj)
        row = [
            str(record["scenario"]),
            str(record["solver"]),
        ]
        if "preset_label" in summary.columns:
            row.append(str(record.get("preset_label", "")))
        objective_val = _coerce_float(record.get("objective", 0.0))
        runtime_val = _coerce_float(record.get("runtime_s", 0.0))
        objective_fmt = (
            f"{objective_val:.3f}"
            if objective_val is not None
            else str(record.get("objective", ""))
        )
        runtime_fmt = (
            f"{runtime_val:.2f}" if runtime_val is not None else str(record.get("runtime_s", ""))
        )
        row.extend(
            [
                objective_fmt,
                runtime_fmt,
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
    sa_cooling_rate: float = typer.Option(
        0.999, "--sa-cooling-rate", help="Simulated annealing cooling rate (0<rate<1)."
    ),
    sa_restart_interval: int = typer.Option(
        0,
        "--sa-restart-interval",
        help="Non-accepting iterations before SA restarts (0=auto).",
    ),
    include_ils: bool = typer.Option(False, help="Include Iterated Local Search in benchmarks"),
    ils_iters: int = typer.Option(250, help="Iterated Local Search iterations"),
    ils_seed: int = typer.Option(42, help="Iterated Local Search RNG seed"),
    ils_batch_neighbours: int = typer.Option(
        1, help="Neighbours sampled per ILS local search step"
    ),
    ils_workers: int = typer.Option(1, help="Worker threads for ILS batched evaluation"),
    ils_perturbation_strength: int = typer.Option(3, help="ILS perturbation strength"),
    ils_stall_limit: int = typer.Option(10, help="ILS stall limit before restart/perturbation"),
    ils_hybrid_use_mip: bool = typer.Option(False, help="Enable hybrid MIP warm start in ILS"),
    ils_hybrid_mip_time_limit: int = typer.Option(
        60, help="Time limit (s) for hybrid MIP warm start"
    ),
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
    objective_weight: list[str] | None = typer.Option(
        None,
        "--objective-weight",
        help=(
            "Override objective weights via name=value (production|mobilisation|transitions|"
            "landing_slack). Repeatable."
        ),
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
    watch: bool = typer.Option(
        False,
        "--watch/--no-watch",
        help="Render a live dashboard showing heuristic progress.",
    ),
    watch_refresh: float = typer.Option(
        0.5,
        "--watch-refresh",
        min=0.1,
        help="Refresh interval for the live dashboard (seconds).",
    ),
    compare_preset: list[str] | None = typer.Option(
        None,
        "--compare-preset",
        "-C",
        help="Run additional SA passes for each preset and include them in the summary.",
    ),
):
    """Run the benchmark harness from the CLI and emit summary CSV/JSON artifacts.

    This command is a thin CLI wrapper over :func:`run_benchmark_suite`.  All options map 1:1 to
    keyword arguments on that helper so power users can either call the function from notebooks or
    shell out through Typer.  Results are written under ``--out-dir`` (assignments per solver +
    ``summary.csv``/``summary.json``), and any telemetry log provided with ``--telemetry-log`` is
    appended with structured JSONL rows.
    """
    weight_config: dict[str, float]
    if list_operator_presets:
        console.print("Operator presets:")
        console.print(format_operator_presets())
        raise typer.Exit()

    try:
        weight_config = parse_operator_weights(operator_weight)
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise typer.BadParameter(str(exc)) from exc

    try:
        objective_weight_override = parse_objective_weight_overrides(objective_weight)
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise typer.BadParameter(str(exc)) from exc
    if list_profiles:
        console.print("Solver profiles:")
        console.print(format_profiles())
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
        sa_cooling_rate=sa_cooling_rate,
        sa_restart_interval=sa_restart_interval if sa_restart_interval > 0 else None,
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
        watch=watch,
        watch_refresh=watch_refresh,
        objective_weight_overrides=(
            objective_weight_override if objective_weight_override else None
        ),
    )
