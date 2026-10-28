"""Explicit road and culvert asset evidence for flood-aware constraints.

Assets are an external inventory. FHOPS maps them to scenario road jobs and
watersheds through explicit ids; it never infers them from geometry.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fhops.scenario.hydrology_mapping import (
    FemicHydrologyMappingError,
    load_hydrology_mapping,
)
from fhops.scenario.io import load_scenario

HYDROLOGY_ASSETS_SCHEMA = "fhops.hydrology.assets.v1"
HYDROLOGY_ASSET_TYPES: tuple[str, ...] = ("road", "culvert")
HYDROLOGY_ASSET_VULNERABILITY: tuple[str, ...] = (
    "low",
    "moderate",
    "high",
    "unknown",
)
HYDROLOGY_ASSET_REVIEW_STATUSES: tuple[str, ...] = (
    "not_reviewed",
    "review_pending",
    "reviewed",
)

__all__ = [
    "FemicHydrologyAssetError",
    "HYDROLOGY_ASSET_TYPES",
    "HYDROLOGY_ASSET_VULNERABILITY",
    "HYDROLOGY_ASSETS_SCHEMA",
    "HydrologyAsset",
    "HydrologyAssetMapping",
    "HydrologyAssetValidation",
    "load_hydrology_assets",
    "map_hydrology_assets",
    "validate_hydrology_assets",
]


class FemicHydrologyAssetError(RuntimeError):
    """Raised when a road/culvert asset table cannot be consumed or mapped."""


@dataclass(frozen=True)
class HydrologyAsset:
    """One explicit road or culvert asset.

    Attributes
    ----------
    asset_id : str
        Stable asset identifier.
    asset_type : str
        ``road`` or ``culvert``.
    watershed_id : str
        FEMIC watershed identifier.
    road_job_id : str | None
        Scenario road-construction id for a road asset.
    vulnerability_class : str
        ``low``, ``moderate``, ``high``, or ``unknown``.
    notes : str
        Human notes.
    """

    asset_id: str
    asset_type: str
    watershed_id: str
    road_job_id: str | None
    vulnerability_class: str
    notes: str

    def to_dict(self) -> dict[str, object]:
        """Return the asset as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Asset fields.
        """
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "watershed_id": self.watershed_id,
            "road_job_id": self.road_job_id,
            "vulnerability_class": self.vulnerability_class,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HydrologyAssetMapping:
    """Assets resolved against a scenario and hydrology mapping.

    Attributes
    ----------
    inventory_id : str
        Asset inventory identifier.
    generated_utc : str
        Inventory timestamp.
    source_id : str
        Asset source.
    review_status : str
        Review state.
    reviewer_id : str | None
        Reviewer when reviewed.
    assets : tuple[HydrologyAsset, ...]
        Validated assets.
    road_job_ids : tuple[str, ...]
        Scenario road-job ids referenced by road assets.
    watershed_ids : tuple[str, ...]
        Watersheds referenced by assets.
    warnings : tuple[str, ...]
        Non-fatal observations.
    caveats : tuple[str, ...]
        Evidence caveats.
    assets_sha256 : str
        Asset file digest.
    """

    inventory_id: str
    generated_utc: str
    source_id: str
    review_status: str
    reviewer_id: str | None
    assets: tuple[HydrologyAsset, ...]
    road_job_ids: tuple[str, ...]
    watershed_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]
    assets_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Return the mapped inventory as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Inventory, assets, coverage, warnings, and caveats.
        """
        return {
            "schema_version": HYDROLOGY_ASSETS_SCHEMA,
            "inventory_id": self.inventory_id,
            "generated_utc": self.generated_utc,
            "source_id": self.source_id,
            "review_status": self.review_status,
            "reviewer_id": self.reviewer_id,
            "assets": [asset.to_dict() for asset in self.assets],
            "asset_count": len(self.assets),
            "road_job_ids": list(self.road_job_ids),
            "watershed_ids": list(self.watershed_ids),
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
            "assets_sha256": self.assets_sha256,
        }


@dataclass(frozen=True)
class HydrologyAssetValidation:
    """Validation report for an asset table.

    Attributes
    ----------
    path : Path
        Asset JSON path.
    is_valid : bool
        Whether every required check passed.
    checked_utc : str
        Report timestamp.
    errors : tuple[str, ...]
        Blocking findings.
    warnings : tuple[str, ...]
        Non-blocking findings.
    asset_count : int
        Parsed asset count.
    assets_sha256 : str
        File digest.
    """

    path: Path
    is_valid: bool
    checked_utc: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    asset_count: int
    assets_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Return the validation report as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Path, validity, findings, count, and digest.
        """
        return {
            "path": str(self.path),
            "is_valid": self.is_valid,
            "checked_utc": self.checked_utc,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "asset_count": self.asset_count,
            "assets_sha256": self.assets_sha256,
        }


def validate_hydrology_assets(path: Path) -> HydrologyAssetValidation:
    """Validate an asset table without raising.

    Parameters
    ----------
    path : Path
        Asset JSON path.

    Returns
    -------
    HydrologyAssetValidation
        Validation report with specific errors and warnings.
    """
    report, _assets = _load(path)
    return report


def load_hydrology_assets(path: Path) -> tuple[HydrologyAssetMapping, HydrologyAssetValidation]:
    """Load and validate an asset table.

    Parameters
    ----------
    path : Path
        Asset JSON path.

    Returns
    -------
    tuple[HydrologyAssetMapping, HydrologyAssetValidation]
        Loaded assets and their validation report.

    Raises
    ------
    FemicHydrologyAssetError
        If the table is invalid.
    """
    report, assets = _load(path)
    if not report.is_valid or assets is None:
        raise FemicHydrologyAssetError("; ".join(report.errors) or "Invalid hydrology asset table.")
    return assets, report


def map_hydrology_assets(
    scenario_path: str | Path,
    mapping_path: str | Path,
    assets_path: str | Path,
) -> HydrologyAssetMapping:
    """Map explicit assets to scenario road jobs and FEMIC watersheds.

    Parameters
    ----------
    scenario_path : str | Path
        FHOPS scenario YAML.
    mapping_path : str | Path
        Hydrology mapping directory or manifest.
    assets_path : str | Path
        Asset JSON path.

    Returns
    -------
    HydrologyAssetMapping
        Resolved assets with coverage and caveats.

    Raises
    ------
    FemicHydrologyAssetError
        If a road job or watershed is unknown or the mapping cannot load.
    """
    try:
        scenario = load_scenario(Path(scenario_path))
        mapping = load_hydrology_mapping(Path(mapping_path))
    except (FemicHydrologyMappingError, ValueError, FileNotFoundError) as exc:
        raise FemicHydrologyAssetError(str(exc)) from exc
    assets, report = load_hydrology_assets(Path(assets_path))
    road_ids = {road.id for road in scenario.road_construction or []}
    mapped_watersheds = {row.watershed_id for row in mapping.rows}
    warnings = list(report.warnings)
    for asset in assets.assets:
        if asset.asset_type == "road":
            if asset.road_job_id is None:
                raise FemicHydrologyAssetError(
                    f"Road asset {asset.asset_id!r} requires road_job_id."
                )
            if asset.road_job_id not in road_ids:
                raise FemicHydrologyAssetError(
                    f"Road asset {asset.asset_id!r} references unknown road job "
                    f"{asset.road_job_id!r}."
                )
        if asset.watershed_id not in mapped_watersheds:
            raise FemicHydrologyAssetError(
                f"Asset {asset.asset_id!r} references watershed "
                f"{asset.watershed_id!r} that is not in the hydrology mapping."
            )
    if assets.review_status != "reviewed":
        warnings.append("Asset inventory is not reviewed; use is provisional.")
    return HydrologyAssetMapping(
        inventory_id=assets.inventory_id,
        generated_utc=assets.generated_utc,
        source_id=assets.source_id,
        review_status=assets.review_status,
        reviewer_id=assets.reviewer_id,
        assets=assets.assets,
        road_job_ids=tuple(
            sorted(road_ids & {a.road_job_id for a in assets.assets if a.road_job_id})
        ),
        watershed_ids=tuple(sorted({asset.watershed_id for asset in assets.assets})),
        warnings=tuple(warnings),
        caveats=(
            "Asset evidence is explicit; it is not inferred from geometry.",
            "An asset is not a damage curve or a flood-risk determination.",
            *assets.caveats,
        ),
        assets_sha256=assets.assets_sha256,
    )


def _load(
    path: Path,
) -> tuple[HydrologyAssetValidation, HydrologyAssetMapping | None]:
    resolved = path.expanduser().resolve()
    checked = datetime.now(UTC).isoformat()
    errors: list[str] = []
    warnings: list[str] = []
    digest = ""
    asset_count = 0
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return (
            HydrologyAssetValidation(
                path=resolved,
                is_valid=False,
                checked_utc=checked,
                errors=(f"Unable to read assets: {exc}",),
                warnings=(),
                asset_count=0,
                assets_sha256="",
            ),
            None,
        )
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        errors.append(f"Asset table is not UTF-8: {exc}")
        payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid asset JSON: {exc}")
        payload = None
    if not isinstance(payload, Mapping):
        if not errors:
            errors.append("Asset table must be a JSON object.")
        return _report(resolved, checked, errors, warnings, 0, digest), None
    if payload.get("schema_version") != HYDROLOGY_ASSETS_SCHEMA:
        errors.append(f"Unsupported asset schema {payload.get('schema_version')!r}.")
    inventory_id = _required_text(payload.get("inventory_id"), "inventory_id", errors)
    generated_utc = _required_text(payload.get("generated_utc"), "generated_utc", errors)
    source_id = _required_text(payload.get("source_id"), "source_id", errors)
    review_status = _required_text(payload.get("review_status"), "review_status", errors)
    if review_status and review_status not in HYDROLOGY_ASSET_REVIEW_STATUSES:
        errors.append(f"Unsupported review_status {review_status!r}.")
    reviewer_id = _optional_text(payload.get("reviewer_id"))
    if review_status == "reviewed" and reviewer_id is None:
        errors.append("Reviewed asset table requires reviewer_id.")
    caveats = _text_list(payload.get("caveats"), "caveats", errors, allow_empty=False)
    rows = payload.get("assets")
    if not isinstance(rows, list) or not rows:
        errors.append("Asset rows must be a non-empty list.")
        rows = []
    assets: list[HydrologyAsset] = []
    seen: set[str] = set()
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, Mapping):
            errors.append(f"Asset row {index} must be an object.")
            continue
        asset = _asset(item, index, errors)
        if asset is None:
            continue
        if asset.asset_id in seen:
            errors.append(f"Duplicate asset id {asset.asset_id!r}.")
        seen.add(asset.asset_id)
        assets.append(asset)
    asset_count = len(assets)
    if errors:
        return _report(resolved, checked, errors, warnings, asset_count, digest), None
    mapping = HydrologyAssetMapping(
        inventory_id=inventory_id,
        generated_utc=generated_utc,
        source_id=source_id,
        review_status=review_status,
        reviewer_id=reviewer_id,
        assets=tuple(assets),
        road_job_ids=tuple(sorted({asset.road_job_id for asset in assets if asset.road_job_id})),
        watershed_ids=tuple(sorted({asset.watershed_id for asset in assets})),
        warnings=tuple(warnings),
        caveats=caveats,
        assets_sha256=digest,
    )
    return _report(resolved, checked, errors, warnings, asset_count, digest, valid=True), mapping


def _asset(item: Mapping[str, object], index: int, errors: list[str]) -> HydrologyAsset | None:
    asset_id = _required_text(item.get("asset_id"), f"asset row {index} asset_id", errors)
    asset_type = _required_text(item.get("asset_type"), f"asset row {index} asset_type", errors)
    if asset_type and asset_type not in HYDROLOGY_ASSET_TYPES:
        errors.append(f"Asset row {index} has unsupported asset_type {asset_type!r}.")
    watershed_id = _required_text(
        item.get("watershed_id"), f"asset row {index} watershed_id", errors
    )
    vulnerability = _required_text(
        item.get("vulnerability_class"),
        f"asset row {index} vulnerability_class",
        errors,
    )
    if vulnerability and vulnerability not in HYDROLOGY_ASSET_VULNERABILITY:
        errors.append(f"Asset row {index} has unsupported vulnerability_class {vulnerability!r}.")
    road_job_id = _optional_text(item.get("road_job_id"))
    if asset_type == "road" and road_job_id is None:
        errors.append(f"Asset row {index} is a road asset but has no road_job_id.")
    notes = _optional_text(item.get("notes")) or ""
    if not asset_id or not asset_type or not watershed_id or not vulnerability:
        return None
    return HydrologyAsset(
        asset_id=asset_id,
        asset_type=asset_type,
        watershed_id=watershed_id,
        road_job_id=road_job_id,
        vulnerability_class=vulnerability,
        notes=notes,
    )


def _report(
    path: Path,
    checked: str,
    errors: list[str],
    warnings: list[str],
    asset_count: int,
    digest: str,
    *,
    valid: bool | None = None,
) -> HydrologyAssetValidation:
    return HydrologyAssetValidation(
        path=path,
        is_valid=(not errors if valid is None else valid),
        checked_utc=checked,
        errors=tuple(errors),
        warnings=tuple(warnings),
        asset_count=asset_count,
        assets_sha256=digest,
    )


def _required_text(value: object, field: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string.")
        return ""
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _text_list(
    value: object, field: str, errors: list[str], *, allow_empty: bool
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{field} must be a list of non-empty strings.")
        return ()
    items = tuple(item.strip() for item in value)
    if any(not item for item in items):
        errors.append(f"{field} must be a list of non-empty strings.")
        return ()
    if not allow_empty and not items:
        errors.append(f"{field} must not be empty.")
    return items
