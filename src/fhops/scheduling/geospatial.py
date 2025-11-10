"""Geospatial helpers for mobilisation distance computation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

try:  # Optional dependency; we fall back to a lightweight parser if unavailable.
    import geopandas as gpd
except ModuleNotFoundError:  # pragma: no cover - exercised when geopandas not installed
    gpd = cast(Any, None)

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry


@dataclass
class BlockGeometry:
    """Block identifier paired with geometry in a projected CRS."""

    block_id: str
    geometry: BaseGeometry


def load_block_geometries(geojson_path: Path | str) -> list[BlockGeometry]:
    """Load block geometries from a GeoJSON file (projected CRS expected)."""
    if gpd is not None:
        gdf = gpd.read_file(geojson_path)
        if gdf.crs is None or not gdf.crs.is_projected:
            raise ValueError(
                "GeoJSON must use a projected CRS (e.g., UTM) for distance calculations."
            )
        if "block_id" not in gdf.columns:
            raise ValueError("GeoJSON must contain a 'block_id' column.")
        return [
            BlockGeometry(block_id=row.block_id, geometry=row.geometry) for row in gdf.itertuples()
        ]

    # Lightweight fallback when geopandas is not installed.
    path = Path(geojson_path)
    data = json.loads(path.read_text())
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("GeoJSON must contain a non-empty 'features' collection.")

    crs_props = (
        data.get("crs", {}).get("properties", {}) if isinstance(data.get("crs"), dict) else {}
    )
    crs_name = crs_props.get("name") if isinstance(crs_props, dict) else None
    if not crs_name:
        raise ValueError("GeoJSON must declare a projected CRS when geopandas is unavailable.")
    if any(token in crs_name for token in ("4326", "WGS84", "CRS84")):
        raise ValueError("GeoJSON must use a projected CRS (e.g., UTM) for distance calculations.")

    geometries: list[BlockGeometry] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {})
        block_id = properties.get("block_id") if isinstance(properties, dict) else None
        if block_id is None:
            raise ValueError("GeoJSON must contain a 'block_id' property for each feature.")
        geometry_payload = feature.get("geometry")
        if geometry_payload is None:
            raise ValueError("GeoJSON feature is missing geometry data.")
        geometry = shape(geometry_payload)
        geometries.append(BlockGeometry(block_id=str(block_id), geometry=geometry))

    if not geometries:
        raise ValueError("GeoJSON did not yield any valid geometries.")
    return geometries


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
