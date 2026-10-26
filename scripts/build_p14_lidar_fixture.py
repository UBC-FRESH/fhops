#!/usr/bin/env python3
"""Build the public TFL 6 LidarBC FHOPS fixture.

The fixture is a small public example: seven clipped VRI polygons, one landing,
one road job, seven ground-based machines, and native-resolution slope/CHM
support rows from a FEMIC bundle. Tables other than the LiDAR evidence are
synthetic planning values for a smoke solve, not field inventory or calibrated
costs.

Example
-------
python scripts/build_p14_lidar_fixture.py \
  --bundle /path/to/lidarbc-995fb1f771f4d7fe \
  --vri /path/to/vri_aoi.geojson

The command is deterministic for a given bundle and VRI layer. It validates the
written scenario through the normal FHOPS loader before returning.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import LineString, box

from fhops.scenario.io import load_scenario
from fhops.scenario.lidar import (
    FemicLidarBundle,
    LidarPolygonSummary,
    load_femic_lidar_bundle,
    summarize_femic_lidar_for_polygons,
)

DEFAULT_BUNDLE_ID = "lidarbc-995fb1f771f4d7fe"
DEFAULT_BUNDLE_VERSION = "2026.10.0-tfl6-pilot"
LANDING_BOX = (881710.0, 627510.0, 881730.0, 627530.0)
ROAD_LINE = ((881720.0, 627520.0), (882200.0, 628000.0))
ROAD_BUFFER_M = 5.0
WORK_PER_HA_M3 = 20.0
DAYS = 10


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path, help="FEMIC LidarBC bundle.")
    parser.add_argument("--vri", required=True, type=Path, help="Clipped VRI GeoJSON layer.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("examples/lidar_tfl6"),
        help="Fixture output directory.",
    )
    parser.add_argument("--bundle-id", default=DEFAULT_BUNDLE_ID)
    parser.add_argument("--bundle-version", default=DEFAULT_BUNDLE_VERSION)
    args = parser.parse_args()

    bundle = load_femic_lidar_bundle(
        args.bundle,
        expected_bundle_id=args.bundle_id,
        expected_bundle_version=args.bundle_version,
    )
    out = args.out
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    vri = gpd.read_file(args.vri)
    if vri.crs is None:
        raise SystemExit("VRI layer has no CRS.")
    if vri.crs.to_string() != "EPSG:3005":
        raise SystemExit("The fixture expects the TFL 6 VRI layer in EPSG:3005.")
    if vri.empty:
        raise SystemExit("VRI layer is empty.")
    vri = vri.copy()
    vri["block_id"] = "T6_" + vri["feature_id"].astype(str)
    vri["area_ha"] = vri.geometry.area / 10000.0
    vri[["block_id", "area_ha", "geometry"]].to_file(out / "blocks.geojson", driver="GeoJSON")

    landing = gpd.GeoDataFrame(
        {"landing_id": ["L1"]},
        geometry=[box(*LANDING_BOX)],
        crs="EPSG:3005",
    )
    landing.to_file(out / "landings.geojson", driver="GeoJSON")
    road = gpd.GeoDataFrame(
        {"road_id": ["R1"]},
        geometry=[LineString(ROAD_LINE).buffer(ROAD_BUFFER_M, cap_style=2)],
        crs="EPSG:3005",
    )
    road.to_file(out / "roads.geojson", driver="GeoJSON")

    support_rows = _support_rows(bundle, vri, out)
    _write_tables(out, vri, support_rows)
    _write_scenario(out, bundle, vri, support_rows)
    _write_provenance(out, bundle, args.vri)
    _write_readme(out)
    load_scenario(out / "scenario.yaml")
    print(
        f"Wrote {len(vri)} blocks, 1 landing, and 1 road to {out} "
        f"from {bundle.bundle_id}@{bundle.bundle_version}."
    )


def _support_rows(
    bundle: FemicLidarBundle,
    vri: gpd.GeoDataFrame,
    out: Path,
) -> list[dict[str, object]]:
    blocks_path = out / "blocks.geojson"
    landing_path = out / "landings.geojson"
    road_path = out / "roads.geojson"
    rows: list[dict[str, object]] = []
    for unit, path, id_field in (
        ("block", blocks_path, "block_id"),
        ("landing", landing_path, "landing_id"),
        ("road", road_path, "road_id"),
    ):
        frame = gpd.read_file(path)
        areas = {
            str(feature[id_field]): float(feature.geometry.area) for _, feature in frame.iterrows()
        }
        for product, field in (("slope", "slope_percent"), ("chm", "canopy_height_m")):
            summaries = summarize_femic_lidar_for_polygons(
                bundle,
                path,
                product=product,
                id_field=id_field,
                statistics=("mean",),
            )
            for summary in summaries:
                rows.append(
                    _support_payload(
                        unit,
                        summary,
                        field,
                        areas[summary.polygon_id],
                        bundle,
                        product,
                    )
                )
    return rows


def _support_payload(
    unit: str,
    summary: LidarPolygonSummary,
    field: str,
    area_m2: float,
    bundle: FemicLidarBundle,
    product: str,
) -> dict[str, object]:
    record = bundle.products[product]
    return {
        "support_unit": unit,
        "support_id": summary.polygon_id,
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.bundle_version,
        "product": product,
        "aggregation": "mean",
        "native_resolution_m": record.resolution_m or 1.0,
        "support_area_m2": round(area_m2, 3),
        "valid_pixels": summary.valid_pixels,
        field: round(float(summary.statistics["mean"]), 6),
        "provenance": (
            f"FEMIC {bundle.bundle_id}@{bundle.bundle_version}; native "
            f"{record.resolution_m or 1.0:g} m {product} mean; no reprojection or resampling"
        ),
    }


def _write_tables(
    out: Path,
    vri: gpd.GeoDataFrame,
    support_rows: list[dict[str, object]],
) -> None:
    data_dir = out / "data"
    slope_by_block = _block_values(support_rows, "slope_percent")
    blocks = pd.DataFrame(
        {
            "id": vri["block_id"],
            "landing_id": "L1",
            "harvest_system_id": "ground_fb_skid",
            "work_required": (vri["area_ha"] * WORK_PER_HA_M3).round(1),
            "earliest_start": 1,
            "latest_finish": DAYS,
            "avg_stem_size_m3": 0.4,
            "volume_per_ha_m3": 300.0,
            "stem_density_per_ha": 750.0,
            "ground_slope_percent": vri["block_id"].map(slope_by_block).round(3),
        }
    )
    blocks.to_csv(data_dir / "blocks.csv", index=False)

    machines = pd.DataFrame(
        [
            ("H1", "CH1", 24.0, 950.0, "feller_buncher"),
            ("H2", "CH2", 24.0, 1050.0, "feller_buncher"),
            ("H3", "CH3", 24.0, 1045.0, "grapple_skidder"),
            ("H4", "CH4", 24.0, 902.5, "roadside_processor"),
            ("H5", "CH5", 24.0, 997.5, "roadside_processor"),
            ("H6", "CH6", 24.0, 855.0, "loader"),
            ("H7", "CH7", 24.0, 945.0, "loader"),
        ],
        columns=["id", "crew", "daily_hours", "operating_cost", "role"],
    )
    machines.to_csv(data_dir / "machines.csv", index=False)

    pd.DataFrame({"id": ["L1"], "daily_capacity": [4]}).to_csv(
        data_dir / "landings.csv", index=False
    )
    calendar_rows = [
        {"machine_id": machine_id, "day": day, "available": 1}
        for machine_id in machines["id"]
        for day in range(1, DAYS + 1)
    ]
    pd.DataFrame(calendar_rows).to_csv(data_dir / "calendar.csv", index=False)
    rates = [
        {"machine_id": machine_id, "block_id": block_id, "rate": 500.0}
        for machine_id in machines["id"]
        for block_id in blocks["id"]
    ]
    pd.DataFrame(rates).to_csv(data_dir / "prod_rates.csv", index=False)


def _write_scenario(
    out: Path,
    bundle: FemicLidarBundle,
    vri: gpd.GeoDataFrame,
    support_rows: list[dict[str, object]],
) -> None:
    payload = {
        "name": "TFL 6 LidarBC Public Fixture",
        "num_days": DAYS,
        "start_date": "2026-01-01",
        "data": {
            "blocks": "data/blocks.csv",
            "machines": "data/machines.csv",
            "landings": "data/landings.csv",
            "calendar": "data/calendar.csv",
            "prod_rates": "data/prod_rates.csv",
        },
        "geo_block_path": "blocks.geojson",
        "geo_landing_path": "landings.geojson",
        "geo_crs": "EPSG:3005",
        "road_construction": [
            {
                "id": "R1",
                "machine_slug": "tr28",
                "road_length_m": 500.0,
                "notes": "Synthetic smoke-test road job; not a LiDAR-derived cost.",
            }
        ],
        "lidar_products": [
            {
                "bundle_id": bundle.bundle_id,
                "bundle_version": bundle.bundle_version,
                "manifest_sha256": bundle.manifest_sha256,
                "licence_id": str(bundle.source.get("licence_id", "OGL-BC")),
                "crs": str(bundle.source.get("native_crs", "EPSG:3005")),
                "aoi_bbox": [round(float(value), 3) for value in vri.total_bounds],
                "selection": bundle.selection,
                "products": [
                    {
                        "product": name,
                        "relative_path": product.relative_path,
                        "sha256": product.sha256,
                        "crs": product.crs,
                        "resolution_m": product.resolution_m,
                        "vertical_datum": product.vertical_datum,
                        "source_tile_ids": list(product.source_tile_ids),
                    }
                    for name, product in sorted(bundle.products.items())
                ],
            }
        ],
        "lidar_support": support_rows,
    }
    (out / "scenario.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _write_provenance(out: Path, bundle: FemicLidarBundle, vri_path: Path) -> None:
    payload = {
        "fixture": "TFL 6 LidarBC Public Fixture",
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.bundle_version,
        "manifest_sha256": bundle.manifest_sha256,
        "source_id": bundle.source.get("source_id"),
        "licence_id": bundle.source.get("licence_id"),
        "licence_url": bundle.source.get("licence_url"),
        "native_crs": bundle.source.get("native_crs"),
        "selection": bundle.selection,
        "products": {
            name: {
                "relative_path": product.relative_path,
                "sha256": product.sha256,
                "crs": product.crs,
                "resolution_m": product.resolution_m,
                "vertical_datum": product.vertical_datum,
                "lineage": list(product.lineage),
            }
            for name, product in sorted(bundle.products.items())
        },
        "vri_layer": vri_path.name,
        "synthetic_tables": {
            "work_per_ha_m3": WORK_PER_HA_M3,
            "productivity_rate_m3_per_day": 500.0,
            "stem_size_m3": 0.4,
            "volume_per_ha_m3": 300.0,
            "stem_density_per_ha": 750.0,
        },
        "notes": [
            "Only the LiDAR product values and clipped VRI geometry are source data.",
            "Machine, work, productivity, landing capacity, and road values are synthetic for a smoke solve.",
            "No field accuracy, calibrated cost, or production release is claimed.",
            "The fixture does not include the FEMIC bundle; pass a local bundle to the regeneration script.",
        ],
    }
    (out / "provenance.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_readme(out: Path) -> None:
    readme = """# TFL 6 LidarBC Public Fixture

Small public FHOPS scenario built from seven clipped VRI polygons (about 100 ha) in the TFL 6
pilot AOI and the FEMIC bundle `lidarbc-995fb1f771f4d7fe` / `2026.10.0-tfl6-pilot`.

The fixture exercises:

- block and landing slope/CHM support rows at native 1 m resolution;
- a road job with optional road geometry;
- terrain/canopy provenance, bundle/product checksums, and OGL-BC attribution;
- the P14.4 operability assessment (several blocks recommend cable/steep classes but the fixture
  intentionally provides only ground-based machines, so the fallbacks are visible);
- a short schedule smoke solve.

## Data

- `scenario.yaml` — FHOPS scenario, bundle pin, and `lidar_support` rows.
- `blocks.geojson`, `landings.geojson`, `roads.geojson` — EPSG:3005 support geometry.
- `data/` — block, machine, landing, calendar, and productivity tables.
- `provenance.json` — bundle/product checksums, licence, selection, and synthetic-table labels.

Only the LiDAR values and clipped VRI geometry are source data. Machine rates, work volumes
(20 m3/ha), productivity (500 m3 per machine-day), landing capacity, and the road job are synthetic
planning values for a smoke test; they are not a field inventory or a calibrated cost model.

## Regenerate

Install `fhops[lidar]`, then:

```bash
python scripts/build_p14_lidar_fixture.py \
  --bundle /path/to/lidarbc-995fb1f771f4d7fe \
  --vri /path/to/vri_aoi.geojson
```

The script validates the written scenario through the normal loader. The committed fixture does
not include the bundle or source rasters.

## Validation

```bash
fhops scenario lidar validate /path/to/bundle
fhops scenario operability assess examples/lidar_tfl6/scenario.yaml
fhops solve-heur examples/lidar_tfl6/scenario.yaml --iters 50 --seed 7
```

## Licence

LidarBC products: Open Government Licence - British Columbia (OGL-BC). The fixture preserves the
bundle licence and source metadata in `provenance.json`. VRI geometry is public BC data; retain
the source attribution when reusing it.
"""
    (out / "README.md").write_text(readme, encoding="utf-8")


def _block_values(
    rows: list[dict[str, object]],
    field: str,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in rows:
        if row["support_unit"] == "block" and field in row:
            values[str(row["support_id"])] = float(row[field])
    return values


if __name__ == "__main__":
    main()
