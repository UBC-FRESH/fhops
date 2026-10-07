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
    MILPSolver,
    RollingHorizonConfig,
    RollingInfeasibleError,
    RollingPlanResult,
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
            help="MILP solver name (e.g., highs, gurobi) when --solver mip; auto resolves to highs.",
        ),
    ] = "auto",
    mip_time_limit: Annotated[
        int,
        typer.Option(
            "--mip-time-limit",
            help="MILP time limit in seconds when --solver mip",
        ),
    ] = 300,
    mip_earliness: Annotated[
        bool,
        typer.Option(
            "--mip-earliness/--no-mip-earliness",
            help=(
                "Break ties of each MILP window in favour of early production (lexicographic "
                "second solve; the window objective is unchanged) so work is not deferred past "
                "the lock span. Skipped for windows whose lock span covers the whole window."
            ),
        ),
    ] = True,
    mip_earliness_time_limit: Annotated[
        int | None,
        typer.Option(
            "--mip-earliness-time-limit",
            min=1,
            help="Time limit in seconds of the earliness stage (default: --mip-time-limit).",
        ),
    ] = None,
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
            help=(
                "Optional path to write locked assignments CSV aggregated across iterations "
                "(machine_id, block_id, day, shift_id, assigned, production for MILP runs + run "
                "metadata)."
            ),
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
            min=1,
            help="Cap the number of rolling iterations (>= 1; defaults to full master horizon).",
        ),
    ] = None,
    fail_on_empty_window: Annotated[
        bool,
        typer.Option(
            "--fail-on-empty-window",
            help=(
                "Stop (exit code 1) at the first window whose solver returns no solution or that "
                "is solved to an empty plan (its lock span produces nothing or its plan delivers "
                "nothing while work remains) instead of continuing. Partial outputs are still "
                "written."
            ),
        ),
    ] = False,
    fail_on_no_solution: Annotated[
        bool,
        typer.Option(
            "--fail-on-no-solution",
            help=(
                "Stop (exit code 1) at the first window whose solver returns no solution; empty "
                "windows are recorded and the run continues. Partial outputs are still written."
            ),
        ),
    ] = False,
) -> None:
    """Execute a rolling-horizon plan using a solver hook.

    Each window after the first starts from the state reached by the locked plan so far (remaining
    block volume, staged inventory, role progress, machine positions), and user locks from the
    scenario are enforced in every window they fall in. A window whose solver returns no solution
    is recorded (status ``no_solution``) and its lock span left idle unless
    ``--fail-on-no-solution`` or ``--fail-on-empty-window`` is set. The requested outputs are
    always written, also when the run fails part-way.

    Exit codes: 0 when the run completes and at least one window that was passed to the solver
    returned a solution; 1 when a ``--fail-on-*`` flag stopped the run, the run raised, or no
    window returned a solution (e.g. every window failed with a solver error); 2 for usage errors
    (invalid horizon arguments, unknown solver hook, unavailable MILP solver).
    """

    scenario = load_scenario(scenario_path)
    solver_options = parse_solver_options(mip_solver_option)
    try:
        config = RollingHorizonConfig(
            scenario=scenario,
            master_days=master_days,
            subproblem_days=sub_days,
            lock_days=lock_days,
        )
    except ValueError as exc:
        raise typer.BadParameter(
            f"{exc} (--master-days {master_days}, --sub-days {sub_days}, --lock-days "
            f"{lock_days}; scenario num_days {scenario.num_days})",
            param_hint="--master-days/--sub-days/--lock-days",
        ) from exc

    try:
        solver_hook = get_solver_hook(
            solver,
            sa_iters=sa_iters,
            sa_seed=sa_seed,
            mip_solver=mip_solver,
            mip_time_limit=mip_time_limit,
            mip_solver_options=solver_options,
            mip_earliness=mip_earliness,
            mip_earliness_time_limit=mip_earliness_time_limit,
        )
    except RollingInfeasibleError as exc:
        raise typer.BadParameter(str(exc), param_hint="--solver") from exc
    if isinstance(solver_hook, MILPSolver) and not solver_hook.available():
        raise typer.BadParameter(
            f"MILP solver '{solver_hook.solver}' is not available (SolverFactory reports it "
            "missing or unusable).",
            param_hint="--mip-solver",
        )

    failure: BaseException | None = None
    try:
        result = run_rolling_horizon(
            config,
            solver_hook,
            max_iterations=max_iterations,
            solver_name=solver,
            fail_on_empty_window=fail_on_empty_window,
            fail_on_no_solution=fail_on_no_solution,
        )
    except Exception as exc:
        partial = getattr(exc, "partial_result", None)
        if not isinstance(partial, RollingPlanResult):
            raise
        result = partial
        failure = exc

    summary = summarize_plan(result)
    attempted = [s for s in result.iteration_summaries if s.status != "skipped"]
    nothing_solved = (
        failure is None and bool(attempted) and not any(s.has_solution for s in attempted)
    )
    if nothing_solved:
        errors = sorted({s.error for s in attempted if s.error})
        detail = f"; solver error: {errors[0]}" if errors else ""
        console.print(
            f"[bold red]Rolling plan failed[/]: no window returned a solution "
            f"({len(attempted)} window(s) passed to the solver){detail}"
        )
    elif failure is None:
        console.print(
            f"[bold green]Rolling plan completed[/]: {len(result.locked_assignments)} locks"
        )
    else:
        console.print(
            f"[bold red]Rolling plan failed[/] ({type(failure).__name__}): {failure}\n"
            f"Writing partial outputs: {len(result.locked_assignments)} locks from "
            f"{len(result.iteration_summaries)} recorded iteration(s)."
        )

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
                f"earliness={metadata.get('mip_earliness')} "
                f"options={metadata.get('mip_solver_options') or {}}"
            )

    iteration_records = summary.get("iterations") or []
    if not isinstance(iteration_records, list):
        iteration_records = []
    for iteration in iteration_records:
        start_day = iteration.get("start_day", 0)
        horizon_days = iteration.get("horizon_days", 0)
        locked_assignments = iteration.get("locked_assignments", 0)
        flag = " [yellow](empty)[/]" if iteration.get("empty") else ""
        console.print(
            f" - Iter {iteration.get('iteration_index', '?')}: "
            f"days {start_day}-{start_day + horizon_days - 1}, "
            f"status {iteration.get('status', 'solved')}, "
            f"locked {locked_assignments} assignments{flag}"
        )
    if summary.get("empty_windows"):
        console.print(
            f"[yellow]Empty windows:[/] {summary.get('empty_windows')} "
            f"(no solution: {summary.get('no_solution_windows')}, "
            f"skipped: {summary.get('skipped_windows')})"
        )

    warnings = summary.get("warnings") or []
    warning_lines: list[str] = (
        [str(item) for item in warnings] if isinstance(warnings, list) else []
    )
    if warning_lines:
        console.print("[yellow]Warnings:[/]\n- " + "\n- ".join(warning_lines))

    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(summary)
        if failure is not None:
            payload["error"] = f"{type(failure).__name__}: {failure}"
        elif nothing_solved:
            payload["error"] = "no window returned a solution"
        out_json.write_text(json.dumps(payload, indent=2))
        console.print(f"Wrote summary to {out_json}")

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

    if failure is not None or nothing_solved:
        raise typer.Exit(code=1)
