"""Entry point for the `fhops` Typer CLI.

This module wires together the top-level command group and the sub-apps (`bench`,
`dataset`, `telemetry`, `geo`, `synth`) that ship with FHOPS.  It also exposes
utility routines shared by the solver/evaluation commands (KPI summaries,
scenario bundle helpers, telemetry logging, etc.).  Most users interact with
FHOPS strictly through this CLI, so the docstrings here double as the canonical
reference when the API docs are generated.
"""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click
import optuna
import pandas as pd
import typer
import yaml
from rich.console import Console
from rich.table import Table

from fhops.cli._utils import (
    OPERATOR_PRESETS,
    format_operator_presets,
    operator_preset_help,
    parse_operator_weights,
)
from fhops.cli.benchmarks import benchmark_app
from fhops.cli.dataset import dataset_app
from fhops.cli.geospatial import geospatial_app
from fhops.cli.profiles import format_profiles, get_profile, merge_profile_with_cli
from fhops.cli.synthetic import synth_app
from fhops.cli.telemetry import telemetry_app
from fhops.cli.watch_dashboard import LiveWatch
from fhops.evaluation import (
    DaySummary,
    PlaybackConfig,
    SamplingConfig,
    ShiftSummary,
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
from fhops.model.milp.data import build_operational_bundle
from fhops.model.milp.driver import solve_operational_milp
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
from fhops.telemetry.machine_costs import build_machine_cost_snapshots
from fhops.telemetry.sqlite_store import persist_tuner_summary
from fhops.telemetry.watch import WatchConfig

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(geospatial_app, name="geo")
app.add_typer(benchmark_app, name="bench")
app.add_typer(synth_app, name="synth")
app.add_typer(telemetry_app, name="telemetry")
app.add_typer(dataset_app, name="dataset")
console = Console()
KPI_MODE = click.Choice(["basic", "extended"], case_sensitive=False)

TUNING_BUNDLE_ALIASES: dict[str, list[tuple[str, Path]]] = {
    "baseline": [
        ("minitoy", Path("examples/minitoy/scenario.yaml")),
        ("small21", Path("examples/small21/scenario.yaml")),
        ("med42", Path("examples/med42/scenario.yaml")),
    ],
    "minitoy": [("minitoy", Path("examples/minitoy/scenario.yaml"))],
    "small21": [("small21", Path("examples/small21/scenario.yaml"))],
    "med42": [("med42", Path("examples/med42/scenario.yaml"))],
    "large84": [("large84", Path("examples/large84/scenario.yaml"))],
    "synthetic-small": [("synthetic-small", Path("examples/synthetic/small/scenario.yaml"))],
    "synthetic-medium": [("synthetic-medium", Path("examples/synthetic/medium/scenario.yaml"))],
    "synthetic-large": [("synthetic-large", Path("examples/synthetic/large/scenario.yaml"))],
    "synthetic": [
        ("synthetic-small", Path("examples/synthetic/small/scenario.yaml")),
        ("synthetic-medium", Path("examples/synthetic/medium/scenario.yaml")),
        ("synthetic-large", Path("examples/synthetic/large/scenario.yaml")),
    ],
}


def _enable_rich_tracebacks():
    """Enable rich tracebacks with local variables and customized formatting."""
    try:
        import rich.traceback as _rt

        _rt.install(show_locals=True, width=140, extra_lines=2)
    except Exception:
        pass


def _ensure_kpi_dict(kpis: Any) -> dict[str, Any]:
    """Normalize KPI payloads (dataclasses, pandas objects, dicts) into a plain dict."""
    if hasattr(kpis, "to_dict") and callable(kpis.to_dict):
        return dict(kpis.to_dict())
    return dict(kpis)


def _format_metric_value(value: Any) -> Any:
    """Format KPI values for console display, compressing JSON blobs and floats."""
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
    """Pretty-print KPI sections for solver/evaluation commands.

    Parameters
    ----------
    kpis : Any
        Mapping or KPI dataclass returned by :func:`fhops.evaluation.compute_kpis`.
    mode : str, default \"extended\"
        Controls which KPI sections are printed (\"basic\" omits utilisation/downtime/weather blocks).
    """
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
    alert = data.get("repair_usage_alert")
    if alert:
        console.print(
            f"[red]Repair Usage Alert:[/red] non-default FPInnovations usage bucket for {alert}"
        )


def _machine_cost_snapshot(sc) -> list[dict[str, Any]]:
    """Return CPI-adjusted machine-cost snapshots for telemetry logging."""
    return [snapshot.to_dict() for snapshot in build_machine_cost_snapshots(sc.machines)]


def _discover_scenarios_from_path(path: Path) -> list[Path]:
    """Resolve a CLI path argument into one or more scenario YAML files."""
    expanded = path.expanduser()
    if not expanded.exists():
        raise typer.BadParameter(f"Scenario path not found: {path}")
    if expanded.is_file():
        return [expanded]
    scenario_file = expanded / "scenario.yaml"
    if scenario_file.exists():
        return [scenario_file]
    immediate_yaml = sorted(expanded.glob("*.yaml"))
    if immediate_yaml:
        return immediate_yaml
    child_candidates: list[Path] = []
    for child in sorted(expanded.iterdir()):
        if not child.is_dir():
            continue
        child_scenario = child / "scenario.yaml"
        if child_scenario.exists():
            child_candidates.append(child_scenario)
    if child_candidates:
        return child_candidates
    raise typer.BadParameter(f"No scenario.yaml discovered under directory: {path}")


def _parse_bundle_spec(spec: str) -> tuple[str, str | None]:
    """Split ``alias=target`` CLI bundle specs into the alias and optional target path."""
    if "=" not in spec:
        return spec, None
    alias, target = spec.split("=", 1)
    alias = alias.strip()
    target = target.strip()
    if not alias:
        raise typer.BadParameter(f"Invalid bundle spec (empty alias): {spec}")
    if not target:
        raise typer.BadParameter(f"Invalid bundle spec (empty target): {spec}")
    return alias, target


def _resolve_bundle_from_path(alias: str, target_path: Path) -> list[tuple[str, str, Path]]:
    """Return bundle members discovered beneath ``target_path`` (single path or directory)."""
    resolved = target_path.expanduser()
    if not resolved.exists():
        raise typer.BadParameter(f"Bundle target not found: {target_path}")
    members: list[tuple[str, str, Path]] = []
    if resolved.is_file():
        suffix = resolved.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
            base_dir = resolved.parent
            if isinstance(data, dict):
                for key in sorted(data):
                    scenario_dir = base_dir / key
                    scenario_file = scenario_dir / "scenario.yaml"
                    if scenario_file.exists():
                        members.append((alias, str(key), scenario_file))
            if members:
                return members
            return [(alias, resolved.stem, resolved)]
        return [(alias, resolved.stem, resolved)]
    metadata_file = resolved / "metadata.yaml"
    if metadata_file.exists():
        return _resolve_bundle_from_path(alias, metadata_file)
    scenario_file = resolved / "scenario.yaml"
    if scenario_file.exists():
        return [(alias, resolved.name, scenario_file)]
    child_members: list[tuple[str, str, Path]] = []
    for child in sorted(resolved.iterdir()):
        if not child.is_dir():
            continue
        child_scenario = child / "scenario.yaml"
        if child_scenario.exists():
            child_members.append((alias, child.name, child_scenario))
    if child_members:
        return child_members
    raise typer.BadParameter(f"Bundle target does not contain scenarios: {target_path}")


def _resolve_bundle_spec(spec: str) -> list[tuple[str, str, Path]]:
    """Expand a CLI bundle spec into ``(bundle_alias, member_name, scenario_path)`` tuples."""
    alias, target = _parse_bundle_spec(spec)
    normalized = alias.lower()
    if target is None and normalized in TUNING_BUNDLE_ALIASES:
        bundle_members: list[tuple[str, str, Path]] = []
        for member_name, scenario_path in TUNING_BUNDLE_ALIASES[normalized]:
            bundle_members.append((alias, member_name, scenario_path))
        return bundle_members
    target_path = Path(target) if target else Path(alias)
    bundle_alias = alias if target else target_path.name
    return _resolve_bundle_from_path(bundle_alias, target_path)


def _collect_tuning_scenarios(
    scenario_args: Sequence[Path] | None,
    bundle_specs: Sequence[str] | None,
) -> tuple[list[Path], dict[Path, dict[str, str]]]:
    """Collect explicit scenario paths and bundle members for tuning commands."""
    discovered: list[Path] = []
    bundle_map: dict[Path, dict[str, str]] = {}

    if scenario_args:
        for entry in scenario_args:
            for scenario_path in _discover_scenarios_from_path(entry):
                discovered.append(scenario_path)

    if bundle_specs:
        for spec in bundle_specs:
            for alias, member, scenario_path in _resolve_bundle_spec(spec):
                discovered.append(scenario_path)
                bundle_map[scenario_path.resolve()] = {
                    "bundle": alias,
                    "bundle_member": member,
                }

    ordered: list[Path] = []
    seen: set[Path] = set()
    for scenario_path in discovered:
        resolved = scenario_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(scenario_path)
    return ordered, bundle_map


@app.command()
def validate(scenario: Path):
    """Validate a scenario bundle and print an entity summary.

    Parameters
    ----------
    scenario : pathlib.Path
        Path to the ``scenario.yaml`` file or directory containing the FHOPS data bundle.

    Notes
    -----
    The command loads the scenario via :func:`fhops.scenario.io.load_scenario`, instantiates a
    :class:`fhops.scenario.contract.Problem`, and prints counts of days/blocks/machines/landings so
    users can verify that parsing succeeded before attempting solver runs.
    """
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
    """Build the MIP model without solving and print component counts.

    Parameters
    ----------
    scenario : pathlib.Path
        Scenario YAML path to load.

    Notes
    -----
    This helper is useful for verifying that Pyomo/HiGHS dependencies are correctly installed and
    for inspecting the size of the generated model (sets/variables/constraints) before committing to
    a full solve.  It invokes :func:`fhops.optimization.mip.builder.build_model` and never calls a
    solver.
    """
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
    driver: str = typer.Option(
        "auto",
        help="MIP driver: auto|highs-appsi|highs-exec|gurobi|gurobi-appsi|gurobi-direct",
    ),
    debug: bool = typer.Option(False, "--debug", help="Verbose tracebacks & solver logs"),
):
    """Solve the scenario with the exact MIP and write assignments/KPIs.

    Parameters
    ----------
    scenario : pathlib.Path
        Scenario YAML path to load.
    out : pathlib.Path
        CSV destination for the assignment matrix (``machine_id, block_id, day, shift_id``).
    time_limit : int, default=60
        Solver wall-clock time limit in seconds.
    driver : str, default="auto"
        HiGHS driver backend (`auto`, `highs-appsi`, `highs-exec`, or Gurobi variants when licensed).
    debug : bool, default=False
        Enable verbose solver logging and rich tracebacks.

    Notes
    -----
    The command streams a KPI summary to the console via :func:`fhops.evaluation.compute_kpis`.
    The return value mirrors :func:`fhops.optimization.mip.solve_mip` (objective, assignments,
    solver metadata) and is serialized through the CLI side-effects.
    """
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


@app.command("solve-mip-operational")
def solve_mip_operational_cmd(
    scenario: Path,
    out: Path = typer.Option(..., "--out", help="Output CSV path"),
    solver: str = typer.Option("highs", help="MILP solver backend (default: highs)."),
    time_limit: int | None = typer.Option(
        None, "--time-limit", help="Optional wall-clock time limit (seconds)."
    ),
    gap: float | None = typer.Option(None, "--gap", help="Optional relative MIP gap target (0-1)."),
    debug: bool = typer.Option(False, "--debug", help="Verbose solver output/tracebacks."),
):
    """Solve the operational (day×shift) MILP prototype and emit assignments."""

    if debug:
        _enable_rich_tracebacks()
        console.print(
            f"[dim]types → scenario={type(scenario).__name__}, out={type(out).__name__}[/]"
        )

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    bundle = build_operational_bundle(pb)

    result = solve_operational_milp(
        bundle,
        solver=solver,
        time_limit=time_limit,
        gap=gap,
        tee=debug,
    )
    assignments = cast(pd.DataFrame, result.get("assignments", pd.DataFrame()))
    out.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(str(out), index=False)
    console.print(
        f"Operational MILP solver_status={result.get('solver_status')} "
        f"termination={result.get('termination_condition')} "
        f"objective={result.get('objective')}"
    )
    console.print(f"Assignments written to {out}")
    if not assignments.empty:
        metrics = compute_kpis(pb, assignments)
        _print_kpi_summary(metrics)
    else:
        console.print("[yellow]No feasible assignment returned; skipping KPI summary.[/]")


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
    tier_label: str | None = typer.Option(
        None,
        "--tier-label",
        help="Optional label describing the budget tier for telemetry summaries.",
    ),
    cooling_rate: float = typer.Option(
        0.999,
        "--cooling-rate",
        help="Simulated annealing cooling rate (0<rate<1; closer to 1 cools slower).",
    ),
    restart_interval: int = typer.Option(
        0,
        "--restart-interval",
        help="Non-accepting iterations before SA restarts (0=auto).",
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
    """Solve the scenario with the simulated annealing heuristic and emit KPIs.

    Parameters
    ----------
    scenario : pathlib.Path
        Scenario YAML bundle to load.
    out : pathlib.Path
        CSV destination for heuristic assignments (``machine_id, block_id, day, shift_id``).
    iters : int, default=2000
        Number of annealing iterations to run per worker.
    seed : int, default=42
        RNG seed controlling reproducibility.
    debug : bool, default=False
        Emit verbose debug logs and enable rich tracebacks.
    operator / operator_weight / operator_preset / profile :
        CLI mirrors of :func:`fhops.optimization.heuristics.solve_sa` arguments. Use them to
        restrict operators, override weights, or load saved solver profiles.
    list_operator_presets / list_profiles : bool
        Utility flags that print the registry/profile catalogues and exit.
    show_operator_stats : bool
        When ``True`` print the per-operator proposal/acceptance table produced by SA.
    telemetry_log : pathlib.Path | None
        When provided, append run metadata and optional step logs to JSONL files.
    tier_label : str | None
        Custom label forwarded to telemetry to distinguish experiment tiers/budgets.
    cooling_rate : float, default=0.999
        Cooling rate multiplier (higher = slower cooling).
    restart_interval : int, default=0
        Non-accepting-iteration interval before restarts (0 auto-scales with ``iters``).
    kpi_mode : str, default="extended"
        Controls verbosity of KPI summaries (``basic`` omits diagnostics).
    batch_neighbours : int, default=1
        Number of neighbour candidates sampled per iteration.
    parallel_workers : int, default=1
        Worker threads for evaluating batched candidates or multi-start orchestration.
    multi_start : int, default=1
        Number of SA instances to launch in parallel before selecting the best objective.

    Notes
    -----
    The command persists assignments to ``--out``, prints KPI summaries using the requested mode,
    and optionally records telemetry events so bench/tuning workflows can analyse solver health.
    """
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
    scenario_label = getattr(sc, "name", None) or scenario.stem
    machine_costs = _machine_cost_snapshot(sc)
    watch_runner: LiveWatch | None = None
    if watch:
        if console.is_terminal:
            watch_runner = LiveWatch(WatchConfig(refresh_interval=watch_refresh), console=console)
            watch_runner.start()
        else:
            console.print("[yellow]Watch mode disabled: not running in an interactive terminal.[/]")
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
    restart_value = restart_interval if restart_interval > 0 else None
    sa_kwargs: dict[str, Any] = {
        "iters": iters,
        "operators": resolved.operators,
        "operator_weights": resolved_weights,
        "batch_size": batch_arg,
        "max_workers": worker_arg,
        "cooling_rate": cooling_rate,
        "restart_interval": restart_value,
    }
    if resolved.extra_kwargs:
        sa_kwargs.update(resolved.extra_kwargs)
    if watch_runner:
        sa_kwargs["watch_sink"] = watch_runner.sink
        sa_kwargs["watch_interval"] = max(1, iters // 200 or 1)
        sa_kwargs["watch_metadata"] = {
            "scenario": scenario_label,
            "solver": "sa",
        }

    runs_meta = None
    seed_used = seed
    base_telemetry_context: dict[str, Any] | None = None
    if telemetry_log:
        base_telemetry_context = {
            "scenario_path": str(scenario),
            "source": "cli.solve-heur",
            "machine_costs": machine_costs,
        }
        if selected_profile:
            base_telemetry_context["profile"] = selected_profile.name
            base_telemetry_context["profile_version"] = selected_profile.version
        if tier_label:
            base_telemetry_context["tier"] = tier_label
        tuner_meta_payload = {
            "algorithm": "sa",
            "budget": {
                "iters": iters,
                "tier": tier_label,
            },
            "config": {
                "batch_size": batch_arg,
                "max_workers": worker_arg,
                "parallel_multistart": multi_start,
                "cooling_rate": cooling_rate,
                "restart_interval": restart_value if restart_value is not None else "auto",
            },
        }
        base_telemetry_context["tuner_meta"] = tuner_meta_payload
        sa_kwargs["telemetry_log"] = telemetry_log
        sa_kwargs["telemetry_context"] = base_telemetry_context

    try:
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
    finally:
        if watch_runner:
            watch_runner.stop()
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
            "machine_costs": machine_costs,
        }
        if tier_label:
            record["tier"] = tier_label
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
    tier_label: str | None = typer.Option(
        None,
        "--tier-label",
        help="Optional label describing the budget tier for telemetry summaries.",
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
    """Solve with the Iterated Local Search heuristic and emit KPI summaries.

    Parameters
    ----------
    scenario : pathlib.Path
        Scenario YAML bundle to load.
    out : pathlib.Path
        CSV destination for ILS assignments.
    iters : int, default=250
        Number of ILS outer iterations (perturbation + local search cycles).
    seed : int, default=42
        RNG seed for reproducible operator selection.
    perturbation_strength / stall_limit / hybrid_use_mip / hybrid_mip_time_limit :
        Direct mirrors of :func:`fhops.optimization.heuristics.solve_ils` arguments controlling
        diversification and optional MIP warm starts.
    operator / operator_weight / operator_preset / profile :
        Controls which operators are active and allows profile presets to be merged.
    list_operator_presets / list_profiles :
        Convenience flags that print the catalogues then exit.
    batch_neighbours / parallel_workers :
        Tune the number of neighbours sampled per step and how many worker threads score them.
    telemetry_log / tier_label :
        Optional telemetry logging location plus a label to group runs in the dashboard.
    watch / watch_refresh :
        Enable and configure the live Rich dashboard for solver progress.
    kpi_mode : str, default="extended"
        Toggle KPI verbosity (``basic`` omits detailed breakdowns).
    show_operator_stats : bool
        When ``True`` print proposal/acceptance metrics emitted by ``solve_ils``.

    Notes
    -----
    Behaviour matches ``solve-heur`` aside from the iterative local search loop.  Assignments and
    KPIs are written identically so results can be compared solver-to-solver.
    """
    if list_profiles:
        console.print("Solver profiles:")
        console.print(format_profiles())
        raise typer.Exit()

    if list_operator_presets:
        console.print("Operator presets:")
        console.print(format_operator_presets())
        raise typer.Exit()

    sc = load_scenario(str(scenario))
    scenario_label = getattr(sc, "name", None) or scenario.stem
    machine_costs = _machine_cost_snapshot(sc)
    watch_runner: LiveWatch | None = None
    if watch:
        if console.is_terminal:
            watch_runner = LiveWatch(WatchConfig(refresh_interval=watch_refresh), console=console)
            watch_runner.start()
        else:
            console.print("[yellow]Watch mode disabled: not running in an interactive terminal.[/]")
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
            "machine_costs": machine_costs,
        }
        if selected_profile:
            base_context["profile"] = selected_profile.name
            base_context["profile_version"] = selected_profile.version
        if isinstance(existing_ctx, dict):
            base_context.update(existing_ctx)
        if tier_label:
            base_context["tier"] = tier_label
        tuner_meta_payload = {
            "algorithm": "ils",
            "budget": {
                "iters": iters,
                "tier": tier_label,
            },
            "config": {
                "perturbation_strength": perturbation_strength,
                "stall_limit": stall_limit,
                "hybrid_use_mip": hybrid_use_mip,
            },
        }
        base_context["tuner_meta"] = tuner_meta_payload
        telemetry_kwargs["telemetry_log"] = telemetry_log
        telemetry_kwargs["telemetry_context"] = base_context
    elif isinstance(existing_ctx, dict):
        extra_ils_kwargs["telemetry_context"] = existing_ctx

    solver_kwargs: dict[str, Any] = {
        "iters": iters,
        "seed": seed,
        "operators": resolved.operators,
        "operator_weights": resolved.operator_weights or None,
        "batch_size": batch_arg,
        "max_workers": worker_arg,
        "perturbation_strength": perturbation_strength,
        "stall_limit": stall_limit,
        "hybrid_use_mip": hybrid_use_mip,
        "hybrid_mip_time_limit": hybrid_mip_time_limit,
    }
    solver_kwargs.update(extra_ils_kwargs)
    solver_kwargs.update(telemetry_kwargs)
    if watch_runner:
        solver_kwargs["watch_sink"] = watch_runner.sink
        solver_kwargs["watch_interval"] = max(1, iters // 50 or 1)
        solver_kwargs["watch_metadata"] = {
            "scenario": scenario_label,
            "solver": "ils",
        }

    try:
        res = solve_ils(pb, **solver_kwargs)
    finally:
        if watch_runner:
            watch_runner.stop()
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
            "machine_costs": machine_costs,
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
        1_000_000, "--stall-limit", help="Max non-improving iterations before stopping."
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
    tier_label: str | None = typer.Option(
        None,
        "--tier-label",
        help="Optional label describing the budget tier for telemetry summaries.",
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
    """Solve with the Tabu Search heuristic and emit KPI summaries.

    Parameters
    ----------
    scenario : pathlib.Path
        Scenario YAML bundle to load.
    out : pathlib.Path
        CSV destination for Tabu assignments.
    iters : int, default=2000
        Number of Tabu Search iterations to execute.
    seed : int, default=42
        RNG seed for reproducible neighbourhood sampling.
    tabu_tenure : int, default=0
        Override for tabu tenure (``0`` lets the solver auto-size it).
    stall_limit : int, default=1_000_000
        Max non-improving iterations before halting.
    batch_neighbours / parallel_workers :
        Control neighbourhood sampling volume and scoring concurrency.
    operator / operator_weight / operator_preset / profile :
        Operator registry controls mirroring :func:`fhops.optimization.heuristics.solve_tabu`.
    list_operator_presets / list_profiles :
        Print available presets/profiles before exiting.
    telemetry_log / tier_label :
        Optional telemetry logging destination and label for grouping experiments.
    watch / watch_refresh :
        Enable and configure the live Rich dashboard during Tabu runs.
    kpi_mode : str, default="extended"
        KPI verbosity switch (``basic`` or ``extended``).
    watch / watch_refresh :
        Enable and configure the live Rich dashboard for Tabu runs.
    show_operator_stats : bool
        When ``True`` print proposal/acceptance details produced by Tabu Search.

    Notes
    -----
    Results are persisted to ``--out`` and summarised via the shared KPI printer so they can be
    compared against SA/ILS/MIP runs.
    """
    if list_profiles:
        console.print("Solver profiles:")
        console.print(format_profiles())
        raise typer.Exit()

    if list_operator_presets:
        console.print("Operator presets:")
        console.print(format_operator_presets())
        raise typer.Exit()

    sc = load_scenario(str(scenario))
    scenario_label = getattr(sc, "name", None) or scenario.stem
    machine_costs = _machine_cost_snapshot(sc)
    watch_runner: LiveWatch | None = None
    if watch:
        if console.is_terminal:
            watch_runner = LiveWatch(WatchConfig(refresh_interval=watch_refresh), console=console)
            watch_runner.start()
        else:
            console.print("[yellow]Watch mode disabled: not running in an interactive terminal.[/]")
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
            "machine_costs": machine_costs,
        }
        if selected_profile:
            base_context["profile"] = selected_profile.name
            base_context["profile_version"] = selected_profile.version
        if isinstance(existing_ctx, dict):
            base_context.update(existing_ctx)
        if tier_label:
            base_context["tier"] = tier_label
        tuner_meta_payload = {
            "algorithm": "tabu",
            "budget": {
                "iters": iters,
                "tier": tier_label,
            },
            "config": {
                "tabu_tenure": tenure if tenure is not None else max(10, len(pb.scenario.machines)),
                "stall_limit": stall_limit,
            },
        }
        base_context["tuner_meta"] = tuner_meta_payload
        telemetry_kwargs["telemetry_log"] = telemetry_log
        telemetry_kwargs["telemetry_context"] = base_context
    elif isinstance(existing_ctx, dict):
        profile_extra_kwargs["telemetry_context"] = existing_ctx

    solver_kwargs: dict[str, Any] = {
        "iters": iters,
        "seed": seed,
        "operators": resolved.operators,
        "operator_weights": resolved.operator_weights or None,
        "batch_size": batch_arg,
        "max_workers": worker_arg,
        "tabu_tenure": tenure,
        "stall_limit": stall_limit,
    }
    solver_kwargs.update(profile_extra_kwargs)
    solver_kwargs.update(telemetry_kwargs)
    if watch_runner:
        solver_kwargs["watch_sink"] = watch_runner.sink
        solver_kwargs["watch_interval"] = max(1, iters // 50 or 1)
        solver_kwargs["watch_metadata"] = {
            "scenario": scenario_label,
            "solver": "tabu",
        }

    try:
        res = solve_tabu(pb, **solver_kwargs)
    finally:
        if watch_runner:
            watch_runner.stop()
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
            "machine_costs": machine_costs,
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
    """Compute KPI summaries for a schedule CSV and print them to the console.

    Parameters
    ----------
    scenario : pathlib.Path
        Scenario YAML bundle to load.
    assignments_csv : pathlib.Path
        CSV containing ``machine_id, block_id, day, shift_id`` rows produced by a solver.
    kpi_mode : str, default="extended"
        Verbosity toggle for the KPI printer (``basic`` omits deep breakdowns).

    Notes
    -----
    This is a fast wrapper around :func:`fhops.evaluation.compute_kpis` for users who only need
    aggregated KPIs without the full playback/export pipeline.
    """
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    df = pd.read_csv(str(assignments_csv))
    kpis = compute_kpis(pb, df)
    _print_kpi_summary(kpis, mode=kpi_mode)


@app.command("eval-playback")
def eval_playback(
    scenario: Path,
    assignments_csv: Path = typer.Option(
        ..., "--assignments", help="Assignments CSV (machine_id, block_id, day, shift_id)."
    ),
    shift_out: Path | None = typer.Option(
        None, "--shift-out", help="Optional path to save shift-level playback summary (CSV)."
    ),
    day_out: Path | None = typer.Option(
        None, "--day-out", help="Optional path to save day-level playback summary (CSV)."
    ),
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
    """Run deterministic/stochastic playback to produce shift/day summaries.

    Parameters
    ----------
    scenario : pathlib.Path
        Scenario YAML bundle to load.
    assignments_csv : pathlib.Path
        Assignments CSV (same schema as solver outputs) to replay.
    shift_out / day_out / shift_parquet / day_parquet :
        Optional destinations for the exported playback summaries (CSV and/or Parquet).
    include_idle : bool, default=False
        Whether to emit idle rows for machine/shift slots with no work.
    samples : int, default=1
        Number of stochastic samples to run (``1`` keeps deterministic playback).
    base_seed : int, default=123
        RNG seed forwarded to stochastic playback.
    downtime_probability / downtime_max_concurrent :
        Parameters that control random downtime events.
    weather_probability / weather_severity / weather_window :
        Parameters that control weather impacts.
    landing_probability / landing_multiplier_low / landing_multiplier_high / landing_duration :
        Parameters for landing throughput shocks.
    summary_md : pathlib.Path | None
        Optional Markdown report destination.
    telemetry_log : pathlib.Path | None
        Optional telemetry JSONL log to capture playback runs.

    Notes
    -----
    Use this command when you need shift/day tables, KPI exports, or stochastic playback for Monte
    Carlo studies.  Deterministic playback is automatically selected when all stochastic knobs are
    zeroed out.
    """

    sc = load_scenario(str(scenario))
    machine_costs = _machine_cost_snapshot(sc)
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
        "source": "eval-playback",
        **scenario_features,
        "machine_costs": machine_costs,
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

    with telemetry_logger if telemetry_logger else nullcontext() as run_logger:
        playback_config = PlaybackConfig(include_idle_records=include_idle)

        deterministic_mode = (
            samples <= 1
            and downtime_probability <= 0
            and weather_probability <= 0
            and landing_probability <= 0
        )

        shift_summaries: list[ShiftSummary]
        day_summaries: list[DaySummary]

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
        for shift_summary in shift_summaries[:20]:
            shift_table.add_row(
                shift_summary.machine_id,
                str(shift_summary.day),
                shift_summary.shift_id,
                f"{shift_summary.production_units:.2f}",
                f"{shift_summary.total_hours:.2f}",
                f"{(shift_summary.idle_hours or 0.0):.2f}",
                f"{shift_summary.mobilisation_cost:.2f}",
                str(shift_summary.sequencing_violations),
                f"{(shift_summary.utilisation_ratio or 0.0):.2f}",
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
        for day_summary in day_summaries:
            day_table.add_row(
                str(day_summary.day),
                f"{day_summary.production_units:.2f}",
                f"{day_summary.total_hours:.2f}",
                f"{(day_summary.idle_hours or 0.0):.2f}",
                f"{day_summary.mobilisation_cost:.2f}",
                str(day_summary.completed_blocks),
                str(day_summary.sequencing_violations),
                f"{(day_summary.utilisation_ratio or 0.0):.2f}",
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
            console.print(
                "[red]Parquet export requires either pyarrow or fastparquet. Install one of them to enable this feature.[/red]"
            )
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
            export_payload = {}
            if shift_out:
                export_payload["shift_csv"] = str(shift_out)
            if day_out:
                export_payload["day_csv"] = str(day_out)
            if shift_parquet:
                export_payload["shift_parquet"] = str(shift_parquet)
            if day_parquet:
                export_payload["day_parquet"] = str(day_parquet)
            if summary_md:
                export_payload["summary_md"] = str(summary_md)
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
                "export": export_payload,
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
    """Run both MIP and simulated annealing to compare objective quality.

    Parameters
    ----------
    scenario : pathlib.Path
        Scenario YAML bundle to load.
    out_dir : pathlib.Path, default="bench_out"
        Directory where solver outputs are stored (one CSV per solver).
    time_limit : int, default=60
        MIP wall-clock limit in seconds.
    iters : int, default=5000
        Simulated annealing iteration budget.
    driver : str, default="auto"
        MIP driver selection.
    debug : bool, default=False
        Enable verbose logging and rich tracebacks.

    Notes
    -----
    This helper predates the richer ``fhops bench`` app but remains handy for quick smoke tests.  It
    writes ``mip_solution.csv`` and ``sa_solution.csv`` under ``out_dir`` and prints KPI summaries
    for both solvers.
    """
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
    scenarios: list[Path] | None = typer.Argument(
        None,
        exists=True,
        readable=True,
        dir_okay=True,
        help="Scenario YAMLs or directories to sample during tuning (repeatable).",
    ),
    bundle: list[str] | None = typer.Option(
        None,
        "--bundle",
        "-b",
        help="Scenario bundle alias or path (repeatable). Supports alias=path syntax.",
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
    tier_label: str | None = typer.Option(
        None,
        "--tier-label",
        help="Optional label describing the budget tier for telemetry summaries.",
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
):
    """Randomly sample simulated annealing configurations and log telemetry.

    Parameters
    ----------
    scenarios : list[pathlib.Path] | None
        Explicit scenario YAML paths (repeatable). Can be omitted when using ``--bundle``.
    bundle : list[str] | None
        Scenario bundle aliases or ``alias=path`` overrides that expand to multiple scenarios.
    telemetry_log : pathlib.Path
        JSONL telemetry sink where each run (and optional tuner summary) is appended.
    runs : int, default=3
        Number of random operator configurations to evaluate per scenario.
    iters : int, default=250
        Simulated annealing iteration budget per sampled configuration.
    base_seed : int, default=123
        Seed controlling the RNG that draws per-run seeds/batch sizes/operator weights.
    tier_label : str | None
        Optional label forwarded to telemetry to distinguish experimentation budgets.

    Notes
    -----
    Each sampled configuration records operator weights, batch size, objective, and references to
    telemetry artefacts so downstream notebooks can triage winners.  The function prints a summary
    table ordered by objective and persists a ``tuner_summary`` record when telemetry is enabled.
    """
    scenario_files, bundle_map = _collect_tuning_scenarios(scenarios, bundle)
    if not scenario_files:
        console.print("[yellow]No scenarios resolved. Provide --bundle or explicit paths.[/]")
        raise typer.Exit(1)

    watch_runner: LiveWatch | None = None
    if watch and console.is_terminal:
        watch_runner = LiveWatch(WatchConfig(refresh_interval=watch_refresh), console=console)
    elif watch and not console.is_terminal:
        console.print("[yellow]Watch mode disabled: not running in an interactive terminal.[/]")

    rng = random.Random(base_seed)
    registry = OperatorRegistry.from_defaults()
    operator_names = list(registry.names())

    results: list[dict[str, Any]] = []

    with watch_runner or nullcontext():
        for scenario_path in scenario_files:
            sc = load_scenario(str(scenario_path))
            pb = Problem.from_scenario(sc)
            scenario_resolved = scenario_path.resolve()
            bundle_meta = bundle_map.get(scenario_resolved)
            scenario_display = (
                getattr(sc, "name", None) or scenario_path.parent.name or scenario_path.stem
            )
            if bundle_meta:
                console.print(
                    f"[dim]Tuning {scenario_display} (bundle={bundle_meta['bundle']}, runs={runs})[/]"
                )
            else:
                console.print(f"[dim]Tuning {scenario_display} ({runs} run(s))[/]")

            for run_idx in range(runs):
                run_seed = rng.randrange(1, 1_000_000_000)
                batch_size_choice = rng.choice([1, 2, 3, 4, 5])
                cooling_rate_choice = round(rng.uniform(0.995, 0.99999), 6)
                restart_interval_choice = rng.choice([0, 100, 250, 500, 750, 1000, 1500])
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
                    if bundle_meta:
                        telemetry_context["bundle"] = bundle_meta["bundle"]
                        telemetry_context["bundle_member"] = bundle_meta.get(
                            "bundle_member", scenario_display
                        )
                    if tier_label:
                        telemetry_context["tier"] = tier_label
                    tuner_meta_payload = {
                        "algorithm": "random",
                        "budget": {
                            "runs_total": runs,
                            "iters_per_run": iters,
                            "tier": tier_label,
                        },
                        "config": {
                            "batch_size": batch_size_choice,
                            "operator_count": weight_count,
                            "operators": operator_weights,
                            "cooling_rate": cooling_rate_choice,
                            "restart_interval": restart_interval_choice,
                        },
                        "progress": {
                            "run_index": run_idx + 1,
                            "total_runs": runs,
                        },
                    }
                    if bundle_meta:
                        tuner_meta_payload["bundle"] = bundle_meta["bundle"]
                        tuner_meta_payload["bundle_member"] = bundle_meta.get(
                            "bundle_member", scenario_display
                        )
                    telemetry_kwargs = {
                        "telemetry_log": telemetry_log,
                        "telemetry_context": telemetry_context,
                    }
                    telemetry_kwargs["telemetry_context"]["tuner_meta"] = tuner_meta_payload

                sa_kwargs: dict[str, Any] = {
                    "iters": iters,
                    "seed": run_seed,
                    "batch_size": batch_size_choice if batch_size_choice > 1 else None,
                    "operator_weights": operator_weights,
                    "cooling_rate": cooling_rate_choice,
                    "restart_interval": (
                        restart_interval_choice if restart_interval_choice > 0 else None
                    ),
                }
                sa_kwargs.update(telemetry_kwargs)
                if watch_runner:
                    sa_kwargs["watch_sink"] = watch_runner.sink
                    sa_kwargs["watch_interval"] = max(1, iters // 200 or 1)
                    sa_kwargs["watch_metadata"] = {
                        "scenario": scenario_display,
                        "solver": f"tune-random[{run_idx + 1}]",
                    }

                try:
                    res = solve_sa(pb, **sa_kwargs)
                except Exception as exc:  # pragma: no cover - defensive
                    console.print(
                        f"[yellow]Run failed for {scenario_path} (seed={run_seed}): {exc!r}[/]"
                    )
                    continue

                results.append(
                    {
                        "scenario": scenario_display,
                        "scenario_key": (
                            f"{bundle_meta['bundle']}:{bundle_meta.get('bundle_member', scenario_display)}"
                            if bundle_meta
                            else scenario_display
                        ),
                        "bundle": bundle_meta["bundle"] if bundle_meta else None,
                        "objective": float(res.get("objective", 0.0)),
                        "seed": run_seed,
                        "batch_size": batch_size_choice,
                        "cooling_rate": cooling_rate_choice,
                        "restart_interval": restart_interval_choice,
                        "operator_weights": operator_weights,
                        "telemetry_run_id": res.get("meta", {}).get("telemetry_run_id"),
                    }
                )

    if not results:
        console.print("[yellow]Random tuner did not produce any successful runs.[/]")
        return

    table = Table(title="Random tuner results", show_lines=False)
    include_bundle = any(entry.get("bundle") for entry in results)
    table.add_column("Scenario")
    if include_bundle:
        table.add_column("Bundle")
    table.add_column("Objective", justify="right")
    table.add_column("Seed", justify="right")
    table.add_column("Batch", justify="right")
    table.add_column("Cooling", justify="right")
    table.add_column("Restart", justify="right")
    table.add_column("Operators")

    for entry in sorted(results, key=lambda item: item["objective"], reverse=True):
        op_preview = ", ".join(
            f"{name}={weight:.2f}" for name, weight in sorted(entry["operator_weights"].items())
        )
        row = [
            entry["scenario"],
        ]
        if include_bundle:
            row.append(entry.get("bundle") or "")
        row.extend(
            [
                f"{entry['objective']:.3f}",
                str(entry["seed"]),
                str(entry["batch_size"]),
                f"{entry['cooling_rate']:.6f}",
                (str(entry["restart_interval"]) if entry["restart_interval"] else "auto"),
                op_preview if len(op_preview) < 80 else op_preview[:77] + "...",
            ]
        )
        table.add_row(*row)
    console.print(table)

    if telemetry_log:
        console.print(
            f"[dim]{len(results)} telemetry record(s) written to {telemetry_log}. Step logs stored in {telemetry_log.parent / 'steps'}.[/]"
        )
        scenario_best: dict[str, float] = {}
        for entry in results:
            key = entry.get("scenario_key", entry["scenario"])
            scenario_best[key] = max(scenario_best.get(key, float("-inf")), entry["objective"])
        summary_record = {
            "record_type": "tuner_summary",
            "schema_version": "1.1",
            "algorithm": "random",
            "scenarios_evaluated": len(scenario_best),
            "configurations": len(results),
            "scenario_best": scenario_best,
        }
        summary_record = persist_tuner_summary(
            telemetry_log.with_suffix(".sqlite"),
            summary_record,
        )
        append_jsonl(telemetry_log, summary_record)


@app.command("tune-grid")
def tune_grid_cli(
    scenarios: list[Path] | None = typer.Argument(
        None,
        exists=True,
        readable=True,
        dir_okay=True,
        help="Scenario YAMLs or bundle directories to evaluate.",
    ),
    bundle: list[str] | None = typer.Option(
        None,
        "--bundle",
        "-b",
        help="Scenario bundle alias or path (repeatable). Supports alias=path syntax.",
    ),
    telemetry_log: Path = typer.Option(
        Path("telemetry/runs.jsonl"),
        "--telemetry-log",
        help="Telemetry JSONL capturing per-run metadata (optional).",
        dir_okay=False,
        writable=False,
    ),
    batch_size: list[int] = typer.Option(
        None,
        "--batch-size",
        help="Batch size options to evaluate (repeatable). Defaults to [1, 2, 3].",
    ),
    preset: list[str] = typer.Option(
        None,
        "--preset",
        help="Operator preset(s) to evaluate (repeatable). Defaults to balanced/explore/mobilisation.",
    ),
    iters: int = typer.Option(
        250,
        "--iters",
        min=10,
        help="Simulated annealing iterations per configuration.",
    ),
    seed: int = typer.Option(
        123,
        "--seed",
        help="Base seed (increments deterministically across grid points).",
    ),
    tier_label: str | None = typer.Option(
        None,
        "--tier-label",
        help="Optional label describing the budget tier for telemetry summaries.",
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
):
    """Exhaustively evaluate a grid of operator presets and batch sizes.

    Parameters
    ----------
    scenarios : list[pathlib.Path] | None
        Scenario YAML paths (repeatable). Optional when ``--bundle`` is provided.
    bundle : list[str] | None
        Scenario bundle aliases or ``alias=path`` overrides to expand into multiple cases.
    telemetry_log : pathlib.Path
        JSONL telemetry sink for per-run metadata and tuner summaries.
    batch_size : list[int]
        Explicit batch sizes to evaluate (defaults to ``[1, 2, 3]`` when omitted).
    preset : list[str]
        Operator preset names to evaluate (defaults to ``balanced``, ``explore``, ``mobilisation``).
    iters : int, default=250
        Simulated annealing iteration budget per configuration.
    seed : int, default=123
        Base seed incremented deterministically across configurations for reproducibility.
    tier_label : str | None
        Optional telemetry label for grouping tuning campaigns.

    Notes
    -----
    The command prints a table ordered by objective and writes telemetry records summarising each
    configuration.  When telemetry logging is enabled, a ``tuner_summary`` record captures the best
    objective per scenario.
    """
    scenario_files, bundle_map = _collect_tuning_scenarios(scenarios, bundle)
    if not scenario_files:
        console.print("[yellow]No scenarios resolved. Provide --bundle or explicit paths.[/]")
        raise typer.Exit(1)

    batch_values = sorted(set(batch_size)) if batch_size else [1, 2, 3]
    preset_values = [name.lower() for name in (preset or ["balanced", "explore", "mobilisation"])]
    for name in preset_values:
        if name not in OPERATOR_PRESETS:
            console.print(
                f"[red]Unknown operator preset '{name}'. Available: {', '.join(sorted(OPERATOR_PRESETS))}[/]"
            )
            raise typer.Exit(1)

    watch_runner: LiveWatch | None = None
    if watch and console.is_terminal:
        watch_runner = LiveWatch(WatchConfig(refresh_interval=watch_refresh), console=console)
    elif watch and not console.is_terminal:
        console.print("[yellow]Watch mode disabled: not running in an interactive terminal.[/]")

    results: list[dict[str, Any]] = []
    run_seed = seed

    with watch_runner or nullcontext():
        for scenario_path in scenario_files:
            sc = load_scenario(str(scenario_path))
            pb = Problem.from_scenario(sc)
            scenario_resolved = scenario_path.resolve()
            bundle_meta = bundle_map.get(scenario_resolved)
            scenario_display = (
                getattr(sc, "name", None) or scenario_path.parent.name or scenario_path.stem
            )
            config_count = len(batch_values) * len(preset_values)
            if bundle_meta:
                console.print(
                    f"[dim]Grid tuning {scenario_display} (bundle={bundle_meta['bundle']}, configs={config_count})[/]"
                )
            else:
                console.print(
                    f"[dim]Grid tuning {scenario_display} ({config_count} configuration(s))[/]"
                )
            config_counter = 0
            for batch_choice in batch_values:
                for preset_name in preset_values:
                    operator_weights = {
                        key.lower(): float(value)
                        for key, value in OPERATOR_PRESETS[preset_name].items()
                    }
                    telemetry_kwargs: dict[str, Any] = {}
                    if telemetry_log:
                        telemetry_kwargs = {
                            "telemetry_log": telemetry_log,
                            "telemetry_context": {
                                "source": "cli.tune-grid",
                                "preset": preset_name,
                                "batch_size": batch_choice,
                                "grid_seed": run_seed,
                            },
                        }
                        if bundle_meta:
                            telemetry_kwargs["telemetry_context"]["bundle"] = bundle_meta["bundle"]
                            telemetry_kwargs["telemetry_context"]["bundle_member"] = (
                                bundle_meta.get("bundle_member", scenario_display)
                            )
                        if tier_label:
                            telemetry_kwargs["telemetry_context"]["tier"] = tier_label
                        config_counter += 1
                        tuner_meta_payload = {
                            "algorithm": "grid",
                            "budget": {
                                "total_configs": config_count,
                                "iters_per_config": iters,
                                "tier": tier_label,
                            },
                            "config": {
                                "preset": preset_name,
                                "batch_size": batch_choice,
                                "operators": operator_weights,
                            },
                            "progress": {
                                "config_index": config_counter,
                                "total_configs": config_count,
                            },
                        }
                        if bundle_meta:
                            tuner_meta_payload["bundle"] = bundle_meta["bundle"]
                            tuner_meta_payload["bundle_member"] = bundle_meta.get(
                                "bundle_member", scenario_display
                            )
                        telemetry_kwargs["telemetry_context"]["tuner_meta"] = tuner_meta_payload
                    sa_kwargs: dict[str, Any] = {
                        "iters": iters,
                        "seed": run_seed,
                        "batch_size": batch_choice if batch_choice > 1 else None,
                        "operator_weights": operator_weights,
                    }
                    sa_kwargs.update(telemetry_kwargs)
                    if watch_runner:
                        sa_kwargs["watch_sink"] = watch_runner.sink
                        sa_kwargs["watch_interval"] = max(1, iters // 200 or 1)
                        sa_kwargs["watch_metadata"] = {
                            "scenario": scenario_display,
                            "solver": f"tune-grid[{preset_name}/{batch_choice}]",
                        }
                    try:
                        res = solve_sa(pb, **sa_kwargs)
                    except Exception as exc:  # pragma: no cover - defensive
                        console.print(
                            f"[yellow]Run failed for {scenario_path} (preset={preset_name}, batch={batch_choice}): {exc!r}[/]"
                        )
                        run_seed += 1
                        continue

                    results.append(
                        {
                            "scenario": scenario_display,
                            "scenario_key": (
                                f"{bundle_meta['bundle']}:{bundle_meta.get('bundle_member', scenario_display)}"
                                if bundle_meta
                                else scenario_display
                            ),
                            "bundle": bundle_meta["bundle"] if bundle_meta else None,
                            "objective": float(res.get("objective", 0.0)),
                            "preset": preset_name,
                            "batch_size": batch_choice,
                            "seed": run_seed,
                            "telemetry_run_id": res.get("meta", {}).get("telemetry_run_id"),
                        }
                    )
                    run_seed += 1
        console.print("[yellow]Grid tuner did not produce any successful runs.[/]")
        return

    table = Table(title="Grid tuner results", show_lines=False)
    include_bundle = any(entry.get("bundle") for entry in results)
    table.add_column("Scenario")
    if include_bundle:
        table.add_column("Bundle")
    table.add_column("Objective", justify="right")
    table.add_column("Preset")
    table.add_column("Batch", justify="right")
    table.add_column("Seed", justify="right")

    for entry in sorted(results, key=lambda item: item["objective"], reverse=True):
        row = [
            entry["scenario"],
        ]
        if include_bundle:
            row.append(entry.get("bundle") or "")
        row.extend(
            [
                f"{entry['objective']:.3f}",
                entry["preset"],
                str(entry["batch_size"]),
                str(entry["seed"]),
            ]
        )
        table.add_row(*row)
    console.print(table)

    if telemetry_log:
        console.print(
            f"[dim]{len(results)} telemetry record(s) written to {telemetry_log}. Step logs stored in {telemetry_log.parent / 'steps'}.[/]"
        )
        scenario_best: dict[str, float] = {}
        for entry in results:
            key = entry.get("scenario_key", entry["scenario"])
            scenario_best[key] = max(scenario_best.get(key, float("-inf")), entry["objective"])
        summary_record = {
            "record_type": "tuner_summary",
            "schema_version": "1.1",
            "algorithm": "grid",
            "scenarios_evaluated": len(scenario_best),
            "configurations": len(results),
            "scenario_best": scenario_best,
        }
        summary_record = persist_tuner_summary(
            telemetry_log.with_suffix(".sqlite"),
            summary_record,
        )
        append_jsonl(telemetry_log, summary_record)


@app.command("tune-bayes")
def tune_bayes_cli(
    scenarios: list[Path] | None = typer.Argument(
        None,
        exists=True,
        readable=True,
        dir_okay=True,
        help="Scenario YAMLs or bundle directories to evaluate.",
    ),
    bundle: list[str] | None = typer.Option(
        None,
        "--bundle",
        "-b",
        help="Scenario bundle alias or path (repeatable). Supports alias=path syntax.",
    ),
    telemetry_log: Path = typer.Option(
        Path("telemetry/runs.jsonl"),
        "--telemetry-log",
        help="Telemetry JSONL capturing per-trial metadata (optional).",
        dir_okay=False,
        writable=False,
    ),
    trials: int = typer.Option(
        20,
        "--trials",
        min=1,
        help="Number of Bayesian optimisation trials per scenario.",
    ),
    iters: int = typer.Option(
        250,
        "--iters",
        min=10,
        help="Simulated annealing iterations per trial.",
    ),
    seed: int = typer.Option(
        123,
        "--seed",
        help="Random seed for the Bayesian sampler.",
    ),
    tier_label: str | None = typer.Option(
        None,
        "--tier-label",
        help="Optional label describing the budget tier for telemetry summaries.",
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
):
    """Optimise simulated annealing hyperparameters with Bayesian/SMBO search (Optuna TPE).

    Parameters
    ----------
    scenarios : list[pathlib.Path] | None
        Scenario YAML paths (repeatable). Optional when ``--bundle`` is provided.
    bundle : list[str] | None
        Scenario bundle aliases or ``alias=path`` overrides.
    telemetry_log : pathlib.Path
        JSONL telemetry sink capturing each Optuna trial plus a tuner summary.
    trials : int, default=20
        Number of Bayesian optimisation trials per scenario.
    iters : int, default=250
        Simulated annealing iteration budget per trial.
    seed : int, default=123
        Seed forwarded to the Optuna sampler and per-trial solver runs.
    tier_label : str | None
        Optional telemetry label describing the experiment budget/tier.

    Notes
    -----
    Each Optuna trial samples operator weights and batch size, runs ``solve_sa``, and records the
    resulting objective.  Results are summarised in a Rich table, the best trial is printed, and
    telemetry consumers receive both per-trial events and a ``tuner_summary`` snapshot.
    """

    scenario_files, bundle_map = _collect_tuning_scenarios(scenarios, bundle)
    if not scenario_files:
        console.print("[yellow]No scenarios resolved. Provide --bundle or explicit paths.[/]")
        raise typer.Exit(1)

    watch_runner: LiveWatch | None = None
    if watch:
        if console.is_terminal:
            watch_runner = LiveWatch(WatchConfig(refresh_interval=watch_refresh), console=console)
            watch_runner.start()
        else:
            console.print("[yellow]Watch mode disabled: not running in an interactive terminal.[/]")

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    operator_names = list(OperatorRegistry.from_defaults().names())

    for scenario_path in scenario_files:
        sc = load_scenario(str(scenario_path))
        pb = Problem.from_scenario(sc)
        scenario_resolved = scenario_path.resolve()
        bundle_meta = bundle_map.get(scenario_resolved)
        scenario_display = (
            getattr(sc, "name", None) or scenario_path.parent.name or scenario_path.stem
        )
        if bundle_meta:
            console.print(
                f"[dim]Bayesian tuning {scenario_display} (bundle={bundle_meta['bundle']}, trials={trials})[/]"
            )
        else:
            console.print(f"[dim]Bayesian tuning {scenario_display} ({trials} trial(s))[/]")

        sampler = optuna.samplers.TPESampler(seed=seed)
        study = optuna.create_study(direction="maximize", sampler=sampler)
        trial_results: list[dict[str, Any]] = []

        def objective(trial: optuna.trial.Trial) -> float:
            batch_choice = trial.suggest_int("batch_size", 1, 3)
            operator_weights = {
                name: trial.suggest_float(f"weight_{name}", 0.0, 2.0) for name in operator_names
            }
            telemetry_kwargs: dict[str, Any] = {}
            if telemetry_log:
                telemetry_kwargs = {
                    "telemetry_log": telemetry_log,
                    "telemetry_context": {
                        "source": "cli.tune-bayes",
                        "trial": trial.number,
                        "batch_size": batch_choice,
                        "tuner_seed": seed,
                    },
                }
                if bundle_meta:
                    telemetry_kwargs["telemetry_context"]["bundle"] = bundle_meta["bundle"]
                    telemetry_kwargs["telemetry_context"]["bundle_member"] = bundle_meta.get(
                        "bundle_member", scenario_display
                    )
                if tier_label:
                    telemetry_kwargs["telemetry_context"]["tier"] = tier_label
                tuner_meta_payload = {
                    "algorithm": "bayes",
                    "budget": {
                        "trials_total": trials,
                        "iters_per_trial": iters,
                        "tier": tier_label,
                    },
                    "config": {
                        "trial_number": trial.number,
                        "batch_size": batch_choice,
                        "operators": operator_weights,
                    },
                    "progress": {
                        "trial_index": trial.number + 1,
                        "total_trials": trials,
                    },
                }
                if bundle_meta:
                    tuner_meta_payload["bundle"] = bundle_meta["bundle"]
                    tuner_meta_payload["bundle_member"] = bundle_meta.get(
                        "bundle_member", scenario_display
                    )
                telemetry_kwargs["telemetry_context"]["tuner_meta"] = tuner_meta_payload
            sa_kwargs: dict[str, Any] = {
                "iters": iters,
                "seed": seed + trial.number,
                "batch_size": batch_choice if batch_choice > 1 else None,
                "operator_weights": operator_weights,
            }
            sa_kwargs.update(telemetry_kwargs)
            if watch_runner:
                sa_kwargs["watch_sink"] = watch_runner.sink
                sa_kwargs["watch_interval"] = max(1, iters // 200 or 1)
                sa_kwargs["watch_metadata"] = {
                    "scenario": scenario_display,
                    "solver": f"tune-bayes[{trial.number}]",
                }
            try:
                res = solve_sa(pb, **sa_kwargs)
            except Exception as exc:  # pragma: no cover - defensive path
                trial.set_user_attr("error", repr(exc))
                raise optuna.exceptions.TrialPruned() from exc

            objective = float(res.get("objective", 0.0))
            trial.set_user_attr("telemetry_run_id", res.get("meta", {}).get("telemetry_run_id"))
            trial_results.append(
                {
                    "trial": trial.number,
                    "objective": objective,
                    "batch_size": batch_choice,
                    "operator_weights": operator_weights,
                    "scenario": scenario_display,
                    "scenario_key": (
                        f"{bundle_meta['bundle']}:{bundle_meta.get('bundle_member', scenario_display)}"
                        if bundle_meta
                        else scenario_display
                    ),
                    "bundle": bundle_meta["bundle"] if bundle_meta else None,
                    "telemetry_run_id": res.get("meta", {}).get("telemetry_run_id"),
                }
            )
            return objective

        try:
            study.optimize(objective, n_trials=trials)
        except optuna.exceptions.OptunaError as exc:  # pragma: no cover - defensive path
            console.print(f"[red]Bayesian tuner failed for {scenario_path}: {exc!r}[/]")
            continue

        best = study.best_trial
        console.print(
            f"Best objective for {scenario_path.name}: {best.value:.3f} (trial {best.number}, batch={best.params.get('batch_size')})"
        )

        table = Table(title=f"Bayesian tuner trials — {scenario_path.name}", show_lines=False)
        include_bundle = any(record.get("bundle") for record in trial_results)
        table.add_column("Trial", justify="right")
        table.add_column("Objective", justify="right")
        table.add_column("Batch", justify="right")
        table.add_column("Weights")
        if include_bundle:
            table.add_column("Bundle")

        for record in sorted(trial_results, key=lambda row: row["objective"], reverse=True):
            weights_preview = ", ".join(
                f"{name}={weight:.2f}"
                for name, weight in sorted(record["operator_weights"].items())
            )
            row = [
                str(record["trial"]),
                f"{record['objective']:.3f}",
                str(record["batch_size"]),
                weights_preview if len(weights_preview) < 80 else weights_preview[:77] + "...",
            ]
            if include_bundle:
                row.append(record.get("bundle") or "")
            table.add_row(*row)
        console.print(table)

        if telemetry_log:
            console.print(
                f"[dim]{len(trial_results)} telemetry record(s) written to {telemetry_log}. Step logs stored in {telemetry_log.parent / 'steps'}.[/]"
            )
            scenario_best: dict[str, float] = {}
            for record in trial_results:
                key = record.get("scenario_key", scenario_display)
                scenario_best[key] = max(scenario_best.get(key, float("-inf")), record["objective"])
            summary_record = {
                "record_type": "tuner_summary",
                "schema_version": "1.1",
                "algorithm": "bayes",
                "scenarios_evaluated": len(scenario_best),
                "configurations": len(trial_results),
                "scenario_best": scenario_best,
            }
            summary_record = persist_tuner_summary(
                telemetry_log.with_suffix(".sqlite"),
                summary_record,
            )
            append_jsonl(telemetry_log, summary_record)
    if watch_runner:
        watch_runner.stop()


if __name__ == "__main__":
    app()
