"""Register FEMIC LidarBC bundles against a FHOPS scenario AOI.

Registration verifies the bundle with the P14.1 consumer, checks CRS compatibility with the
scenario's geo metadata, records a stable pin (bundle id/version, manifest checksum, product
checksums, selection), and writes the pin to the scenario only after the loader accepts the result.
No source tiles are discovered or downloaded here.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from fhops.scenario.contract.lidar import LidarProductPin, LidarProductRef
from fhops.scenario.contract.models import Scenario
from fhops.scenario.io import load_scenario
from fhops.scenario.lidar import FemicLidarBundle, FemicLidarError, load_femic_lidar_bundle

__all__ = ["FemicLidarRegistrationError", "RegistrationResult", "register_femic_lidar_bundle"]


class FemicLidarRegistrationError(RuntimeError):
    """A bundle cannot be bound to the scenario AOI or written safely."""


@dataclass(frozen=True)
class RegistrationResult:
    """Outcome of a bundle registration."""

    scenario_path: Path
    bundle_id: str
    bundle_version: str
    manifest_sha256: str
    manifest_path: str
    aoi_bbox: tuple[float, float, float, float] | None
    warnings: tuple[str, ...]
    written: bool
    pin: LidarProductRef

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready summary."""
        return {
            "scenario_path": str(self.scenario_path),
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "manifest_sha256": self.manifest_sha256,
            "manifest_path": self.manifest_path,
            "aoi_bbox": list(self.aoi_bbox) if self.aoi_bbox else None,
            "warnings": list(self.warnings),
            "written": self.written,
            "pin": self.pin.model_dump(mode="json", exclude_none=True),
        }


def register_femic_lidar_bundle(
    scenario_path: str | Path,
    bundle_dir: str | Path,
    *,
    expected_bundle_id: str | None = None,
    expected_bundle_version: str | None = None,
    verify_checksums: bool = True,
    dry_run: bool = False,
) -> RegistrationResult:
    """Validate a FEMIC bundle and pin it in a scenario's ``lidar_products`` section."""
    scenario_path = Path(scenario_path).expanduser().resolve()
    bundle_dir = Path(bundle_dir).expanduser().resolve()
    try:
        scenario = load_scenario(scenario_path)
        bundle = load_femic_lidar_bundle(
            bundle_dir,
            expected_bundle_id=expected_bundle_id,
            expected_bundle_version=expected_bundle_version,
            verify_checksums=verify_checksums,
        )
    except (FemicLidarError, ValueError, FileNotFoundError) as exc:
        raise FemicLidarRegistrationError(_format_error(exc)) from exc

    warnings: list[str] = []
    bundle_crs = _bundle_crs(bundle)
    scenario_crs = scenario.geo.crs if scenario.geo is not None else None
    if scenario_crs:
        if scenario_crs.strip().upper() != bundle_crs.strip().upper():
            raise FemicLidarRegistrationError(
                f"Scenario CRS {scenario_crs!r} does not match FEMIC bundle CRS {bundle_crs!r}; "
                "reprojection is not performed during registration."
            )
    else:
        warnings.append(
            "Scenario has no geo.crs; the bundle CRS is recorded but not cross-checked."
        )
    aoi_bbox = _scenario_aoi_bbox(scenario, scenario_path.parent)
    if aoi_bbox is None:
        warnings.append("Scenario has no block GeoJSON; no AOI bbox was recorded.")

    manifest_path = _relative_manifest_path(scenario_path, bundle.manifest_path)
    product_pins = _product_pins(bundle)
    pin = LidarProductRef(
        bundle_id=bundle.bundle_id,
        bundle_version=bundle.bundle_version,
        manifest_sha256=bundle.manifest_sha256,
        licence_id=str(bundle.source.get("licence_id", "")),
        manifest_path=manifest_path,
        crs=bundle_crs,
        aoi_bbox=aoi_bbox,
        selection=bundle.selection,
        products=product_pins,
    )
    existing = list(scenario.lidar_products or [])
    for current in existing:
        if (current.bundle_id, current.bundle_version) == (pin.bundle_id, pin.bundle_version):
            if current.manifest_sha256 and current.manifest_sha256 != pin.manifest_sha256:
                raise FemicLidarRegistrationError(
                    f"Bundle {pin.bundle_id}@{pin.bundle_version} is already pinned with a "
                    "different manifest checksum."
                )
            existing.remove(current)
            break
    pins = [*existing, pin]

    text = _replace_top_level_section(
        scenario_path.read_text(encoding="utf-8"),
        "lidar_products",
        [item.model_dump(mode="json", exclude_none=True) for item in pins],
    )
    if not dry_run:
        _validate_and_replace(scenario_path, text)
    return RegistrationResult(
        scenario_path=scenario_path,
        bundle_id=bundle.bundle_id,
        bundle_version=bundle.bundle_version,
        manifest_sha256=bundle.manifest_sha256,
        manifest_path=manifest_path,
        aoi_bbox=aoi_bbox,
        warnings=tuple(warnings),
        written=not dry_run,
        pin=pin,
    )


def _bundle_crs(bundle: FemicLidarBundle) -> str:
    crs_values = {product.crs.strip().upper() for product in bundle.products.values()}
    if len(crs_values) != 1:
        raise FemicLidarRegistrationError(
            "A bundle with mixed product CRS values cannot be bound to one scenario AOI: "
            + ", ".join(sorted(crs_values))
        )
    return next(iter(crs_values))


def _product_pins(bundle: FemicLidarBundle) -> list[LidarProductPin]:
    return [
        LidarProductPin(
            product=name,
            relative_path=product.relative_path,
            sha256=product.sha256,
            crs=product.crs,
            resolution_m=product.resolution_m,
            vertical_datum=product.vertical_datum,
            source_tile_ids=list(product.source_tile_ids),
        )
        for name, product in sorted(bundle.products.items())
    ]


def _relative_manifest_path(scenario_path: Path, manifest_path: Path) -> str:
    try:
        return str(manifest_path.relative_to(scenario_path.parent))
    except ValueError:
        return str(manifest_path)


def _scenario_aoi_bbox(
    scenario: Scenario, scenario_dir: Path
) -> tuple[float, float, float, float] | None:
    if scenario.geo is None or not scenario.geo.block_geojson:
        return None
    block_path = Path(scenario.geo.block_geojson)
    if not block_path.is_absolute():
        block_path = scenario_dir / block_path
    try:
        payload = json.loads(block_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FemicLidarRegistrationError(f"Cannot read scenario block GeoJSON: {exc}") from exc
    coordinates: list[tuple[float, float]] = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if isinstance(geometry, dict):
            _collect_coordinates(geometry.get("coordinates"), coordinates)
    if not coordinates:
        return None
    xs = [point[0] for point in coordinates]
    ys = [point[1] for point in coordinates]
    return (min(xs), min(ys), max(xs), max(ys))


def _collect_coordinates(value: object, output: list[tuple[float, float]]) -> None:
    if isinstance(value, (list, tuple)):
        if (
            len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            output.append((float(value[0]), float(value[1])))
            return
        for item in value:
            _collect_coordinates(item, output)


def _replace_top_level_section(text: str, key: str, value: Any) -> str:
    lines = text.splitlines()
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    start = next((index for index, line in enumerate(lines) if pattern.match(line)), None)
    rendered = (
        yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True, default_flow_style=False)
        .rstrip("\n")
        .splitlines()
    )
    if start is None:
        prefix = text.rstrip("\n")
        return (prefix + "\n\n" if prefix else "") + "\n".join(rendered) + "\n"
    end = start + 1
    while end < len(lines):
        line = lines[end]
        stripped = line.strip()
        if not stripped:
            end += 1
            continue
        # ``yaml.safe_dump`` emits top-level list items without indentation, so they belong to
        # the section until the next top-level key.
        if line[0] in " \t" or stripped.startswith("-"):
            end += 1
            continue
        break
    return "\n".join(lines[:start] + rendered + [""] + lines[end:]).rstrip("\n") + "\n"


def _validate_and_replace(path: Path, text: str) -> None:
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".fhops-lidar-",
        suffix=path.suffix,
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        load_scenario(temp_path)
        os.chmod(temp_path, path.stat().st_mode)
        os.replace(temp_path, path)
    except Exception as exc:  # noqa: BLE001 - the loader message is the user-facing result
        temp_path.unlink(missing_ok=True)
        raise FemicLidarRegistrationError(_format_error(exc)) from exc


def _format_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for error in exc.errors():
            location = ".".join(str(item) for item in error.get("loc", ()))
            parts.append(f"{location}: {error.get('msg', 'invalid value')}")
        return "; ".join(parts) or str(exc)
    return f"{type(exc).__name__}: {exc}"
