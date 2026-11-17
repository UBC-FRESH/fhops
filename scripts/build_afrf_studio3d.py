#!/usr/bin/env python3
"""Build a WS4 studio-3D scene for an AFRF block from public geometry.

This is a visual scene pack, not an inventory.  It can use LidarBC DEM/CHM
rasters when present, an SRTM terrain fallback, and block-level stem
density/height/species.  The browser synthesises the full stem field inside the
polygons; it does not claim measured tree positions.  CHM no-data gaps are
filled from block height for display only and are labelled as fallback.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.warp import reproject

SCENE_CRS = "EPSG:3005"
SOURCE_CRS = "EPSG:3005"


def _srtm_tile(lat: float, lon: float, directory: Path) -> np.ndarray:
    name = f"N{math.floor(lat):02d}W{abs(math.floor(lon)):03d}"
    path = directory / f"{name}.hgt"
    if not path.is_file():
        raise FileNotFoundError(f"missing SRTM tile {path}")
    array = np.frombuffer(path.read_bytes(), dtype=">i2").reshape((3601, 3601)).astype(np.float32)
    array[array <= -1000] = np.nan
    return array


def _sample_srtm(lat: np.ndarray, lon: np.ndarray, directory: Path) -> np.ndarray:
    result = np.full(lat.shape, np.nan, dtype=np.float64)
    for tile_lat in sorted({math.floor(float(v)) for v in lat.ravel()}):
        for tile_lon in sorted({math.floor(float(v)) for v in lon.ravel()}):
            name = f"N{tile_lat:02d}W{abs(tile_lon):03d}"
            path = directory / f"{name}.hgt"
            if not path.is_file():
                continue
            tile = (
                np.frombuffer(path.read_bytes(), dtype=">i2")
                .reshape((3601, 3601))
                .astype(np.float32)
            )
            tile[tile <= -1000] = np.nan
            mask = (
                (lat >= tile_lat)
                & (lat <= tile_lat + 1)
                & (lon >= tile_lon)
                & (lon <= tile_lon + 1)
            )
            if not mask.any():
                continue
            rows = np.clip((tile_lat + 1.0 - lat[mask]) * 3600.0, 0, 3600)
            cols = np.clip((lon[mask] - tile_lon) * 3600.0, 0, 3600)
            r0 = np.floor(rows).astype(int)
            c0 = np.floor(cols).astype(int)
            r1 = np.minimum(r0 + 1, 3600)
            c1 = np.minimum(c0 + 1, 3600)
            tr = rows - r0
            tc = cols - c0
            a = tile[r0, c0] * (1 - tr) + tile[r1, c0] * tr
            b = tile[r0, c1] * (1 - tr) + tile[r1, c1] * tr
            result[mask] = a * (1 - tc) + b * tc
    return result


def _polygon_ring(geometry: object) -> list[list[float]]:
    if geometry.geom_type == "Polygon":
        return [[round(float(x), 2), round(float(y), 2)] for x, y in geometry.exterior.coords]
    if geometry.geom_type == "MultiPolygon":
        return _polygon_ring(max(geometry.geoms, key=lambda g: g.area))
    return []


def _choose_default_block(block_rows: list[dict[str, object]]) -> dict[str, object] | None:
    """Pick a central production block, not the first row in the inventory."""
    if not block_rows:
        return None
    total_area = sum(float(row["area_ha"]) for row in block_rows) or 1.0
    center_x = sum(float(row["centroid"][0]) * float(row["area_ha"]) for row in block_rows)
    center_z = sum(float(row["centroid"][1]) * float(row["area_ha"]) for row in block_rows)
    center_x /= total_area
    center_z /= total_area
    candidates = [row for row in block_rows if float(row["area_ha"]) >= 1.0]
    if not candidates:
        candidates = block_rows
    return min(
        candidates,
        key=lambda row: (
            (float(row["centroid"][0]) - center_x) ** 2
            + (float(row["centroid"][1]) - center_z) ** 2
        ),
    )


def _rasterize_block_heights(
    block_rows: list[dict[str, object]], dx: float, ny: int, nx: int
) -> np.ndarray:
    """Burn block heights onto the scene grid for CHM no-data fallback."""
    shapes = [
        ({"type": "Polygon", "coordinates": [row["polygon"]]}, row["height_m"])
        for row in block_rows
        if isinstance(row.get("polygon"), list) and len(row["polygon"]) >= 4
    ]
    if not shapes:
        return np.zeros((ny, nx), dtype=np.float32)
    return rasterize(
        shapes,
        out_shape=(ny, nx),
        transform=Affine(dx, 0.0, 0.0, 0.0, dx, 0.0),
        fill=0.0,
        all_touched=True,
        dtype="float32",
    )


def build(args: argparse.Namespace) -> dict[str, object]:
    blocks = gpd.read_file(args.blocks).to_crs(SOURCE_CRS)
    metrics = pd.read_csv(args.metrics) if args.metrics else None
    if metrics is not None:
        metrics[args.id_field] = metrics[args.id_field].astype(str)
        metrics = metrics.set_index(args.id_field)
    left, bottom, right, top = blocks.total_bounds
    pad = 500.0
    left -= pad
    bottom -= pad
    right += pad
    top += pad
    dx = float(args.resolution)
    nx = max(2, round((right - left) / dx) + 1)
    ny = max(2, round((top - bottom) / dx) + 1)
    x0 = left
    y1 = top
    xx, zz = np.meshgrid(np.arange(nx) * dx + x0, np.arange(ny) * dx)
    yy = y1 - zz
    scene_left = float(left)
    scene_top = float(top)
    synthetic_canopy = True
    canopy_valid: np.ndarray | None = None
    canopy_fallback = False
    chm_valid_fraction: float | None = None
    to_wgs = Transformer.from_crs(SOURCE_CRS, "EPSG:4326", always_xy=True)
    lon, lat = to_wgs.transform(xx, yy)
    srtm = (
        _sample_srtm(lat, lon, Path(args.srtm_dir))
        if args.srtm_dir is not None
        else np.full((ny, nx), np.nan, dtype=np.float32)
    )
    if args.dem and args.chm:
        dst_transform = Affine(dx, 0.0, scene_left, 0.0, -dx, scene_top)

        def _read_raster(path: Path) -> np.ndarray:
            with rasterio.open(path) as source:
                dst = np.full((ny, nx), np.nan, dtype=np.float32)
                reproject(
                    source=source.read(1).astype(np.float32),
                    destination=dst,
                    src_transform=source.transform,
                    src_crs=source.crs,
                    src_nodata=source.nodata,
                    dst_transform=dst_transform,
                    dst_crs=SCENE_CRS,
                    dst_nodata=np.nan,
                    resampling=Resampling.bilinear,
                )
                return dst

        terrain_source = _read_raster(Path(args.dem))
        canopy_source = _read_raster(Path(args.chm))
        canopy_valid = np.isfinite(canopy_source)
        # LidarBC coverage is not wall-to-wall. Use the real 30 m SRTM surface
        # only where lidar DEM has no data; never fill CHM canopy here.
        terrain = np.where(np.isfinite(terrain_source), terrain_source, srtm)
        terrain = np.where(np.isfinite(terrain), terrain, np.nanmean(terrain))
        canopy = np.where(canopy_valid, canopy_source, 0.0)
        synthetic_canopy = False
        chm_valid_fraction = float(np.mean(canopy_valid))
    else:
        terrain = np.where(np.isfinite(srtm), srtm, np.nanmean(srtm))
        canopy = np.zeros_like(terrain)
    block_rows = []
    for _, row in blocks.iterrows():
        geom = row.geometry
        ring = _polygon_ring(geom)
        if len(ring) < 4:
            continue
        block_id = str(row[args.id_field])
        metric = (
            metrics.loc[block_id] if metrics is not None and block_id in metrics.index else None
        )
        area = float(geom.area) / 10000.0
        density = (
            float(metric[args.density_field])
            if metric is not None
            and args.density_field in metric
            and pd.notna(metric[args.density_field])
            else float(args.default_density)
        )
        height = (
            float(metric[args.height_field])
            if metric is not None
            and args.height_field in metric
            and pd.notna(metric[args.height_field])
            else float(args.default_height)
        )
        species = [["FD", 100.0]]
        if (
            metric is not None
            and args.species_field in metric
            and pd.notna(metric[args.species_field])
        ):
            try:
                parsed = json.loads(str(metric[args.species_field]))
                if isinstance(parsed, list) and parsed:
                    species = parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                species = [["FD", 100.0]]
        centroid = geom.centroid
        local_ring = [
            [round(float(x) - scene_left, 2), round(scene_top - float(y), 2)] for x, y in ring
        ]
        block_rows.append(
            {
                "id": block_id,
                "polygon": local_ring,
                "centroid": [
                    round(float(centroid.x) - scene_left, 2),
                    round(scene_top - float(centroid.y), 2),
                ],
                "area_ha": round(area, 3),
                "density": round(max(0.0, density), 1),
                "height_m": round(max(0.0, height), 2),
                "volume_per_ha_m3": 0.0,
                "au_id": str(metric[args.au_field])
                if metric is not None and args.au_field in metric
                else "",
                "species": species,
                "treatment": "",
                "treat_year": None,
                "removal": 0.0,
                "retention": 1.0,
            }
        )
    if canopy_valid is not None:
        block_heights = _rasterize_block_heights(block_rows, dx, ny, nx)
        fallback = (~canopy_valid) & (block_heights > 0.0)
        canopy[fallback] = block_heights[fallback]
        canopy_fallback = bool(fallback.any())
        if canopy_fallback:
            block_mask = block_heights > 0.0
            if block_mask.any():
                chm_valid_fraction = float(canopy_valid[block_mask].mean())
    default = _choose_default_block(block_rows)
    source_note = args.source_note
    if chm_valid_fraction is not None and canopy_fallback:
        source_note = (
            f"{source_note} LidarBC CHM is valid over {chm_valid_fraction:.0%} "
            "of the block area; CHM no-data gaps use block-height fallback, not measured canopy."
        )
    payload: dict[str, object] = {
        "schema": "ws4.studio3d.v1",
        "label": args.label,
        "subtitle": args.subtitle,
        "generated_utc": dt.datetime.now(dt.UTC).isoformat(),
        "crs": SCENE_CRS,
        "synthetic_canopy": synthetic_canopy,
        "canopy_fallback": canopy_fallback,
        "chm_valid_fraction": round(chm_valid_fraction, 4)
        if chm_valid_fraction is not None
        else None,
        "source_note": source_note,
        "bounds": {
            "min_x": 0.0,
            "max_x": round((nx - 1) * dx, 2),
            "min_z": 0.0,
            "max_z": round((ny - 1) * dx, 2),
        },
        "terrain": {
            "x0": round(x0, 2),
            "z0": 0.0,
            "dx": round(dx, 3),
            "dy": round(dx, 3),
            "nx": nx,
            "ny": ny,
            "values": np.round(terrain, 2).tolist(),
        },
        "canopy": {
            "x0": round(x0, 2),
            "z0": 0.0,
            "dx": round(dx, 3),
            "dy": round(dx, 3),
            "nx": nx,
            "ny": ny,
            "values": canopy.tolist(),
        },
        "canopy_valid": {
            "x0": round(x0, 2),
            "z0": 0.0,
            "dx": round(dx, 3),
            "dy": round(dx, 3),
            "nx": nx,
            "ny": ny,
            "values": canopy_valid.astype(np.uint8).tolist()
            if canopy_valid is not None
            else None,
        },
        "blocks": block_rows,
        "default_block": default["id"] if default else None,
        "default_center": default["centroid"] if default else [0.0, 0.0],
        "solar": {"tracks": []},
        "light": None,
        "method": {
            "terrain": "5 m LidarBC DEM bilinear sample; SRTM 1 arc-second in DEM no-data gaps"
            if not synthetic_canopy
            else "SRTM 1 arc-second bilinear sample",
            "canopy": "5 m LidarBC CHM bilinear sample; block-height fallback in CHM no-data gaps"
            if not synthetic_canopy
            else "synthetic block-height field; no CHM installed",
            "stem_placement": "deterministic browser stems at block density inside block polygon",
        },
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocks", required=True, type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--id-field", default="block_id")
    parser.add_argument("--density-field", default="density")
    parser.add_argument("--height-field", default="height_m")
    parser.add_argument("--species-field", default="species")
    parser.add_argument("--au-field", default="au_id")
    parser.add_argument("--default-density", type=float, default=700.0)
    parser.add_argument("--default-height", type=float, default=25.0)
    parser.add_argument("--resolution", type=float, default=15.0)
    parser.add_argument("--srtm-dir", type=Path)
    parser.add_argument("--dem", type=Path)
    parser.add_argument("--chm", type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--subtitle", default="")
    parser.add_argument(
        "--source-note", default="Public block geometry, SRTM terrain, synthetic stems."
    )
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    payload = build(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out} ({args.out.stat().st_size / 1_000_000:.1f} MB), blocks={len(payload['blocks'])}"
    )


if __name__ == "__main__":
    main()
