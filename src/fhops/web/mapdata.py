"""Map payload construction for the FHOPS web service.

The map is built from the scenario's block geometry plus the run's own assignment, flow, or
harvest artefacts. It never invents geometry for a yard, mill, depot, or road; those layers are
reported as unavailable until a geometry source is supplied.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from fhops.web.discovery import RunRecord

__all__ = [
    "LAYER_DEFINITIONS",
    "layer_registry",
    "load_block_geometry",
    "map_payload",
    "time_payload",
]

LAYER_DEFINITIONS = (
    ("blocks", "Blocks", "all"),
    ("treatments", "Treatments (current vs cumulative)", "operational"),
    ("machines", "Machines / crews", "operational"),
    ("tactical_units", "Tactical planning units", "tactical_operational"),
    ("roads", "Roads", "operational"),
    ("mills", "Mills", "hauling"),
    ("haul_routes", "Haul routes", "hauling"),
    ("facilities", "Facilities", "tactical_operational"),
)


def load_block_geometry(
    record: RunRecord,
    geometry_path: Path | None = None,
    geometry_crs: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Load block geometry indexed by ``block_id``.

    Parameters
    ----------
    record:
        Discovered run.
    geometry_path:
        Optional GeoJSON path from ``--geometry``.
    geometry_crs:
        Optional source CRS for ``--geometry`` or a run-local GeoJSON. When omitted, the scenario
        ``geo_crs`` or the GeoJSON top-level ``crs`` is used; the default is EPSG:4326. Coordinates
        are transformed to EPSG:4326 for MapLibre.

    Returns
    -------
    dict[str, dict[str, Any]]
        Mapping from block id to GeoJSON geometry. An empty mapping means no geometry is available.

    Raises
    ------
    ValueError
        When a candidate file exists but is not a FeatureCollection.
    """
    for candidate in _geometry_candidates(record, geometry_path):
        if candidate.exists():
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if payload.get("type") != "FeatureCollection":
                raise ValueError(f"{candidate} must be a GeoJSON FeatureCollection")
            source_crs = (
                geometry_crs
                or _scenario_crs(record)
                or (payload.get("crs") or {}).get("properties", {}).get("name")
                or "EPSG:4326"
            )
            transformer = _transformer(source_crs)
            geometry: dict[str, dict[str, Any]] = {}
            for feature in payload.get("features", []):
                props = feature.get("properties") or {}
                block_id = props.get("block_id") or feature.get("id")
                if block_id is None:
                    continue
                feature_geometry = feature.get("geometry")
                if feature_geometry is not None:
                    if transformer is not None:
                        feature_geometry = _transform_geometry(feature_geometry, transformer)
                    _validate_wgs84(feature_geometry, block_id, source_crs)
                geometry[str(block_id)] = {
                    "geometry": feature_geometry,
                    "properties": {key: value for key, value in props.items() if key != "block_id"},
                }
            return geometry
    return {}


def _geometry_candidates(
    record: RunRecord,
    geometry_path: Path | None,
) -> list[Path]:
    candidates: list[Path] = []
    if geometry_path is not None:
        candidates.append(geometry_path.expanduser().resolve())
    scenario_path = _scenario_path(record)
    if scenario_path is not None and scenario_path.exists():
        try:
            meta = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
            data = meta.get("data") or {}
            block_geo = meta.get("geo_block_path") or data.get("geo_block_path")
            if block_geo:
                candidates.append((scenario_path.parent / str(block_geo)).resolve())
        except (OSError, yaml.YAMLError):
            pass
    candidates.extend(sorted(record.path.glob("blocks.geojson")))
    candidates.extend(sorted(record.path.glob("block*.geojson")))
    return candidates


def _scenario_crs(record: RunRecord) -> str | None:
    scenario_path = _scenario_path(record)
    if scenario_path is None or not scenario_path.exists():
        return None
    try:
        meta = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    data = meta.get("data") or {}
    return meta.get("geo_crs") or data.get("geo_crs")


def _transformer(source_crs: str):
    """Return a pyproj transformer to EPSG:4326, or None for WGS84 input."""
    normalized = str(source_crs).strip().upper()
    if normalized in {"EPSG:4326", "CRS84", "WGS84", "OGC:CRS84"}:
        return None
    try:
        from pyproj import Transformer
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise ValueError(
            "The map geometry is not WGS84 and pyproj is not installed. "
            "Install the web extra: pip install 'fhops[web]'"
        ) from exc
    return Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)


def _transform_geometry(geometry: dict[str, Any], transformer: Any) -> dict[str, Any]:
    """Transform every coordinate in a GeoJSON geometry to WGS84."""
    transformed = dict(geometry)
    coordinates = geometry.get("coordinates")
    if coordinates is not None:
        transformed["coordinates"] = _transform_coordinates(coordinates, transformer)
    return transformed


def _validate_wgs84(geometry: dict[str, Any], block_id: str, source_crs: str) -> None:
    """Reject coordinates outside WGS84 lng/lat instead of handing them to MapLibre."""
    coordinates = geometry.get("coordinates")

    def check(value: Any) -> None:
        if not value:
            return
        if isinstance(value[0], int | float):
            x, y = float(value[0]), float(value[1])
            if (
                not math.isfinite(x)
                or not math.isfinite(y)
                or not (-180 <= x <= 180 and -90 <= y <= 90)
            ):
                raise ValueError(
                    f"Block {block_id} has coordinates outside WGS84 after CRS {source_crs}; "
                    "check --geometry-crs and the source geometry."
                )
            return
        for item in value:
            check(item)

    check(coordinates)


def _transform_coordinates(coordinates: Any, transformer: Any) -> Any:
    if not coordinates:
        return coordinates
    if isinstance(coordinates[0], int | float):
        x, y = transformer.transform(coordinates[0], coordinates[1])
        return [x, y, *coordinates[2:]]
    return [_transform_coordinates(item, transformer) for item in coordinates]


def _scenario_path(record: RunRecord) -> Path | None:
    value = (record.manifest or {}).get("scenario")
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    if path.exists():
        return path.resolve()
    return (record.path / path).resolve()


def layer_registry(
    record: RunRecord,
    geometry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return every known layer with availability and a legend/reason."""
    files = record.files
    has_geometry = bool(geometry)
    availability = {
        "blocks": (
            has_geometry,
            "block geometry is available" if has_geometry else "no block geometry",
        ),
        "treatments": (
            has_geometry and "assignments" in files,
            "operational assignments + block geometry"
            if has_geometry and "assignments" in files
            else "needs operational assignments and block geometry",
        ),
        "machines": (
            has_geometry and "assignments" in files,
            "operational assignments + block geometry"
            if has_geometry and "assignments" in files
            else "needs operational assignments and block geometry",
        ),
        "tactical_units": (
            has_geometry and "harvest_decisions" in files,
            "tactical harvest + block geometry"
            if has_geometry and "harvest_decisions" in files
            else "needs tactical harvest decisions and block geometry",
        ),
        "roads": (
            False,
            "no road geometry source; pass --geometry with road features in a future cut",
        ),
        "mills": (False, "no mill/sort-yard coordinates in the contract; map follow-up"),
        "haul_routes": (False, "needs sort-yard/depot coordinates; map follow-up"),
        "facilities": (False, "no facility coordinates in the tactical contract; map follow-up"),
    }
    layers = []
    for name, label, domain in LAYER_DEFINITIONS:
        available, reason = availability[name]
        layers.append(
            {
                "name": name,
                "label": label,
                "domain": domain,
                "available": available,
                "reason": reason,
                "legend": _legend(name),
            }
        )
    return layers


def _legend(name: str) -> str:
    return {
        "blocks": "block boundary; hover for attributes",
        "treatments": "current treatment vs cumulative through the selected day",
        "machines": "machine/crew position at the selected block",
        "tactical_units": "harvested area in the selected period",
        "roads": "source/access roads",
        "mills": "mills and sort yards",
        "haul_routes": "loaded/empty haul routes",
        "facilities": "tactical facilities",
    }.get(name, "")


def time_payload(record: RunRecord) -> dict[str, Any]:
    """Return the domain's time control values."""
    assignments = _read_frame(record, "assignments")
    if not assignments.empty and "day" in assignments.columns:
        days = sorted({int(value) for value in assignments["day"].dropna()})
        shifts = sorted(
            {str(value) for value in assignments.get("shift_id", pd.Series(dtype=str)).dropna()}
        )
        return {
            "domain": "operational",
            "unit": "day",
            "min": min(days),
            "max": max(days),
            "values": days,
            "shifts": shifts,
        }
    hauling_days: set[int] = set()
    for logical in ("haul_truckloads", "haul_flows"):
        frame = _read_frame(record, logical)
        if not frame.empty and "day" in frame.columns:
            hauling_days.update(int(value) for value in frame["day"].dropna())
    if hauling_days:
        days = sorted(hauling_days)
        return {
            "domain": "hauling",
            "unit": "day",
            "min": min(days),
            "max": max(days),
            "values": days,
            "shifts": [],
        }
    tactical_periods: set[str] = set()
    for logical in ("harvest_decisions", "production", "flows"):
        frame = _read_frame(record, logical)
        if not frame.empty and "period_id" in frame.columns:
            tactical_periods.update(str(value) for value in frame["period_id"].dropna())
    if tactical_periods:
        periods = sorted(tactical_periods)
        return {
            "domain": "tactical_operational",
            "unit": "period",
            "min": 0,
            "max": len(periods) - 1,
            "values": periods,
            "shifts": [],
        }
    return {"domain": record.domain, "unit": "day", "min": 1, "max": 1, "values": [1], "shifts": []}


def map_payload(
    record: RunRecord,
    geometry: dict[str, dict[str, Any]],
    *,
    day: int | None = None,
    period: str | None = None,
    shift: str | None = None,
    layers: list[str] | None = None,
) -> dict[str, Any]:
    """Build a GeoJSON FeatureCollection for the requested layers.

    Raises
    ------
    ValueError
        When a requested layer is unknown or unavailable.
    """
    registry = {layer["name"]: layer for layer in layer_registry(record, geometry)}
    requested = layers or [name for name, layer in registry.items() if layer["available"]]
    features: list[dict[str, Any]] = []
    for name in requested:
        layer = registry.get(name)
        if layer is None:
            raise ValueError(f"Unknown map layer: {name}")
        if not layer["available"]:
            raise ValueError(f"Map layer {name} is unavailable: {layer['reason']}")
        if name == "blocks":
            features.extend(_block_features(record, geometry, day=day, period=period, shift=shift))
        elif name == "treatments":
            features.extend(_treatment_features(record, geometry, day=day, shift=shift))
        elif name == "machines":
            features.extend(_machine_features(record, geometry, day=day, shift=shift))
        elif name == "tactical_units":
            features.extend(_tactical_features(record, geometry, period=period))
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "run_id": record.run_id,
            "domain": record.domain,
            "day": day,
            "period": period,
            "shift": shift,
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


def _block_features(
    record: RunRecord,
    geometry: dict[str, dict[str, Any]],
    *,
    day: int | None,
    period: str | None,
    shift: str | None,
) -> list[dict[str, Any]]:
    activities = _activity_by_block(record, day=day, period=period, shift=shift)
    features = []
    for block_id, item in sorted(geometry.items()):
        activity = activities.get(block_id, {})
        properties = {
            "layer": "blocks",
            "block_id": block_id,
            "domain": record.domain,
            "treated": activity.get("treated", False),
            "production": activity.get("production", 0.0),
            "machine_ids": activity.get("machine_ids", ""),
            "flow_m3": activity.get("flow_m3", 0.0),
            "harvested_area_ha": activity.get("harvested_area_ha", 0.0),
            **item.get("properties", {}),
        }
        features.append(
            {
                "type": "Feature",
                "id": f"blocks:{block_id}",
                "geometry": item["geometry"],
                "properties": properties,
            }
        )
    return features


def _activity_by_block(
    record: RunRecord,
    *,
    day: int | None,
    period: str | None,
    shift: str | None,
) -> dict[str, dict[str, Any]]:
    assignments = _filtered(record, "assignments", day=day, shift=shift)
    if not assignments.empty:
        result: dict[str, dict[str, Any]] = {}
        for block_id, group in assignments.groupby("block_id"):
            result[str(block_id)] = {
                "treated": True,
                "production": float(group.get("production", pd.Series(dtype=float)).sum()),
                "machine_ids": ",".join(
                    str(value) for value in group.get("machine_id", pd.Series(dtype=str)).unique()
                ),
            }
        return result
    flows = _filtered(record, "haul_flows", day=day)
    if not flows.empty and "block_id" in flows.columns:
        result = {}
        for block_id, group in flows.groupby("block_id"):
            volume = sum(
                float(group[column].sum())
                for column in ("sorted_m3", "unsorted_m3")
                if column in group.columns
            )
            result[str(block_id)] = {"treated": volume > 0, "flow_m3": volume}
        return result
    harvest = _filtered(record, "harvest_decisions", period=period)
    if not harvest.empty and "block_id" in harvest.columns:
        result = {}
        for block_id, group in harvest.groupby("block_id"):
            area = float(group.get("area_ha", pd.Series(dtype=float)).sum())
            result[str(block_id)] = {"treated": area > 0, "harvested_area_ha": area}
        return result
    return {}


def _treatment_features(
    record: RunRecord,
    geometry: dict[str, dict[str, Any]],
    *,
    day: int | None,
    shift: str | None,
) -> list[dict[str, Any]]:
    current = _filtered(record, "assignments", day=day, shift=shift)
    cumulative = _read_frame(record, "assignments")
    if day is not None and "day" in cumulative.columns:
        cumulative = cumulative[cumulative["day"].astype(int) <= int(day)]
    current_blocks = set(current.get("block_id", pd.Series(dtype=str)).astype(str))
    cumulative_blocks = set(cumulative.get("block_id", pd.Series(dtype=str)).astype(str))
    features = []
    for block_id, item in sorted(geometry.items()):
        features.append(
            {
                "type": "Feature",
                "id": f"treatments:{block_id}",
                "geometry": item["geometry"],
                "properties": {
                    "layer": "treatments",
                    "block_id": block_id,
                    "current": block_id in current_blocks,
                    "cumulative": block_id in cumulative_blocks,
                },
            }
        )
    return features


def _machine_features(
    record: RunRecord,
    geometry: dict[str, dict[str, Any]],
    *,
    day: int | None,
    shift: str | None,
) -> list[dict[str, Any]]:
    assignments = _filtered(record, "assignments", day=day, shift=shift)
    features = []
    for _, row in assignments.iterrows():
        block_id = str(row.get("block_id", ""))
        item = geometry.get(block_id)
        if item is None:
            continue
        point = _centroid(item["geometry"])
        if point is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"machines:{row.get('machine_id', '')}:{block_id}",
                "geometry": {"type": "Point", "coordinates": point},
                "properties": {
                    "layer": "machines",
                    "block_id": block_id,
                    "machine_id": str(row.get("machine_id", "")),
                    "shift_id": str(row.get("shift_id", "")),
                    "production": float(row.get("production", 0.0) or 0.0),
                },
            }
        )
    return features


def _tactical_features(
    record: RunRecord,
    geometry: dict[str, dict[str, Any]],
    *,
    period: str | None,
) -> list[dict[str, Any]]:
    harvest = _filtered(record, "harvest_decisions", period=period)
    features = []
    for _, row in harvest.iterrows():
        block_id = str(row.get("block_id", ""))
        item = geometry.get(block_id)
        if item is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"tactical_units:{block_id}:{row.get('period_id', '')}",
                "geometry": item["geometry"],
                "properties": {
                    "layer": "tactical_units",
                    "block_id": block_id,
                    "period_id": str(row.get("period_id", "")),
                    "system_id": str(row.get("system_id", "")),
                    "harvested_area_ha": float(row.get("area_ha", 0.0) or 0.0),
                },
            }
        )
    return features


def _centroid(geometry: dict[str, Any] | None) -> list[float] | None:
    if not geometry:
        return None
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Polygon" and coords:
        ring = coords[0]
        return _average(ring)
    if kind == "MultiPolygon" and coords:
        points = [point for polygon in coords for point in polygon[0]]
        return _average(points)
    if kind == "Point" and coords:
        return [float(coords[0]), float(coords[1])]
    return None


def _average(points: list[Any]) -> list[float] | None:
    if not points:
        return None
    cleaned = [point for point in points if len(point) >= 2]
    if not cleaned:
        return None
    return [
        sum(float(point[0]) for point in cleaned) / len(cleaned),
        sum(float(point[1]) for point in cleaned) / len(cleaned),
    ]


def _filtered(
    record: RunRecord,
    logical: str,
    *,
    day: int | None = None,
    period: str | None = None,
    shift: str | None = None,
) -> pd.DataFrame:
    frame = _read_frame(record, logical)
    if frame.empty:
        return frame
    if day is not None and "day" in frame.columns:
        frame = frame[frame["day"].astype(str) == str(day)]
    if period is not None and "period_id" in frame.columns:
        frame = frame[frame["period_id"].astype(str) == str(period)]
    if shift is not None and "shift_id" in frame.columns:
        frame = frame[frame["shift_id"].astype(str) == str(shift)]
    return frame


def _read_frame(record: RunRecord, logical: str) -> pd.DataFrame:
    filename = record.files.get(logical)
    if not filename:
        return pd.DataFrame()
    path = (record.path / filename).resolve()
    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        if path.suffix.lower() == ".parquet":
            return pd.read_parquet(path)
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return pd.DataFrame(payload)
            if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
                return pd.DataFrame(payload["rows"])
            return pd.DataFrame([payload])
    except (OSError, ValueError):
        return pd.DataFrame()
    return pd.DataFrame()
