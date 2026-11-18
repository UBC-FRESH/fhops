#!/usr/bin/env python3
"""Build the public MKRF variable-retention policy handoff.

Source: the age-aware, bucked-log, 400 m² retained-BA policy screen. The
handoff is a read-only FHOPS tactical view; it does not re-solve the estate.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-mkrf-instance")
SOURCE = INSTANCE / "ws4" / "runtime" / "vr_grade_seed_asof"
MATRIX = INSTANCE / "ws4" / "runtime" / "matrix_vr_grid"
BASE = ROOT / "examples" / "demo_runs" / "mkrf-full-estate"
OUT = ROOT / "examples" / "demo_runs" / "mkrf-vr-policy"


def periods() -> list[dict[str, object]]:
    return [
        {
            "period_id": f"P{index:02d}",
            "start_date": f"{2026 + index * 10}-01-01",
            "end_date": f"{2035 + index * 10}-12-31",
            "duration_years": 10,
        }
        for index in range(10)
    ]


def npv4(values: list[float]) -> float:
    return sum(
        (value / 10.0) / ((1.04) ** year)
        for index, value in enumerate(values)
        for year in range(index * 10 + 1, index * 10 + 11)
    )


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copyfile(BASE / "blocks.geojson", OUT / "blocks.geojson")
    geometry = json.loads((BASE / "blocks.geojson").read_text(encoding="utf-8"))
    areas = {
        str(feature["properties"]["block_id"]): float(feature["properties"]["area_ha"])
        for feature in geometry["features"]
    }
    schedule = pd.read_csv(SOURCE / "schedule.csv")
    schedule["block_id"] = schedule["block_id"].astype(int)
    schedule["period_id"] = schedule["offset"].astype(int).map(
        lambda offset: f"P{int(offset) // 10:02d}"
    )
    schedule["area_ha"] = schedule["block_id"].astype(str).map(areas).fillna(0.0)
    schedule = schedule[
        ["period_id", "block_id", "treatment", "offset", "area_ha"]
    ].rename(columns={"offset": "year"})
    schedule.to_csv(OUT / "schedule.csv", index=False)
    schedule.rename(columns={"treatment": "system_id"})[
        ["period_id", "block_id", "system_id", "area_ha"]
    ].to_csv(OUT / "harvest_decisions.csv", index=False)

    accounts = pd.read_csv(SOURCE / "account_values.csv")
    wanted = [
        "product.yield.managed.total",
        "product.LogValue.managed.total",
        "product.NetRevenue.managed.total",
        "product.Cost_Harvesting.managed.total",
        "product.ba.retention.total",
        "product.retention.total.volume",
        "product.retention.total.value",
        "product.retention.sawlog_butt.volume",
        "product.retention.sawlog_butt.value",
        "product.retention.sawlog_upper.volume",
        "product.retention.sawlog_upper.value",
        "product.retention.pulp.volume",
        "product.retention.pulp.value",
    ]
    accounts = accounts.loc[accounts["account"].isin(wanted)].copy()
    accounts["period_id"] = accounts["offset"].astype(int).map(
        lambda offset: f"P{int(offset) // 10:02d}"
    )
    values = accounts.groupby(["period_id", "account"])["value"].sum().unstack(
        fill_value=0.0
    )
    values = values.reindex([f"P{index:02d}" for index in range(10)], fill_value=0.0)
    values.index.name = "period_id"
    values.to_csv(OUT / "retention_by_period.csv")

    production = values.reset_index()[["period_id", "product.yield.managed.total"]]
    production = production.rename(
        columns={"product.yield.managed.total": "volume_m3"}
    )
    production["product_id"] = "all_products"
    production[["period_id", "product_id", "volume_m3"]].to_csv(
        OUT / "production.csv", index=False
    )
    revenue = values.reset_index()[
        [
            "period_id",
            "product.LogValue.managed.total",
            "product.NetRevenue.managed.total",
            "product.Cost_Harvesting.managed.total",
            "product.ba.retention.total",
            "product.retention.total.volume",
            "product.retention.total.value",
        ]
    ].rename(
        columns={
            "product.LogValue.managed.total": "gross_log_value_cad",
            "product.NetRevenue.managed.total": "net_revenue_cad",
            "product.Cost_Harvesting.managed.total": "harvest_cost_cad",
            "product.ba.retention.total": "retained_ba_m2",
            "product.retention.total.volume": "retained_volume_m3",
            "product.retention.total.value": "retained_log_value_cad",
        }
    )
    revenue.to_csv(OUT / "revenue_by_period.csv", index=False)

    for name in (
        "report_targets.csv",
        "report_accounts.csv",
        "ending_inventory.csv",
        "patch_metrics.csv",
        "patch_accounts.csv",
    ):
        shutil.copyfile(SOURCE / name, OUT / name)
    shutil.copyfile(INSTANCE / "ws4" / "targets_vr_policy.yaml", OUT / "policy_targets.yaml")

    report = pd.read_csv(SOURCE / "report_accounts.csv")

    def mean(account: str, *, annual: bool = True) -> float:
        row = report.loc[report["account"] == account]
        if row.empty:
            return 0.0
        return float(row.iloc[0]["mean"]) * (100.0 if annual else 1.0)

    targets = pd.read_csv(SOURCE / "report_targets.csv")["status"].value_counts().to_dict()
    gross = mean("product.LogValue.managed.total")
    net = mean("product.NetRevenue.managed.total")
    cost = mean("product.Cost_Harvesting.managed.total")
    volume = mean("product.yield.managed.total")
    retained_ba = mean("product.ba.retention.total")
    retained_volume = mean("product.retention.total.volume")
    retained_value = mean("product.retention.total.value")
    periods_total = values.reset_index()
    summary = {
        "run_id": "mkrf-vr-policy",
        "label": "MKRF variable-retention policy — 400 m² retained BA per period",
        "planning_level": "tactical_operational",
        "source": "WS4 age-aware, bucked-log retention seed; 400 m² policy floor",
        "source_run": str(SOURCE),
        "dataset": str(MATRIX),
        "horizon_years": 100,
        "periods": 10,
        "period_width_years": 10,
        "blocks_total": 1763,
        "blocks_scheduled": int(schedule["block_id"].nunique()),
        "schedule_events": int(len(schedule)),
        "area_total_ha": 4810.85,
        "scheduled_area_ha": round(float(schedule.groupby("block_id")["area_ha"].first().sum()), 3),
        "managed_area_ha": round(mean("feature.area.managed.total", annual=False), 3),
        "unmanaged_area_ha": round(mean("feature.area.unmanaged.total", annual=False), 3),
        "total_production_m3": round(volume, 3),
        "gross_log_value_cad": round(gross, 3),
        "net_revenue_cad": round(net, 3),
        "harvest_cost_cad": round(cost, 3),
        "net_after_harvest_cost_cad": round(net - cost, 3),
        "retained_ba_m2": round(retained_ba, 3),
        "retained_volume_m3": round(retained_volume, 3),
        "retained_log_value_cad": round(retained_value, 3),
        "mean_annual_production_m3": round(volume / 100.0, 3),
        "mean_annual_net_revenue_cad": round(net / 100.0, 3),
        "npv_gross_4pct_cad": round(npv4(periods_total["product.LogValue.managed.total"].tolist()), 3),
        "npv_net_4pct_cad": round(npv4(periods_total["product.NetRevenue.managed.total"].tolist()), 3),
        "targets_met": int(targets.get("met", 0)),
        "targets_below": int(targets.get("below", 0)),
        "targets_above": int(targets.get("above", 0)),
        "retention_policy": "product.ba.retention.total >= 400 m² per 10-year period",
        "retention_basis": "dispersed retention, percent of pre-harvest basal area",
        "retention_state": "full managed area; retained DF carried in composite next-rotation track",
        "notes": "Bucked log-class ledger; coastal D/F/H/I/J/U/X/Y grade mapping still pending.",
    }
    for name in ("summary.json", "kpis.json", "tactical_summary.json"):
        (OUT / name).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    scenario = yaml.safe_load((BASE / "scenario.yaml").read_text(encoding="utf-8"))
    scenario["name"] = "MKRF variable-retention policy — 400 m² retained BA"
    scenario["periods"] = periods()
    scenario["source"] = "femic-mkrf-instance matrix_vr_grid; vr_grade_seed_asof"
    scenario["notes"] = (
        "Full 1,763-block MKRF estate. Dispersed variable retention, 400 m² "
        "retained BA per period, full managed area, composite retained-DF "
        "next-rotation track. Read-only WS4 handoff."
    )
    (OUT / "scenario.yaml").write_text(
        yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8"
    )
    provenance = {
        "instance": str(INSTANCE),
        "matrix": str(MATRIX),
        "source_run": str(SOURCE),
        "policy_targets": str(INSTANCE / "ws4" / "targets_vr_policy.yaml"),
        "geometry": "examples/demo_runs/mkrf-full-estate/blocks.geojson",
        "retention_basis": "m² retained basal area per 10-year period",
        "state": "full managed block; composite plantation + retained-DF track",
        "caveats": [
            "Policy seed schedule, not a fully re-optimized target search.",
            "Bucked sawlog butt/upper/pulp ledger; coastal grade mapping still pending.",
            "Composite retained-overstory curves are additive.",
            "400 m² floor is a scenario policy, not a legal requirement.",
        ],
    }
    (OUT / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "README.md").write_text(
        "\n".join(
            [
                "# MKRF variable-retention policy",
                "",
                "Public tactical handoff for the MKRF dispersed-retention policy.",
                "",
                "- 400 m² retained basal area per 10-year period;",
                "- 10/20/30% BA choice grid plus CC;",
                "- full managed block area;",
                "- retained DF carried into the composite next-rotation track;",
                "- 44/2/1 targets; gross CAD 655.2M; net CAD 369.2M;",
                "- retained BA 12,798 m²; retained log volume 193,970 m³;",
                "- bucked sawlog butt/upper/pulp ledger;",
                "- coastal grade mapping still pending.",
                "",
                "Read-only WS4 handoff; not an approved management plan.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    from fhops.web.discovery import write_run_manifest

    write_run_manifest(
        OUT,
        domain="tactical_operational",
        run_type="tactical_operational",
        command="WS4 MKRF variable-retention policy handoff",
        scenario="scenario.yaml",
        solver="ws4",
        seed=44,
        status="policy-screen",
        run_id="mkrf-vr-policy",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
