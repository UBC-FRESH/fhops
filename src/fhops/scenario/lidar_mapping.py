"""Map FEMIC LidarBC raster products onto FHOPS block/landing/road support.

This is a thin consumer layer: it calls the P14.1 polygon summarizer, keeps the native product
resolution/CRS, and writes explicit support/aggregation metadata into the scenario. It never
reprojects or resamples. Optional geospatial dependencies are required.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fhops.scenario.contract.lidar import LidarSupport
from fhops.scenario.io import load_scenario
from fhops.scenario.lidar import (
    FemicLidarBundle,
    FemicLidarError,
    LidarPolygonSummary,
    load_femic_lidar_bundle,
    summarize_femic_lidar_for_polygons,
)
from fhops.scenario.lidar_registration import (
    FemicLidarRegistrationError,
    _format_error,
    _replace_top_level_section,
    _validate_and_replace,
)

__all__ = ["FemicLidarMappingError", "MappingResult", "map_femic_lidar_to_scenario"]

#: Default FEMIC product name -> LidarSupport attribute.
DEFAULT_PRODUCT_FIELDS: dict[str, str] = {
    "slope": "slope_percent",
    "aspect": "aspect_degrees",
    "roughness": "roughness_m",
    "canopy_cover": "canopy_cover_percent",
    "canopy_cover_percent": "canopy_cover_percent",
    "canopy_height": "canopy_height_m",
    "canopy_height_m": "canopy_height_m",
    "chm": "canopy_height_m",
    "vertical_structure": "vertical_structure_index",
    "vertical_structure_index": "vertical_structure_index",
}
_SUPPORTED_FIELDS = {
    "slope_percent",
    "aspect_degrees",
    "roughness_m",
    "canopy_cover_percent",
    "canopy_height_m",
    "vertical_structure_index",
}
_AGGREGATION_NAMES = {
    "mean": "mean",
    "p95": "p95",
    "min": "minimum",
    "max": "maximum",
}


class FemicLidarMappingError(RuntimeError):
    """A FEMIC product could not be mapped to scenario support."""


@dataclass(frozen=True)
class MappingResult:
    """Outcome of mapping FEMIC products into a scenario."""

    scenario_path: Path
    bundle_id: str
    bundle_version: str
    rows: tuple[LidarSupport, ...]
    warnings: tuple[str, ...]
    written: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready summary."""
        return {
            "scenario_path": str(self.scenario_path),
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "rows": [row.model_dump(mode="json", exclude_none=True) for row in self.rows],
            "warnings": list(self.warnings),
            "written": self.written,
        }


def map_femic_lidar_to_scenario(
    scenario_path: str | Path,
    bundle_dir: str | Path,
    *,
    products: dict[str, str] | None = None,
    statistic: str = "mean",
    include_blocks: bool = True,
    include_landings: bool = True,
    roads_geojson: str | Path | None = None,
    road_id_field: str = "road_id",
    dry_run: bool = False,
) -> MappingResult:
    """Summarize FEMIC products over scenario support and write ``lidar_support`` rows."""
    scenario_path = Path(scenario_path).expanduser().resolve()
    bundle_dir = Path(bundle_dir).expanduser().resolve()
    if statistic not in _AGGREGATION_NAMES:
        raise FemicLidarMappingError(
            f"Unsupported statistic {statistic!r}; use one of {sorted(_AGGREGATION_NAMES)}."
        )
    try:
        scenario = load_scenario(scenario_path)
        bundle = load_femic_lidar_bundle(bundle_dir)
    except (FemicLidarError, ValueError, FileNotFoundError) as exc:
        raise FemicLidarMappingError(_format_error(exc)) from exc

    pin = _matching_pin(scenario, bundle)
    if pin is None:
        raise FemicLidarMappingError(
            f"Bundle {bundle.bundle_id}@{bundle.bundle_version} is not pinned in the scenario; "
            "run `fhops scenario lidar register` first."
        )
    field_products = _resolve_products(bundle, products)
    native_resolution = _native_resolution(bundle)
    warnings: list[str] = []
    rows: list[LidarSupport] = []

    if include_blocks:
        path, id_field = _geo_path(
            scenario.geo.block_geojson if scenario.geo else None, scenario_path, "block_id"
        )
        if path is None:
            warnings.append("Scenario has no block GeoJSON; no block support was mapped.")
        else:
            rows.extend(
                _map_support_unit(
                    bundle,
                    support_unit="block",
                    geometry_path=path,
                    id_field=id_field,
                    known_ids=set(scenario.block_ids()),
                    field_products=field_products,
                    statistic=statistic,
                    native_resolution=native_resolution,
                )
            )
    if include_landings:
        path, id_field = _geo_path(
            scenario.geo.landing_geojson if scenario.geo else None, scenario_path, "landing_id"
        )
        if path is None:
            warnings.append("Scenario has no landing GeoJSON; no landing support was mapped.")
        else:
            rows.extend(
                _map_support_unit(
                    bundle,
                    support_unit="landing",
                    geometry_path=path,
                    id_field=id_field,
                    known_ids=set(scenario.landing_ids()),
                    field_products=field_products,
                    statistic=statistic,
                    native_resolution=native_resolution,
                )
            )
    if roads_geojson is not None:
        path = Path(roads_geojson).expanduser()
        if not path.is_absolute():
            path = scenario_path.parent / path
        rows.extend(
            _map_support_unit(
                bundle,
                support_unit="road",
                geometry_path=path,
                id_field=road_id_field,
                known_ids={road.id for road in scenario.road_construction or []}
                if scenario.road_construction
                else None,
                field_products=field_products,
                statistic=statistic,
                native_resolution=native_resolution,
            )
        )

    if not rows:
        raise FemicLidarMappingError("No support rows were produced; check the scenario geo paths.")

    existing = list(scenario.lidar_support or [])
    produced_keys = {(row.support_unit, row.support_id, row.product) for row in rows}
    kept = [
        row
        for row in existing
        if (row.support_unit, row.support_id, row.product) not in produced_keys
    ]
    merged = [*kept, *rows]
    text = _replace_top_level_section(
        scenario_path.read_text(encoding="utf-8"),
        "lidar_support",
        [row.model_dump(mode="json", exclude_none=True) for row in merged],
    )
    if not dry_run:
        try:
            _validate_and_replace(scenario_path, text)
        except FemicLidarRegistrationError as exc:
            raise FemicLidarMappingError(str(exc)) from exc
    return MappingResult(
        scenario_path=scenario_path,
        bundle_id=bundle.bundle_id,
        bundle_version=bundle.bundle_version,
        rows=tuple(rows),
        warnings=tuple(warnings),
        written=not dry_run,
    )


def _resolve_products(bundle: FemicLidarBundle, products: dict[str, str] | None) -> dict[str, str]:
    if products is None:
        selected = {
            product: field
            for product, field in DEFAULT_PRODUCT_FIELDS.items()
            if product in bundle.products
        }
    else:
        selected = dict(products)
    if not selected:
        raise FemicLidarMappingError(
            "No known terrain/canopy products found; pass --product FIELD=PRODUCT explicitly."
        )
    seen_fields: set[str] = set()
    for product, field in selected.items():
        if product not in bundle.products:
            raise FemicLidarMappingError(f"Bundle has no product {product!r}.")
        if field not in _SUPPORTED_FIELDS:
            raise FemicLidarMappingError(
                f"Unsupported support field {field!r}; use one of {sorted(_SUPPORTED_FIELDS)}."
            )
        if field in seen_fields:
            raise FemicLidarMappingError(f"Multiple products map to support field {field!r}.")
        seen_fields.add(field)
    return selected


def _matching_pin(scenario, bundle: FemicLidarBundle):
    for pin in scenario.lidar_products or []:
        if (
            pin.bundle_id == bundle.bundle_id
            and pin.bundle_version == bundle.bundle_version
            and (pin.manifest_sha256 is None or pin.manifest_sha256 == bundle.manifest_sha256)
        ):
            return pin
    return None


def _native_resolution(bundle: FemicLidarBundle) -> float:
    resolutions = {
        product.resolution_m
        for product in bundle.products.values()
        if product.resolution_m is not None
    }
    if len(resolutions) != 1:
        raise FemicLidarMappingError(
            "Bundle products do not declare one native resolution; pass a product-specific "
            "bundle before mapping."
        )
    return next(iter(resolutions))


def _geo_path(value: str | None, scenario_path: Path, id_field: str) -> tuple[Path | None, str]:
    if not value:
        return None, id_field
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = scenario_path.parent / path
    return path, id_field


def _map_support_unit(
    bundle: FemicLidarBundle,
    *,
    support_unit: str,
    geometry_path: Path,
    id_field: str,
    known_ids: set[str] | None,
    field_products: dict[str, str],
    statistic: str,
    native_resolution: float,
) -> list[LidarSupport]:
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - optional dependency boundary
        raise FemicLidarMappingError(
            "Scenario mapping requires `fhops[lidar]` (geopandas, rasterio)."
        ) from exc
    if not geometry_path.is_file():
        raise FemicLidarMappingError(f"Support geometry not found: {geometry_path}")
    try:
        frame = gpd.read_file(geometry_path)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise FemicLidarMappingError(f"Cannot read support geometry: {exc}") from exc
    if frame.crs is None:
        raise FemicLidarMappingError(f"Support geometry has no CRS: {geometry_path}")
    if id_field not in frame.columns:
        raise FemicLidarMappingError(
            f"Support geometry {geometry_path} has no {id_field!r} column."
        )
    if known_ids is not None:
        frame = frame[frame[id_field].astype(str).isin(known_ids)]
    if frame.empty:
        raise FemicLidarMappingError(
            f"Support geometry {geometry_path} has no rows matching scenario {support_unit} ids."
        )
    projected = _is_projected(frame.crs)
    summaries: dict[str, dict[str, LidarPolygonSummary]] = {}
    for product in field_products:
        try:
            rows = summarize_femic_lidar_for_polygons(
                bundle,
                geometry_path,
                product=product,
                id_field=id_field,
                statistics=(statistic,),
            )
        except FemicLidarError as exc:
            raise FemicLidarMappingError(str(exc)) from exc
        summaries[product] = {row.polygon_id: row for row in rows}

    output: list[LidarSupport] = []
    for _, feature in frame.iterrows():
        support_id = str(feature[id_field])
        area = float(feature.geometry.area) if projected and feature.geometry is not None else None
        for product, field in field_products.items():
            summary = summaries[product].get(support_id)
            if summary is None:
                continue
            value = summary.statistics.get(statistic)
            if value is None:
                continue
            payload: dict[str, object] = {
                "support_unit": support_unit,
                "support_id": support_id,
                "bundle_id": bundle.bundle_id,
                "bundle_version": bundle.bundle_version,
                "product": product,
                "aggregation": _AGGREGATION_NAMES[statistic],
                "native_resolution_m": native_resolution,
                "valid_pixels": summary.valid_pixels,
                "provenance": (
                    f"{bundle.bundle_id}@{bundle.bundle_version} {product} "
                    f"{statistic} from {bundle.products[product].relative_path}"
                ),
            }
            if area is not None:
                payload["support_area_m2"] = area
            payload[field] = float(value)
            output.append(LidarSupport.model_validate(payload))
    return output


def _is_projected(crs) -> bool:
    try:
        from pyproj import CRS

        return bool(CRS.from_user_input(crs).is_projected)
    except Exception:  # noqa: BLE001 - optional CRS boundary
        return False
