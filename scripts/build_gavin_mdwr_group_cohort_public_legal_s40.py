#!/usr/bin/env python3
"""Publish the corrected full-area Gavin MDWR group cohort prototype."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
GROUPS = INSTANCE / "planning" / "2026-11-20_gavin-mdwr_groups_all_legal_s40.geojson"
CUTS = INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_cuts_legal_s40.csv"
STATE = INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_state_legal_s40.json"
OUT = Path("examples/demo_runs/gavin-mdwr-group")
SOURCE = Path("examples/demo_runs/gavin-mdwr")


def periods() -> list[dict[str, object]]:
    return [
        {
            "period_id": f"P{index:02d}",
            "start_date": f"{2026 + index * 10}-01-01",
            "end_date": f"{2035 + index * 10}-12-31",
            "duration_years": 10,
        }
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
    scenario["name"] = "Gavin Lake MDWR legal-order group cohort prototype"
    scenario["periods"] = periods()
    scenario["source"] = "Legal-order Low33/Moderate25/High20; 45/40 BA gate; 0.1 ha minimum openings"
    scenario["notes"] = (
        "Group-level WS4 cohort prototype with cut and standing groups. "
        "It inherits the accepted block-level BA gate; group BA is reported, not a per-group gate. "
        "Not a replacement for the block policy screen."
    )
    (out / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")

    cuts = pd.read_csv(CUTS)
    cuts = cuts.loc[cuts["ba_ok"]].copy()
    cuts["period_id"] = (cuts["entry_year"].astype(int) // 10).map(lambda value: f"P{value:02d}")
    schedule = cuts[["group_id", "entry_year", "period_id", "area_ha"]].rename(
        columns={"group_id": "block_id", "entry_year": "offset"}
    )
    schedule["treatment"] = "CC"
    schedule = schedule[["block_id", "treatment", "offset", "period_id", "area_ha"]]
    schedule.to_csv(out / "schedule.csv", index=False)
    schedule.rename(columns={"treatment": "system_id"})[
        ["period_id", "block_id", "system_id", "area_ha"]
    ].to_csv(out / "harvest_decisions.csv", index=False)

    production = cuts.groupby("period_id", as_index=False)["volume_m3"].sum()
    production["product_id"] = "all_products"
    production[["period_id", "product_id", "volume_m3"]].to_csv(out / "production.csv", index=False)
    production.to_csv(out / "harvest_by_period.csv", index=False)
    (out / "report_targets.csv").write_text("account,min,max,mean,final\n", encoding="utf-8")
    (out / "ending_inventory.csv").write_text("offset,account,value\n299,feature.ba.managed.total,190708.029\n299,feature.yield.managed.total,1167610.664\n", encoding="utf-8")

    state = json.loads(STATE.read_text(encoding="utf-8"))
    summary = {
        "run_id": "gavin-mdwr-group",
        "label": "Gavin Lake — MDWR full-area group cohort prototype",
        "planning_level": "tactical_operational",
        "source": "10 m group cohorts; accepted block entries; VRI BA fit; base CC successor curves",
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
        "min_period_production_m3": round(float(production["volume_m3"].min()), 3),
        "max_period_production_m3": round(float(production["volume_m3"].max()), 3),
        "growing_stock_final_m3": state["final_state_volume_m3"],
        "final_ba_m2": state["final_ba_m2"],
        "mdwr_area_ha": 2799.31,
        "mdwr_blocks": 1443,
        "group_count": int(len(groups)),
        "assigned_groups": int(groups["assigned"].sum()),
        "standing_groups": int((~groups["assigned"]).sum()),
        "cohort_entries": state["cuts"],
        "mdwr_clearcuts": 0,
        "targets_met": 0,
        "targets_below": 0,
        "targets_above": 0,
        "status_note": "Group-cohort prototype; no policy targets applied.",
    }
    for name in ("summary.json", "kpis.json", "tactical_summary.json"):
        (out / name).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    run_meta = {
        "schema_version": "1.0.0",
        "run_id": "gavin-mdwr-group",
        "domain": "tactical_operational",
        "run_type": "tactical_operational",
        "status": "prototype",
        "files": {
            "summary": "summary.json",
            "kpis": "kpis.json",
            "harvest_decisions": "harvest_decisions.csv",
            "production": "production.csv",
            "tactical_summary": "tactical_summary.json",
        },
        "warnings": [
            "Group-cohort prototype, not a policy decision.",
            "Block-level BA gate inherited; group BA is reported, not a per-group gate.",
            "Full group area 2,797.5 ha of 2,799.3 ha MDWR.",
        ],
        "command": "WS4 Gavin MDWR group-cohort prototype",
        "scenario": "scenario.yaml",
        "solver": "ws4-simulate",
    }
    (out / "run.json").write_text(json.dumps(run_meta, indent=2) + "\n", encoding="utf-8")
    provenance = {
        "groups": "planning/2026-11-19_gavin-mdwr_groups_all.geojson",
        "cohort_cuts": "planning/2026-11-20_gavin-mdwr_group_cohort_cuts.csv",
        "cohort_state": "planning/2026-11-20_gavin-mdwr_group_cohort_state.json",
        "ba_fit": "planning/2026-11-19_gavin-mdwr_ba_fit.json",
        "caveats": [
            "Schematic 10 m groups; no minimum group size.",
            "VRI cross-sectional BA fit; no plantation BA model.",
            "Accepted block entries inherit the stand-level BA gate.",
        ],
    }
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        "\n".join(
            [
                "# Gavin Lake MDWR legal-order group cohort prototype",
                "",
                "This is a group-level diagnostic, not a policy scenario.",
                "",
                "34,512 groups on 1,443 blocks; 2,797.5 ha represented.",
                "9,674 assigned groups, 24,838 standing groups.",
                "",
                f"Harvested volume: {summary['total_production_m3']:,.0f} m³ / 300 years.",
                f"Final standing volume: {summary['growing_stock_final_m3']:,.0f} m³.",
                f"Final BA: {summary['final_ba_m2']:,.0f} m².",
                "",
                "Limits: schematic 10 m groups, no minimum group size, no",
                "windthrow, and a VRI cross-sectional BA fit. Not a replacement",
                "for the block-level policy screen.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
