"""Optional DEM and road routing for tree-scale system simulations.

This module is deliberately small: it samples an optional DEM along a route and
can route through a single connected road corridor. It is not a full forest-road
network solver. Rasterio and Shapely are imported lazily so the core tree
simulation does not require the optional geo/lidar dependencies.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["RouteProfile", "TerrainError", "TerrainRouter"]


class TerrainError(RuntimeError):
    """Raised when a DEM or road route cannot be evaluated."""


@dataclass(frozen=True)
class RouteProfile:
    """Terrain summary for one skidder route.

    Attributes
    ----------
    distance_m:
        Route length in metres.
    elevation_gain_m:
        Positive elevation gain in metres.
    elevation_loss_m:
        Negative elevation change, expressed as a positive number.
    max_grade_percent:
        Maximum absolute segment grade in percent.
    mean_grade_percent:
        Distance-weighted absolute grade in percent.
    speed_factor:
        Multiplier applied to flat-ground travel speed.
    samples:
        Number of DEM samples along the route.
    """

    distance_m: float
    elevation_gain_m: float
    elevation_loss_m: float
    max_grade_percent: float
    mean_grade_percent: float
    speed_factor: float
    samples: int


class TerrainRouter:
    """Route a skidder between two points using optional DEM and road inputs.

    Parameters
    ----------
    dem_path:
        Optional GeoTIFF DEM in the same CRS as the tree coordinates.
    road_path:
        Optional GeoJSON LineString or MultiLineString in the same CRS. The
        route follows the nearest road corridor between the landing and the
        bunch, then leaves the road for the final off-road segment.
    sample_step_m:
        DEM sampling interval along a route.
    max_grade_percent:
        Maximum allowed absolute route grade.
    grade_speed_factor:
        Fractional speed loss per percent of mean absolute grade.
    """

    def __init__(
        self,
        *,
        dem_path: str | Path | None = None,
        road_path: str | Path | None = None,
        sample_step_m: float = 10.0,
        max_grade_percent: float = 35.0,
        grade_speed_factor: float = 0.02,
    ) -> None:
        if not math.isfinite(sample_step_m) or sample_step_m <= 0:
            raise TerrainError("sample_step_m must be positive and finite.")
        if not math.isfinite(max_grade_percent) or max_grade_percent <= 0:
            raise TerrainError("max_grade_percent must be positive and finite.")
        if not math.isfinite(grade_speed_factor) or grade_speed_factor < 0:
            raise TerrainError("grade_speed_factor must be finite and non-negative.")
        self.dem_path = Path(dem_path).expanduser().resolve() if dem_path else None
        self.road_path = Path(road_path).expanduser().resolve() if road_path else None
        self.sample_step_m = sample_step_m
        self.max_grade_percent = max_grade_percent
        self.grade_speed_factor = grade_speed_factor
        self._dataset: Any | None = None
        self._road: Any | None = None
        if self.dem_path is not None:
            try:
                import rasterio
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise TerrainError(
                    "DEM routing requires the rasterio optional dependency."
                ) from exc
            try:
                self._dataset = rasterio.open(self.dem_path)
            except Exception as exc:  # noqa: BLE001 - preserve rasterio diagnostics
                raise TerrainError(f"Could not open DEM {self.dem_path}: {exc}") from exc
        if self.road_path is not None:
            self._road = self._load_road(self.road_path)

    @property
    def dem_crs(self) -> str | None:
        """Return the DEM CRS string, when a DEM is present."""
        if self._dataset is None:
            return None
        return str(self._dataset.crs) if self._dataset.crs else None

    def route(self, start: tuple[float, float], end: tuple[float, float]) -> RouteProfile:
        """Return the terrain profile for a start/end pair."""
        points = [start]
        if self._road is not None:
            points.extend(self._road_points(start, end))
        points.append(end)
        points = _deduplicate(points)
        points = _densify(points, self.sample_step_m)
        elevations = [self._elevation(x, y) for x, y in points]
        distance = 0.0
        gain = 0.0
        loss = 0.0
        weighted_grade = 0.0
        max_grade = 0.0
        for (x0, y0), (x1, y1), z0, z1 in zip(
            points[:-1], points[1:], elevations[:-1], elevations[1:], strict=True
        ):
            horizontal = math.hypot(x1 - x0, y1 - y0)
            if horizontal <= 0:
                continue
            dz = z1 - z0
            grade = abs(dz) / horizontal * 100.0
            distance += horizontal
            weighted_grade += grade * horizontal
            max_grade = max(max_grade, grade)
            if dz >= 0:
                gain += dz
            else:
                loss += -dz
        mean_grade = weighted_grade / distance if distance > 0 else 0.0
        if max_grade > self.max_grade_percent + 1e-9:
            raise TerrainError(
                f"Route maximum grade {max_grade:.1f}% exceeds {self.max_grade_percent:.1f}%."
            )
        speed_factor = max(0.4, min(1.2, 1.0 - self.grade_speed_factor * mean_grade))
        return RouteProfile(
            distance_m=distance,
            elevation_gain_m=gain,
            elevation_loss_m=loss,
            max_grade_percent=max_grade,
            mean_grade_percent=mean_grade,
            speed_factor=speed_factor,
            samples=len(elevations),
        )

    def provenance(self) -> dict[str, object]:
        """Return route configuration and source metadata."""
        return {
            "dem_path": str(self.dem_path) if self.dem_path else None,
            "dem_crs": self.dem_crs,
            "road_path": str(self.road_path) if self.road_path else None,
            "sample_step_m": self.sample_step_m,
            "max_grade_percent": self.max_grade_percent,
            "grade_speed_factor": self.grade_speed_factor,
            "road_model": "single connected road corridor"
            if self._road is not None
            else "direct line",
        }

    def close(self) -> None:
        """Close the DEM dataset when present."""
        if self._dataset is not None:
            self._dataset.close()
            self._dataset = None

    def _elevation(self, x: float, y: float) -> float:
        if self._dataset is None:
            return 0.0
        try:
            value = next(self._dataset.sample([(x, y)]))[0]
        except Exception as exc:  # noqa: BLE001 - preserve rasterio diagnostics
            raise TerrainError(f"Could not sample DEM at ({x:.1f}, {y:.1f}): {exc}") from exc
        if value is None or not math.isfinite(float(value)):
            raise TerrainError(f"DEM returned no elevation at ({x:.1f}, {y:.1f}).")
        return float(value)

    def _load_road(self, path: Path) -> Any:
        try:
            from shapely.geometry import shape
            from shapely.ops import linemerge, unary_union
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise TerrainError("Road routing requires the shapely optional dependency.") from exc
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - preserve file diagnostics
            raise TerrainError(f"Could not read road GeoJSON {path}: {exc}") from exc
        features = (
            payload.get("features") if payload.get("type") == "FeatureCollection" else [payload]
        )
        if not isinstance(features, list):
            raise TerrainError("Road GeoJSON must contain a feature collection.")
        geometries = []
        for feature in features:
            geometry = feature.get("geometry") if isinstance(feature, dict) else None
            if not isinstance(geometry, dict):
                continue
            geom = shape(geometry)
            if geom.geom_type in {"LineString", "MultiLineString"}:
                geometries.append(geom)
        if not geometries:
            raise TerrainError("Road GeoJSON contains no LineString geometry.")
        merged = unary_union(geometries)
        if merged.geom_type == "MultiLineString":
            merged = linemerge(merged)
        if merged.geom_type not in {"LineString", "MultiLineString"}:
            raise TerrainError("Road geometry must be a connected LineString.")
        return merged

    def _road_points(
        self, start: tuple[float, float], end: tuple[float, float]
    ) -> list[tuple[float, float]]:
        from shapely.geometry import Point
        from shapely.ops import nearest_points, substring

        road = self._road
        if road is None:
            return []
        start_point = nearest_points(road, Point(start))[0]
        end_point = nearest_points(road, Point(end))[0]
        if road.geom_type == "MultiLineString":
            # A disconnected corridor cannot be traversed as one route.
            raise TerrainError("Road GeoJSON must be a single connected corridor.")
        start_s = road.project(start_point)
        end_s = road.project(end_point)
        low, high = sorted((start_s, end_s))
        segment = substring(road, low, high)
        coords = list(segment.coords)
        if start_s > end_s:
            coords.reverse()
        return [(float(x), float(y)) for x, y in coords]


def _deduplicate(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for point in points:
        if not result or math.hypot(point[0] - result[-1][0], point[1] - result[-1][1]) > 1e-9:
            result.append((float(point[0]), float(point[1])))
    return result


def _densify(points: list[tuple[float, float]], step_m: float) -> list[tuple[float, float]]:
    result = [points[0]]
    for (x0, y0), (x1, y1) in zip(points[:-1], points[1:], strict=True):
        distance = math.hypot(x1 - x0, y1 - y0)
        count = max(1, int(math.ceil(distance / step_m)))
        for index in range(1, count + 1):
            fraction = index / count
            result.append((x0 + (x1 - x0) * fraction, y0 + (y1 - y0) * fraction))
    return result
