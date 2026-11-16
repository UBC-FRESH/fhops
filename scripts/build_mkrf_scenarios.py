"""Build the MKRF base/low/high WS4 scenario handoffs for the FHOPS console.

The full-estate geometry is shared from the base handoff. Each scenario gets its
own schedule, production, public WS4 revenue/cost accounts, target report, and
period map.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/srv/shared-data/gep/ws4/ws4-public-demo/runs/femic-mkrf-instance")
BASE = ROOT / "examples" / "demo_runs" / "mkrf-full-estate"
SCENARIOS = {
    "mkrf-full-estate": "scenario-base-44",
    "mkrf-low-estate": "scenario-low-44",
    "mkrf-high-estate": "scenario-high-44",
}


def period(offset: int) -> str:
    return f"P{int(offset) // 10:02d}"


def main() -> None:
    geometry = json.loads((BASE / "blocks.geojson").read_text(encoding="utf-8"))
    areas = {
        feature["properties"]["block_id"]: float(feature["properties"]["area_ha"])
        for feature in geometry["features"]
    }
    for run_id, source_name in SCENARIOS.items():
        if run_id == "mkrf-full-estate":
            continue
        source = SOURCE / source_name
        out = ROOT / "examples" / "demo_runs" / run_id
        out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE / "blocks.geojson", out / "blocks.geojson")
        schedule = pd.read_csv(source / "schedule.csv")
        schedule["block_id"] = schedule["block_id"].astype(str)
        schedule["period_id"] = schedule["offset"].astype(int).map(period)
        schedule["area_ha"] = schedule["block_id"].map(areas).fillna(0.0)
        schedule[["period_id", "block_id", "treatment", "offset", "area_ha"]].rename(
            columns={"treatment": "system_id", "offset": "year"}
        ).to_csv(out / "harvest_decisions.csv", index=False)
        schedule.to_csv(out / "schedule.csv", index=False)
        product = pd.read_csv(source / "product_values.csv")
        product = product[product["account"] == "product.yield.managed.total"].copy()
        product["period_id"] = product["offset"].astype(int).map(period)
        production = product.groupby("period_id")["value"].sum().reset_index()
        production["product_id"] = "all_products"
        production = production.rename(columns={"value": "volume_m3"})
        production[["period_id", "product_id", "volume_m3"]].to_csv(
            out / "production.csv", index=False
        )
        accounts = pd.read_csv(source / "account_values.csv")
        revenue = accounts[accounts["account"] == "product.NetRevenue.managed.total"].copy()
        cost = accounts[accounts["account"] == "product.Cost_Harvesting.managed.total"].copy()
        period_rows = []
        for p in sorted(production["period_id"].unique()):
            lo = int(p[1:]) * 10
            rv = float(revenue[revenue["offset"].between(lo, lo + 9)]["value"].sum())
            cv = float(cost[cost["offset"].between(lo, lo + 9)]["value"].sum())
            volume = float(production.loc[production["period_id"] == p, "volume_m3"].iloc[0])
            period_rows.append({"period_id": p, "volume_m3": volume, "net_revenue_cad": rv, "harvest_cost_cad": cv})
        period_df = pd.DataFrame(period_rows)
        period_df.to_csv(out / "revenue_by_period.csv", index=False)
        targets = pd.read_csv(source / "report_targets.csv")
        statuses = targets["status"].value_counts().to_dict()
        for name in ("report_targets.csv", "report_accounts.csv", "patch_metrics.csv", "patch_accounts.csv", "ending_inventory.csv"):
            shutil.copyfile(source / name, out / name)
        volume = float(period_df["volume_m3"].sum())
        net = float(period_df["net_revenue_cad"].sum())
        cost_total = float(period_df["harvest_cost_cad"].sum())
        summary = {
            "run_id": run_id,
            "label": f"MKRF full estate — WS4 {source_name}",
            "planning_level": "tactical_operational",
            "source": f"WS4 {source_name}",
            "source_run": str(source),
            "horizon_years": 100,
            "periods": 10,
            "period_width_years": 10,
            "blocks_total": len(areas),
            "blocks_scheduled": int(schedule["block_id"].nunique()),
            "schedule_events": int(len(schedule)),
            "area_total_ha": round(sum(areas.values()), 3),
            "scheduled_area_ha": round(sum(areas[b] for b in schedule["block_id"].unique()), 3),
            "total_production_m3": round(volume, 3),
            "net_revenue_cad": round(net, 3),
            "harvest_cost_cad": round(cost_total, 3),
            "net_revenue_after_harvest_cost_cad": round(net - cost_total, 3),
            "mean_annual_net_revenue_cad": round(net / 100.0, 3),
            "mean_annual_production_m3": round(volume / 100.0, 3),
            "targets_met": int(statuses.get("met", 0)),
            "targets_below": int(statuses.get("below", 0)),
            "targets_above": int(statuses.get("above", 0)),
            "opening_size_policy": "5-40 ha dominant; patch metrics included in reports",
        }
        for name in ("tactical_summary.json", "summary.json", "kpis.json"):
            (out / name).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        scenario = yaml.safe_load((BASE / "scenario.yaml").read_text(encoding="utf-8"))
        scenario["name"] = f"MKRF full estate — {source_name}"
        scenario["source"] = f"femic-mkrf-instance {source_name}"
        (out / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
        (out / "provenance.json").write_text(json.dumps({"run": str(source), "dataset": "ws4/runtime/matrix_silv", "notes": ["Read-only WS4 scenario handoff.", "Public WS4 revenue/cost accounts."]}, indent=2) + "\n", encoding="utf-8")
        from fhops.web.discovery import write_run_manifest
        write_run_manifest(out, domain="tactical_operational", run_type="tactical_operational", command=f"WS4 {source_name} MKRF estate handoff", scenario="scenario.yaml", solver="ws4", seed=44, status="completed", run_id=run_id)
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
