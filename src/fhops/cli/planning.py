"""Planning-related CLI commands (rolling-horizon orchestration, etc.)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from fhops.planning import (
    RollingHorizonConfig,
    RollingInfeasibleError,
    RollingIterationPlan,
    SolverOutput,
    run_rolling_horizon,
    summarize_plan,
)
from fhops.scenario.io import load_scenario

console = Console()
plan_app = typer.Typer(add_completion=False, no_args_is_help=True)


class StubSolver:
    """Placeholder solver that returns no assignments.

    This keeps the CLI usable while we wire a real heuristic/MILP hook.
    """

    name = "stub"

    def __call__(
        self,
        scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments,
    ) -> SolverOutput:
        warning = (
            f"[stub solver] iteration {plan.iteration_index} "
            f"({plan.start_day}-{plan.end_day}): no assignments produced"
        )
        return SolverOutput(assignments=[], objective=None, runtime_s=None, warnings=[warning])


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
            help="Solver backend (currently only 'stub' is wired; SA/MILP hooks to follow).",
        ),
    ] = "stub",
    out_json: Annotated[
        Path | None,
        typer.Option("--out-json", help="Optional path to write rolling plan summary JSON."),
    ] = None,
) -> None:
    """Execute a rolling-horizon plan using a solver hook."""

    scenario = load_scenario(scenario_path)
    config = RollingHorizonConfig(
        scenario=scenario,
        master_days=master_days,
        subproblem_days=sub_days,
        lock_days=lock_days,
    )

    solver_hook = _resolve_solver(solver)

    try:
        result = run_rolling_horizon(config, solver_hook)
    except RollingInfeasibleError as exc:
        raise typer.BadParameter(str(exc))

    summary = summarize_plan(result)
    console.print(f"[bold green]Rolling plan completed[/]: {len(result.locked_assignments)} locks")

    iterations = summary.get("iterations") or []
    if isinstance(iterations, list):
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
    warning_lines = [str(item) for item in warnings] if isinstance(warnings, list) else []
    if warning_lines:
        console.print("[yellow]Warnings:[/]\n- " + "\n- ".join(warning_lines))

    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2))
        console.print(f"Wrote summary to {out_json}")


def _resolve_solver(name: str):
    if name.lower() == "stub":
        return StubSolver()
    raise typer.BadParameter(
        f"Solver '{name}' not supported yet. Use 'stub' until SA/MILP hooks are wired."
    )
