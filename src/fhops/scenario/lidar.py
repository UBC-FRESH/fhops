"""Read and validate FEMIC LidarBC product bundles.

FHOPS is a consumer of the FEMIC producer contract. This module pins a bundle,
verifies its manifest and checksums, and maps terrain/canopy rasters to
polygon support without re-running FEMIC discovery or materialization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

FEMIC_LIDAR_MANIFEST_SCHEMA = "femic.lidar.product.v1"
FEMIC_LIDAR_LAYOUT_VERSION = "femic.lidar.bundle.v1"
FEMIC_LIDAR_LICENCE_ID = "OGL-BC"
FEMIC_LIDAR_MANIFEST_NAME = "manifest.json"
FEMIC_LIDAR_SELECTION_PATH = "provenance/selection.json"


class FemicLidarError(RuntimeError):
    """Raised when a FEMIC LidarBC bundle cannot be consumed."""


@dataclass(frozen=True)
class FemicLidarProduct:
    """One pinned product record from a FEMIC bundle manifest."""

    product: str
    relative_path: str
    sha256: str
    size_bytes: int
    crs: str
    resolution_m: float | None
    vertical_datum: str
    licence_id: str
    source_tile_ids: tuple[str, ...]
    derived: bool
    lineage: tuple[str, ...]


@dataclass(frozen=True)
class FemicLidarBundle:
    """Pinned FEMIC LidarBC bundle metadata."""

    bundle_dir: Path
    manifest_path: Path
    bundle_id: str
    bundle_version: str
    source: dict[str, object]
    selection: dict[str, object]
    processing: dict[str, object]
    products: dict[str, FemicLidarProduct]
    manifest_sha256: str
    total_bytes: int


@dataclass(frozen=True)
class FemicLidarValidation:
    """Validation report for a FEMIC LidarBC bundle."""

    bundle_dir: Path
    is_valid: bool
    checked_utc: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    product_count: int
    total_bytes: int

    def to_dict(self) -> dict[str, object]:
        """Return the validation report as a JSON-serializable mapping."""

        return {
            "bundle_dir": str(self.bundle_dir),
            "is_valid": self.is_valid,
            "checked_utc": self.checked_utc,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "product_count": self.product_count,
            "total_bytes": self.total_bytes,
        }


@dataclass(frozen=True)
class LidarPolygonSummary:
    """One polygon-level support summary from a FEMIC product."""

    polygon_id: str
    product: str
    valid_pixels: int
    statistics: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        """Return the summary as a JSON-serializable mapping."""

        return {
            "polygon_id": self.polygon_id,
            "product": self.product,
            "valid_pixels": self.valid_pixels,
            "statistics": self.statistics,
        }


def load_femic_lidar_bundle(
    bundle_dir: Path,
    *,
    expected_bundle_id: str | None = None,
    expected_bundle_version: str | None = None,
    verify_checksums: bool = True,
) -> FemicLidarBundle:
    """Load and validate a FEMIC LidarBC bundle for consumption."""

    report, bundle = _validate(
        bundle_dir,
        verify_checksums=verify_checksums,
        expected_bundle_id=expected_bundle_id,
        expected_bundle_version=expected_bundle_version,
    )
    if bundle is None or not report.is_valid:
        raise FemicLidarError("Invalid FEMIC LidarBC bundle: " + "; ".join(report.errors))
    return bundle


def validate_femic_lidar_bundle(
    bundle_dir: Path,
    *,
    verify_checksums: bool = True,
) -> FemicLidarValidation:
    """Validate a FEMIC LidarBC bundle without raising on contract errors."""

    report, _ = _validate(
        bundle_dir,
        verify_checksums=verify_checksums,
        expected_bundle_id=None,
        expected_bundle_version=None,
    )
    return report


def bundle_pin(bundle: FemicLidarBundle) -> dict[str, object]:
    """Return the stable pin fields FHOPS records in its scenario provenance."""

    return {
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.bundle_version,
        "manifest_sha256": bundle.manifest_sha256,
        "products": {
            name: {"sha256": product.sha256, "relative_path": product.relative_path}
            for name, product in sorted(bundle.products.items())
        },
    }


def summarize_femic_lidar_for_polygons(
    bundle: FemicLidarBundle,
    polygons_path: Path,
    *,
    product: str = "slope",
    id_field: str | None = None,
    statistics: tuple[str, ...] = ("mean", "p95"),
) -> tuple[LidarPolygonSummary, ...]:
    """Summarize one bundle raster over polygon support.

    Geometry and raster CRS must already match. No reprojection or resampling
    is performed.
    """

    try:
        import geopandas as gpd
        import numpy as np
        import rasterio
        import rasterio.mask
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise FemicLidarError(
            "Polygon summaries require the `geo` optional dependencies plus rasterio."
        ) from exc
    if product not in bundle.products:
        raise FemicLidarError(f"Bundle does not contain product {product!r}.")
    record = bundle.products[product]
    raster_path = bundle.bundle_dir / record.relative_path
    try:
        frame = gpd.read_file(polygons_path)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise FemicLidarError(f"Unable to read polygon support: {exc}") from exc
    if frame.crs is None:
        raise FemicLidarError("Polygon support has no CRS.")
    if frame.crs.to_string() != record.crs:
        raise FemicLidarError(
            f"Polygon CRS {frame.crs.to_string()!r} does not match product CRS "
            f"{record.crs!r}; reprojection is not allowed."
        )
    if id_field is not None and id_field not in frame.columns:
        raise FemicLidarError(f"Polygon support is missing id field {id_field!r}.")
    summaries: list[LidarPolygonSummary] = []
    with rasterio.open(raster_path) as source:
        for index, row in frame.iterrows():
            geometry = row.geometry
            if geometry is None or geometry.is_empty:
                continue
            try:
                masked, _ = rasterio.mask.mask(
                    source,
                    [geometry],
                    crop=True,
                    filled=False,
                )
            except ValueError:
                continue
            values = np.asarray(masked[0].compressed(), dtype=float)
            if values.size == 0:
                continue
            stats: dict[str, float] = {}
            for stat in statistics:
                if stat == "mean":
                    stats[stat] = float(np.mean(values))
                elif stat == "p95":
                    stats[stat] = float(np.percentile(values, 95))
                elif stat == "min":
                    stats[stat] = float(np.min(values))
                elif stat == "max":
                    stats[stat] = float(np.max(values))
                else:
                    raise FemicLidarError(f"Unsupported summary statistic {stat!r}.")
            polygon_id = str(row[id_field]) if id_field is not None else str(index)
            summaries.append(
                LidarPolygonSummary(
                    polygon_id=polygon_id,
                    product=product,
                    valid_pixels=int(values.size),
                    statistics=stats,
                )
            )
    return tuple(summaries)


def _validate(
    bundle_dir: Path,
    *,
    verify_checksums: bool,
    expected_bundle_id: str | None,
    expected_bundle_version: str | None,
) -> tuple[FemicLidarValidation, FemicLidarBundle | None]:
    root = bundle_dir.expanduser().resolve()
    manifest_path = root / FEMIC_LIDAR_MANIFEST_NAME
    errors: list[str] = []
    warnings: list[str] = []
    bundle: FemicLidarBundle | None = None
    product_count = 0
    total_bytes = 0
    try:
        raw = manifest_path.read_bytes()
        manifest = _require_object(json.loads(raw), context="manifest")
        manifest_sha = hashlib.sha256(raw).hexdigest()
        if manifest.get("schema_version") != FEMIC_LIDAR_MANIFEST_SCHEMA:
            errors.append(f"Unsupported manifest schema {manifest.get('schema_version')!r}.")
        if manifest.get("layout_version") != FEMIC_LIDAR_LAYOUT_VERSION:
            errors.append(f"Unsupported layout version {manifest.get('layout_version')!r}.")
        bundle_id = _require_string(manifest, "bundle_id")
        bundle_version = _require_string(manifest, "bundle_version")
        if expected_bundle_id is not None and bundle_id != expected_bundle_id:
            errors.append("Bundle id does not match the pinned id.")
        if expected_bundle_version is not None and bundle_version != expected_bundle_version:
            errors.append("Bundle version does not match the pinned version.")
        source = _require_object(manifest.get("source"), context="source")
        selection = _require_object(manifest.get("selection"), context="selection")
        processing = _require_object(manifest.get("processing"), context="processing")
        if source.get("licence_id") != FEMIC_LIDAR_LICENCE_ID:
            errors.append("Bundle licence is not OGL-BC.")
        if not isinstance(source.get("native_crs"), str) or not source["native_crs"]:
            errors.append("Bundle source has no native CRS.")
        selection_tiles = selection.get("tile_ids")
        if not isinstance(selection_tiles, list):
            errors.append("Bundle selection has no tile_ids.")
            selection_tiles = []
        product_records = manifest.get("products")
        if not isinstance(product_records, list) or not product_records:
            errors.append("Bundle manifest has no products.")
            product_records = []
        products: dict[str, FemicLidarProduct] = {}
        for index, item in enumerate(product_records, start=1):
            record = _require_object(item, context=f"product {index}")
            product = _require_string(record, "product")
            relative_path = _require_string(record, "relative_path")
            sha256 = _require_string(record, "sha256")
            size_bytes = _require_int(record, "size_bytes")
            crs = _require_string(record, "crs")
            vertical_datum = _require_string(record, "vertical_datum")
            licence_id = _require_string(record, "licence_id")
            resolution = _optional_float(record.get("resolution_m"))
            source_tiles = record.get("source_tile_ids")
            if not isinstance(source_tiles, list):
                errors.append(f"Product {product!r} has no source_tile_ids.")
                source_tiles = []
            unknown_tiles = set(str(value) for value in source_tiles) - set(
                str(value) for value in selection_tiles
            )
            if unknown_tiles:
                errors.append(
                    f"Product {product!r} references tiles outside the selection: "
                    + ", ".join(sorted(unknown_tiles))
                )
            path = (root / relative_path).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                errors.append(f"Product {product!r} path escapes the bundle.")
                continue
            if not path.is_file():
                errors.append(f"Product {product!r} file is missing: {relative_path}")
            else:
                if path.stat().st_size != size_bytes:
                    errors.append(f"Product {product!r} size mismatch.")
                if verify_checksums and _sha256_file(path) != sha256:
                    errors.append(f"Product {product!r} checksum mismatch.")
            product_count += 1
            total_bytes += size_bytes
            products[product] = FemicLidarProduct(
                product=product,
                relative_path=relative_path,
                sha256=sha256,
                size_bytes=size_bytes,
                crs=crs,
                resolution_m=resolution,
                vertical_datum=vertical_datum,
                licence_id=licence_id,
                source_tile_ids=tuple(str(value) for value in source_tiles),
                derived=bool(record.get("derived", False)),
                lineage=_string_tuple(record.get("lineage", [])),
            )
        summary = _require_object(manifest.get("summary"), context="summary")
        if summary.get("product_count") != product_count:
            errors.append("Manifest product_count does not match products.")
        if summary.get("total_bytes") != total_bytes:
            errors.append("Manifest total_bytes does not match products.")
        if not errors:
            bundle = FemicLidarBundle(
                bundle_dir=root,
                manifest_path=manifest_path,
                bundle_id=bundle_id,
                bundle_version=bundle_version,
                source=source,
                selection=selection,
                processing=processing,
                products=products,
                manifest_sha256=manifest_sha,
                total_bytes=total_bytes,
            )
    except (OSError, json.JSONDecodeError, FemicLidarError) as exc:
        errors.append(str(exc))
    report = FemicLidarValidation(
        bundle_dir=root,
        is_valid=not errors,
        checked_utc=datetime.now(UTC).isoformat(),
        errors=tuple(errors),
        warnings=tuple(warnings),
        product_count=product_count,
        total_bytes=total_bytes,
    )
    return report, bundle


def _require_object(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FemicLidarError(f"{context} must be an object.")
    return {str(key): item for key, item in value.items()}


def _require_string(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FemicLidarError(f"Manifest field {key!r} must be a non-empty string.")
    return value.strip()


def _require_int(mapping: dict[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise FemicLidarError(f"Manifest field {key!r} must be an integer.")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FemicLidarError("Numeric manifest field must be a number.")
    return float(value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
