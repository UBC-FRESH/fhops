"""Build a rolling 12-month Phase I haul run for MKRF low-44 P01.

Each month uses 1/12 of the block supply and the same 30-day demand/fleet contract. The
monthly HiGHS Phase I plans are aggregated into one full-year run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples" / "demo_runs" / "mkrf-low-p01-operational"
OUT = ROOT / "examples" / "demo_runs" / "mkrf-low-p01-haul-year"
WORK = Path("/srv/shared-data/gep/ws4/tmp/mkrf-low-p01-haul-year")
INPUTS = ("blocks.csv", "blocks.geojson", "machines.csv", "landings.csv", "calendar.csv", "prod_rates.csv", "harvest_systems.yaml")


def month_scenario(month: int) -> Path:
    work = WORK / f"month-{month:02d}"
    work.mkdir(parents=True, exist_ok=True)
    for name in INPUTS:
        (work / name).write_bytes((SOURCE / name).read_bytes())
    blocks = pd.read_csv(work / "blocks.csv", dtype={"id": str})
    travel = pd.read_csv(SOURCE / "road_haul_blocks.csv", dtype={"block_id": str}).set_index("block_id")
    machines = pd.read_csv(work / "machines.csv")
    extra = [
        {"id": "ldr_" + block_id, "crew": "load", "daily_hours": 10.0, "operating_cost": 0.0, "role": "loader"}
        for block_id in blocks["id"]
    ]
    extra.append({"id": "ldr_y", "crew": "yard", "daily_hours": 10.0, "operating_cost": 0.0, "role": "loader"})
    pd.concat([machines, pd.DataFrame(extra)], ignore_index=True).to_csv(work / "machines.csv", index=False)
    total = float(blocks["work_required"].sum())
    supply = [
        {"block_id": row.id, "log_sort_id": "mixed", "sorted_m3": 0.0, "unsorted_m3": float(row.work_required) / 12.0}
        for row in blocks.itertuples()
    ]
    per_day = 832.0
    demand = [{"yard_id": "y_gl", "log_sort_id": "mixed", "day": day, "volume_m3": per_day} for day in range(1, 31)]
    demand[-1]["volume_m3"] = round(sum(item["unsorted_m3"] for item in supply) - per_day * 29.0 - 1.0, 3)
    hauling = {
        "planning_horizon_days": 30,
        "start_day": 1,
        "log_sorts": [{"id": "mixed", "product_id": "mixed", "sorted": False}],
        "contractors": [{"id": "c1", "name": "Rolling hauler", "preferred_daily_truckloads": 19}],
        "truck_types": [{"id": "highway", "capacity_m3": 45, "fixed_cost": 120.0, "variable_cost_per_minute": 1.2, "overtime_cost_per_minute": 1.8, "can_carry_sorted": True, "can_carry_unsorted": True}],
        "trucks": [{"id": f"c1_h{i}", "contractor_id": "c1", "truck_type_id": "highway"} for i in range(1, 21)],
        "depots": [{"id": "depot", "name": "Vancouver screening depot"}],
        "sort_yards": [{"id": "y_gl", "facility_id": "mill_gl", "unsorted_storage_m3": 50000, "sorted_processing_m3_per_day": 0, "unsorted_processing_m3_per_day": 20000, "total_processing_m3_per_day": 20000, "initial_unsorted_inventory_m3": 0, "initial_water_inventory_m3": 0}],
        "loader_locations": [{"loader_id": "ldr_" + row.id, "location_id": row.id, "location_kind": "pickup", "service_minutes": 22} for row in blocks.itertuples()] + [{"loader_id": "ldr_y", "location_id": "y_gl", "location_kind": "delivery", "service_minutes": 18}],
        "supply": supply,
        "demand": demand,
        "haul_arcs": [{"block_id": row.id, "yard_id": "y_gl", "truck_type_id": "highway", "travel_minutes": round(float(travel.loc[row.id, "one_way_km"]) / 50.0 * 60.0 + 15.0, 2), "distance_km": float(travel.loc[row.id, "one_way_km"])} for row in blocks.itertuples()],
        "depot_legs": [{"depot_id": "depot", "location_id": row.id, "truck_type_id": "highway", "travel_minutes": round(float(travel.loc[row.id, "one_way_km"]) / 50.0 * 60.0 + 15.0, 2)} for row in blocks.itertuples()] + [{"depot_id": "depot", "location_id": "y_gl", "truck_type_id": "highway", "travel_minutes": 15}],
        "contractor_blocks": [{"contractor_id": "c1", "block_id": row.id} for row in blocks.itertuples()],
        "driver_policy": {"regular_minutes": 600, "max_overtime_minutes": 120, "overtime_violation_penalty_per_minute": 10},
        "roadside_inventory_penalty_per_m3": 25,
        "loader_travel_cost_per_km": 0,
        "default_loader_service_minutes": 20,
    }
    scenario = yaml.safe_load((SOURCE / "scenario.yaml").read_text(encoding="utf-8"))
    scenario["schema_version"] = "1.1.0"
    scenario["num_days"] = 365
    scenario["name"] = f"MKRF low-44 P01 rolling month {month}"
    scenario["hauling"] = hauling
    (work / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    return work


def main() -> None:
    flows = []
    truckloads = []
    monthly = []
    for month in range(1, 13):
        work = month_scenario(month)
        plan = work / "plan"
        cmd = [sys.executable, "-m", "fhops.cli.main", "haul", "plan", str(work / "scenario.yaml"), "--out-dir", str(plan), "--time-limit", "12"]
        result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=120)
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr[-1000:])
        summary = json.loads((plan / "haul_summary.json").read_text(encoding="utf-8"))
        if summary.get("status") not in {"optimal", "feasible"}:
            raise RuntimeError(f"month {month} status {summary.get('status')}")
        flow = pd.read_csv(plan / "haul_flows.csv")
        flow["day"] = flow["day"].astype(int) + (month - 1) * 30
        flow["scenario_day"] = flow["scenario_day"].astype(int) + (month - 1) * 30
        flows.append(flow)
        trucks = pd.read_csv(plan / "haul_truckloads.csv")
        trucks["day"] = trucks["day"].astype(int) + (month - 1) * 30
        trucks["scenario_day"] = trucks["scenario_day"].astype(int) + (month - 1) * 30
        truckloads.append(trucks)
        delivered_month = float(flow["unsorted_m3"].sum())
        loads_month = int(trucks["total_truckloads"].sum())
        monthly.append({"month": month, "delivered_m3": delivered_month, "truckloads": loads_month, "status": summary.get("status")})
    OUT.mkdir(parents=True, exist_ok=True)
    for name in INPUTS:
        (OUT / name).write_bytes((SOURCE / name).read_bytes())
    scenario = yaml.safe_load((SOURCE / "scenario.yaml").read_text(encoding="utf-8"))
    scenario["schema_version"] = "1.1.0"
    scenario["name"] = "MKRF low-44 P01 rolling full-year haul"
    scenario["notes"] = "12 rolling 30-day FHOPS Phase I windows; aggregate flows cover days 1-360."
    (OUT / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    pd.concat(flows, ignore_index=True).to_csv(OUT / "haul_flows.csv", index=False)
    pd.concat(truckloads, ignore_index=True).to_csv(OUT / "haul_truckloads.csv", index=False)
    delivered = sum(row["delivered_m3"] for row in monthly)
    loads = sum(row["truckloads"] for row in monthly)
    summary = {
        "schema_version": "1.1.0",
        "run_type": "plan",
        "phase": "I rolling",
        "scenario": "MKRF low-44 P01 rolling full-year haul",
        "start_day": 1,
        "status": "feasible",
        "months": 12,
        "planning_horizon_days": 360,
        "delivered_m3": round(delivered, 3),
        "truckloads": loads,
        "monthly": monthly,
        "files": {"flows": "haul_flows.csv", "truckloads": "haul_truckloads.csv"},
        "note": "Twelve rolling 30-day Phase I windows; not a single 365-day MIP.",
    }
    (OUT / "haul_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    kpis = {
        "status": "feasible",
        "phase_i_delivered_m3": round(delivered, 3),
        "phase_i_truckloads": loads,
        "months": 12,
        "label": "MKRF low-44 P01 — rolling full-year Phase I haul",
        "note": "12 rolling 30-day FHOPS Phase I windows; Phase II/III day samples are separate.",
    }
    (OUT / "haul_kpis.json").write_text(json.dumps(kpis, indent=2) + "\n", encoding="utf-8")
    (OUT / "kpis.json").write_text(json.dumps(kpis, indent=2) + "\n", encoding="utf-8")
    (OUT / "provenance.json").write_text(json.dumps({"source": str(SOURCE), "method": "12 rolling 30-day Phase I windows", "months": monthly}, indent=2) + "\n", encoding="utf-8")
    from fhops.web.discovery import write_run_manifest
    write_run_manifest(OUT, domain="hauling", run_type="haul_plan", command="12 rolling FHOPS haul Phase I months", scenario="scenario.yaml", solver="highs", seed=42, status="feasible", run_id="mkrf-low-p01-haul-year")
    (OUT / "README.md").write_text("# MKRF low-44 P01 rolling full-year haul\n\nTwelve rolling 30-day FHOPS Phase I windows.\n\n- 110 blocks\n- 20 trucks per window\n- 832 m³/day demand\n- aggregate delivered volume and loads in `haul_summary.json`\n- monthly detail in `provenance.json`\n\nThis is a rolling Phase I aggregation, not a single 365-day MILP. Phase II/III day samples are separate.\n", encoding="utf-8")
    print(json.dumps(summary, indent=2)[:2000])


if __name__ == "__main__":
    main()
