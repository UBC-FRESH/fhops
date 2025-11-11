from __future__ import annotations

from collections.abc import Sequence
from collections import deque
import random
from contextlib import nullcontext
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import typer
import click
from rich.console import Console
from rich.table import Table

from fhops.cli._utils import format_operator_presets, operator_preset_help, parse_operator_weights
from fhops.cli.benchmarks import benchmark_app
from fhops.cli.geospatial import geospatial_app
from fhops.cli.telemetry import telemetry_app
from fhops.cli.synthetic import synth_app
from fhops.cli.profiles import format_profiles, get_profile, merge_profile_with_cli
from fhops.evaluation import (
    PlaybackConfig,
    SamplingConfig,
    compute_kpis,
    day_dataframe,
    day_dataframe_from_ensemble,
    export_playback,
    playback_summary_metrics,
    run_playback,
    run_stochastic_playback,
    shift_dataframe,
    shift_dataframe_from_ensemble,
)
from fhops.optimization.heuristics import (
    build_exploration_plan,
    run_multi_start,
    solve_ils,
    solve_sa,
    solve_tabu,
)
from fhops.optimization.heuristics.registry import OperatorRegistry
from fhops.optimization.mip import solve_mip
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.telemetry import RunTelemetryLogger, append_jsonl

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(geospatial_app, name="geo")
app.add_typer(benchmark_app, name="bench")
app.add_typer(synth_app, name="synth")
app.add_typer(telemetry_app, name="telemetry")
console = Console()
KPI_MODE = click.Choice(["basic", "extended"], case_sensitive=False)


def _enable_rich_tracebacks():
    """Enable rich tracebacks with local variables and customized formatting."""
    try:
        import rich.traceback as _rt

        _rt.install(show_locals=True, width=140, extra_lines=2)
    except Exception:
        pass


def _ensure_kpi_dict(kpis: Any) -> dict[str, Any]:
    if hasattr(kpis, "to_dict") and callable(kpis.to_dict):
        return dict(kpis.to_dict())
    return dict(kpis)


def _format_metric_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(parsed, dict):
            return ", ".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    if isinstance(value, float):
        return f"{value:.3f}"
    return value


def _print_kpi_summary(kpis: Any, mode: str = "extended") -> None:
    mode = mode.lower()
    data = _ensure_kpi_dict(kpis)
    if not data:
        return

    sections: list[tuple[str, list[str]]] = [
        (
            "Production",
            ["total_production", "completed_blocks", "makespan_day", "makespan_shift"],
        ),
        (
            "Mobilisation",
            [
                "mobilisation_cost",
                "mobilisation_cost_by_machine",
                "mobilisation_cost_by_landing",
            ],
        ),
        (
            "Utilisation",
            [
                "utilisation_ratio_mean_shift",
                "utilisation_ratio_weighted_shift",
                "utilisation_ratio_mean_day",
                "utilisation_ratio_weighted_day",
                "utilisation_ratio_by_machine",
                "utilisation_ratio_by_role",
            ],
        ),
        (
            "Downtime",
            [
                "downtime_hours_total",
                "downtime_event_count",
                "downtime_production_loss_est",
                "downtime_hours_by_machine",
            ],
        ),
        (
            "Weather",
            [
                "weather_severity_total",
                "weather_hours_est",
                "weather_production_loss_est",
                "weather_severity_by_machine",
            ],
        ),
        (
            "Sequencing",
            [
                "sequencing_violation_count",
                "sequencing_violation_blocks",
                "sequencing_violation_days",
                "sequencing_violation_breakdown",
            ],
        ),
    ]

    console.print("[bold]KPI Summary[/bold]")
    for title, keys in sections:
        if mode == "basic" and title not in {"Production", "Mobilisation"}:
            continue
        lines = [(key, data[key]) for key in keys if key in data]
        if not lines:
            continue
        console.print(f"[bold]{title}[/bold]")
        for key, value in lines:
            console.print(f"  {key}: {_format_metric_value(value)}")


@app.command()
def validate(scenario: Path):
    """Validate a scenario YAML and print summary."""
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    t = Table(title=f"Scenario: {sc.name}")
    t.add_column("Entities")
    t.add_column("Count")
    t.add_row("Days", str(len(pb.days)))
    t.add_row("Blocks", str(len(sc.blocks)))
    t.add_row("Machines", str(len(sc.machines)))
    t.add_row("Landings", str(len(sc.landings)))
    console.print(t)


@app.command()
def build_mip(scenario: Path):
    """Build the MIP and print basic stats (no solve)."""
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    try:
        from fhops.model.pyomo_builder import build_model

        m = build_model(pb)
        console.print(
            f"Model built with |M|={len(m.M)} |B|={len(m.B)} |D|={len(m.D)}; "
            f"components={len(list(m.component_objects()))}"
        )
    except Exception as e:
        console.print(f"[red]Build failed:[/red] {e}")
        raise typer.Exit(1)


@app.command("solve-mip")
def solve_mip_cmd(
    scenario: Path,
    out: Path = typer.Option(..., "--out", help="Output CSV path"),
    time_limit: int = 60,
    driver: str = typer.Option("auto", help="HiGHS driver: auto|appsi|exec"),
    debug: bool = typer.Option(False, "--debug", help="Verbose tracebacks & solver logs"),
):
    """Solve with HiGHS (exact)."""
    if debug:
        _enable_rich_tracebacks()
        console.print(
            f"[dim]types → scenario={type(scenario).__name__}, out={type(out).__name__}[/]"
        )

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)

    out.parent.mkdir(parents=True, exist_ok=True)
    res = solve_mip(pb, time_limit=time_limit, driver=driver, debug=debug)
    assignments = cast(pd.DataFrame, res["assignments"])
    objective = cast(float, res.get("objective", 0.0))

    assignments.to_csv(str(out), index=False)
    console.print(f"Objective: {objective:.3f}. Saved to {out}")
    metrics = compute_kpis(pb, assignments)
    _print_kpi_summary(metrics)


@app.command("solve-heur")
def solve_heur_cmd(
    scenario: Path,
    out: Path = typer.Option(..., "--out", help="Output CSV path"),
    iters: int = 2000,
    seed: int = 42,
    debug: bool = False,
    operator: list[str] | None = typer.Option(
        None,
        "--operator",
        "-o",
        help="Enable specific heuristic operators (repeatable). Defaults to all.",
    ),
    operator_weight: list[str] | None = typer.Option(
        None,
        "--operator-weight",
        "-w",
        help="Set operator weight as name=value (e.g., --operator-weight swap=2). Repeatable.",
    ),
    operator_preset: list[str] | None = typer.Option(
        None,
        "--operator-preset",
        "-P",
        help=f"Apply operator preset ({operator_preset_help()}).",
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Apply a solver profile combining presets and advanced options.",
    ),
    list_operator_presets: bool = typer.Option(
        False, "--list-operator-presets", help="Show available operator presets and exit."
    ),
    list_profiles: bool = typer.Option(
        False, "--list-profiles", help="Show available solver profiles and exit."
    ),
    show_operator_stats: bool = typer.Option(
        False, "--show-operator-stats", help="Print per-operator stats after solving."
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append run telemetry to a JSONL file (e.g. telemetry/runs.jsonl); step logs land in telemetry/steps/.",
        writable=True,
        dir_okay=False,
    ),
    kpi_mode: str = typer.Option(
        "extended",
        "--kpi-mode",
        help="Control verbosity of KPI output (basic|extended).",
        show_choices=True,
        click_type=KPI_MODE,
    ),
    batch_neighbours: int = typer.Option(
        1,
        "--batch-neighbours",
        help="Number of neighbour candidates sampled per iteration (1 keeps sequential scoring).",
        min=1,
    ),
    parallel_workers: int = typer.Option(
        1,
        "--parallel-workers",
        help="Worker threads for batched evaluation or multi-start orchestration (1 keeps sequential).",
        min=1,
    ),
    multi_start: int = typer.Option(
        1,
        "--parallel-multistart",
        help="Run multiple SA instances in parallel and select the best objective (1 disables).",
        min=1,
    ),
):
    """Solve with Simulated Annealing (heuristic)."""
    if debug:
        _enable_rich_tracebacks()
        console.print(
            f"[dim]types → scenario={type(scenario).__name__}, out={type(out).__name__}[/]"
        )

    if list_profiles:
        console.print("Solver profiles:")
        console.print(format_profiles())
        raise typer.Exit()

    if list_operator_presets:
        console.print("Operator presets:")
        console.print(format_operator_presets())
        raise typer.Exit()

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    try:
        weight_override = parse_operator_weights(operator_weight)
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise typer.BadParameter(str(exc)) from exc

    explicit_ops = [op.lower() for op in operator] if operator else []

    selected_profile = None
    if profile:
        try:
            selected_profile = get_profile(profile)
        except KeyError as exc:  # pragma: no cover - CLI validation
            raise typer.BadParameter(str(exc)) from exc

    resolved = merge_profile_with_cli(
        selected_profile.sa if selected_profile else None,
        operator_preset,
        weight_override,
        explicit_ops,
        batch_neighbours,
        parallel_workers,
        multi_start,
    )

    if resolved.batch_neighbours is not None:
        batch_neighbours = resolved.batch_neighbours
    if resolved.parallel_workers is not None:
        parallel_workers = resolved.parallel_workers
    if resolved.parallel_multistart is not None:
        multi_start = resolved.parallel_multistart

    batch_arg = batch_neighbours if batch_neighbours and batch_neighbours > 1 else None
    worker_arg = parallel_workers if parallel_workers and parallel_workers > 1 else None

    resolved_weights = resolved.operator_weights if resolved.operator_weights else None
    sa_kwargs: dict[str, Any] = {
        "iters": iters,
        "operators": resolved.operators,
        "operator_weights": resolved_weights,
        "batch_size": batch_arg,
        "max_workers": worker_arg,
    }
    if resolved.extra_kwargs:
        sa_kwargs.update(resolved.extra_kwargs)

    runs_meta = None
    seed_used = seed
    base_telemetry_context: dict[str, Any] | None = None
    if telemetry_log:
        base_telemetry_context = {
            "scenario_path": str(scenario),
            "source": "cli.solve-heur",
        }
        if selected_profile:
            base_telemetry_context["profile"] = selected_profile.name
            base_telemetry_context["profile_version"] = selected_profile.version
        sa_kwargs["telemetry_log"] = telemetry_log
        sa_kwargs["telemetry_context"] = base_telemetry_context

    if multi_start > 1:
        seeds, auto_presets = build_exploration_plan(multi_start, base_seed=seed)
        if resolved.operators:
            preset_plan: list[Sequence[str] | None] = [None for _ in range(multi_start)]
        else:
            preset_plan = list(auto_presets)
        try:
            res_container = run_multi_start(
                pb,
                seeds=seeds,
                presets=preset_plan,
                max_workers=worker_arg,
                sa_kwargs=sa_kwargs,
                telemetry_log=telemetry_log,
                telemetry_context=base_telemetry_context,
            )
            res = res_container.best_result
            runs_meta = res_container.runs_meta
            best_meta = max(
                (meta for meta in runs_meta if meta.get("status") == "ok"),
                key=lambda meta: meta.get("objective", float("-inf")),
                default=None,
            )
            if best_meta:
                seed_value = best_meta.get("seed")
                if isinstance(seed_value, int):
                    seed_used = seed_value
                elif isinstance(seed_value, str):
                    try:
                        seed_used = int(seed_value)
                    except ValueError:
                        pass
        except Exception as exc:  # pragma: no cover - guardrail path
            console.print(
                f"[yellow]Multi-start execution failed ({exc!r}); falling back to single run.[/]"
            )
            runs_meta = None
            fallback_kwargs: dict[str, Any] = dict(sa_kwargs)
            fallback_kwargs["seed"] = seed
            res = solve_sa(pb, **fallback_kwargs)
    else:
        single_run_kwargs: dict[str, Any] = dict(sa_kwargs)
        single_run_kwargs["seed"] = seed
        res = solve_sa(pb, **single_run_kwargs)
    assignments = cast(pd.DataFrame, res["assignments"])
    objective = cast(float, res.get("objective", 0.0))
    meta = cast(dict[str, Any], res.get("meta", {}))
    if selected_profile:
        meta["profile"] = selected_profile.name
        meta["profile_version"] = selected_profile.version

    out.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(str(out), index=False)
    console.print(f"Objective (heuristic): {objective:.3f}. Saved to {out}")
    metrics = compute_kpis(pb, assignments)
    _print_kpi_summary(metrics, mode=kpi_mode)
    operators_meta = cast(dict[str, float], meta.get("operators", {}))
    if operators_meta:
        console.print(f"Operators: {operators_meta}")
    if show_operator_stats:
        stats = res.get("meta", {}).get("operators_stats", {})
        if stats:
            console.print("Operator stats:")
            for name, payload in stats.items():
                console.print(
                    f"  {name}: proposals={payload.get('proposals', 0)}, "
                    f"accepted={payload.get('accepted', 0)}, "
                    f"accept_rate={payload.get('acceptance_rate', 0):.3f}, "
                    f"weight={payload.get('weight', 0)}"
                )
    if runs_meta:
        console.print(
            f"[dim]Parallel multi-start executed {len(runs_meta)} runs; best seed={seed_used}. See telemetry log for per-run details.[/]"
        )
    elif telemetry_log and "telemetry_run_id" not in meta:
        stats = meta.get("operators_stats", {}) or {}
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "solve-heur",
            "scenario": sc.name,
            "scenario_path": str(scenario),
            "seed": seed_used,
            "iterations": iters,
            "objective": float(objective),
            "kpis": metrics.to_dict(),
            "operators_config": operators_meta or resolved.operator_weights,
            "operators_stats": stats,
            "batch_size": batch_neighbours,
            "max_workers": parallel_workers,
        }
        if selected_profile:
            record["profile"] = selected_profile.name
            record["profile_version"] = selected_profile.version
        append_jsonl(telemetry_log, record)


@app.command("solve-ils")
def solve_ils_cmd(
    scenario: Path,
    out: Path = typer.Option(..., "--out", help="Output CSV path"),
    iters: int = 250,
    seed: int = 42,
    perturbation_strength: int = typer.Option(
        3,
        "--perturbation-strength",
        help="Number of perturbation steps applied after each local search cycle.",
    ),
    stall_limit: int = typer.Option(
        10,
        "--stall-limit",
        help="Number of non-improving iterations before triggering perturbation/restart.",
    ),
    hybrid_use_mip: bool = typer.Option(
        False,
        "--hybrid-use-mip",
        help="Attempt a time-boxed MIP solve when stalls exceed the limit.",
    ),
    hybrid_mip_time_limit: int = typer.Option(
        60,
        "--hybrid-mip-time-limit",
        help="Seconds to spend on the hybrid MIP warm start when enabled.",
    ),
    operator: list[str] | None = typer.Option(
        None,
        "--operator",
        "-o",
        help="Enable specific operators (repeatable). Defaults to all registered operators.",
    ),
    operator_weight: list[str] | None = typer.Option(
        None,
        "--operator-weight",
        "-w",
        help="Set operator weight via name=value (repeatable).",
    ),
    operator_preset: list[str] | None = typer.Option(
        None,
        "--operator-preset",
        "-P",
        help=f"Apply operator preset ({operator_preset_help()}). Repeatable.",
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Apply a solver profile combining presets and advanced options.",
    ),
    list_operator_presets: bool = typer.Option(
        False, "--list-operator-presets", help="Show available operator presets and exit."
    ),
    list_profiles: bool = typer.Option(
        False, "--list-profiles", help="Show available solver profiles and exit."
    ),
    batch_neighbours: int = typer.Option(
        1,
        "--batch-neighbours",
        help="Neighbour candidates sampled per local search step (1 keeps sequential scoring).",
        min=1,
    ),
    parallel_workers: int = typer.Option(
        1,
        "--parallel-workers",
        help="Worker threads for batched neighbour evaluation (1 keeps sequential scoring).",
        min=1,
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append run telemetry to a JSONL file (default recommendation: telemetry/runs.jsonl).",
        writable=True,
        dir_okay=False,
    ),
    kpi_mode: str = typer.Option(
        "extended",
        "--kpi-mode",
        help="Control verbosity of KPI output (basic|extended).",
        show_choices=True,
        click_type=KPI_MODE,
    ),
    show_operator_stats: bool = typer.Option(
        False, "--show-operator-stats", help="Print per-operator stats after solving."
    ),
):
    """Solve with the Iterated Local Search heuristic."""
    if list_profiles:
        console.print("Solver profiles:")
        console.print(format_profiles())
        raise typer.Exit()

    if list_operator_presets:
        console.print("Operator presets:")
        console.print(format_operator_presets())
        raise typer.Exit()

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    try:
        weight_override = parse_operator_weights(operator_weight)
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise typer.BadParameter(str(exc)) from exc

    explicit_ops = [op.lower() for op in operator] if operator else []

    selected_profile = None
    if profile:
        try:
            selected_profile = get_profile(profile)
        except KeyError as exc:  # pragma: no cover - CLI validation
            raise typer.BadParameter(str(exc)) from exc

    resolved = merge_profile_with_cli(
        selected_profile.ils if selected_profile else None,
        operator_preset,
        weight_override,
        explicit_ops,
        batch_neighbours,
        parallel_workers,
        None,
    )

    if resolved.batch_neighbours is not None:
        batch_neighbours = resolved.batch_neighbours
    if resolved.parallel_workers is not None:
        parallel_workers = resolved.parallel_workers

    batch_arg = batch_neighbours if batch_neighbours and batch_neighbours > 1 else None
    worker_arg = parallel_workers if parallel_workers and parallel_workers > 1 else None
    profile_extra_kwargs: dict[str, Any] = dict(resolved.extra_kwargs)
    if profile_extra_kwargs:
        if "perturbation_strength" in profile_extra_kwargs and perturbation_strength == 3:
            value = profile_extra_kwargs.pop("perturbation_strength")
            if isinstance(value, int):
                perturbation_strength = value
        if "stall_limit" in profile_extra_kwargs and stall_limit == 10:
            value = profile_extra_kwargs.pop("stall_limit")
            if isinstance(value, int):
                stall_limit = value
        if "hybrid_use_mip" in profile_extra_kwargs and not hybrid_use_mip:
            value = profile_extra_kwargs.pop("hybrid_use_mip")
            if isinstance(value, bool):
                hybrid_use_mip = value
        if "hybrid_mip_time_limit" in profile_extra_kwargs and hybrid_mip_time_limit == 60:
            value = profile_extra_kwargs.pop("hybrid_mip_time_limit")
            if isinstance(value, int):
                hybrid_mip_time_limit = value
    extra_ils_kwargs: dict[str, Any] = profile_extra_kwargs

    telemetry_kwargs: dict[str, Any] = {}
    existing_ctx = extra_ils_kwargs.pop("telemetry_context", None)
    if telemetry_log:
        base_context: dict[str, Any] = {
            "scenario_path": str(scenario),
            "source": "cli.solve-ils",
        }
        if selected_profile:
            base_context["profile"] = selected_profile.name
            base_context["profile_version"] = selected_profile.version
        if isinstance(existing_ctx, dict):
            base_context.update(existing_ctx)
        telemetry_kwargs["telemetry_log"] = telemetry_log
        telemetry_kwargs["telemetry_context"] = base_context
    elif isinstance(existing_ctx, dict):
        extra_ils_kwargs["telemetry_context"] = existing_ctx

    res = solve_ils(
        pb,
        iters=iters,
        seed=seed,
        operators=resolved.operators,
        operator_weights=resolved.operator_weights or None,
        batch_size=batch_arg,
        max_workers=worker_arg,
        perturbation_strength=perturbation_strength,
        stall_limit=stall_limit,
        hybrid_use_mip=hybrid_use_mip,
        hybrid_mip_time_limit=hybrid_mip_time_limit,
        **extra_ils_kwargs,
        **telemetry_kwargs,
    )
    assignments = cast(pd.DataFrame, res["assignments"])
    objective = cast(float, res.get("objective", 0.0))

    out.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(str(out), index=False)
    console.print(f"Objective (ils): {objective:.3f}. Saved to {out}")
    metrics = compute_kpis(pb, assignments)
    _print_kpi_summary(metrics, mode=kpi_mode)
    meta = cast(dict[str, Any], res.get("meta", {}))
    if selected_profile:
        meta["profile"] = selected_profile.name
        meta["profile_version"] = selected_profile.version
    operators_meta = cast(dict[str, float], meta.get("operators", {}))
    if operators_meta:
        console.print(f"Operators: {operators_meta}")
    if show_operator_stats:
        stats = cast(dict[str, dict[str, float]], meta.get("operators_stats", {}))
        if stats:
            console.print("Operator stats:")
            for name, payload in stats.items():
                console.print(
                    f"  {name}: proposals={payload.get('proposals', 0)}, "
                    f"accepted={payload.get('accepted', 0)}, "
                    f"accept_rate={payload.get('acceptance_rate', 0):.3f}, "
                    f"weight={payload.get('weight', 0)}"
                )
    if telemetry_log and "telemetry_run_id" not in meta:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "solve-ils",
            "scenario": sc.name,
            "scenario_path": str(scenario),
            "seed": seed,
            "iterations": iters,
            "objective": objective,
            "kpis": metrics.to_dict(),
            "operators_config": operators_meta or resolved.operator_weights,
            "operators_stats": meta.get("operators_stats"),
            "batch_size": batch_neighbours,
            "max_workers": parallel_workers,
            "perturbation_strength": perturbation_strength,
            "stall_limit": stall_limit,
            "hybrid_use_mip": hybrid_use_mip,
            "hybrid_mip_time_limit": hybrid_mip_time_limit,
        }
        if selected_profile:
            record["profile"] = selected_profile.name
            record["profile_version"] = selected_profile.version
        append_jsonl(telemetry_log, record)


@app.command("solve-tabu")
def solve_tabu_cmd(
    scenario: Path,
    out: Path = typer.Option(..., "--out", help="Output CSV path"),
    iters: int = 2000,
    seed: int = 42,
    tabu_tenure: int = typer.Option(0, "--tabu-tenure", help="Override tabu tenure (0=auto)"),
    stall_limit: int = typer.Option(
        200, "--stall-limit", help="Max non-improving iterations before stopping."
    ),
    batch_neighbours: int = typer.Option(
        1, "--batch-neighbours", help="Neighbour samples per iteration."
    ),
    parallel_workers: int = typer.Option(
        1, "--parallel-workers", help="Threads for scoring batched neighbours."
    ),
    operator: list[str] | None = typer.Option(
        None, "--operator", "-o", help="Enable specific operators (repeatable)."
    ),
    operator_weight: list[str] | None = typer.Option(
        None, "--operator-weight", "-w", help="Set operator weight as name=value (repeatable)."
    ),
    operator_preset: list[str] | None = typer.Option(
        None,
        "--operator-preset",
        "-P",
        help=f"Apply operator preset ({operator_preset_help()}). Repeatable.",
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Apply a solver profile combining presets and advanced options.",
    ),
    list_operator_presets: bool = typer.Option(
        False, "--list-operator-presets", help="Show available operator presets and exit."
    ),
    list_profiles: bool = typer.Option(
        False, "--list-profiles", help="Show available solver profiles and exit."
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append run telemetry to a JSONL file (e.g. telemetry/runs.jsonl); step logs are written next to it under telemetry/steps/.",
        writable=True,
        dir_okay=False,
    ),
    kpi_mode: str = typer.Option(
        "extended",
        "--kpi-mode",
        help="Control verbosity of KPI output (basic|extended).",
        show_choices=True,
        click_type=KPI_MODE,
    ),
    show_operator_stats: bool = typer.Option(
        False, "--show-operator-stats", help="Print per-operator stats."
    ),
):
    """Solve with the Tabu Search heuristic."""
    if list_profiles:
        console.print("Solver profiles:")
        console.print(format_profiles())
        raise typer.Exit()

    if list_operator_presets:
        console.print("Operator presets:")
        console.print(format_operator_presets())
        raise typer.Exit()

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    try:
        weight_override = parse_operator_weights(operator_weight)
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise typer.BadParameter(str(exc)) from exc

    explicit_ops = [op.lower() for op in operator] if operator else []

    selected_profile = None
    if profile:
        try:
            selected_profile = get_profile(profile)
        except KeyError as exc:  # pragma: no cover - CLI validation
            raise typer.BadParameter(str(exc)) from exc

    resolved = merge_profile_with_cli(
        selected_profile.tabu if selected_profile else None,
        operator_preset,
        weight_override,
        explicit_ops,
        batch_neighbours,
        parallel_workers,
        None,
    )

    if resolved.batch_neighbours is not None:
        batch_neighbours = resolved.batch_neighbours
    if resolved.parallel_workers is not None:
        parallel_workers = resolved.parallel_workers

    batch_arg = batch_neighbours if batch_neighbours and batch_neighbours > 1 else None
    worker_arg = parallel_workers if parallel_workers and parallel_workers > 1 else None
    profile_extra_kwargs: dict[str, Any] = dict(resolved.extra_kwargs)
    if profile_extra_kwargs:
        if "tabu_tenure" in profile_extra_kwargs and (tabu_tenure is None or tabu_tenure == 0):
            value = profile_extra_kwargs.pop("tabu_tenure")
            if isinstance(value, int):
                tabu_tenure = value
        if "stall_limit" in profile_extra_kwargs and stall_limit == 200:
            value = profile_extra_kwargs.pop("stall_limit")
            if isinstance(value, int):
                stall_limit = value
    tenure = tabu_tenure if tabu_tenure and tabu_tenure > 0 else None

    existing_ctx = profile_extra_kwargs.pop("telemetry_context", None)
    telemetry_kwargs: dict[str, Any] = {}
    if telemetry_log:
        base_context: dict[str, Any] = {
            "scenario_path": str(scenario),
            "source": "cli.solve-tabu",
        }
        if selected_profile:
            base_context["profile"] = selected_profile.name
            base_context["profile_version"] = selected_profile.version
        if isinstance(existing_ctx, dict):
            base_context.update(existing_ctx)
        telemetry_kwargs["telemetry_log"] = telemetry_log
        telemetry_kwargs["telemetry_context"] = base_context
    elif isinstance(existing_ctx, dict):
        profile_extra_kwargs["telemetry_context"] = existing_ctx

    res = solve_tabu(
        pb,
        iters=iters,
        seed=seed,
        operators=resolved.operators,
        operator_weights=resolved.operator_weights or None,
        batch_size=batch_arg,
        max_workers=worker_arg,
        tabu_tenure=tenure,
        stall_limit=stall_limit,
        **profile_extra_kwargs,
        **telemetry_kwargs,
    )
    assignments = cast(pd.DataFrame, res["assignments"])
    objective = cast(float, res.get("objective", 0.0))

    out.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(str(out), index=False)
    console.print(f"Objective (tabu): {objective:.3f}. Saved to {out}")
    metrics = compute_kpis(pb, assignments)
    _print_kpi_summary(metrics, mode=kpi_mode)
    meta = cast(dict[str, Any], res.get("meta", {}))
    if selected_profile:
        meta["profile"] = selected_profile.name
        meta["profile_version"] = selected_profile.version
    operators_meta = cast(dict[str, float], meta.get("operators", {}))
    if operators_meta:
        console.print(f"Operators: {operators_meta}")
    if show_operator_stats:
        stats = meta.get("operators_stats", {})
        if stats:
            console.print("Operator stats:")
            for name, payload in stats.items():
                console.print(
                    f"  {name}: proposals={payload.get('proposals', 0)}, "
                    f"accepted={payload.get('accepted', 0)}, "
                    f"weight={payload.get('weight', 0)}"
                )
    if telemetry_log and "telemetry_run_id" not in meta:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "solve-tabu",
            "scenario": sc.name,
            "scenario_path": str(scenario),
            "seed": seed,
            "iterations": iters,
            "objective": objective,
            "kpis": metrics.to_dict(),
            "operators_config": operators_meta or resolved.operator_weights,
            "operators_stats": meta.get("operators_stats"),
            "tabu_tenure": tenure if tenure is not None else max(10, len(pb.scenario.machines)),
            "stall_limit": stall_limit,
            "batch_size": batch_neighbours,
            "max_workers": parallel_workers,
        }
        if selected_profile:
            record["profile"] = selected_profile.name
            record["profile_version"] = selected_profile.version
        append_jsonl(telemetry_log, record)


@app.command()
def evaluate(
    scenario: Path,
    assignments_csv: Path = typer.Option(
        ..., "--assignments", help="Assignments CSV (machine_id, block_id, day, shift_id)."
    ),
    kpi_mode: str = typer.Option(
        "extended",
        "--kpi-mode",
        help="Control verbosity of KPI output (basic|extended).",
        show_choices=True,
        click_type=KPI_MODE,
    ),
):
    """Evaluate a schedule CSV against the scenario."""
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    df = pd.read_csv(str(assignments_csv))
    kpis = compute_kpis(pb, df)
    _print_kpi_summary(kpis, mode=kpi_mode)


@app.command("eval-playback")
def eval_playback(
    scenario: Path,
    assignments_csv: Path = typer.Option(..., "--assignments", help="Assignments CSV (machine_id, block_id, day, shift_id)."),
    shift_out: Path | None = typer.Option(None, "--shift-out", help="Optional path to save shift-level playback summary (CSV)."),
    day_out: Path | None = typer.Option(None, "--day-out", help="Optional path to save day-level playback summary (CSV)."),
    include_idle: bool = typer.Option(
        False,
        "--include-idle",
        help="Emit idle entries for machine/shift combinations without work.",
    ),
    samples: int = typer.Option(
        1,
        "--samples",
        help="Number of stochastic samples to run (1 keeps deterministic playback).",
        min=1,
    ),
    base_seed: int = typer.Option(123, "--seed", help="Base RNG seed for stochastic playback."),
    downtime_probability: float = typer.Option(
        0.0,
        "--downtime-prob",
        min=0.0,
        max=1.0,
        help="Probability of downtime per eligible assignment (0 disables downtime).",
    ),
    downtime_max_concurrent: int | None = typer.Option(
        None,
        "--downtime-max",
        min=1,
        help="Max assignments to drop per day (None uses binomial sampling).",
    ),
    weather_probability: float = typer.Option(
        0.0,
        "--weather-prob",
        min=0.0,
        max=1.0,
        help="Probability a day receives a weather impact (0 disables weather).",
    ),
    weather_severity: float = typer.Option(
        0.3,
        "--weather-severity",
        min=0.0,
        max=1.0,
        help="Fractional production reduction applied when weather strikes.",
    ),
    weather_window: int = typer.Option(
        1,
        "--weather-window",
        min=1,
        help="Number of consecutive days affected once weather occurs.",
    ),
    landing_probability: float = typer.Option(
        0.0,
        "--landing-prob",
        min=0.0,
        max=1.0,
        help="Probability a landing experiences a throughput shock (0 disables).",
    ),
    landing_multiplier_low: float = typer.Option(
        0.4,
        "--landing-mult-min",
        min=0.0,
        max=1.0,
        help="Minimum throughput multiplier applied during landing shocks.",
    ),
    landing_multiplier_high: float = typer.Option(
        0.8,
        "--landing-mult-max",
        min=0.0,
        max=1.0,
        help="Maximum throughput multiplier applied during landing shocks.",
    ),
    landing_duration: int = typer.Option(
        1,
        "--landing-duration",
        min=1,
        help="Number of consecutive days landing shocks persist.",
    ),
    shift_parquet: Path | None = typer.Option(
        None,
        "--shift-parquet",
        help="Optional Parquet output for shift-level summary.",
    ),
    day_parquet: Path | None = typer.Option(
        None,
        "--day-parquet",
        help="Optional Parquet output for day-level summary.",
    ),
    summary_md: Path | None = typer.Option(
        None,
        "--summary-md",
        help="Write a Markdown summary of aggregated metrics.",
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append playback telemetry to a JSONL file (e.g. telemetry/runs.jsonl); step logs land in telemetry/steps/.",
        writable=True,
        dir_okay=False,
    ),
):
    """Run deterministic playback to produce shift/day summaries."""

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)

    df = pd.read_csv(assignments_csv)

    config_snapshot = {
        "include_idle": include_idle,
        "samples": samples,
        "downtime_probability": downtime_probability,
        "downtime_max_concurrent": downtime_max_concurrent,
        "weather_probability": weather_probability,
        "weather_severity": weather_severity,
        "weather_window": weather_window,
        "landing_probability": landing_probability,
        "landing_multiplier_low": landing_multiplier_low,
        "landing_multiplier_high": landing_multiplier_high,
        "landing_duration": landing_duration,
    }
    scenario_features = {
        "num_days": getattr(sc, "num_days", None),
        "num_blocks": len(getattr(sc, "blocks", []) or []),
        "num_machines": len(getattr(sc, "machines", []) or []),
        "num_landings": len(getattr(sc, "landings", []) or []),
        "num_shift_calendar_entries": len(getattr(sc, "shift_calendar", []) or []),
    }
    context_snapshot = {
        "assignments_path": str(assignments_csv),
        "command": "eval-playback",
        **scenario_features,
    }
    telemetry_logger: RunTelemetryLogger | None = None
    if telemetry_log:
        telemetry_logger = RunTelemetryLogger(
            log_path=telemetry_log,
            solver="playback",
            scenario=sc.name,
            scenario_path=str(scenario),
            config=config_snapshot,
            context=context_snapshot,
            step_interval=1,
        )

    artifacts: list[str] = []

    with (telemetry_logger if telemetry_logger else nullcontext()) as run_logger:
        playback_config = PlaybackConfig(include_idle_records=include_idle)

        deterministic_mode = (
            samples <= 1
            and downtime_probability <= 0
            and weather_probability <= 0
            and landing_probability <= 0
        )

        if deterministic_mode:
            playback_result = run_playback(pb, df, config=playback_config)
            shift_summaries = list(playback_result.shift_summaries)
            day_summaries = list(playback_result.day_summaries)
            shift_df = shift_dataframe(playback_result)
            day_df = day_dataframe(playback_result)
        else:
            sampling_config = SamplingConfig(
                samples=samples,
                base_seed=base_seed,
            )
            sampling_config.downtime.enabled = downtime_probability > 0
            sampling_config.downtime.probability = downtime_probability
            sampling_config.downtime.max_concurrent = downtime_max_concurrent
            sampling_config.weather.enabled = weather_probability > 0
            sampling_config.weather.day_probability = weather_probability
            sampling_config.weather.severity_levels = {"default": weather_severity}
            sampling_config.weather.impact_window_days = weather_window
            sampling_config.landing.enabled = landing_probability > 0
            sampling_config.landing.probability = landing_probability
            sampling_config.landing.capacity_multiplier_range = (
                landing_multiplier_low,
                landing_multiplier_high,
            )
            sampling_config.landing.duration_days = landing_duration

            ensemble = run_stochastic_playback(
                pb,
                df,
                sampling_config=sampling_config,
            )
            if ensemble.samples:
                shift_summaries = [
                    summary
                    for sample in ensemble.samples
                    for summary in sample.result.shift_summaries
                ]
                day_summaries = [
                    summary
                    for sample in ensemble.samples
                    for summary in sample.result.day_summaries
                ]
                shift_df = shift_dataframe_from_ensemble(ensemble)
                day_df = day_dataframe_from_ensemble(ensemble)
            else:
                base_result = ensemble.base_result
                shift_summaries = list(base_result.shift_summaries)
                day_summaries = list(base_result.day_summaries)
                shift_df = shift_dataframe(base_result)
                day_df = day_dataframe(base_result)

        if telemetry_logger and run_logger:
            cumulative_production = 0.0
            for idx, summary in enumerate(day_summaries, start=1):
                production = float(getattr(summary, "production_units", 0.0))
                cumulative_production += production
                run_logger.log_step(
                    step=idx,
                    objective=production,
                    best_objective=cumulative_production,
                    temperature=None,
                    acceptance_rate=None,
                    proposals=0,
                    accepted_moves=0,
                )

        shift_table = Table(title="Shift Playback Summary")
        shift_table.add_column("Machine")
        shift_table.add_column("Day")
        shift_table.add_column("Shift")
        shift_table.add_column("Prod", justify="right")
        shift_table.add_column("Hours", justify="right")
        shift_table.add_column("Idle", justify="right")
        shift_table.add_column("Mobilisation", justify="right")
        shift_table.add_column("Sequencing", justify="right")
        shift_table.add_column("Utilisation", justify="right")
        for summary in shift_summaries[:20]:
            shift_table.add_row(
                summary.machine_id,
                str(summary.day),
                summary.shift_id,
                f"{summary.production_units:.2f}",
                f"{summary.total_hours:.2f}",
                f"{(summary.idle_hours or 0.0):.2f}",
                f"{summary.mobilisation_cost:.2f}",
                str(summary.sequencing_violations),
                f"{(summary.utilisation_ratio or 0.0):.2f}",
            )
        console.print(shift_table)

        day_table = Table(title="Day Playback Summary")
        day_table.add_column("Day")
        day_table.add_column("Prod", justify="right")
        day_table.add_column("Hours", justify="right")
        day_table.add_column("Idle", justify="right")
        day_table.add_column("Mobilisation", justify="right")
        day_table.add_column("Completed", justify="right")
        day_table.add_column("Sequencing", justify="right")
        day_table.add_column("Utilisation", justify="right")
        for summary in day_summaries:
            day_table.add_row(
                str(summary.day),
                f"{summary.production_units:.2f}",
                f"{summary.total_hours:.2f}",
                f"{(summary.idle_hours or 0.0):.2f}",
                f"{summary.mobilisation_cost:.2f}",
                str(summary.completed_blocks),
                str(summary.sequencing_violations),
                f"{(summary.utilisation_ratio or 0.0):.2f}",
            )
        console.print(day_table)

        export_metrics: dict[str, Any] = {}
        try:
            export_metrics = export_playback(
                shift_df,
                day_df,
                shift_csv=shift_out,
                day_csv=day_out,
                shift_parquet=shift_parquet,
                day_parquet=day_parquet,
                summary_md=summary_md,
            )
        except ImportError as exc:
            console.print("[red]Parquet export requires either pyarrow or fastparquet. Install one of them to enable this feature.[/red]")
            raise typer.Exit(1) from exc

        if shift_out:
            console.print(f"Shift summary saved to {shift_out}")
            artifacts.append(str(shift_out))
        if day_out:
            console.print(f"Day summary saved to {day_out}")
            artifacts.append(str(day_out))
        if shift_parquet:
            console.print(f"Shift parquet saved to {shift_parquet}")
            artifacts.append(str(shift_parquet))
        if day_parquet:
            console.print(f"Day parquet saved to {day_parquet}")
            artifacts.append(str(day_parquet))
        if summary_md:
            console.print(f"Markdown summary saved to {summary_md}")
            artifacts.append(str(summary_md))

        if telemetry_logger:
            metrics_payload = {
                "total_production": float(day_df["production_units"].sum())
                if "production_units" in day_df
                else 0.0,
                "total_hours": float(day_df["total_hours"].sum())
                if "total_hours" in day_df
                else 0.0,
                "shift_rows": int(len(shift_df)),
                "day_rows": int(len(day_df)),
                "deterministic": bool(deterministic_mode),
                "samples_requested": samples,
            }
            extra_payload = {
                "export_metrics": export_metrics or playback_summary_metrics(shift_df, day_df),
                "scenario_features": scenario_features,
            }
            telemetry_logger.finalize(
                status="ok",
                metrics=metrics_payload,
                extra=extra_payload,
                artifacts=artifacts,
            )


@app.command()
def benchmark(
    scenario: Path,
    out_dir: Path = Path("bench_out"),
    time_limit: int = 60,
    iters: int = 5000,
    driver: str = "auto",
    debug: bool = False,
):
    """Run both MIP and SA, save both outputs, and print objectives."""
    if debug:
        _enable_rich_tracebacks()
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    out_dir.mkdir(parents=True, exist_ok=True)

    res_mip = solve_mip(pb, time_limit=time_limit, driver=driver, debug=debug)
    mip_csv = out_dir / "mip_solution.csv"
    mip_assignments = cast(pd.DataFrame, res_mip["assignments"])
    mip_assignments.to_csv(str(mip_csv), index=False)

    res_sa = solve_sa(pb, iters=iters)
    sa_csv = out_dir / "sa_solution.csv"
    sa_assignments = cast(pd.DataFrame, res_sa["assignments"])
    sa_assignments.to_csv(str(sa_csv), index=False)

    mip_metrics = compute_kpis(pb, mip_assignments)
    sa_metrics = compute_kpis(pb, sa_assignments)

    console.print(
        f"MIP obj={cast(float, res_mip['objective']):.3f}, "
        f"SA obj={cast(float, res_sa['objective']):.3f}"
    )
    console.print(f"Saved: {mip_csv}, {sa_csv}")
    console.print("MIP metrics:")
    for key, value in mip_metrics.items():
        console.print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")
    console.print("SA metrics:")
    for key, value in sa_metrics.items():
        console.print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")


@app.command("tune-random")
def tune_random_cli(
    scenarios: list[Path] = typer.Argument(
        ...,
        exists=True,
        readable=True,
        dir_okay=True,
        help="Scenario YAMLs or bundle directories to sample during tuning.",
    ),
    telemetry_log: Path = typer.Option(
        Path("telemetry/runs.jsonl"),
        "--telemetry-log",
        help="Telemetry JSONL capturing prior heuristic runs (optional).",
        dir_okay=False,
        writable=False,
    ),
    runs: int = typer.Option(
        3,
        "--runs",
        min=1,
        help="Number of random configurations to evaluate per scenario.",
    ),
    iters: int = typer.Option(
        250,
        "--iters",
        min=10,
        help="Simulated annealing iterations per run.",
    ),
    base_seed: int = typer.Option(
        123,
        "--base-seed",
        help="Seed used to initialise the random tuner (per-run seeds derive from this).",
    ),
):
    """Randomly sample simulated annealing configurations and record telemetry."""
    scenario_files: list[Path] = []
    for entry in scenarios:
        if entry.is_dir():
            scenario_files.extend(sorted(entry.rglob("*.yaml")))
        else:
            scenario_files.append(entry)

    if not scenario_files:
        console.print("[yellow]No scenario files discovered. Nothing to tune.[/]")
        raise typer.Exit(1)

    rng = random.Random(base_seed)
    registry = OperatorRegistry.from_defaults()
    operator_names = list(registry.names())

    results: list[dict[str, Any]] = []

    for scenario_path in scenario_files:
        sc = load_scenario(str(scenario_path))
        pb = Problem.from_scenario(sc)
        console.print(f"[dim]Tuning {scenario_path} ({runs} run(s))[/]")
        for run_idx in range(runs):
            run_seed = rng.randrange(1, 1_000_000_000)
            batch_size_choice = rng.choice([1, 2, 3])
            weight_count = rng.randint(1, max(1, len(operator_names)))
            selected_ops = rng.sample(operator_names, weight_count)
            operator_weights = {name: round(rng.uniform(0.5, 1.5), 3) for name in selected_ops}

            telemetry_kwargs: dict[str, Any] = {}
            if telemetry_log:
                telemetry_context = {
                    "source": "cli.tune-random",
                    "tuner_seed": base_seed,
                    "run_index": run_idx,
                    "batch_size_choice": batch_size_choice,
                    "operator_count": weight_count,
                }
                telemetry_kwargs = {
                    "telemetry_log": telemetry_log,
                    "telemetry_context": telemetry_context,
                }

            try:
                res = solve_sa(
                    pb,
                    iters=iters,
                    seed=run_seed,
                    batch_size=batch_size_choice if batch_size_choice > 1 else None,
                    operator_weights=operator_weights,
                    **telemetry_kwargs,
                )
            except Exception as exc:  # pragma: no cover - defensive
                console.print(
                    f"[yellow]Run failed for {scenario_path} (seed={run_seed}): {exc!r}[/]"
                )
                continue

            results.append(
                {
                    "scenario": scenario_path.name,
                    "objective": float(res.get("objective", 0.0)),
                    "seed": run_seed,
                    "batch_size": batch_size_choice,
                    "operator_weights": operator_weights,
                    "telemetry_run_id": res.get("meta", {}).get("telemetry_run_id"),
                }
            )

    if not results:
        console.print("[yellow]Random tuner did not produce any successful runs.[/]")
        return

    table = Table(title="Random tuner results", show_lines=False)
    table.add_column("Scenario")
    table.add_column("Objective", justify="right")
    table.add_column("Seed", justify="right")
    table.add_column("Batch", justify="right")
    table.add_column("Operators")

    for entry in sorted(results, key=lambda item: item["objective"], reverse=True):
        op_preview = ", ".join(
            f"{name}={weight:.2f}" for name, weight in sorted(entry["operator_weights"].items())
        )
        table.add_row(
            entry["scenario"],
            f"{entry['objective']:.3f}",
            str(entry["seed"]),
            str(entry["batch_size"]),
            op_preview if len(op_preview) < 80 else op_preview[:77] + "...",
        )
    console.print(table)

    if telemetry_log:
        console.print(
            f"[dim]{len(results)} telemetry record(s) written to {telemetry_log}. Step logs stored in {telemetry_log.parent / 'steps'}.[/]"
        )


if __name__ == "__main__":
    app()
