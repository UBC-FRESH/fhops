"""Build the full-estate MKRF WS4 handoff run for the FHOPS web console.

The source of truth is the MKRF WS4 instance and its full 100-year
``scenario-base-44`` run. This bridge does not re-solve the estate model in
FHOPS; it materializes the full block inventory, schedule, period accounts, and
provenance in the tactical-operational run contract the FHOPS web service reads.

Run from the public-demo repository root with the WS4 checkout available:

    python scripts/build_mkrf_full_estate.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[1]
WS4_ROOT = Path("/srv/shared-data/gep/ws4")
INSTANCE = WS4_ROOT / "femic" / "external" / "femic-mkrf-instance"
SOURCE_RUN = (
    WS4_ROOT / "ws4-public-demo" / "runs" / "femic-mkrf-instance" / "scenario-base-44"
)
MATRIX = INSTANCE / "ws4" / "runtime" / "matrix_silv"
OUT = ROOT / "examples" / "demo_runs" / "mkrf-full-estate"
SIMPLIFY_M = 4.0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _period(offset: int) -> str:
    return f"P{offset // 10:02d}"


def _period_periods() -> list[dict[str, Any]]:
    periods = []
    for index in range(10):
        start = 2026 + index * 10
        periods.append(
            {
                "period_id": f"P{index:02d}",
                "start_date": f"{start}-01-01",
                "end_date": f"{start + 9}-12-31",
                "duration_years": 10,
            }
        )
    return periods


def _simplified_blocks(areas: pd.Series) -> dict[str, Any]:
    source = _read_json(INSTANCE / "ws4" / "runtime" / "fragments.geojson")
    features = []
    for feature in source["features"]:
        block_id = str(feature["properties"]["block_id"])
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        simplified = geometry.simplify(SIMPLIFY_M, preserve_topology=True)
        if simplified.is_empty:
            simplified = geometry
        features.append(
            {
                "type": "Feature",
                "id": block_id,
                "properties": {
                    "block_id": block_id,
                    "area_ha": round(float(areas.get(int(block_id), 0.0)), 6),
                },
                "geometry": mapping(simplified),
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "mkrf-full-estate",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3005"}},
        "features": features,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    blocks = pd.read_parquet(MATRIX / "blocks.parquet")
    areas = blocks.groupby("block_id")["area_ha"].sum()
    schedule = pd.read_csv(SOURCE_RUN / "schedule.csv")
    schedule["block_id"] = schedule["block_id"].astype(int)
    schedule["period_id"] = schedule["offset"].astype(int).map(_period)
    schedule["area_ha"] = schedule["block_id"].map(areas).fillna(0.0)
    schedule = schedule[
        ["period_id", "block_id", "treatment", "offset", "area_ha"]
    ].rename(columns={"offset": "year"})

    product = pd.read_csv(SOURCE_RUN / "product_values.csv")
    product = product[product["account"].isin(
        [
            "product.yield.managed.total",
            "product.NetRevenue.managed.total",
            "product.Cost_Harvesting.managed.total",
        ]
    )].copy()
    product["period_id"] = product["offset"].astype(int).map(_period)
    period_values = (
        product.groupby(["period_id", "account"])["value"].sum().unstack(fill_value=0.0)
    ).rename(
        columns={
            "product.yield.managed.total": "volume_m3",
            "product.NetRevenue.managed.total": "net_revenue_cad",
            "product.Cost_Harvesting.managed.total": "harvest_cost_cad",
        }
    )
    period_values = period_values.reindex([f"P{i:02d}" for i in range(10)], fill_value=0.0)
    period_values.index.name = "period_id"
    period_values.to_csv(OUT / "revenue_by_period.csv")

    production = period_values.reset_index()[["period_id", "volume_m3"]].copy()
    production["product_id"] = "all_products"
    production = production[["period_id", "product_id", "volume_m3"]]
    production.to_csv(OUT / "production.csv", index=False)

    harvest = schedule.rename(columns={"treatment": "system_id"})[
        ["period_id", "block_id", "system_id", "area_ha"]
    ]
    harvest.to_csv(OUT / "harvest_decisions.csv", index=False)
    schedule.to_csv(OUT / "schedule.csv", index=False)

    report_targets = pd.read_csv(SOURCE_RUN / "report_targets.csv")
    for name in ("report_accounts.csv", "report_targets.csv", "patch_metrics.csv", "patch_accounts.csv", "ending_inventory.csv"):
        shutil.copyfile(SOURCE_RUN / name, OUT / name)

    total_volume = float(period_values["volume_m3"].sum())
    total_revenue = float(period_values["net_revenue_cad"].sum())
    total_cost = float(period_values["harvest_cost_cad"].sum())
    scheduled_area = float(schedule["area_ha"].sum())
    statuses = report_targets["status"].value_counts().to_dict()
    summary = {
        "run_id": "mkrf-full-estate",
        "label": "MKRF full estate — WS4 100-year base plan",
        "planning_level": "tactical_operational",
        "source": "WS4 scenario-base-44",
        "source_run": str(SOURCE_RUN),
        "dataset": str(MATRIX),
        "horizon_years": 100,
        "periods": 10,
        "period_width_years": 10,
        "blocks_total": int(len(areas)),
        "blocks_scheduled": int(schedule["block_id"].nunique()),
        "schedule_events": int(len(schedule)),
        "area_total_ha": round(float(areas.sum()), 3),
        "scheduled_area_ha": round(scheduled_area, 3),
        "total_production_m3": round(total_volume, 3),
        "net_revenue_cad": round(total_revenue, 3),
        "harvest_cost_cad": round(total_cost, 3),
        "net_revenue_after_harvest_cost_cad": round(total_revenue - total_cost, 3),
        "mean_annual_net_revenue_cad": round(total_revenue / 100.0, 3),
        "mean_annual_production_m3": round(total_volume / 100.0, 3),
        "targets_met": int(statuses.get("met", 0)),
        "targets_below": int(statuses.get("below", 0)),
        "targets_above": int(statuses.get("above", 0)),
        "opening_size_policy": "5-40 ha dominant; patch metrics included in reports",
    }
    (OUT / "tactical_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (OUT / "kpis.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    scenario = {
        "name": "MKRF full estate — WS4 100-year base plan",
        "planning_level": "tactical_operational",
        "schema_version": "0.1.0",
        "geo_block_path": "blocks.geojson",
        "geo_crs": "EPSG:3005",
        "periods": _period_periods(),
        "source": "femic-mkrf-instance ws4/runtime/matrix_silv; scenario-base-44",
        "notes": "Full 1,763-block MKRF ESRI:3005 estate handoff from WS4. The FHOPS console is a read-only view of the WS4 base plan.",
    }
    (OUT / "scenario.yaml").write_text(
        yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8"
    )
    (OUT / "blocks.geojson").write_text(
        json.dumps(_simplified_blocks(areas), separators=(",", ":")), encoding="utf-8"
    )

    provenance = {
        "schema_version": "fhops.mkrf.handoff.v1",
        "generated_from": {
            "instance": str(INSTANCE),
            "matrix": str(MATRIX),
            "run": str(SOURCE_RUN),
        },
        "model": "WS4 matrix_silv / MKRF canonical rebuild",
        "scenario": "scenario-base-44",
        "crs": "EPSG:3005",
        "geometry": "ws4/runtime/fragments.geojson, block polygons simplified at 4 m for web transfer",
        "notes": [
            "The FHOPS handoff is a read-only tactical view of the WS4 plan; it does not re-solve the estate model.",
            "Net revenue and harvest cost are WS4 public model accounts; raw contractor/cost overlays remain outside this public artifact.",
            "Patch metrics and target status are copied from the WS4 report surface.",
        ],
    }
    (OUT / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    from fhops.web.discovery import write_run_manifest

    write_run_manifest(
        OUT,
        domain="tactical_operational",
        run_type="tactical_operational",
        command="WS4 scenario-base-44 full-estate handoff",
        scenario="scenario.yaml",
        solver="ws4",
        seed=44,
        status="completed",
        run_id="mkrf-full-estate",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
