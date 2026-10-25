"""Stable output writers and reports for log-hauling runs.

The filenames in this module are the artefact contract used by the CLI and, later, the web UI. The
writers do not recompute a result; they serialise the DataFrames and objective payloads produced by
the flow, scheduling, and SA solvers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from fhops.hauling.flow import FlowSolveResult
from fhops.hauling.heuristic import HaulingSAResult
from fhops.hauling.schedule import ScheduleSolveResult

__all__ = [
    "FLOW_FILES",
    "SCHEDULE_FILES",
    "build_markdown_report",
    "write_flow_run",
    "write_schedule_run",
    "write_solve_run",
]

FLOW_FILES = {
    "flows": "haul_flows.csv",
    "truckloads": "haul_truckloads.csv",
    "yard_inventory": "haul_yard_inventory.csv",
    "block_inventory": "haul_block_inventory.csv",
    "contractor_workload": "haul_contractor_workload.csv",
    "marine_flows": "haul_marine_flows.csv",
    "marine_truckloads": "haul_marine_truckloads.csv",
    "barge_trips": "haul_barge_trips.csv",
    "port_inventory": "haul_port_inventory.csv",
    "kpis": "haul_kpis.json",
    "summary": "haul_summary.json",
}
SCHEDULE_FILES = {
    "schedule": "haul_schedule.csv",
    "truck_summary": "haul_truck_summary.csv",
    "loader_summary": "haul_loader_summary.csv",
    "barge_schedule": "haul_barge_schedule.csv",
    "barge_summary": "haul_barge_summary.csv",
    "kpis": "haul_kpis.json",
    "summary": "haul_summary.json",
}
OUTPUT_SCHEMA_VERSION = "1.1.0"


def write_flow_run(
    result: FlowSolveResult,
    out_dir: Path,
    *,
    scenario_name: str,
    start_day: int,
    run_type: str = "plan",
) -> dict[str, Path]:
    """Write a Phase I result to the stable artefact names.

    Parameters
    ----------
    result:
        Phase I result.
    out_dir:
        Directory to create/write.
    scenario_name:
        Scenario label for the summary.
    start_day:
        Parent-scenario start day of the hauling horizon.
    run_type:
        ``plan`` or ``solve``.

    Returns
    -------
    dict[str, Path]
        Logical name -> written path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: out_dir / filename for name, filename in FLOW_FILES.items()}
    result.flows.to_csv(paths["flows"], index=False)
    result.truckloads.to_csv(paths["truckloads"], index=False)
    result.yard_inventory.to_csv(paths["yard_inventory"], index=False)
    result.block_inventory.to_csv(paths["block_inventory"], index=False)
    result.contractor_workload.to_csv(paths["contractor_workload"], index=False)
    result.marine_flows.to_csv(paths["marine_flows"], index=False)
    result.marine_truckloads.to_csv(paths["marine_truckloads"], index=False)
    result.barge_trips.to_csv(paths["barge_trips"], index=False)
    result.port_inventory.to_csv(paths["port_inventory"], index=False)
    kpis = _flow_kpis(result)
    _write_json(paths["kpis"], kpis)
    summary = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_type": run_type,
        "phase": "I",
        "scenario": scenario_name,
        "start_day": start_day,
        "status": result.status,
        "solver": result.solver,
        "termination": result.termination,
        "runtime_seconds": result.runtime_seconds,
        "objective": result.cost_objective,
        "workload_objective": result.workload_objective,
        "files": {name: path.name for name, path in paths.items()},
        "generated_at": _now(),
    }
    _write_json(paths["summary"], summary)
    return paths


def write_schedule_run(
    result: ScheduleSolveResult | HaulingSAResult,
    out_dir: Path,
    *,
    scenario_name: str,
    day: int,
    run_type: str = "schedule",
) -> dict[str, Path]:
    """Write a Phase II/III schedule to the stable artefact names.

    Parameters
    ----------
    result:
        Exact or SA scheduling result.
    out_dir:
        Directory to create/write.
    scenario_name:
        Scenario label for the summary.
    day:
        Relative hauling-horizon day.
    run_type:
        ``schedule`` or ``solve``.

    Returns
    -------
    dict[str, Path]
        Logical name -> written path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: out_dir / filename for name, filename in SCHEDULE_FILES.items()}
    result.schedule.to_csv(paths["schedule"], index=False)
    result.truck_summary.to_csv(paths["truck_summary"], index=False)
    result.loader_summary.to_csv(paths["loader_summary"], index=False)
    if hasattr(result, "barge_schedule"):
        result.barge_schedule.to_csv(paths["barge_schedule"], index=False)
        result.barge_summary.to_csv(paths["barge_summary"], index=False)
    else:
        pd.DataFrame().to_csv(paths["barge_schedule"], index=False)
        pd.DataFrame().to_csv(paths["barge_summary"], index=False)
    kpis = _schedule_kpis(result)
    _write_json(paths["kpis"], kpis)
    summary = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_type": run_type,
        "phase": "II" if isinstance(result, ScheduleSolveResult) else "III",
        "scenario": scenario_name,
        "day": day,
        "status": result.status,
        "solver": result.solver if isinstance(result, ScheduleSolveResult) else "sa",
        "termination": result.termination if isinstance(result, ScheduleSolveResult) else None,
        "runtime_seconds": result.runtime_seconds,
        "objective": result.objective,
        "files": {name: path.name for name, path in paths.items()},
        "generated_at": _now(),
    }
    _write_json(paths["summary"], summary)
    return paths


def write_solve_run(
    flow_result: FlowSolveResult,
    schedule_result: ScheduleSolveResult | HaulingSAResult,
    out_dir: Path,
    *,
    scenario_name: str,
    start_day: int,
    day: int,
) -> dict[str, Path]:
    """Write a combined Phase I + II/III run and merge the summaries.

    Parameters
    ----------
    flow_result:
        Phase I result.
    schedule_result:
        Phase II or III result.
    out_dir:
        Directory to create/write.
    scenario_name:
        Scenario label.
    start_day:
        Parent-scenario start day of the hauling horizon.
    day:
        Relative hauling-horizon day of the schedule.

    Returns
    -------
    dict[str, Path]
        Logical name -> written path, including both phases.
    """
    flow_paths = write_flow_run(
        flow_result,
        out_dir,
        scenario_name=scenario_name,
        start_day=start_day,
        run_type="solve",
    )
    flow_summary = json.loads(flow_paths["summary"].read_text(encoding="utf-8"))
    schedule_paths = write_schedule_run(
        schedule_result,
        out_dir,
        scenario_name=scenario_name,
        day=day,
        run_type="solve",
    )
    schedule_summary = json.loads(schedule_paths["summary"].read_text(encoding="utf-8"))
    merged = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_type": "solve",
        "phase": "I+II/III",
        "scenario": scenario_name,
        "start_day": start_day,
        "day": day,
        "status": schedule_summary.get("status", flow_summary.get("status")),
        "solver": schedule_summary.get("solver", flow_summary.get("solver")),
        "runtime_seconds": (flow_summary.get("runtime_seconds") or 0.0)
        + (schedule_summary.get("runtime_seconds") or 0.0),
        "objective": schedule_summary.get("objective"),
        "flow_objective": flow_summary.get("objective"),
        "files": {**flow_summary.get("files", {}), **schedule_summary.get("files", {})},
        "flow": flow_summary,
        "schedule": schedule_summary,
        "generated_at": _now(),
    }
    _write_json(out_dir / FLOW_FILES["summary"], merged)
    return {**flow_paths, **schedule_paths}


def _flow_kpis(result: FlowSolveResult) -> dict[str, Any]:
    """Build the Phase I KPI payload."""
    delivered = 0.0
    if not result.flows.empty:
        delivered = float(result.flows[["sorted_m3", "unsorted_m3"]].to_numpy().sum())
    sorted_loads = (
        int(result.truckloads["sorted_truckloads"].sum()) if not result.truckloads.empty else 0
    )
    unsorted_loads = (
        int(result.truckloads["unsorted_truckloads"].sum()) if not result.truckloads.empty else 0
    )
    ending_unsorted = 0.0
    ending_water = 0.0
    if not result.yard_inventory.empty:
        ending = (
            result.yard_inventory.sort_values(["yard_id", "log_sort_id", "day"])
            .groupby(["yard_id", "log_sort_id"], as_index=False)
            .last()
        )
        ending_unsorted = float(ending["unsorted_inventory_m3"].sum())
        ending_water = float(ending["water_inventory_m3"].sum())
    marine_water = (
        float(result.marine_flows["water_m3"].sum()) if not result.marine_flows.empty else 0.0
    )
    barge_trips = (
        int(result.barge_trips["barge_trips"].sum()) if not result.barge_trips.empty else 0
    )
    terminal_handling = (
        float(result.marine_flows["origin_handling_m3"].sum())
        + float(result.marine_flows["destination_handling_m3"].sum())
        if not result.marine_flows.empty
        else 0.0
    )
    marine_drayage_cost = (
        float(result.marine_flows["drayage_cost"].sum()) if not result.marine_flows.empty else 0.0
    )
    barge_variable_cost = (
        float(result.marine_flows["barge_variable_cost"].sum())
        if not result.marine_flows.empty
        else 0.0
    )
    terminal_handling_cost = (
        float(result.marine_flows["origin_handling_cost"].sum())
        + float(result.marine_flows["destination_handling_cost"].sum())
        if not result.marine_flows.empty
        else 0.0
    )
    return {
        "status": result.status,
        "cost_objective": result.cost_objective,
        "workload_objective": result.workload_objective,
        "goal1": result.goal1,
        "goal2": result.goal2,
        "goal_deviations": result.goal_deviations,
        "delivered_m3": delivered,
        "sorted_truckloads": sorted_loads,
        "unsorted_truckloads": unsorted_loads,
        "total_truckloads": sorted_loads + unsorted_loads,
        "ending_unsorted_inventory_m3": ending_unsorted,
        "ending_water_inventory_m3": ending_water,
        "marine_water_m3": marine_water,
        "barge_trips": barge_trips,
        "terminal_handling_m3": terminal_handling,
        "marine_drayage_cost": marine_drayage_cost,
        "barge_variable_cost": barge_variable_cost,
        "terminal_handling_cost": terminal_handling_cost,
    }


def _schedule_kpis(result: ScheduleSolveResult | HaulingSAResult) -> dict[str, Any]:
    """Build the Phase II/III KPI payload."""
    loads = len(result.schedule)
    trucks_used = int(result.truck_summary["used"].sum()) if not result.truck_summary.empty else 0
    regular = (
        float(result.truck_summary["regular_minutes"].sum())
        if "regular_minutes" in result.truck_summary
        else 0.0
    )
    overtime = (
        float(result.truck_summary["overtime_minutes"].sum())
        if "overtime_minutes" in result.truck_summary
        else 0.0
    )
    busy = (
        float(result.loader_summary["busy_minutes"].sum())
        if not result.loader_summary.empty
        else 0.0
    )
    barge_schedule = getattr(result, "barge_schedule", pd.DataFrame())
    barge_summary = getattr(result, "barge_summary", pd.DataFrame())
    return {
        "status": result.status,
        "objective": result.objective,
        "fixed_cost": result.fixed_cost,
        "variable_cost": result.variable_cost,
        "overtime_cost": result.overtime_cost,
        "violation_cost": getattr(result, "violation_cost", 0.0),
        "violation_minutes": getattr(result, "violation_minutes", 0.0),
        "loads": loads,
        "trucks_used": trucks_used,
        "regular_minutes": regular,
        "overtime_minutes": overtime,
        "loader_busy_minutes": busy,
        "barge_trips": len(barge_schedule),
        "barge_volume_m3": (
            float(barge_schedule["volume_m3"].sum()) if not barge_schedule.empty else 0.0
        ),
        "barge_objective": getattr(result, "barge_objective", None),
        "barge_fixed_cost": getattr(result, "barge_fixed_cost", 0.0),
        "barges_used": len(barge_summary),
    }


def build_markdown_report(run_dir: Path) -> str:
    """Build a compact Markdown report from a run directory.

    Parameters
    ----------
    run_dir:
        Directory containing ``haul_summary.json`` and the stable CSV/JSON artefacts.

    Returns
    -------
    str
        Markdown report. Missing artefacts are named rather than treated as zero.

    Raises
    ------
    FileNotFoundError
        When ``haul_summary.json`` is absent.
    """
    summary_path = run_dir / FLOW_FILES["summary"]
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    kpis_path = run_dir / FLOW_FILES["kpis"]
    kpis = json.loads(kpis_path.read_text(encoding="utf-8")) if kpis_path.exists() else {}

    lines = [
        "# Hauling run report",
        "",
        f"- Run type: `{summary.get('run_type', 'unknown')}`",
        f"- Phase: `{summary.get('phase', 'unknown')}`",
        f"- Scenario: `{summary.get('scenario', 'unknown')}`",
        f"- Status: `{summary.get('status', 'unknown')}`",
        f"- Solver: `{summary.get('solver', 'unknown')}`",
        f"- Objective: `{summary.get('objective')}`",
        f"- Runtime: `{summary.get('runtime_seconds')}` s",
        f"- Generated: `{summary.get('generated_at', 'unknown')}`",
        "",
    ]
    if kpis:
        lines.extend(["## KPIs", "", "| Metric | Value |", "|---|---:|"])
        for key, value in sorted(kpis.items()):
            if isinstance(value, dict):
                continue
            lines.append(f"| `{key}` | {value} |")
        lines.append("")

    for title, filename in (
        ("Flows", FLOW_FILES["flows"]),
        ("Truckloads", FLOW_FILES["truckloads"]),
        ("Marine flows", FLOW_FILES["marine_flows"]),
        ("Barge trips", FLOW_FILES["barge_trips"]),
        ("Port inventory", FLOW_FILES["port_inventory"]),
        ("Schedule", SCHEDULE_FILES["schedule"]),
        ("Truck summary", SCHEDULE_FILES["truck_summary"]),
        ("Loader summary", SCHEDULE_FILES["loader_summary"]),
        ("Barge schedule", SCHEDULE_FILES["barge_schedule"]),
        ("Barge summary", SCHEDULE_FILES["barge_summary"]),
    ):
        path = run_dir / filename
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        lines.extend([f"## {title}", ""])
        lines.extend(_markdown_table(frame, max_rows=12))
        if len(frame) > 12:
            lines.append(f"\n_Showing 12 of {len(frame)} rows._")
        lines.append("")
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame, *, max_rows: int = 12) -> list[str]:
    """Render a simple Markdown table without an optional tabulate dependency."""
    if frame.empty:
        return ["_No rows._"]
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for row in frame.head(max_rows).itertuples(index=False):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return lines


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON payload with stable formatting."""
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _now() -> str:
    """Return a UTC timestamp."""
    return datetime.now(UTC).isoformat()
