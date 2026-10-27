"""Read and validate individual-tree inventories for FHOPS blocks.

FHOPS consumes a producer-neutral tree list; it does not run individual-tree
detection, crown segmentation, or raw point-cloud processing. The inventory is
validated and referenced, and every record must resolve to a known FHOPS block
before downstream tree-scale simulation uses it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

TREE_INVENTORY_SCHEMA = "fhops.tree.inventory.v1"
TREE_INVENTORY_STATUSES: tuple[str, ...] = ("live", "dead", "snag", "other")
TREE_INVENTORY_REVIEW_STATUSES: tuple[str, ...] = (
    "not_reviewed",
    "review_pending",
    "reviewed",
    "reviewed_with_conditions",
)
TREE_INVENTORY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "tree_id",
    "block_id",
    "x_m",
    "y_m",
    "species_code",
    "dbh_cm",
    "height_m",
    "status",
    "confidence",
)
TREE_INVENTORY_OPTIONAL_COLUMNS: tuple[str, ...] = (
    "elevation_m",
    "crown_radius_m",
    "source_id",
    "source_tile_id",
    "merchantable_height_m",
    "defect",
    "grade_hint",
)
TREE_INVENTORY_UNITS: dict[str, str] = {
    "x_y": "m",
    "elevation": "m",
    "dbh": "cm",
    "height": "m",
    "crown_radius": "m",
}
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

__all__ = [
    "TREE_INVENTORY_OPTIONAL_COLUMNS",
    "TREE_INVENTORY_REQUIRED_COLUMNS",
    "TREE_INVENTORY_REVIEW_STATUSES",
    "TREE_INVENTORY_SCHEMA",
    "TREE_INVENTORY_STATUSES",
    "TreeInventory",
    "TreeInventoryError",
    "TreeInventoryMetadata",
    "TreeInventoryValidation",
    "TreeRecord",
    "load_tree_inventory",
    "validate_tree_inventory",
]


class TreeInventoryError(RuntimeError):
    """Raised when a tree inventory cannot be consumed."""


@dataclass(frozen=True)
class TreeRecord:
    """One validated individual-tree record.

    Attributes
    ----------
    tree_id : str
        Stable tree identifier, unique within the inventory.
    block_id : str
        FHOPS block identifier.
    x_m : float
        Easting in the inventory CRS, metres.
    y_m : float
        Northing in the inventory CRS, metres.
    elevation_m : float | None
        Ground elevation in metres, when supplied.
    species_code : str
        Producer species code, preserved verbatim.
    dbh_cm : float
        Diameter at breast height in centimetres.
    height_m : float
        Total tree height in metres.
    crown_radius_m : float | None
        Crown radius in metres, when supplied.
    status : str
        ``live``, ``dead``, ``snag``, or ``other``.
    confidence : float
        Detection/classification confidence in the closed interval 0–1.
    source_id : str | None
        Producer source identifier, when supplied.
    source_tile_id : str | None
        Producer tile identifier, when supplied.
    merchantable_height_m : float | None
        Merchantable stem height in metres, when supplied.
    defect : str | None
        Producer defect note, when supplied.
    grade_hint : str | None
        Producer product/grade hint, when supplied.
    """

    tree_id: str
    block_id: str
    x_m: float
    y_m: float
    elevation_m: float | None
    species_code: str
    dbh_cm: float
    height_m: float
    crown_radius_m: float | None
    status: str
    confidence: float
    source_id: str | None
    source_tile_id: str | None
    merchantable_height_m: float | None
    defect: str | None
    grade_hint: str | None

    def to_dict(self) -> dict[str, object]:
        """Return the tree record as a JSON-serializable mapping."""
        return {
            "tree_id": self.tree_id,
            "block_id": self.block_id,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "elevation_m": self.elevation_m,
            "species_code": self.species_code,
            "dbh_cm": self.dbh_cm,
            "height_m": self.height_m,
            "crown_radius_m": self.crown_radius_m,
            "status": self.status,
            "confidence": self.confidence,
            "source_id": self.source_id,
            "source_tile_id": self.source_tile_id,
            "merchantable_height_m": self.merchantable_height_m,
            "defect": self.defect,
            "grade_hint": self.grade_hint,
        }


@dataclass(frozen=True)
class TreeInventoryMetadata:
    """Inventory-level provenance and review metadata.

    Attributes
    ----------
    inventory_id : str
        Stable inventory identifier.
    generated_utc : str
        Producer generation timestamp.
    source_id : str
        Source or process identifier.
    producer : str
        Producer name.
    method : str
        Detection/segmentation method.
    crs : str
        Coordinate reference system for ``x_m``/``y_m`` and elevation.
    units : dict[str, str]
        Declared units.
    review_status : str
        ``not_reviewed``, ``review_pending``, ``reviewed``, or
        ``reviewed_with_conditions``.
    reviewed_by : str | None
        Reviewer identifier when reviewed.
    block_ids : tuple[str, ...]
        Declared block memberships, when supplied.
    caveats : tuple[str, ...]
        Inventory caveats.
    tree_count : int | None
        Declared row count, when supplied.
    inventory_sha256 : str | None
        Declared CSV digest, when supplied.
    """

    inventory_id: str
    generated_utc: str
    source_id: str
    producer: str
    method: str
    crs: str
    units: dict[str, str]
    review_status: str
    reviewed_by: str | None
    block_ids: tuple[str, ...]
    caveats: tuple[str, ...]
    tree_count: int | None
    inventory_sha256: str | None


@dataclass(frozen=True)
class TreeInventory:
    """Loaded and checksummed individual-tree inventory.

    Attributes
    ----------
    path : Path
        Resolved CSV path.
    metadata_path : Path
        Resolved metadata path.
    sha256 : str
        SHA-256 digest of the CSV bytes.
    metadata : TreeInventoryMetadata
        Inventory provenance and review metadata.
    rows : tuple[TreeRecord, ...]
        Validated tree records in file order.
    """

    path: Path
    metadata_path: Path
    sha256: str
    metadata: TreeInventoryMetadata
    rows: tuple[TreeRecord, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable inventory summary.

        Returns
        -------
        dict[str, object]
            Inventory identity, digest, metadata, row count, and rows.
        """
        return {
            "schema_version": TREE_INVENTORY_SCHEMA,
            "inventory_id": self.metadata.inventory_id,
            "inventory_sha256": self.sha256,
            "metadata_path": str(self.metadata_path),
            "crs": self.metadata.crs,
            "review_status": self.metadata.review_status,
            "tree_count": len(self.rows),
            "rows": [row.to_dict() for row in self.rows],
        }


@dataclass(frozen=True)
class TreeInventoryValidation:
    """Validation report for an individual-tree inventory.

    Attributes
    ----------
    path : Path
        Resolved inventory path.
    metadata_path : Path
        Resolved metadata path.
    is_valid : bool
        Whether every required check passed.
    checked_utc : str
        Report timestamp.
    errors : tuple[str, ...]
        Blocking findings.
    warnings : tuple[str, ...]
        Non-blocking findings.
    tree_count : int
        Parsed tree count.
    block_count : int
        Number of distinct blocks in the parsed rows.
    species_count : int
        Number of distinct species codes in the parsed rows.
    inventory_sha256 : str
        CSV digest.
    """

    path: Path
    metadata_path: Path
    is_valid: bool
    checked_utc: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    tree_count: int
    block_count: int
    species_count: int
    inventory_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Return the validation report as a JSON-serializable mapping."""
        return {
            "path": str(self.path),
            "metadata_path": str(self.metadata_path),
            "is_valid": self.is_valid,
            "checked_utc": self.checked_utc,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "tree_count": self.tree_count,
            "block_count": self.block_count,
            "species_count": self.species_count,
            "inventory_sha256": self.inventory_sha256,
        }


def validate_tree_inventory(
    path: Path,
    *,
    metadata_path: Path | None = None,
    block_ids: set[str] | None = None,
) -> TreeInventoryValidation:
    """Validate an individual-tree inventory without raising.

    Parameters
    ----------
    path : Path
        Tree CSV path.
    metadata_path : Path | None, optional
        Metadata JSON path. Defaults to the CSV stem plus ``.meta.json``.
    block_ids : set[str] | None, optional
        Known block IDs. When supplied, every tree must belong to one.

    Returns
    -------
    TreeInventoryValidation
        Validation report with specific errors and warnings.
    """
    report, _inventory = _load(path, metadata_path=metadata_path, block_ids=block_ids)
    return report


def load_tree_inventory(
    path: Path,
    *,
    metadata_path: Path | None = None,
    block_ids: set[str] | None = None,
) -> TreeInventory:
    """Load and validate an individual-tree inventory.

    Parameters
    ----------
    path : Path
        Tree CSV path.
    metadata_path : Path | None, optional
        Metadata JSON path. Defaults to the CSV stem plus ``.meta.json``.
    block_ids : set[str] | None, optional
        Known block IDs. When supplied, every tree must belong to one.

    Returns
    -------
    TreeInventory
        Validated inventory with checksum and provenance.

    Raises
    ------
    TreeInventoryError
        If the inventory is invalid.
    """
    report, inventory = _load(path, metadata_path=metadata_path, block_ids=block_ids)
    if not report.is_valid or inventory is None:
        raise TreeInventoryError("; ".join(report.errors) or "Invalid tree inventory.")
    return inventory


def _load(
    path: Path,
    *,
    metadata_path: Path | None,
    block_ids: set[str] | None,
) -> tuple[TreeInventoryValidation, TreeInventory | None]:
    resolved = path.expanduser().resolve()
    metadata_resolved = (
        metadata_path.expanduser().resolve()
        if metadata_path is not None
        else resolved.with_name(f"{resolved.stem}.meta.json")
    )
    checked = datetime.now(UTC).isoformat()
    errors: list[str] = []
    warnings: list[str] = []
    digest = ""
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return (
            TreeInventoryValidation(
                path=resolved,
                metadata_path=metadata_resolved,
                is_valid=False,
                checked_utc=checked,
                errors=(f"Unable to read tree inventory: {exc}",),
                warnings=(),
                tree_count=0,
                block_count=0,
                species_count=0,
                inventory_sha256="",
            ),
            None,
        )
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"Tree inventory is not UTF-8: {exc}")
        text = ""
    metadata = _metadata(metadata_resolved, digest=digest, errors=errors)
    reader = csv.DictReader(text.splitlines()) if text else None
    if reader is None:
        return _report(resolved, metadata_resolved, checked, errors, warnings, [], digest), None
    if reader.fieldnames is None:
        errors.append("Tree inventory CSV has no header.")
        return _report(resolved, metadata_resolved, checked, errors, warnings, [], digest), None
    missing = set(TREE_INVENTORY_REQUIRED_COLUMNS) - set(reader.fieldnames)
    if missing:
        errors.append(
            "Tree inventory CSV is missing required columns: " + ", ".join(sorted(missing)) + "."
        )
    rows: list[TreeRecord] = []
    seen: set[str] = set()
    for index, payload in enumerate(reader, start=2):
        record = _record(payload, index=index, errors=errors)
        if record is None:
            continue
        if record.tree_id in seen:
            errors.append(f"Duplicate tree_id {record.tree_id!r} at row {index}.")
            continue
        seen.add(record.tree_id)
        if block_ids is not None and record.block_id not in block_ids:
            errors.append(f"Tree {record.tree_id!r} references unknown block {record.block_id!r}.")
        rows.append(record)
    if not rows and not errors:
        errors.append("Tree inventory contains no tree rows.")
    if metadata is not None:
        if metadata.tree_count is not None and metadata.tree_count != len(rows):
            errors.append(
                f"Metadata tree_count={metadata.tree_count} does not match {len(rows)} rows."
            )
        if metadata.block_ids:
            unknown = sorted({row.block_id for row in rows} - set(metadata.block_ids))
            if unknown:
                errors.append(
                    "Tree inventory contains blocks not declared in metadata: "
                    + ", ".join(unknown)
                    + "."
                )
        if metadata.review_status == "reviewed" and metadata.reviewed_by is None:
            errors.append("Reviewed tree inventory metadata requires reviewed_by.")
    if errors:
        return _report(resolved, metadata_resolved, checked, errors, warnings, rows, digest), None
    assert metadata is not None
    return _report(
        resolved,
        metadata_resolved,
        checked,
        errors,
        warnings,
        rows,
        digest,
        valid=True,
    ), TreeInventory(
        path=resolved,
        metadata_path=metadata_resolved,
        sha256=digest,
        metadata=metadata,
        rows=tuple(rows),
    )


def _report(
    path: Path,
    metadata_path: Path,
    checked: str,
    errors: list[str],
    warnings: list[str],
    rows: list[TreeRecord],
    digest: str,
    *,
    valid: bool | None = None,
) -> TreeInventoryValidation:
    return TreeInventoryValidation(
        path=path,
        metadata_path=metadata_path,
        is_valid=(not errors if valid is None else valid),
        checked_utc=checked,
        errors=tuple(errors),
        warnings=tuple(warnings),
        tree_count=len(rows),
        block_count=len({row.block_id for row in rows}),
        species_count=len({row.species_code for row in rows}),
        inventory_sha256=digest,
    )


def _metadata(
    path: Path,
    *,
    digest: str,
    errors: list[str],
) -> TreeInventoryMetadata | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"Unable to read tree inventory metadata: {exc}")
        return None
    if not isinstance(payload, Mapping):
        errors.append("Tree inventory metadata must be a JSON object.")
        return None
    if payload.get("schema_version") != TREE_INVENTORY_SCHEMA:
        errors.append(f"Unsupported tree inventory schema {payload.get('schema_version')!r}.")
    inventory_id = _required_text(payload.get("inventory_id"), "inventory_id", errors)
    generated_utc = _required_text(payload.get("generated_utc"), "generated_utc", errors)
    source_id = _required_text(payload.get("source_id"), "source_id", errors)
    producer = _required_text(payload.get("producer"), "producer", errors)
    method = _required_text(payload.get("method"), "method", errors)
    crs = _required_text(payload.get("crs"), "crs", errors)
    units = payload.get("units")
    if not isinstance(units, Mapping):
        errors.append("Metadata units must be an object.")
        unit_values: dict[str, str] = {}
    else:
        unit_values = {str(key): str(value) for key, value in units.items()}
        for key in TREE_INVENTORY_UNITS:
            if not unit_values.get(key):
                errors.append(f"Metadata units is missing {key!r}.")
    review_status = _required_text(payload.get("review_status"), "review_status", errors)
    if review_status and review_status not in TREE_INVENTORY_REVIEW_STATUSES:
        errors.append(f"Unsupported review_status {review_status!r}.")
    reviewed_by = _optional_text(payload.get("reviewed_by"))
    block_ids = _text_list(payload.get("block_ids", []), "block_ids", errors)
    caveats = _text_list(payload.get("caveats", []), "caveats", errors)
    tree_count_raw = payload.get("tree_count")
    tree_count: int | None = None
    if tree_count_raw is not None:
        if (
            isinstance(tree_count_raw, bool)
            or not isinstance(tree_count_raw, int)
            or tree_count_raw < 0
        ):
            errors.append("Metadata tree_count must be a non-negative integer.")
        else:
            tree_count = tree_count_raw
    inventory_sha = _optional_text(payload.get("inventory_sha256"))
    if inventory_sha is not None:
        if SHA256_PATTERN.fullmatch(inventory_sha) is None:
            errors.append("Metadata inventory_sha256 must be a 64-character hex digest.")
        elif inventory_sha.lower() != digest.lower():
            errors.append("Metadata inventory_sha256 does not match the CSV.")
    return TreeInventoryMetadata(
        inventory_id=inventory_id,
        generated_utc=generated_utc,
        source_id=source_id,
        producer=producer,
        method=method,
        crs=crs,
        units=unit_values,
        review_status=review_status,
        reviewed_by=reviewed_by,
        block_ids=block_ids,
        caveats=caveats,
        tree_count=tree_count,
        inventory_sha256=inventory_sha,
    )


def _record(
    payload: Mapping[str, object],
    *,
    index: int,
    errors: list[str],
) -> TreeRecord | None:
    tree_id = _required_text(payload.get("tree_id"), f"row {index} tree_id", errors)
    block_id = _required_text(payload.get("block_id"), f"row {index} block_id", errors)
    species = _required_text(payload.get("species_code"), f"row {index} species_code", errors)
    status = _required_text(payload.get("status"), f"row {index} status", errors).lower()
    if status and status not in TREE_INVENTORY_STATUSES:
        errors.append(f"Row {index} has unsupported status {status!r}.")
    x = _required_number(payload.get("x_m"), f"row {index} x_m", errors)
    y = _required_number(payload.get("y_m"), f"row {index} y_m", errors)
    elevation = _optional_number(payload.get("elevation_m"), f"row {index} elevation_m", errors)
    dbh = _required_number(payload.get("dbh_cm"), f"row {index} dbh_cm", errors)
    height = _required_number(payload.get("height_m"), f"row {index} height_m", errors)
    crown = _optional_number(payload.get("crown_radius_m"), f"row {index} crown_radius_m", errors)
    confidence = _required_number(payload.get("confidence"), f"row {index} confidence", errors)
    if dbh is not None and dbh <= 0:
        errors.append(f"Row {index} dbh_cm must be positive.")
    if height is not None and height <= 0:
        errors.append(f"Row {index} height_m must be positive.")
    if crown is not None and crown <= 0:
        errors.append(f"Row {index} crown_radius_m must be positive.")
    if confidence is not None and not 0 <= confidence <= 1:
        errors.append(f"Row {index} confidence must be within 0–1.")
    merchantable = _optional_number(
        payload.get("merchantable_height_m"),
        f"row {index} merchantable_height_m",
        errors,
    )
    if merchantable is not None and merchantable <= 0:
        errors.append(f"Row {index} merchantable_height_m must be positive.")
    if merchantable is not None and height is not None and merchantable > height + 1e-9:
        errors.append(f"Row {index} merchantable_height_m exceeds height_m.")
    if not tree_id or not block_id or not species or not status:
        return None
    if x is None or y is None or dbh is None or height is None or confidence is None:
        return None
    return TreeRecord(
        tree_id=tree_id,
        block_id=block_id,
        x_m=x,
        y_m=y,
        elevation_m=elevation,
        species_code=species,
        dbh_cm=dbh,
        height_m=height,
        crown_radius_m=crown,
        status=status,
        confidence=confidence,
        source_id=_optional_text(payload.get("source_id")),
        source_tile_id=_optional_text(payload.get("source_tile_id")),
        merchantable_height_m=merchantable,
        defect=_optional_text(payload.get("defect")),
        grade_hint=_optional_text(payload.get("grade_hint")),
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


def _required_number(value: object, field: str, errors: list[str]) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        errors.append(f"{field} must be a finite number.")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        errors.append(f"{field} must be a finite number.")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be a finite number.")
        return None
    if not math.isfinite(number):
        errors.append(f"{field} must be a finite number.")
        return None
    return number


def _optional_number(value: object, field: str, errors: list[str]) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _required_number(value, field, errors)


def _text_list(value: object, field: str, errors: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{field} must be a list of non-empty strings.")
        return ()
    items = tuple(item.strip() for item in value)
    if any(not item for item in items):
        errors.append(f"{field} must be a list of non-empty strings.")
        return ()
    return items
