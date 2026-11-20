#!/usr/bin/env python3
"""Publish the legal-order Gavin MDWR group one-cut prototype."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
GROUPS = INSTANCE / "planning" / "2026-11-20_gavin-mdwr_groups_all_legal.geojson"
SCHEDULE = INSTANCE / "ws4" / "runtime" / "gavin-mdwr-group-schedule-legal.csv"
MAPPING = INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_matrix_legal_map.csv"
RUN = INSTANCE / "ws4" / "runtime" / "gavin-mdwr-group-sim-legal"
OUT = Path("examples/demo_runs/gavin-mdwr-group")
SOURCE = Path("examples/demo_runs/gavin-mdwr")


def periods() -> list[dict[str, object]]:
    return [
        {"period_id": f"P{index:02d}", "start_date": f"{2026 + index * 10}-01-01", "end_date": f"{2035 + index * 10}-12-31", "duration_years": 10}
        for index in range(30)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copyfile(SOURCE / "policy_targets.yaml", out / "policy_targets.yaml")

    groups = gpd.read_file(GROUPS)
    groups["block_id"] = groups["group_id"]
    groups.to_file(out / "blocks.geojson", driver="GeoJSON")
    scenario = yaml.safe_load((SOURCE / "scenario.yaml").read_text(encoding="utf-8"))
    scenario["name"] = "Gavin Lake MDWR legal-order group one-cut prototype"
    scenario["periods"] = periods()
    scenario["source"] = "Legal-order Low33/Moderate25/High20; 45/40 BA gate; 0.1 ha minimum openings"
    scenario["notes"] = "Group-level one-cut prototype. All assigned openings ≥0.1 ha. Not a policy replacement."
    (out / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")

    mapping = pd.read_csv(MAPPING).set_index("group_block_id")
    schedule = pd.read_csv(SCHEDULE)
    schedule["area_ha"] = schedule["block_id"].map(mapping["area_ha"]).fillna(0.0)
    schedule["period_id"] = (schedule["offset"].astype(int) // 10).map(lambda value: f"P{value:02d}")
    schedule = schedule[["block_id", "treatment", "offset", "period_id", "area_ha"]]
    schedule.to_csv(out / "schedule.csv", index=False)
    schedule.rename(columns={"treatment": "system_id"})[["period_id", "block_id", "system_id", "area_ha"]].to_csv(out / "harvest_decisions.csv", index=False)

    values = pd.read_csv(RUN / "account_values.csv")
    values = values.loc[values["account"] == "product.yield.managed.total"]
    values["period"] = (values["offset"].astype(int) // 10).astype(int)
    production = values.groupby("period", as_index=False)["value"].sum()
    production["period_id"] = production["period"].map(lambda value: f"P{int(value):02d}")
    production["product_id"] = "all_products"
    production["volume_m3"] = production["value"]
    production[["period_id", "product_id", "volume_m3"]].to_csv(out / "production.csv", index=False)
    production.to_csv(out / "harvest_by_period.csv", index=False)
    shutil.copyfile(RUN / "report_targets.csv", out / "report_targets.csv")
    shutil.copyfile(RUN / "ending_inventory.csv", out / "ending_inventory.csv")

    ending = pd.read_csv(RUN / "ending_inventory.csv").set_index("account")["value"]
    initial = pd.read_csv(RUN / "account_values.csv")
    initial = initial.loc[initial["offset"] == -1].set_index("account")["value"]
    vols = production["volume_m3"].tolist()
    summary = {
        "run_id": "gavin-mdwr-group",
        "label": "Gavin Lake — MDWR legal-order group one-cut prototype",
        "planning_level": "tactical_operational",
        "source": "Legal-order Low33/Moderate25/High20; 45/40 BA gate; 0.1 ha minimum openings",
        "horizon_years": 300,
        "periods": 30,
        "period_width_years": 10,
        "blocks_total": int(len(groups)),
        "blocks_scheduled": int(schedule["block_id"].nunique()),
        "schedule_events": int(len(schedule)),
        "area_total_ha": round(float(groups["area_ha"].sum()), 3),
        "scheduled_area_ha": round(float(schedule.groupby("block_id")["area_ha"].first().sum()), 3),
        "total_production_m3": round(float(production["volume_m3"].sum()), 3),
        "mean_period_production_m3": round(float(production["volume_m3"].mean()), 3),
        "min_period_production_m3": round(float(min(vols)), 3),
        "max_period_production_m3": round(float(max(vols)), 3),
        "growing_stock_initial_m3": round(float(initial.get("feature.yield.managed.total", 0.0)), 3),
        "growing_stock_final_m3": round(float(ending.get("feature.yield.managed.total", 0.0)), 3),
        "initial_ba_m2": round(float(initial.get("feature.ba.managed.total", 0.0)), 3),
        "final_ba_m2": round(float(ending.get("feature.ba.managed.total", 0.0)), 3),
        "mdwr_area_ha": 2799.31,
        "mdwr_blocks": 1443,
        "group_count": int(len(groups)),
        "assigned_groups": int(groups["assigned"].sum()),
        "standing_groups": int((~groups["assigned"]).sum()),
        "min_assigned_opening_ha": 0.1,
        "mdwr_clearcuts": 0,
        "targets_met": 0,
        "targets_below": 0,
        "targets_above": 0,
        "status_note": "Legal-order group one-cut prototype; no policy targets applied.",
    }
    for name in ("summary.json", "kpis.json", "tactical_summary.json"):
        (out / name).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    run_meta = {"schema_version": "1.0.0", "run_id": "gavin-mdwr-group", "domain": "tactical_operational", "run_type": "tactical_operational", "status": "prototype", "files": {"summary": "summary.json", "kpis": "kpis.json", "harvest_decisions": "harvest_decisions.csv", "production": "production.csv", "tactical_summary": "tactical_summary.json"}, "warnings": ["Legal-order group one-cut prototype, not a policy decision.", "No cohort re-entry or target framework."], "command": "WS4 Gavin MDWR legal-order group prototype", "scenario": "scenario.yaml", "solver": "ws4-simulate"}
    (out / "run.json").write_text(json.dumps(run_meta, indent=2) + "\n", encoding="utf-8")
    prov = {"groups": "planning/2026-11-20_gavin-mdwr_groups_all_legal.geojson", "schedule": "ws4/runtime/gavin-mdwr-group-schedule-legal.csv", "run": "ws4/runtime/gavin-mdwr-group-sim-legal", "caveats": ["One cut per assigned group; no 40-year cohort state.", "Minimum opening enforced; frost-prone class not applied."]}
    (out / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text("\n".join(["# Gavin Lake MDWR legal-order group one-cut prototype", "", "All assigned openings ≥0.1 ha; Low33/Moderate25/High20; 45/40 BA gate.", "", f"Harvested: {summary['total_production_m3']:,.0f} m³.", f"Final standing: {summary['growing_stock_final_m3']:,.0f} m³.", f"Final BA: {summary['final_ba_m2']:,.0f} m².", "", "Not a policy replacement; no cohort re-entry or target framework."]) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
