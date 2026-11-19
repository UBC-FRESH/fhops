#!/usr/bin/env python3
"""Build a schematic spatial group layout for the Gavin MDWR screen.

The layout is a grid-cell prototype, not an operational prescription. It:

- samples the Gavin 5 m DEM for slope and aspect;
- classifies warm aspects as slope > 10% and aspect 135-270 degrees (LMH 59);
- builds contiguous 10 m cell groups capped at 0.4 ha warm / 0.7 ha other;
- assigns groups to the accepted temporal group-selection entries.

It does not model cohort growth, minimum group size, windthrow, or the matrix
volume response. The output is a spatial capacity/verification layer.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import Point, box
from shapely.ops import unary_union

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
WARM_CAP_HA = 0.4
OTHER_CAP_HA = 0.7
WARM_ASPECT = (135.0, 270.0)
WARM_SLOPE = 10.0
CELL_M = 10.0
CELL_HA = CELL_M * CELL_M / 10000.0
PASS_FRACTION = {"High": 0.33, "Moderate": 0.25, "Low": 0.20}


def terrain(dem_path: Path) -> tuple[np.ndarray, np.ndarray, rasterio.Affine]:
    """Return slope percent, aspect degrees and transform."""
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(float)
        if src.nodata is not None:
            dem[dem == src.nodata] = np.nan
        filled = np.where(np.isfinite(dem), dem, np.nanmean(dem))
        dz_dy, dz_dx = np.gradient(filled, abs(src.transform.e), abs(src.transform.a))
        dz_dy = -dz_dy
        slope = np.hypot(dz_dx, dz_dy) * 100.0
        aspect = (np.degrees(np.arctan2(-dz_dx, -dz_dy)) + 360.0) % 360.0
        slope[~np.isfinite(dem)] = np.nan
        aspect[~np.isfinite(dem)] = np.nan
        return slope, aspect, src.transform


def sample(slope: np.ndarray, aspect: np.ndarray, transform: rasterio.Affine, x: float, y: float) -> tuple[float, float] | None:
    """Nearest-cell sample of slope and aspect."""
    col = int((x - transform.c) / transform.a)
    row = int((transform.f - y) / abs(transform.e))
    if row < 0 or col < 0 or row >= slope.shape[0] or col >= slope.shape[1]:
        return None
    s, a = slope[row, col], aspect[row, col]
    if not np.isfinite(s) or not np.isfinite(a):
        return None
    return float(s), float(a)


def build_groups(geom, slope: np.ndarray, aspect: np.ndarray, transform: rasterio.Affine) -> list[dict[str, object]]:
    """Build disjoint cell groups inside one block."""
    minx, miny, maxx, maxy = geom.bounds
    i0 = int(np.floor((minx - transform.c) / CELL_M))
    i1 = int(np.ceil((maxx - transform.c) / CELL_M))
    j0 = int(np.floor((transform.f - maxy) / CELL_M))
    j1 = int(np.ceil((transform.f - miny) / CELL_M))
    cells: dict[str, set[tuple[int, int]]] = {"warm": set(), "other": set()}
    cell_box: dict[tuple[int, int], object] = {}
    for i in range(i0, i1):
        for j in range(j0, j1):
            x = transform.c + (i + 0.5) * CELL_M
            y = transform.f - (j + 0.5) * CELL_M
            if not geom.contains(Point(x, y)):
                continue
            values = sample(slope, aspect, transform, x, y)
            if values is None:
                continue
            s, a = values
            kind = "warm" if s > WARM_SLOPE and WARM_ASPECT[0] <= a <= WARM_ASPECT[1] else "other"
            cells[kind].add((i, j))
            cell_box[(i, j)] = box(
                transform.c + i * CELL_M,
                transform.f - (j + 1) * CELL_M,
                transform.c + (i + 1) * CELL_M,
                transform.f - j * CELL_M,
            )
    groups: list[dict[str, object]] = []
    for kind, members in cells.items():
        cap_cells = int(WARM_CAP_HA / CELL_HA) if kind == "warm" else int(OTHER_CAP_HA / CELL_HA)
        remaining = set(members)
        while remaining:
            seed = next(iter(remaining))
            queue = deque([seed])
            remaining.remove(seed)
            chosen: list[tuple[int, int]] = []
            while queue and len(chosen) < cap_cells:
                current = queue.popleft()
                chosen.append(current)
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    neighbour = (current[0] + di, current[1] + dj)
                    if neighbour in remaining and len(chosen) + len(queue) < cap_cells:
                        remaining.remove(neighbour)
                        queue.append(neighbour)
            polygon = unary_union([cell_box[c] for c in chosen]).intersection(geom)
            if polygon.is_empty:
                continue
            groups.append(
                {
                    "class": kind,
                    "area_ha": round(polygon.area / 10000.0, 6),
                    "cells": len(chosen),
                    "geometry": polygon,
                }
            )
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path, default=INSTANCE / "data" / "lidar" / "gavin_2024" / "dem_5m.tif")
    parser.add_argument("--spatial", type=Path, default=INSTANCE / "data" / "legacy_gavinlake" / "spatial" / "fragments.shp")
    parser.add_argument("--schedule", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-schedule-official-ba-temporal-s10.csv")
    parser.add_argument("--habitat", type=Path, default=INSTANCE / "planning" / "2026-11-18_gavin_mdwr_official_habitat.csv")
    parser.add_argument("--out-csv", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_layout.csv")
    parser.add_argument("--out-geojson", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_layout.geojson")
    parser.add_argument("--out-json", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_layout.json")
    args = parser.parse_args()

    slope, aspect, transform = terrain(args.dem)
    blocks = gpd.read_file(args.spatial)
    mdwr = blocks.loc[blocks["WORKING_CI"] == "MDWR"].to_crs("EPSG:6653")
    habitat = pd.read_csv(args.habitat)[["block_id", "model_class"]]
    schedule = pd.read_csv(args.schedule)
    schedule = schedule[schedule["block_id"].isin(set(mdwr["RES_KEY"]))].copy()
    schedule["pass_fraction"] = schedule["block_id"].map(
        habitat.set_index("block_id")["model_class"].map(PASS_FRACTION)
    )
    schedule = schedule.dropna(subset=["pass_fraction"])

    rows: list[dict[str, object]] = []
    features: list[dict[str, object]] = []
    for block in mdwr.itertuples(index=False):
        block_id = int(block.RES_KEY)
        entries = schedule.loc[schedule["block_id"] == block_id].sort_values("offset")
        if entries.empty:
            continue
        groups = build_groups(block.geometry, slope, aspect, transform)
        if not groups:
            rows.append({"block_id": block_id, "entries": len(entries), "groups": 0, "unassigned_groups": 0, "note": "no cell groups"})
            continue
        block_area = block.geometry.area / 10000.0
        remaining = list(groups)
        for entry in entries.itertuples(index=False):
            target = block_area * float(entry.pass_fraction)
            chosen: list[dict[str, object]] = []
            total = 0.0
            while remaining and total < target:
                group = remaining.pop(0)
                chosen.append(group)
                total += float(group["area_ha"])
            for index, group in enumerate(chosen):
                geom = group["geometry"]
                rows.append(
                    {
                        "block_id": block_id,
                        "entry_offset": int(entry.offset),
                        "group_index": index,
                        "class": group["class"],
                        "area_ha": group["area_ha"],
                        "cut_target_ha": round(target, 6),
                        "assigned_ha": round(total, 6),
                    }
                )
                features.append(
                    {
                        "block_id": block_id,
                        "entry_offset": int(entry.offset),
                        "group_index": index,
                        "class": group["class"],
                        "area_ha": group["area_ha"],
                        "geometry": geom,
                    }
                )
        rows.append(
            {
                "block_id": block_id,
                "entries": len(entries),
                "groups": len(groups),
                "unassigned_groups": len(remaining),
                "note": "",
            }
        )

    frame = pd.DataFrame(rows)
    frame.to_csv(args.out_csv, index=False)
    if features:
        grouped = gpd.GeoDataFrame(features, geometry="geometry", crs="EPSG:6653").to_crs("EPSG:3005")
        grouped.to_file(args.out_geojson, driver="GeoJSON")
    else:
        gpd.GeoDataFrame(columns=["block_id", "geometry"], geometry="geometry", crs="EPSG:3005").to_file(args.out_geojson, driver="GeoJSON")
    entry_rows = frame.loc[frame["entry_offset"].notna()] if "entry_offset" in frame else pd.DataFrame()
    summary = {
        "dem": str(args.dem),
        "schedule": str(args.schedule),
        "cell_m": CELL_M,
        "warm_group_cap_ha": WARM_CAP_HA,
        "other_group_cap_ha": OTHER_CAP_HA,
        "warm_aspect": "slope > 10% and aspect 135-270 degrees (LMH 59)",
        "entries": int(len(entry_rows)),
        "blocks_with_groups": int(entry_rows["block_id"].nunique()) if not entry_rows.empty else 0,
        "groups": int(len(entry_rows)),
        "max_group_area_ha": round(float(entry_rows["area_ha"].max()), 6) if not entry_rows.empty else 0.0,
        "assigned_area_ha": round(float(entry_rows["area_ha"].sum()), 3) if not entry_rows.empty else 0.0,
        "unassigned_groups": int(frame["unassigned_groups"].sum()) if "unassigned_groups" in frame else 0,
        "caveat": "Schematic 10 m cell layout; no cohort growth, minimum group size, windthrow or matrix response.",
    }
    args.out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
