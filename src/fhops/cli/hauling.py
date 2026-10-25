"""`fhops haul` CLI commands."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from fhops.hauling.flow import (
    FlowSolveResult,
    build_flow_problem,
    solve_flow,
    summarize_flow_result,
)
from fhops.hauling.heuristic import HaulingSAResult, SAConfig, solve_sa, summarize_sa_result
from fhops.hauling.network import build_schedule_problem
from fhops.hauling.reporting import (
    FLOW_FILES,
    build_markdown_report,
    write_flow_run,
    write_schedule_run,
    write_solve_run,
)
from fhops.hauling.schedule import ScheduleSolveResult, solve_schedule
from fhops.scenario.contract import Scenario
from fhops.scenario.io import load_scenario
from fhops.web.discovery import write_run_manifest

hauling_app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


@hauling_app.command("validate")
def validate_hauling(
    scenario_path: Path = typer.Argument(..., help="Scenario YAML with a hauling section."),
) -> None:
    """Validate a hauling scenario and print its dimensions and residuals."""
    scenario = load_scenario(scenario_path)
    if scenario.hauling is None:
        console.print("[red]Scenario has no hauling section[/red]")
        raise typer.Exit(1)
    config = scenario.hauling
    from fhops.hauling.integration import residual_report

    table = Table(title=f"Hauling: {scenario.name}")
    table.add_column("Dimension")
    table.add_column("Value")
    table.add_row("Horizon (days)", str(config.planning_horizon_days))
    table.add_row("Log sorts", str(len(config.log_sorts)))
    table.add_row("Contractors", str(len(config.contractors)))
    table.add_row("Truck types", str(len(config.truck_types)))
    table.add_row("Trucks", str(len(config.trucks)))
    table.add_row("Barge types", str(len(config.barge_types)))
    table.add_row("Barges", str(len(config.barges)))
    table.add_row("Ports", str(len(config.ports)))
    table.add_row("Water arcs", str(len(config.water_arcs)))
    table.add_row("Marine routes", str(len(config.marine_routes)))
    table.add_row(
        "Transport modes",
        "road+water" if config.marine_routes else "road",
    )
    table.add_row("Sort yards", str(len(config.sort_yards)))
    table.add_row("Supply rows", str(len(config.supply)))
    table.add_row("Demand rows", str(len(config.demand)))
    table.add_row("Haul arcs", str(len(config.haul_arcs)))
    console.print(table)
    residuals = residual_report(scenario)
    if not residuals.empty:
        console.print("\n[bold]Supply/demand residuals[/bold]")
        console.print(residuals.to_string(index=False))


@hauling_app.command("plan")
def plan_hauling(
    scenario_path: Path = typer.Argument(..., help="Scenario YAML with a hauling section."),
    out_dir: Path = typer.Option(..., "--out-dir", help="Directory for the stable output files."),
    objective: str = typer.Option(
        "cost",
        "--objective",
        help="Phase I objective: cost, workload, or goal.",
    ),
    solver: str = typer.Option("highs", "--solver", help="Pyomo solver name."),
    time_limit: float | None = typer.Option(None, "--time-limit", help="Solver seconds."),
    gap: float | None = typer.Option(None, "--gap", help="Relative MIP gap target."),
    goal_weight_cost: float = typer.Option(
        1.0, "--goal-weight-cost", help="Goal-programming weight for cost."
    ),
    goal_weight_workload: float = typer.Option(
        1.0, "--goal-weight-workload", help="Goal-programming weight for workload."
    ),
    tee: bool = typer.Option(False, "--tee", help="Stream the solver log."),
) -> None:
    """Solve Phase I and write the monthly flow artefacts."""
    scenario = load_scenario(scenario_path)
    if scenario.hauling is None:
        console.print("[red]Scenario has no hauling section[/red]")
        raise typer.Exit(1)
    problem = build_flow_problem(scenario)
    result = solve_flow(
        problem,
        objective=objective,
        solver=solver,
        time_limit=time_limit,
        gap=gap,
        weights=(goal_weight_cost, goal_weight_workload),
        tee=tee,
    )
    console.print(summarize_flow_result(result))
    if result.status not in {"optimal", "feasible"}:
        raise typer.Exit(1)
    paths = write_flow_run(
        result,
        out_dir,
        scenario_name=scenario.name,
        start_day=scenario.hauling.start_day,
    )
    write_run_manifest(
        out_dir,
        domain="hauling",
        run_type="haul_plan",
        command=f"fhops haul plan {scenario_path}",
        scenario=str(scenario_path),
        solver=solver,
        status=result.status,
    )
    console.print(f"\nWrote {len(paths)} files under {out_dir}")


@hauling_app.command("schedule")
def schedule_hauling(
    scenario_path: Path = typer.Argument(..., help="Scenario YAML with a hauling section."),
    out_dir: Path = typer.Option(..., "--out-dir", help="Directory for the stable output files."),
    day: int = typer.Option(1, "--day", help="Relative hauling-horizon day to schedule."),
    flow_dir: Path | None = typer.Option(
        None,
        "--flow-dir",
        help="Existing Phase I run directory; when omitted, Phase I is solved in memory.",
    ),
    solver: str = typer.Option("mip", "--solver", help="Schedule solver: mip or sa."),
    time_limit: float | None = typer.Option(None, "--time-limit", help="MIP solver seconds."),
    gap: float | None = typer.Option(None, "--gap", help="Relative MIP gap target."),
    sa_iters: int = typer.Option(5000, "--sa-iters", help="SA move budget."),
    sa_seed: int = typer.Option(42, "--sa-seed", help="SA RNG seed."),
    tee: bool = typer.Option(False, "--tee", help="Stream the solver log."),
) -> None:
    """Solve Phase II/III for one day and write the schedule artefacts."""
    scenario = load_scenario(scenario_path)
    if scenario.hauling is None:
        console.print("[red]Scenario has no hauling section[/red]")
        raise typer.Exit(1)
    flow_result = _load_or_solve_flow(scenario, flow_dir, time_limit=time_limit)
    problem = build_schedule_problem(scenario, flow_result, day)
    if solver == "sa":
        sa_result = solve_sa(
            problem,
            SAConfig(max_iterations=sa_iters, seed=sa_seed),
        )
        console.print(summarize_sa_result(sa_result))
        if sa_result.status != "feasible":
            raise typer.Exit(1)
        paths = write_schedule_run(
            sa_result,
            out_dir,
            scenario_name=scenario.name,
            day=day,
        )
        write_run_manifest(
            out_dir,
            domain="hauling",
            run_type="haul_schedule",
            command=f"fhops haul schedule {scenario_path}",
            scenario=str(scenario_path),
            solver="sa",
            seed=sa_seed,
            status=sa_result.status,
        )
    elif solver == "mip":
        mip_result = solve_schedule(
            problem,
            solver="highs",
            time_limit=time_limit,
            gap=gap,
            tee=tee,
        )
        console.print(
            f"status: {mip_result.status}\nobjective: {mip_result.objective}\n"
            f"loads: {len(mip_result.schedule)}"
        )
        if mip_result.status not in {"optimal", "feasible"}:
            raise typer.Exit(1)
        paths = write_schedule_run(
            mip_result,
            out_dir,
            scenario_name=scenario.name,
            day=day,
        )
        write_run_manifest(
            out_dir,
            domain="hauling",
            run_type="haul_schedule",
            command=f"fhops haul schedule {scenario_path}",
            scenario=str(scenario_path),
            solver="highs",
            status=mip_result.status,
        )
    else:
        console.print("[red]--solver must be mip or sa[/red]")
        raise typer.Exit(2)
    console.print(f"\nWrote {len(paths)} files under {out_dir}")


@hauling_app.command("solve")
def solve_hauling(
    scenario_path: Path = typer.Argument(..., help="Scenario YAML with a hauling section."),
    out_dir: Path = typer.Option(..., "--out-dir", help="Directory for the stable output files."),
    day: int = typer.Option(1, "--day", help="Relative hauling-horizon day to schedule."),
    solver: str = typer.Option("mip", "--solver", help="Schedule solver: mip or sa."),
    time_limit: float | None = typer.Option(None, "--time-limit", help="Phase I/MIP seconds."),
    gap: float | None = typer.Option(None, "--gap", help="Relative MIP gap target."),
    sa_iters: int = typer.Option(5000, "--sa-iters", help="SA move budget."),
    sa_seed: int = typer.Option(42, "--sa-seed", help="SA RNG seed."),
    tee: bool = typer.Option(False, "--tee", help="Stream the solver log."),
) -> None:
    """Run Phase I and Phase II/III in one command."""
    scenario = load_scenario(scenario_path)
    if scenario.hauling is None:
        console.print("[red]Scenario has no hauling section[/red]")
        raise typer.Exit(1)
    flow_result = solve_flow(
        build_flow_problem(scenario),
        time_limit=time_limit,
        gap=gap,
        tee=tee,
    )
    console.print(summarize_flow_result(flow_result))
    if flow_result.status not in {"optimal", "feasible"}:
        raise typer.Exit(1)
    problem = build_schedule_problem(scenario, flow_result, day)
    schedule_result: ScheduleSolveResult | HaulingSAResult
    if solver == "sa":
        schedule_result = solve_sa(
            problem,
            SAConfig(max_iterations=sa_iters, seed=sa_seed),
        )
        console.print(summarize_sa_result(schedule_result))
        if schedule_result.status != "feasible":
            raise typer.Exit(1)
    elif solver == "mip":
        schedule_result = solve_schedule(
            problem,
            solver="highs",
            time_limit=time_limit,
            gap=gap,
            tee=tee,
        )
        console.print(
            f"schedule status: {schedule_result.status}\nobjective: {schedule_result.objective}"
        )
        if schedule_result.status not in {"optimal", "feasible"}:
            raise typer.Exit(1)
    else:
        console.print("[red]--solver must be mip or sa[/red]")
        raise typer.Exit(2)
    paths = write_solve_run(
        flow_result,
        schedule_result,
        out_dir,
        scenario_name=scenario.name,
        start_day=scenario.hauling.start_day,
        day=day,
    )
    write_run_manifest(
        out_dir,
        domain="hauling",
        run_type="haul_solve",
        command=f"fhops haul solve {scenario_path}",
        scenario=str(scenario_path),
        solver=solver,
        seed=sa_seed if solver == "sa" else None,
        status=schedule_result.status,
    )
    console.print(f"\nWrote {len(paths)} files under {out_dir}")


@hauling_app.command("report")
def report_hauling(
    run_dir: Path = typer.Argument(..., help="Run directory with haul_summary.json."),
    out: Path | None = typer.Option(None, "--out", help="Optional Markdown output path."),
) -> None:
    """Render a Markdown report from a hauling run directory."""
    try:
        markdown = build_markdown_report(run_dir)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown + "\n", encoding="utf-8")
        console.print(f"Wrote {out}")
    else:
        console.print(markdown)


def _load_or_solve_flow(
    scenario: Scenario,
    flow_dir: Path | None,
    *,
    time_limit: float | None,
) -> FlowSolveResult:
    """Load Phase I truckloads from a run directory or solve Phase I in memory."""
    if flow_dir is None:
        return solve_flow(build_flow_problem(scenario), time_limit=time_limit)
    path = flow_dir / FLOW_FILES["truckloads"]
    if not path.exists():
        raise typer.BadParameter(f"Missing {path}")
    frame = pd.read_csv(path)
    marine_truckloads = _read_optional_csv(flow_dir / FLOW_FILES["marine_truckloads"])
    barge_trips = _read_optional_csv(flow_dir / FLOW_FILES["barge_trips"])
    marine_flows = _read_optional_csv(flow_dir / FLOW_FILES["marine_flows"])
    return FlowSolveResult(
        status="optimal",
        objective=None,
        cost_objective=None,
        workload_objective=None,
        truckloads=frame,
        marine_truckloads=marine_truckloads,
        barge_trips=barge_trips,
        marine_flows=marine_flows,
    )


def _read_optional_csv(path: Path) -> pd.DataFrame:
    """Read a CSV artefact when it exists, otherwise return an empty frame."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
