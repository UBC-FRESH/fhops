"""Geospatial helpers for mobilisation distance computation."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

try:  # Optional dependency; we fall back to a lightweight parser if unavailable.
    import geopandas as gpd
except ModuleNotFoundError:  # pragma: no cover - exercised when geopandas not installed
    gpd = cast(Any, None)

try:  # Optional dependency mirroring geopandas usage.
    from shapely.geometry import shape as _shape
except ModuleNotFoundError:  # pragma: no cover - exercised when shapely not installed
    shape: Any | None = None
else:
    shape = cast(Any, _shape)


@dataclass(frozen=True)
class BlockGeometry:
    """Block identifier paired with centroid coordinates (projected CRS)."""

    block_id: str
    centroid: tuple[float, float]


def load_block_geometries(geojson_path: Path | str) -> list[BlockGeometry]:
    """Load block geometries from a GeoJSON file (projected CRS expected)."""
    if gpd is not None and shape is not None:
        gdf = gpd.read_file(geojson_path)
        if gdf.crs is None or not gdf.crs.is_projected:
            raise ValueError(
                "GeoJSON must use a projected CRS (e.g., UTM) for distance calculations."
            )
        if "block_id" not in gdf.columns:
            raise ValueError("GeoJSON must contain a 'block_id' column.")
        return [
            BlockGeometry(
                block_id=str(row.block_id),
                centroid=(float(row.geometry.centroid.x), float(row.geometry.centroid.y)),
            )
            for row in gdf.itertuples()
        ]

    # Lightweight fallback when geopandas/shapely are not installed.
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
        raise ValueError(
            "GeoJSON must declare a projected CRS when geopandas/shapely are unavailable."
        )
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
        centroid = _compute_centroid_fallback(geometry_payload)
        geometries.append(BlockGeometry(block_id=str(block_id), centroid=centroid))

    if not geometries:
        raise ValueError("GeoJSON did not yield any valid geometries.")
    return geometries


def compute_distance_matrix(geometries: Iterable[BlockGeometry]) -> dict[tuple[str, str], float]:
    """Compute Euclidean distance (metres) between block centroids."""
    geom_list = list(geometries)
    matrix: dict[tuple[str, str], float] = {}
    for i, src in enumerate(geom_list):
        sx, sy = src.centroid
        for j, dst in enumerate(geom_list):
            if j < i:
                continue
            dx, dy = dst.centroid
            distance = math.hypot(sx - dx, sy - dy)
            matrix[(src.block_id, dst.block_id)] = distance
            matrix[(dst.block_id, src.block_id)] = distance
    return matrix


def _compute_centroid_fallback(geometry: dict[str, Any]) -> tuple[float, float]:
    """Compute centroid without shapely (supports polygons, multipolygons, points)."""
    geom_type = geometry.get("type")
    if geom_type == "Polygon":
        return _polygon_centroid(geometry.get("coordinates"))
    if geom_type == "MultiPolygon":
        multipoly = geometry.get("coordinates")
        if not isinstance(multipoly, list) or not multipoly:
            raise ValueError("MultiPolygon geometry missing coordinates.")
        total_area = 0.0
        cx = 0.0
        cy = 0.0
        for polygon in multipoly:
            centroid, area = _polygon_centroid_with_area(polygon)
            if area <= 0:
                continue
            total_area += area
            cx += centroid[0] * area
            cy += centroid[1] * area
        if total_area == 0:
            return _polygon_centroid(multipoly[0])
        return (cx / total_area, cy / total_area)
    if geom_type == "Point":
        coords = geometry.get("coordinates")
        if (
            isinstance(coords, list | tuple)
            and len(coords) >= 2
            and all(isinstance(v, int | float) for v in coords[:2])
        ):
            return (float(coords[0]), float(coords[1]))
        raise ValueError("Point geometry must contain numeric coordinates.")
    raise ValueError(f"Unsupported geometry type '{geom_type}'.")


def _polygon_centroid(coordinates: Any) -> tuple[float, float]:
    centroid, _ = _polygon_centroid_with_area(coordinates)
    return centroid


def _polygon_centroid_with_area(coordinates: Any) -> tuple[tuple[float, float], float]:
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("Polygon geometry must contain coordinate rings.")
    outer_ring = coordinates[0]
    if not isinstance(outer_ring, list) or len(outer_ring) < 3:
        raise ValueError("Polygon outer ring must contain at least three vertices.")
    ring = list(outer_ring)
    if ring[0] != ring[-1]:
        ring.append(ring[0])

    area = 0.0
    cx = 0.0
    cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    area *= 0.5
    if abs(area) < 1e-9:
        xs = [vertex[0] for vertex in ring[:-1]]
        ys = [vertex[1] for vertex in ring[:-1]]
        return ((sum(xs) / len(xs), sum(ys) / len(ys)), 0.0)

    cx /= 6.0 * area
    cy /= 6.0 * area
    return ((cx, cy), abs(area))


__all__ = ["BlockGeometry", "load_block_geometries", "compute_distance_matrix"]
