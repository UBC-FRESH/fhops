"""Planning-related CLI commands (rolling-horizon orchestration, etc.)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from rich.console import Console

from fhops.cli._utils import parse_solver_options
from fhops.planning import (
    RollingHorizonConfig,
    RollingInfeasibleError,
    get_solver_hook,
    rolling_assignments_dataframe,
    run_rolling_horizon,
    summarize_plan,
)
from fhops.scenario.io import load_scenario

console = Console()
plan_app = typer.Typer(add_completion=False, no_args_is_help=True)


@plan_app.command("rolling")
def rolling_plan(
    scenario_path: Path = typer.Argument(..., help="Path to scenario YAML file."),
    master_days: Annotated[int, typer.Option("--master-days", help="Total days to cover")] = 84,
    sub_days: Annotated[int, typer.Option("--sub-days", help="Days per subproblem window")] = 28,
    lock_days: Annotated[
        int, typer.Option("--lock-days", help="Days to lock after each solve")
    ] = 14,
    solver: Annotated[
        str,
        typer.Option(
            "--solver",
            "-s",
            help="Solver backend: stub (no-op), sa (heuristic), or mip (operational MILP).",
        ),
    ] = "stub",
    sa_iters: Annotated[
        int,
        typer.Option(
            "--sa-iters",
            help="SA iterations per subproblem (only used when --solver sa)",
        ),
    ] = 500,
    sa_seed: Annotated[
        int,
        typer.Option(
            "--sa-seed",
            help="RNG seed for SA solver (only used when --solver sa)",
        ),
    ] = 42,
    mip_solver: Annotated[
        str,
        typer.Option(
            "--mip-solver",
            help="MILP solver name (e.g., highs, gurobi) when --solver mip",
        ),
    ] = "auto",
    mip_time_limit: Annotated[
        int,
        typer.Option(
            "--mip-time-limit",
            help="MILP time limit in seconds when --solver mip",
        ),
    ] = 300,
    mip_solver_option: Annotated[
        list[str] | None,
        typer.Option(
            "--mip-solver-option",
            help=(
                "Repeatable name=value pairs forwarded to the MILP solver "
                "(e.g., --mip-solver-option Threads=64)."
            ),
        ),
    ] = None,
    out_json: Annotated[
        Path | None,
        typer.Option("--out-json", help="Optional path to write rolling plan summary JSON."),
    ] = None,
    out_assignments: Annotated[
        Path | None,
        typer.Option(
            "--out-assignments",
            help="Optional path to write locked assignments CSV aggregated across iterations.",
        ),
    ] = None,
    out_iterations_jsonl: Annotated[
        Path | None,
        typer.Option(
            "--out-iterations-jsonl",
            help="Optional path to write per-iteration summaries as JSONL (one record per iteration).",
        ),
    ] = None,
    out_iterations_csv: Annotated[
        Path | None,
        typer.Option(
            "--out-iterations-csv",
            help="Optional path to write per-iteration summaries as CSV.",
        ),
    ] = None,
    max_iterations: Annotated[
        int | None,
        typer.Option(
            "--max-iterations",
            help="Cap the number of rolling iterations (defaults to full master horizon).",
        ),
    ] = None,
) -> None:
    """Execute a rolling-horizon plan using a solver hook."""

    scenario = load_scenario(scenario_path)
    solver_options = parse_solver_options(mip_solver_option)
    config = RollingHorizonConfig(
        scenario=scenario,
        master_days=master_days,
        subproblem_days=sub_days,
        lock_days=lock_days,
    )

    solver_hook = get_solver_hook(
        solver,
        sa_iters=sa_iters,
        sa_seed=sa_seed,
        mip_solver=mip_solver,
        mip_time_limit=mip_time_limit,
        mip_solver_options=solver_options,
    )

    try:
        result = run_rolling_horizon(
            config,
            solver_hook,
            max_iterations=max_iterations,
            solver_name=solver,
        )
    except RollingInfeasibleError as exc:
        raise typer.BadParameter(str(exc))

    summary = summarize_plan(result)
    console.print(f"[bold green]Rolling plan completed[/]: {len(result.locked_assignments)} locks")

    metadata_obj = summary.get("metadata") or {}
    metadata = metadata_obj if isinstance(metadata_obj, dict) else {}
    if metadata:
        console.print(
            f"[cyan]Metadata:[/] solver={metadata.get('solver')} "
            f"master_days={metadata.get('master_days')} "
            f"sub_days={metadata.get('subproblem_days')} lock_days={metadata.get('lock_days')}"
        )
        if metadata.get("mip_solver"):
            console.print(
                f"[cyan]MILP backend:[/] solver={metadata.get('mip_solver')} "
                f"time_limit={metadata.get('mip_time_limit')} "
                f"options={metadata.get('mip_solver_options') or {}}"
            )

    iterations = summary.get("iterations") or []
    if not isinstance(iterations, list):
        iterations = []
    iterations = [dict(iteration) for iteration in iterations]
    for iteration in iterations:
        start_day = iteration.get("start_day", 0)
        horizon_days = iteration.get("horizon_days", 0)
        locked_assignments = iteration.get("locked_assignments", 0)
        console.print(
            f" - Iter {iteration.get('iteration_index', '?')}: "
            f"days {start_day}-{start_day + horizon_days - 1}, "
            f"locked {locked_assignments} assignments"
        )

    warnings = summary.get("warnings") or []
    warning_lines: list[str] = (
        [str(item) for item in warnings] if isinstance(warnings, list) else []
    )
    if warning_lines:
        console.print("[yellow]Warnings:[/]\n- " + "\n- ".join(warning_lines))

    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2))
        console.print(f"Wrote summary to {out_json}")

    iteration_records = summary.get("iterations") or []
    if not isinstance(iteration_records, list):
        iteration_records = []

    if out_assignments:
        out_assignments.parent.mkdir(parents=True, exist_ok=True)
        df = rolling_assignments_dataframe(result, include_metadata=True)
        df.to_csv(out_assignments, index=False)
        console.print(f"Wrote locked assignments to {out_assignments}")

    if out_iterations_jsonl:
        out_iterations_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with out_iterations_jsonl.open("w", encoding="utf-8") as fp:
            for record in iteration_records:
                fp.write(json.dumps(record))
                fp.write("\n")
        console.print(f"Wrote iteration summaries to {out_iterations_jsonl}")

    if out_iterations_csv:
        out_iterations_csv.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(iteration_records).to_csv(out_iterations_csv, index=False)
        console.print(f"Wrote iteration summaries to {out_iterations_csv}")
