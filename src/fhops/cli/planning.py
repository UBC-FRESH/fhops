"""Planning-related CLI commands (rolling-horizon orchestration, etc.)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from rich.console import Console

from fhops.cli._utils import parse_solver_options
from fhops.model.milp.tactical_operational import (
    DemandBasis,
    TacticalHarvestMode,
    build_tactical_operational_bundle,
    solve_tactical_operational_milp,
)
from fhops.planning import (
    MILPSolver,
    RollingHorizonConfig,
    RollingInfeasibleError,
    RollingPlanResult,
    get_solver_hook,
    load_tactical_operational_scenario,
    rolling_assignments_dataframe,
    run_rolling_horizon,
    summarize_plan,
)
from fhops.planning.tactical_operational.integration import (
    commitments_from_result,
    compile_business_window_scenario,
    write_operational_scenario_bundle,
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
            help="MILP solver name (e.g., highs, gurobi) when --solver mip; auto tries Gurobi when available and falls back to HiGHS (same as solve-mip-operational).",
        ),
    ] = "auto",
    mip_time_limit: Annotated[
        int,
        typer.Option(
            "--mip-time-limit",
            min=0,
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


@plan_app.command("tactical-operational")
def tactical_operational_plan(
    scenario_path: Path = typer.Argument(..., help="Path to tactical–operational scenario YAML."),
    harvest_mode: Annotated[
        str,
        typer.Option(
            "--harvest-mode",
            help="Harvest quantity mode: continuous, semi_continuous, or whole_block.",
        ),
    ] = TacticalHarvestMode.SEMI_CONTINUOUS.value,
    demand_basis: Annotated[
        str,
        typer.Option("--demand-basis", help="Demand envelope driver: target or minimum."),
    ] = DemandBasis.TARGET.value,
    objective_profile: Annotated[
        str | None,
        typer.Option(
            "--objective-profile",
            help=(
                "Objective profile override: min_discounted_delivered_cost, "
                "max_discounted_profit, or max_npv."
            ),
        ),
    ] = None,
    enable_roads: Annotated[
        bool,
        typer.Option("--enable-roads/--no-enable-roads", help="Enable road activation module."),
    ] = False,
    enable_silviculture: Annotated[
        bool,
        typer.Option(
            "--enable-silviculture/--no-enable-silviculture",
            help="Enable silviculture transition module.",
        ),
    ] = False,
    enable_fleet_investment: Annotated[
        bool,
        typer.Option(
            "--enable-fleet-investment/--no-enable-fleet-investment",
            help="Enable fleet acquisition module.",
        ),
    ] = False,
    solver: Annotated[
        str,
        typer.Option("--solver", help="Pyomo solver backend (default: highs)."),
    ] = "highs",
    time_limit: Annotated[
        int | None,
        typer.Option("--time-limit", min=0, help="Solver time limit in seconds."),
    ] = None,
    gap: Annotated[
        float | None,
        typer.Option("--gap", help="Relative MIP gap target (0–1)."),
    ] = None,
    solver_option: Annotated[
        list[str] | None,
        typer.Option(
            "--solver-option",
            help="Repeatable name=value solver option overrides.",
        ),
    ] = None,
    out_json: Annotated[
        Path | None,
        typer.Option("--out-json", help="Optional path to write the solve summary JSON."),
    ] = None,
    out_harvest_csv: Annotated[
        Path | None,
        typer.Option("--out-harvest-csv", help="Optional harvest decision CSV output."),
    ] = None,
    out_production_csv: Annotated[
        Path | None,
        typer.Option("--out-production-csv", help="Optional product production CSV output."),
    ] = None,
    out_flows_csv: Annotated[
        Path | None,
        typer.Option("--out-flows-csv", help="Optional product transport-flow CSV output."),
    ] = None,
    out_purchases_csv: Annotated[
        Path | None,
        typer.Option("--out-purchases-csv", help="Optional external-purchase CSV output."),
    ] = None,
    out_inventory_csv: Annotated[
        Path | None,
        typer.Option("--out-inventory-csv", help="Optional facility inventory CSV output."),
    ] = None,
    out_roads_csv: Annotated[
        Path | None,
        typer.Option("--out-roads-csv", help="Optional road activation CSV output."),
    ] = None,
    out_silviculture_csv: Annotated[
        Path | None,
        typer.Option("--out-silviculture-csv", help="Optional silviculture activity CSV output."),
    ] = None,
    out_fleet_csv: Annotated[
        Path | None,
        typer.Option("--out-fleet-csv", help="Optional fleet acquisition CSV output."),
    ] = None,
) -> None:
    """Solve the aggregate TOPM-inspired harvest/system/period MILP."""

    scenario = load_tactical_operational_scenario(scenario_path)
    if objective_profile is not None:
        payload = scenario.to_dict()
        payload["economics"]["objective_profile"] = objective_profile
        scenario = scenario.model_validate(payload)
    bundle = build_tactical_operational_bundle(
        scenario,
        harvest_mode=TacticalHarvestMode(harvest_mode),
        demand_basis=DemandBasis(demand_basis),
        enable_roads=enable_roads,
        enable_silviculture=enable_silviculture,
        enable_fleet_investment=enable_fleet_investment,
    )
    result = solve_tactical_operational_milp(
        bundle,
        solver=solver,
        time_limit=time_limit,
        gap=gap,
        solver_options=parse_solver_options(solver_option),
    )

    objective = result.get("objective")
    objective_text = "n/a" if objective is None else f"{objective:.3f}"
    console.print(
        "[bold green]Tactical–operational plan completed[/]: "
        f"objective={objective_text} solver={result.get('solver_status')} "
        f"termination={result.get('termination_condition')}"
    )
    components = result.get("objective_components") or {}
    if components:
        console.print(
            "[cyan]Objective components:[/] "
            f"harvest_fixed={components.get('harvest_fixed_cost', 0.0):.3f} "
            f"harvest_variable={components.get('harvest_variable_cost', 0.0):.3f} "
            f"transport={components.get('transport_cost', 0.0):.3f} "
            f"purchases={components.get('purchase_cost', 0.0):.3f} "
            f"roads={components.get('road_cost', 0.0):.3f} "
            f"silviculture={components.get('silviculture_cost', 0.0):.3f} "
            f"fleet={components.get('fleet_investment_cost', 0.0):.3f} "
            f"total={components.get('total_cost', 0.0):.3f}"
        )

    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        serializable = dict(result)
        serializable["harvest_decisions"] = result["harvest_decisions"].to_dict("records")
        serializable["production"] = result["production"].to_dict("records")
        serializable["flows"] = result["flows"].to_dict("records")
        serializable["purchases"] = result["purchases"].to_dict("records")
        serializable["inventory"] = result["inventory"].to_dict("records")
        serializable["consumption"] = result["consumption"].to_dict("records")
        serializable["roads"] = result["roads"].to_dict("records")
        serializable["silviculture"] = result["silviculture"].to_dict("records")
        serializable["fleet"] = result["fleet"].to_dict("records")
        out_json.write_text(json.dumps(serializable, indent=2))
        console.print(f"Wrote summary to {out_json}")
    if out_harvest_csv:
        out_harvest_csv.parent.mkdir(parents=True, exist_ok=True)
        result["harvest_decisions"].to_csv(out_harvest_csv, index=False)
        console.print(f"Wrote harvest decisions to {out_harvest_csv}")
    if out_production_csv:
        out_production_csv.parent.mkdir(parents=True, exist_ok=True)
        result["production"].to_csv(out_production_csv, index=False)
        console.print(f"Wrote production to {out_production_csv}")
    if out_flows_csv:
        out_flows_csv.parent.mkdir(parents=True, exist_ok=True)
        result["flows"].to_csv(out_flows_csv, index=False)
        console.print(f"Wrote product flows to {out_flows_csv}")
    if out_purchases_csv:
        out_purchases_csv.parent.mkdir(parents=True, exist_ok=True)
        result["purchases"].to_csv(out_purchases_csv, index=False)
        console.print(f"Wrote purchases to {out_purchases_csv}")
    if out_inventory_csv:
        out_inventory_csv.parent.mkdir(parents=True, exist_ok=True)
        result["inventory"].to_csv(out_inventory_csv, index=False)
        console.print(f"Wrote inventory to {out_inventory_csv}")
    if out_roads_csv:
        out_roads_csv.parent.mkdir(parents=True, exist_ok=True)
        result["roads"].to_csv(out_roads_csv, index=False)
        console.print(f"Wrote roads to {out_roads_csv}")
    if out_silviculture_csv:
        out_silviculture_csv.parent.mkdir(parents=True, exist_ok=True)
        result["silviculture"].to_csv(out_silviculture_csv, index=False)
        console.print(f"Wrote silviculture to {out_silviculture_csv}")
    if out_fleet_csv:
        out_fleet_csv.parent.mkdir(parents=True, exist_ok=True)
        result["fleet"].to_csv(out_fleet_csv, index=False)
        console.print(f"Wrote fleet to {out_fleet_csv}")


@plan_app.command("compile-tactical")
def compile_tactical_window(
    tactical_result: Path = typer.Argument(
        ..., help="Path to `fhops plan tactical-operational --out-json` result."
    ),
    operational_scenario: Path = typer.Argument(
        ..., help="Base operational scenario YAML providing machines/calendars/rates."
    ),
    block_map: Annotated[
        list[str] | None,
        typer.Option(
            "--block-map",
            help="Repeatable tactical=operational block mapping (e.g., B1=B01).",
        ),
    ] = None,
    start_day: Annotated[
        int,
        typer.Option("--start-day", help="First operational day for the business window."),
    ] = 1,
    horizon_days: Annotated[
        int | None,
        typer.Option("--horizon-days", help="Optional business-window length in days."),
    ] = None,
    out_dir: Path = typer.Option(
        ...,
        "--out-dir",
        help="Directory where the compiled operational scenario bundle is written.",
    ),
) -> None:
    """Compile tactical harvest commitments into an operational FHOPS scenario bundle."""

    payload = json.loads(tactical_result.read_text(encoding="utf-8"))
    commitments = commitments_from_result(payload)
    base = load_scenario(operational_scenario)
    mapping: dict[str, str] = {}
    for item in block_map or []:
        if "=" not in item:
            raise typer.BadParameter(f"Invalid --block-map entry '{item}'; expected A=B")
        tactical_id, operational_id = item.split("=", 1)
        mapping[tactical_id] = operational_id
    compiled = compile_business_window_scenario(
        base,
        commitments,
        block_map=mapping,
        start_day=start_day,
        horizon_days=horizon_days,
    )
    output = write_operational_scenario_bundle(compiled, out_dir)
    console.print(f"Wrote compiled operational scenario to {output}")
