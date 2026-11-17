#!/usr/bin/env python3
"""Build a WS4 studio-3D scene for an AFRF block from public geometry.

This is a visual scene pack, not an inventory.  It uses public block polygons,
an SRTM terrain surface, and block-level stem density/height.  The browser
synthesises the full stem field inside the polygons; it does not claim measured
tree positions.
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

        terrain = _read_raster(Path(args.dem))
        canopy = _read_raster(Path(args.chm))
        terrain = np.where(np.isfinite(terrain), terrain, np.nanmean(terrain))
        canopy = np.where(np.isfinite(canopy), canopy, 0.0)
        synthetic_canopy = False
    else:
        to_wgs = Transformer.from_crs(SOURCE_CRS, "EPSG:4326", always_xy=True)
        lon, lat = to_wgs.transform(xx, yy)
        terrain = _sample_srtm(lat, lon, Path(args.srtm_dir))
        terrain = np.where(np.isfinite(terrain), terrain, np.nanmean(terrain))
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
                "species": [["FD", 70.0], ["PL", 20.0], ["AT", 10.0]],
                "treatment": "",
                "treat_year": None,
                "removal": 0.0,
                "retention": 1.0,
            }
        )
    default = block_rows[0] if block_rows else None
    payload: dict[str, object] = {
        "schema": "ws4.studio3d.v1",
        "label": args.label,
        "subtitle": args.subtitle,
        "generated_utc": dt.datetime.now(dt.UTC).isoformat(),
        "crs": SCENE_CRS,
        "synthetic_canopy": synthetic_canopy,
        "source_note": args.source_note,
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
        "blocks": block_rows,
        "default_block": default["id"] if default else None,
        "default_center": default["centroid"] if default else [0.0, 0.0],
        "solar": {"tracks": []},
        "light": None,
        "method": {
            "terrain": "5 m DEM bilinear sample"
            if not synthetic_canopy
            else "SRTM 1 arc-second bilinear sample",
            "canopy": "5 m LidarBC CHM bilinear sample"
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
