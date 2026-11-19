#!/usr/bin/env python3
"""Build a group-size capacity screen for the Gavin MDWR schedule.

The 2007 MWP #3 caps group openings at 0.4 ha on warm aspects and 0.7 ha on
other aspects. LMH 59 defines warm aspect sites as slopes > 10% with aspect
135–270 degrees.

This script derives slope/aspect from the Gavin 5 m DEM, splits each MDWR block
into warm/other area, and computes the minimum number of group openings needed
for each accepted group-selection entry. It is a capacity check, not a spatial
group layout: it does not draw the openings or model cohort growth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window
from rasterio.windows import transform as window_transform

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
WARM_CAP_HA = 0.4
OTHER_CAP_HA = 0.7
WARM_ASPECT = (135.0, 270.0)
WARM_SLOPE_PERCENT = 10.0
PASS_FRACTION = {"High": 0.33, "Moderate": 0.25, "Low": 0.20}


def raster_terrain(dem_path: Path) -> tuple[np.ndarray, np.ndarray, object]:
    """Return slope percent, aspect degrees and the source transform."""
    with rasterio.open(dem_path) as source:
        dem = source.read(1).astype(float)
        nodata = source.nodata
        transform = source.transform
        if nodata is not None:
            dem[dem == nodata] = np.nan
        filled = np.where(np.isfinite(dem), dem, np.nanmean(dem))
        dz_dy, dz_dx = np.gradient(filled, abs(transform.e), abs(transform.a))
        # Raster rows increase southward; convert the row gradient to northward.
        dz_dy = -dz_dy
        slope = np.hypot(dz_dx, dz_dy) * 100.0
        aspect = (np.degrees(np.arctan2(-dz_dx, -dz_dy)) + 360.0) % 360.0
        slope[~np.isfinite(dem)] = np.nan
        aspect[~np.isfinite(dem)] = np.nan
    return slope, aspect, transform


def block_areas(
    blocks: gpd.GeoDataFrame,
    slope: np.ndarray,
    aspect: np.ndarray,
    transform: object,
) -> pd.DataFrame:
    """Compute warm/other terrain areas for each block."""
    rows: list[dict[str, object]] = []
    for row in blocks.itertuples(index=False):
        geom = row.geometry
        minx, miny, maxx, maxy = geom.bounds
        col0 = max(0, int((minx - transform.c) / transform.a))
        col1 = min(slope.shape[1], int((maxx - transform.c) / transform.a) + 1)
        row0 = max(0, int((transform.f - maxy) / abs(transform.e)))
        row1 = min(slope.shape[0], int((transform.f - miny) / abs(transform.e)) + 1)
        if row1 <= row0 or col1 <= col0:
            continue
        window = Window(col0, row0, col1 - col0, row1 - row0)
        wtransform = window_transform(window, transform)
        mask = geometry_mask(
            [geom],
            out_shape=(row1 - row0, col1 - col0),
            transform=wtransform,
            invert=True,
        )
        valid = mask & np.isfinite(slope[row0:row1, col0:col1])
        cell_ha = abs(transform.a * transform.e) / 10000.0
        warm = valid & (slope[row0:row1, col0:col1] > WARM_SLOPE_PERCENT) & (
            (aspect[row0:row1, col0:col1] >= WARM_ASPECT[0])
            & (aspect[row0:row1, col0:col1] <= WARM_ASPECT[1])
        )
        rows.append(
            {
                "block_id": int(row.RES_KEY),
                "block_area_ha": round(float(geom.area) / 10000.0, 6),
                "warm_area_ha": round(float(warm.sum()) * cell_ha, 6),
                "other_area_ha": round(float((valid & ~warm).sum()) * cell_ha, 6),
                "valid_area_ha": round(float(valid.sum()) * cell_ha, 6),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dem",
        type=Path,
        default=INSTANCE / "data" / "lidar" / "gavin_2024" / "dem_5m.tif",
    )
    parser.add_argument(
        "--spatial",
        type=Path,
        default=INSTANCE / "data" / "legacy_gavinlake" / "spatial" / "fragments.shp",
    )
    parser.add_argument(
        "--schedule",
        type=Path,
        default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-schedule-official-ba-temporal-s10.csv",
    )
    parser.add_argument(
        "--habitat",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-18_gavin_mdwr_official_habitat.csv",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_capacity.csv",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_capacity.json",
    )
    args = parser.parse_args()

    slope, aspect, transform = raster_terrain(args.dem)
    blocks = gpd.read_file(args.spatial)
    mdwr = blocks.loc[blocks["WORKING_CI"] == "MDWR"].to_crs("EPSG:6653")
    areas = block_areas(mdwr, slope, aspect, transform)
    habitat = pd.read_csv(args.habitat)[["block_id", "model_class"]]
    areas = areas.merge(habitat, on="block_id", how="left")
    schedule = pd.read_csv(args.schedule)
    mdwr_ids = set(areas["block_id"])
    schedule = schedule.loc[schedule["block_id"].isin(mdwr_ids)].copy()
    schedule["pass_fraction"] = schedule["block_id"].map(
        areas.set_index("block_id")["model_class"].map(PASS_FRACTION)
    )
    schedule = schedule.dropna(subset=["pass_fraction"])
    schedule = schedule.merge(areas, on="block_id", how="left")
    schedule["cut_area_ha"] = schedule["block_area_ha"] * schedule["pass_fraction"]
    warm_fraction = schedule["warm_area_ha"] / (
        schedule["warm_area_ha"] + schedule["other_area_ha"]
    ).replace(0, np.nan)
    schedule["warm_fraction"] = warm_fraction.fillna(0.0)
    schedule["cut_warm_ha"] = schedule["cut_area_ha"] * schedule["warm_fraction"]
    schedule["cut_other_ha"] = schedule["cut_area_ha"] * (1.0 - schedule["warm_fraction"])
    schedule["min_groups_warm"] = np.ceil(schedule["cut_warm_ha"] / WARM_CAP_HA)
    schedule["min_groups_other"] = np.ceil(schedule["cut_other_ha"] / OTHER_CAP_HA)
    schedule["min_group_count"] = (
        schedule["min_groups_warm"] + schedule["min_groups_other"]
    ).astype(int)
    schedule["mean_group_area_ha"] = schedule["cut_area_ha"] / schedule["min_group_count"]
    schedule["warm_fraction"] = schedule["warm_fraction"].round(4)
    schedule = schedule[
        [
            "block_id",
            "offset",
            "model_class",
            "pass_fraction",
            "block_area_ha",
            "warm_area_ha",
            "other_area_ha",
            "cut_area_ha",
            "cut_warm_ha",
            "cut_other_ha",
            "min_group_count",
            "mean_group_area_ha",
        ]
    ].sort_values(["offset", "block_id"])
    schedule.to_csv(args.out_csv, index=False)

    summary = {
        "dem": str(args.dem),
        "spatial": str(args.spatial),
        "schedule": str(args.schedule),
        "warm_aspect": "slope > 10% and aspect 135-270 degrees (LMH 59)",
        "warm_group_cap_ha": WARM_CAP_HA,
        "other_group_cap_ha": OTHER_CAP_HA,
        "entries": int(len(schedule)),
        "blocks": int(schedule["block_id"].nunique()),
        "total_cut_area_ha": round(float(schedule["cut_area_ha"].sum()), 1),
        "mean_min_groups": round(float(schedule["min_group_count"].mean()), 2),
        "max_min_groups": int(schedule["min_group_count"].max()),
        "warm_area_ha": round(float(areas["warm_area_ha"].sum()), 1),
        "other_area_ha": round(float(areas["other_area_ha"].sum()), 1),
        "blocks_with_no_warm_area": int((areas["warm_area_ha"] == 0).sum()),
        "blocks_with_terrain_gap": int((areas["valid_area_ha"] < areas["block_area_ha"] * 0.5).sum()),
        "caveat": "Capacity check only: no spatial group polygons, no cohort growth, and no minimum group size.",
    }
    args.out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
