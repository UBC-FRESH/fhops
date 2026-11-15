"""Build the Gavin Lake full-estate WS4 handoff for the FHOPS web console.

Source of truth: the AFRF Gavin Lake instance's ws4 baseline-evenflow run. The
handoff exposes all 2,907 blocks and the 300-year baseline schedule in the FHOPS
tactical-operational contract. It is a read-only view of the WS4 baseline, not a
re-optimization of the Gavin Lake estate.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
OUT = ROOT / "examples" / "demo_runs" / "gavin-full-estate"
SIMPLIFY_M = 4.0


def _period(offset: int) -> str:
    return f"P{int(offset) // 10:02d}"


def _periods() -> list[dict[str, Any]]:
    return [
        {
            "period_id": f"P{index:02d}",
            "start_date": f"{2026 + index * 10}-01-01",
            "end_date": f"{2035 + index * 10}-12-31",
            "duration_years": 10,
        }
        for index in range(30)
    ]


def _write_blocks() -> pd.DataFrame:
    source = gpd.read_file(INSTANCE / "data" / "legacy_gavinlake" / "spatial" / "fragments.shp")
    source["block_id"] = source["RES_KEY"].astype(str)
    source["area_ha"] = source.geometry.area / 10_000.0
    features = []
    for _, row in source.iterrows():
        geometry = row.geometry
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        simplified = geometry.simplify(SIMPLIFY_M, preserve_topology=True)
        features.append(
            {
                "type": "Feature",
                "id": row["block_id"],
                "properties": {
                    "block_id": row["block_id"],
                    "area_ha": round(float(row["area_ha"]), 6),
                    "bec": row.get("BEC"),
                    "contclas": row.get("CONTCLAS"),
                    "age_2019": row.get("AGE_2019"),
                },
                "geometry": mapping(simplified if not simplified.is_empty else geometry),
            }
        )
    payload = {
        "type": "FeatureCollection",
        "name": "gavin-lake-full-estate",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3005"}},
        "features": features,
    }
    (OUT / "blocks.geojson").write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )
    return source[["block_id", "area_ha"]]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    areas = _write_blocks()
    area_by_block = areas.set_index("block_id")["area_ha"]
    schedule = pd.read_csv(INSTANCE / "ws4" / "schedules" / "baseline_evenflow.csv")
    schedule["block_id"] = schedule["block_id"].astype(str)
    schedule["period_id"] = schedule["offset"].astype(int).map(_period)
    schedule["area_ha"] = schedule["block_id"].map(area_by_block).fillna(0.0)
    schedule = schedule[["period_id", "block_id", "treatment", "offset", "area_ha"]]
    schedule = schedule.rename(columns={"offset": "year"})
    schedule.to_csv(OUT / "schedule.csv", index=False)
    schedule.rename(columns={"treatment": "system_id"})[
        ["period_id", "block_id", "system_id", "area_ha"]
    ].to_csv(OUT / "harvest_decisions.csv", index=False)

    evidence = json.loads(
        (INSTANCE / "ws4" / "evidence" / "baseline" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    harvest = evidence["harvest_by_decade_m3"]
    production = pd.DataFrame(
        {
            "period_id": [_period(int(offset)) for offset in sorted(harvest, key=int)],
            "volume_m3": [float(harvest[offset]) for offset in sorted(harvest, key=int)],
        }
    )
    production["product_id"] = "all_products"
    production[["period_id", "product_id", "volume_m3"]].to_csv(
        OUT / "production.csv", index=False
    )
    production.to_csv(OUT / "harvest_by_period.csv", index=False)

    shutil.copyfile(
        INSTANCE / "ws4" / "evidence" / "baseline" / "target_report.csv",
        OUT / "target_report.csv",
    )
    shutil.copyfile(
        INSTANCE / "ws4" / "evidence" / "baseline" / "ending_inventory.csv",
        OUT / "ending_inventory.csv",
    )
    shutil.copyfile(
        INSTANCE / "ws4" / "targets_gavin_ltsy.yaml", OUT / "targets_gavin_ltsy.yaml"
    )

    statuses = evidence.get("target_status_counts", {})
    summary = {
        "run_id": "gavin-full-estate",
        "label": "Gavin Lake full estate — WS4 300-year baseline",
        "planning_level": "tactical_operational",
        "source": "AFRF Gavin Lake ws4 baseline_evenflow",
        "source_run": str(INSTANCE / "ws4" / "evidence" / "baseline"),
        "horizon_years": 300,
        "periods": 30,
        "period_width_years": 10,
        "blocks_total": int(len(areas)),
        "blocks_scheduled": int(schedule["block_id"].nunique()),
        "schedule_events": int(len(schedule)),
        "area_total_ha": round(float(areas["area_ha"].sum()), 3),
        "scheduled_area_ha": round(float(areas["area_ha"].sum()), 3),
        "total_production_m3": round(float(evidence["harvest_total_m3"]), 3),
        "mean_period_production_m3": round(float(evidence["harvest_mean_m3"]), 3),
        "min_period_production_m3": round(float(evidence["harvest_min_m3"]), 3),
        "max_period_production_m3": round(float(evidence["harvest_max_m3"]), 3),
        "growing_stock_initial_m3": round(float(evidence["growing_stock_initial_m3"]), 3),
        "growing_stock_final_m3": round(float(evidence["growing_stock_final_m3"]), 3),
        "targets_met": int(statuses.get("met", 0)),
        "targets_below": int(statuses.get("below", 0)),
        "targets_above": int(statuses.get("above", 0)),
        "revenue_note": "No public net-revenue account in the Gavin Lake baseline evidence; not fabricated.",
    }
    for name in ("tactical_summary.json", "summary.json", "kpis.json"):
        (OUT / name).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    scenario = {
        "name": "Gavin Lake full estate — WS4 300-year baseline",
        "planning_level": "tactical_operational",
        "schema_version": "0.1.0",
        "geo_block_path": "blocks.geojson",
        "geo_crs": "EPSG:3005",
        "periods": _periods(),
        "source": "femic-afrf-gavinlake-instance ws4 baseline_evenflow",
        "notes": "All 2,907 Gavin Lake blocks; WS4 baseline schedule; 300-year horizon.",
    }
    (OUT / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    provenance = {
        "schema_version": "fhops.afrf.handoff.v1",
        "instance": str(INSTANCE),
        "source": "ws4/schedules/baseline_evenflow.csv",
        "evidence": "ws4/evidence/baseline",
        "geometry": "data/legacy_gavinlake/spatial/fragments.shp, simplified at 4 m",
        "crs": "EPSG:3005",
        "notes": [
            "Read-only FHOPS tactical view of the WS4 Gavin Lake baseline.",
            "All 2,907 blocks are included; the baseline re-enters blocks every 80 years.",
            "No public net-revenue account is present in the baseline evidence.",
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
        command="WS4 Gavin Lake baseline_evenflow full-estate handoff",
        scenario="scenario.yaml",
        solver="ws4",
        status="completed",
        run_id="gavin-full-estate",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
