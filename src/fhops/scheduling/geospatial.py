"""Geospatial helpers for mobilisation distance computation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry


@dataclass
class BlockGeometry:
    """Block identifier paired with geometry in a projected CRS."""

    block_id: str
    geometry: BaseGeometry


def load_block_geometries(geojson_path: Path | str) -> list[BlockGeometry]:
    """Load block geometries from a GeoJSON file (projected CRS expected)."""
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None or not gdf.crs.is_projected:
        raise ValueError("GeoJSON must use a projected CRS (e.g., UTM) for distance calculations.")
    if "block_id" not in gdf.columns:
        raise ValueError("GeoJSON must contain a 'block_id' column.")
    return [BlockGeometry(block_id=row.block_id, geometry=row.geometry) for row in gdf.itertuples()]


def compute_distance_matrix(geometries: Iterable[BlockGeometry]) -> dict[tuple[str, str], float]:
    """Compute Euclidean distance (metres) between block centroids."""
    geom_list = list(geometries)
    matrix: dict[tuple[str, str], float] = {}
    for i, src in enumerate(geom_list):
        for j, dst in enumerate(geom_list):
            if j < i:
                continue
            distance = src.geometry.centroid.distance(dst.geometry.centroid)
            matrix[(src.block_id, dst.block_id)] = float(distance)
            matrix[(dst.block_id, src.block_id)] = float(distance)
    return matrix


__all__ = ["BlockGeometry", "load_block_geometries", "compute_distance_matrix"]
