from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from fhops.cli._utils import format_operator_presets, operator_preset_help, parse_operator_weights
from fhops.cli.benchmarks import benchmark_app
from fhops.cli.geospatial import geospatial_app
from fhops.cli.profiles import format_profiles, get_profile, merge_profile_with_cli
from fhops.evaluation import (
    PlaybackConfig,
    SamplingConfig,
    compute_kpis,
    run_playback,
    run_stochastic_playback,
)
from fhops.optimization.heuristics import (
    build_exploration_plan,
    run_multi_start,
    solve_ils,
    solve_sa,
    solve_tabu,
)
from fhops.optimization.mip import solve_mip
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.telemetry import append_jsonl

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(geospatial_app, name="geo")
app.add_typer(benchmark_app, name="bench")
console = Console()


def _enable_rich_tracebacks():
    """Enable rich tracebacks with local variables and customized formatting."""
    try:
        import rich.traceback as _rt

        _rt.install(show_locals=True, width=140, extra_lines=2)
    except Exception:
        pass


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
    for key, value in metrics.items():
        console.print(f"{key}: {value:.3f}" if isinstance(value, float) else f"{key}: {value}")


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
        help="Append run telemetry to the given JSONL file.",
        writable=True,
        dir_okay=False,
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
    for key, value in metrics.items():
        console.print(f"{key}: {value:.3f}" if isinstance(value, float) else f"{key}: {value}")
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
    elif telemetry_log:
        stats = meta.get("operators_stats", {}) or {}
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "solve-heur",
            "scenario": sc.name,
            "scenario_path": str(scenario),
            "seed": seed_used,
            "iterations": iters,
            "objective": float(objective),
            "kpis": metrics,
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
        help="Append run telemetry to JSONL.",
        writable=True,
        dir_okay=False,
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
    )
    assignments = cast(pd.DataFrame, res["assignments"])
    objective = cast(float, res.get("objective", 0.0))

    out.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(str(out), index=False)
    console.print(f"Objective (ils): {objective:.3f}. Saved to {out}")
    metrics = compute_kpis(pb, assignments)
    for key, value in metrics.items():
        console.print(f"{key}: {value:.3f}" if isinstance(value, float) else f"{key}: {value}")
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
    if telemetry_log:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "solve-ils",
            "scenario": sc.name,
            "scenario_path": str(scenario),
            "seed": seed,
            "iterations": iters,
            "objective": objective,
            "kpis": metrics,
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
        help="Append run telemetry to JSONL.",
        writable=True,
        dir_okay=False,
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
    )
    assignments = cast(pd.DataFrame, res["assignments"])
    objective = cast(float, res.get("objective", 0.0))

    out.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(str(out), index=False)
    console.print(f"Objective (tabu): {objective:.3f}. Saved to {out}")
    metrics = compute_kpis(pb, assignments)
    for key, value in metrics.items():
        console.print(f"{key}: {value:.3f}" if isinstance(value, float) else f"{key}: {value}")
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
    if telemetry_log:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "solve-tabu",
            "scenario": sc.name,
            "scenario_path": str(scenario),
            "seed": seed,
            "iterations": iters,
            "objective": objective,
            "kpis": metrics,
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
def evaluate(scenario: Path, assignments_csv: Path):
    """Evaluate a schedule CSV against the scenario."""
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    df = pd.read_csv(str(assignments_csv))
    kpis = compute_kpis(pb, df)
    for k, v in kpis.items():
        console.print(f"{k}: {v:.3f}" if isinstance(v, float) else f"{k}: {v}")


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
):
    """Run deterministic playback to produce shift/day summaries."""

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)

    df = pd.read_csv(assignments_csv)

    playback_config = PlaybackConfig(include_idle_records=include_idle)

    if samples <= 1 and downtime_probability <= 0 and weather_probability <= 0:
        playback = run_playback(pb, df, config=playback_config)
        shift_summaries = playback.shift_summaries
        day_summaries = playback.day_summaries
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
                summary for sample in ensemble.samples for summary in sample.result.day_summaries
            ]
        else:
            shift_summaries = ensemble.base_result.shift_summaries
            day_summaries = ensemble.base_result.day_summaries

    shift_table = Table(title="Shift Playback Summary")
    shift_table.add_column("Machine")
    shift_table.add_column("Day")
    shift_table.add_column("Shift")
    shift_table.add_column("Prod", justify="right")
    shift_table.add_column("Hours", justify="right")
    shift_table.add_column("Idle", justify="right")
    shift_table.add_column("Mobilisation", justify="right")
    shift_table.add_column("Sequencing", justify="right")
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
    for summary in day_summaries:
        day_table.add_row(
            str(summary.day),
            f"{summary.production_units:.2f}",
            f"{summary.total_hours:.2f}",
            f"{(summary.idle_hours or 0.0):.2f}",
            f"{summary.mobilisation_cost:.2f}",
            str(summary.completed_blocks),
            str(summary.sequencing_violations),
        )
    console.print(day_table)

    if shift_out:
        shift_df = pd.DataFrame(
            {
                "day": [s.day for s in shift_summaries],
                "shift_id": [s.shift_id for s in shift_summaries],
                "machine_id": [s.machine_id for s in shift_summaries],
                "production_units": [s.production_units for s in shift_summaries],
                "total_hours": [s.total_hours for s in shift_summaries],
                "idle_hours": [s.idle_hours for s in shift_summaries],
                "mobilisation_cost": [s.mobilisation_cost for s in shift_summaries],
                "sequencing_violations": [s.sequencing_violations for s in shift_summaries],
                "available_hours": [s.available_hours for s in shift_summaries],
            }
        )
        shift_out.parent.mkdir(parents=True, exist_ok=True)
        shift_df.to_csv(shift_out, index=False)
        console.print(f"Shift summary saved to {shift_out}")

    if day_out:
        day_df = pd.DataFrame(
            {
                "day": [s.day for s in day_summaries],
                "production_units": [s.production_units for s in day_summaries],
                "total_hours": [s.total_hours for s in day_summaries],
                "idle_hours": [s.idle_hours for s in day_summaries],
                "mobilisation_cost": [s.mobilisation_cost for s in day_summaries],
                "completed_blocks": [s.completed_blocks for s in day_summaries],
                "sequencing_violations": [s.sequencing_violations for s in day_summaries],
                "available_hours": [s.available_hours for s in day_summaries],
            }
        )
        day_out.parent.mkdir(parents=True, exist_ok=True)
        day_df.to_csv(day_out, index=False)
        console.print(f"Day summary saved to {day_out}")


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


if __name__ == "__main__":
    app()
