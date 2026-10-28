"""Pin individual-tree inventories to scenarios and build block tree maps.

The mapper is a consumer layer: it validates the inventory against the scenario
blocks, preserves the inventory checksum and review state, and reconciles
tree-derived summaries with the block-level evidence already in the scenario.
It does not derive stem volume, simulate machines, or copy the inventory.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fhops.scenario.contract.models import Block, Scenario
from fhops.scenario.contract.tree import TreeInventoryRef, TreeInventoryReviewStatus
from fhops.scenario.hydrology_registration import (
    _format_error,
    _replace_top_level_section,
)
from fhops.scenario.io import load_scenario
from fhops.tree_inventory import (
    TreeInventory,
    TreeInventoryError,
    load_tree_inventory,
)

TREE_MAPPING_SCHEMA = "fhops.tree.inventory_map.v1"
DEFAULT_RECONCILIATION_TOLERANCE = 0.25
_FORM_FACTOR = 0.5

__all__ = [
    "BlockTreeSummary",
    "DEFAULT_RECONCILIATION_TOLERANCE",
    "TreeInventoryMapping",
    "TreeInventoryMappingError",
    "TreeInventoryRegistrationError",
    "TreeInventoryRegistrationResult",
    "map_tree_inventory",
    "register_tree_inventory",
    "write_tree_mapping",
]


class TreeInventoryRegistrationError(RuntimeError):
    """A tree inventory cannot be pinned to a scenario."""


class TreeInventoryMappingError(RuntimeError):
    """A pinned tree inventory cannot be mapped or reconciled."""


@dataclass(frozen=True)
class TreeInventoryRegistrationResult:
    """Outcome of pinning a tree inventory in a scenario.

    Attributes
    ----------
    scenario_path : Path
        Scenario YAML.
    inventory_id : str
        Inventory identifier.
    inventory_sha256 : str
        Inventory CSV digest.
    metadata_sha256 : str
        Metadata JSON digest.
    inventory_path : str
        Inventory path recorded in the pin.
    metadata_path : str
        Metadata path recorded in the pin.
    tree_count : int
        Number of tree records.
    block_ids : tuple[str, ...]
        Blocks represented by the inventory.
    written : bool
        False for a dry run.
    pin : TreeInventoryRef
        Pin that was written or would be written.
    """

    scenario_path: Path
    inventory_id: str
    inventory_sha256: str
    metadata_sha256: str
    inventory_path: str
    metadata_path: str
    tree_count: int
    block_ids: tuple[str, ...]
    written: bool
    pin: TreeInventoryRef

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready registration summary."""
        return {
            "scenario_path": str(self.scenario_path),
            "inventory_id": self.inventory_id,
            "inventory_sha256": self.inventory_sha256,
            "metadata_sha256": self.metadata_sha256,
            "inventory_path": self.inventory_path,
            "metadata_path": self.metadata_path,
            "tree_count": self.tree_count,
            "block_ids": list(self.block_ids),
            "written": self.written,
            "pin": self.pin.model_dump(mode="json", exclude_none=True),
        }


@dataclass(frozen=True)
class BlockTreeSummary:
    """Tree-derived summary for one scenario block.

    Attributes
    ----------
    block_id : str
        Scenario block identifier.
    tree_count : int
        Number of trees in the block.
    area_ha : float | None
        Block area from GeoJSON, LiDAR support, or the scenario volume ratio.
    stems_per_ha : float | None
        Tree count per hectare.
    mean_dbh_cm : float | None
        Mean DBH in centimetres.
    mean_height_m : float | None
        Mean height in metres.
    basal_area_m2 : float
        Sum of tree basal area in square metres.
    basal_area_per_ha_m2 : float | None
        Basal area per hectare.
    gross_volume_proxy_m3 : float
        Crude gross-volume proxy, not merchantable volume.
    species_counts : dict[str, int]
        Tree counts by producer species code.
    expected_stem_count : float | None
        Stem density times area, when both are available.
    stem_density_status : str
        ``ok``, ``warning``, or ``unknown``.
    stem_density_difference_fraction : float | None
        Relative difference from the scenario stem density.
    work_required_m3 : float | None
        Scenario terminal volume.
    volume_status : str
        ``ok``, ``warning``, or ``unknown``.
    volume_difference_fraction : float | None
        Relative difference between the proxy and ``work_required``.
    warnings : tuple[str, ...]
        Block-level reconciliation warnings.
    """

    block_id: str
    tree_count: int
    area_ha: float | None
    stems_per_ha: float | None
    mean_dbh_cm: float | None
    mean_height_m: float | None
    basal_area_m2: float
    basal_area_per_ha_m2: float | None
    gross_volume_proxy_m3: float
    species_counts: dict[str, int]
    expected_stem_count: float | None
    stem_density_status: str
    stem_density_difference_fraction: float | None
    work_required_m3: float | None
    volume_status: str
    volume_difference_fraction: float | None
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the block summary as a JSON-serializable mapping."""
        return {
            "block_id": self.block_id,
            "tree_count": self.tree_count,
            "area_ha": self.area_ha,
            "stems_per_ha": self.stems_per_ha,
            "mean_dbh_cm": self.mean_dbh_cm,
            "mean_height_m": self.mean_height_m,
            "basal_area_m2": self.basal_area_m2,
            "basal_area_per_ha_m2": self.basal_area_per_ha_m2,
            "gross_volume_proxy_m3": self.gross_volume_proxy_m3,
            "species_counts": self.species_counts,
            "expected_stem_count": self.expected_stem_count,
            "stem_density_status": self.stem_density_status,
            "stem_density_difference_fraction": self.stem_density_difference_fraction,
            "work_required_m3": self.work_required_m3,
            "volume_status": self.volume_status,
            "volume_difference_fraction": self.volume_difference_fraction,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class TreeInventoryMapping:
    """Block tree map and reconciliation for one pinned inventory.

    Attributes
    ----------
    mapping_id : str
        Deterministic mapping identifier.
    generated_utc : str
        Mapping timestamp.
    scenario_path : Path
        Scenario YAML.
    inventory_id : str
        Inventory identifier.
    inventory_sha256 : str
        Inventory CSV digest.
    metadata_sha256 : str
        Metadata digest.
    crs : str
        Inventory CRS.
    review_status : str
        Inventory review status.
    tolerance : float
        Relative reconciliation tolerance.
    blocks : tuple[BlockTreeSummary, ...]
        Per-block summaries.
    blocks_without_trees : tuple[str, ...]
        Scenario blocks absent from the inventory.
    reconciliation : dict[str, object]
        Aggregate reconciliation counts.
    warnings : tuple[str, ...]
        Non-fatal observations.
    caveats : tuple[str, ...]
        Mapping and proxy caveats.
    """

    mapping_id: str
    generated_utc: str
    scenario_path: Path
    inventory_id: str
    inventory_sha256: str
    metadata_sha256: str
    crs: str
    review_status: str
    tolerance: float
    blocks: tuple[BlockTreeSummary, ...]
    blocks_without_trees: tuple[str, ...]
    reconciliation: dict[str, object]
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the mapping manifest as a JSON-serializable mapping."""
        return {
            "schema_version": TREE_MAPPING_SCHEMA,
            "mapping_id": self.mapping_id,
            "generated_utc": self.generated_utc,
            "scenario_path": str(self.scenario_path),
            "inventory_id": self.inventory_id,
            "inventory_sha256": self.inventory_sha256,
            "metadata_sha256": self.metadata_sha256,
            "crs": self.crs,
            "review_status": self.review_status,
            "tolerance": self.tolerance,
            "block_count": len(self.blocks),
            "tree_count": sum(block.tree_count for block in self.blocks),
            "blocks": [block.to_dict() for block in self.blocks],
            "blocks_without_trees": list(self.blocks_without_trees),
            "reconciliation": self.reconciliation,
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
        }


def register_tree_inventory(
    scenario_path: str | Path,
    inventory_path: str | Path,
    *,
    metadata_path: str | Path | None = None,
    dry_run: bool = False,
) -> TreeInventoryRegistrationResult:
    """Validate a tree inventory and pin it in a scenario.

    Parameters
    ----------
    scenario_path : str | Path
        Scenario YAML to update.
    inventory_path : str | Path
        Tree inventory CSV.
    metadata_path : str | Path | None, optional
        Metadata JSON. Defaults to the CSV stem plus ``.meta.json``.
    dry_run : bool, optional
        Validate and return the pin without writing the scenario.

    Returns
    -------
    TreeInventoryRegistrationResult
        Pin, counts, and whether the scenario changed.

    Raises
    ------
    TreeInventoryRegistrationError
        If the scenario, inventory, or existing pin cannot be used safely.
    """
    scenario_file = Path(scenario_path).expanduser().resolve()
    inventory_file = Path(inventory_path).expanduser().resolve()
    metadata_file = (
        Path(metadata_path).expanduser().resolve()
        if metadata_path is not None
        else inventory_file.with_name(f"{inventory_file.stem}.meta.json")
    )
    try:
        scenario = load_scenario(scenario_file)
        inventory = load_tree_inventory(
            inventory_file,
            metadata_path=metadata_file,
            block_ids=set(scenario.block_ids()),
        )
    except (TreeInventoryError, ValueError, FileNotFoundError) as exc:
        raise TreeInventoryRegistrationError(_format_error(exc)) from exc
    try:
        _check_crs(scenario.geo.crs if scenario.geo else None, inventory.metadata.crs)
    except TreeInventoryMappingError as exc:
        raise TreeInventoryRegistrationError(str(exc)) from exc
    metadata_digest = _metadata_digest(metadata_file)
    pin = TreeInventoryRef(
        inventory_id=inventory.metadata.inventory_id,
        inventory_sha256=inventory.sha256,
        metadata_sha256=metadata_digest,
        inventory_path=_relative_path(scenario_file, inventory_file),
        metadata_path=_relative_path(scenario_file, metadata_file),
        crs=inventory.metadata.crs,
        review_status=cast(TreeInventoryReviewStatus, inventory.metadata.review_status),
        reviewed_by=inventory.metadata.reviewed_by,
        source_id=inventory.metadata.source_id,
        producer=inventory.metadata.producer,
        method=inventory.metadata.method,
        tree_count=len(inventory.rows),
        block_ids=sorted({row.block_id for row in inventory.rows}),
        caveats=list(inventory.metadata.caveats),
    )
    existing = scenario.tree_inventory
    if existing is not None and (
        existing.inventory_id != pin.inventory_id
        or existing.inventory_sha256 != pin.inventory_sha256
    ):
        raise TreeInventoryRegistrationError(
            "Scenario is already pinned to a different tree inventory; remove the existing "
            "tree_inventory section before registering another."
        )
    text = _replace_top_level_section(
        scenario_file.read_text(encoding="utf-8"),
        "tree_inventory",
        pin.model_dump(mode="json", exclude_none=True),
    )
    if not dry_run:
        _validate_and_replace(scenario_file, text)
    return TreeInventoryRegistrationResult(
        scenario_path=scenario_file,
        inventory_id=pin.inventory_id,
        inventory_sha256=pin.inventory_sha256,
        metadata_sha256=pin.metadata_sha256,
        inventory_path=pin.inventory_path,
        metadata_path=pin.metadata_path,
        tree_count=pin.tree_count,
        block_ids=tuple(pin.block_ids),
        written=not dry_run,
        pin=pin,
    )


def map_tree_inventory(
    scenario_path: str | Path,
    *,
    tolerance: float = DEFAULT_RECONCILIATION_TOLERANCE,
    require_reconciled: bool = False,
    generated_utc: str | None = None,
) -> TreeInventoryMapping:
    """Map a pinned tree inventory to scenario blocks and reconcile evidence.

    Parameters
    ----------
    scenario_path : str | Path
        Scenario YAML with a tree-inventory pin.
    tolerance : float, optional
        Relative tolerance for stem-density and volume reconciliation.
    require_reconciled : bool, optional
        Refuse when any block produces a reconciliation warning.
    generated_utc : str | None, optional
        Mapping timestamp.

    Returns
    -------
    TreeInventoryMapping
        Per-block summaries, coverage, and reconciliation.

    Raises
    ------
    TreeInventoryMappingError
        If the pin is missing, stale, inconsistent, or strict reconciliation
        fails.
    """
    if not math.isfinite(tolerance) or tolerance < 0:
        raise TreeInventoryMappingError("Reconciliation tolerance must be finite and non-negative.")
    scenario_file = Path(scenario_path).expanduser().resolve()
    try:
        scenario = load_scenario(scenario_file)
    except (ValueError, FileNotFoundError) as exc:
        raise TreeInventoryMappingError(_format_error(exc)) from exc
    pin = scenario.tree_inventory
    if pin is None:
        raise TreeInventoryMappingError(
            "Scenario has no tree_inventory pin; run `fhops tree register` first."
        )
    inventory_file = _resolve_path(scenario_file, pin.inventory_path)
    metadata_file = _resolve_path(scenario_file, pin.metadata_path)
    try:
        inventory = load_tree_inventory(
            inventory_file,
            metadata_path=metadata_file,
            block_ids=set(scenario.block_ids()),
        )
    except (TreeInventoryError, ValueError, FileNotFoundError) as exc:
        raise TreeInventoryMappingError(_format_error(exc)) from exc
    _check_pin(pin, inventory, metadata_file)
    _check_crs(scenario.geo.crs if scenario.geo else None, pin.crs)
    areas = _block_areas(scenario, scenario_file)
    by_block: dict[str, list] = {}
    for row in inventory.rows:
        by_block.setdefault(row.block_id, []).append(row)
    blocks: list[BlockTreeSummary] = []
    blocks_without_trees: list[str] = []
    warnings: list[str] = []
    for block in scenario.blocks:
        rows = by_block.get(block.id, [])
        if not rows:
            blocks_without_trees.append(block.id)
        summary = _block_summary(
            block,
            rows,
            area_ha=areas.get(block.id),
            tolerance=tolerance,
        )
        blocks.append(summary)
        warnings.extend(f"{block.id}: {warning}" for warning in summary.warnings)
    if blocks_without_trees:
        warnings.append("Blocks without trees: " + ", ".join(sorted(blocks_without_trees)))
    reconciliation = _reconciliation(blocks, tolerance)
    if require_reconciled and reconciliation["warning_blocks"]:
        raise TreeInventoryMappingError(
            "Tree inventory reconciliation failed for block(s): "
            + ", ".join(cast(list[str], reconciliation["warning_blocks"]))
        )
    timestamp = generated_utc or datetime.now(UTC).isoformat()
    material = {
        "inventory_id": pin.inventory_id,
        "inventory_sha256": pin.inventory_sha256,
        "tolerance": tolerance,
        "blocks": [summary.to_dict() for summary in blocks],
    }
    mapping_id = (
        "fhops-tree-map-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    return TreeInventoryMapping(
        mapping_id=mapping_id,
        generated_utc=timestamp,
        scenario_path=scenario_file,
        inventory_id=pin.inventory_id,
        inventory_sha256=pin.inventory_sha256,
        metadata_sha256=pin.metadata_sha256,
        crs=pin.crs,
        review_status=pin.review_status,
        tolerance=tolerance,
        blocks=tuple(blocks),
        blocks_without_trees=tuple(blocks_without_trees),
        reconciliation=reconciliation,
        warnings=tuple(warnings),
        caveats=(
            "Tree-derived volume is a crude gross-volume proxy, not merchantable volume.",
            "Reconciliation is a screening check, not a field validation.",
            *pin.caveats,
        ),
    )


def write_tree_mapping(mapping: TreeInventoryMapping, out_dir: Path) -> dict[str, Path]:
    """Write the block tree map CSV and manifest.

    Parameters
    ----------
    mapping : TreeInventoryMapping
        Mapping result.
    out_dir : Path
        Output directory.

    Returns
    -------
    dict[str, Path]
        Paths keyed by ``rows`` and ``manifest``.
    """
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows_path = output / "tree_inventory_map.csv"
    columns = (
        "block_id",
        "tree_count",
        "area_ha",
        "stems_per_ha",
        "mean_dbh_cm",
        "mean_height_m",
        "basal_area_m2",
        "basal_area_per_ha_m2",
        "gross_volume_proxy_m3",
        "expected_stem_count",
        "stem_density_status",
        "stem_density_difference_fraction",
        "work_required_m3",
        "volume_status",
        "volume_difference_fraction",
    )
    with rows_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(block.to_dict() for block in mapping.blocks)
    manifest_path = output / "tree_inventory_map.json"
    manifest_path.write_text(
        json.dumps(mapping.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"rows": rows_path, "manifest": manifest_path}


def _block_summary(
    block: Block, rows: list[Any], *, area_ha: float | None, tolerance: float
) -> BlockTreeSummary:
    dbh = [float(row.dbh_cm) for row in rows]
    height = [float(row.height_m) for row in rows]
    basal_area = sum(math.pi / 4.0 * (value / 100.0) ** 2 for value in dbh)
    volume_proxy = sum(
        _FORM_FACTOR * (math.pi / 4.0) * (float(row.dbh_cm) / 100.0) ** 2 * float(row.height_m)
        for row in rows
    )
    stems_per_ha = len(rows) / area_ha if area_ha and area_ha > 0 else None
    basal_area_per_ha = basal_area / area_ha if area_ha and area_ha > 0 else None
    expected_stems = (
        block.stem_density_per_ha * area_ha
        if block.stem_density_per_ha is not None and area_ha is not None
        else None
    )
    stem_status, stem_difference = _status(
        len(rows),
        expected_stems,
        tolerance,
    )
    work_required = block.work_required if block.work_required > 0 else None
    volume_status, volume_difference = _status(volume_proxy, work_required, tolerance)
    block_warnings: list[str] = []
    if area_ha is None:
        block_warnings.append("block area evidence is missing; density checks skipped")
    if stem_status == "warning":
        block_warnings.append("tree count differs from stem_density_per_ha evidence")
    if volume_status == "warning":
        block_warnings.append("gross-volume proxy differs from work_required")
    if volume_status == "unknown":
        block_warnings.append("work_required is unavailable; volume reconciliation skipped")
    return BlockTreeSummary(
        block_id=block.id,
        tree_count=len(rows),
        area_ha=area_ha,
        stems_per_ha=stems_per_ha,
        mean_dbh_cm=sum(dbh) / len(dbh) if dbh else None,
        mean_height_m=sum(height) / len(height) if height else None,
        basal_area_m2=basal_area,
        basal_area_per_ha_m2=basal_area_per_ha,
        gross_volume_proxy_m3=volume_proxy,
        species_counts=dict(Counter(row.species_code for row in rows)),
        expected_stem_count=expected_stems,
        stem_density_status=stem_status,
        stem_density_difference_fraction=stem_difference,
        work_required_m3=work_required,
        volume_status=volume_status,
        volume_difference_fraction=volume_difference,
        warnings=tuple(block_warnings),
    )


def _status(observed: float, expected: float | None, tolerance: float) -> tuple[str, float | None]:
    if expected is None or expected <= 0:
        return "unknown", None
    difference = (observed - expected) / expected
    return ("ok" if abs(difference) <= tolerance else "warning"), difference


def _reconciliation(blocks: list[BlockTreeSummary], tolerance: float) -> dict[str, object]:
    stem_counts = Counter(block.stem_density_status for block in blocks)
    volume_counts = Counter(block.volume_status for block in blocks)
    warning_blocks = [
        block.block_id
        for block in blocks
        if "warning" in (block.stem_density_status, block.volume_status)
    ]
    return {
        "tolerance": tolerance,
        "stem_density_ok": stem_counts["ok"],
        "stem_density_warning": stem_counts["warning"],
        "stem_density_unknown": stem_counts["unknown"],
        "volume_ok": volume_counts["ok"],
        "volume_warning": volume_counts["warning"],
        "volume_unknown": volume_counts["unknown"],
        "warning_blocks": warning_blocks,
    }


def _block_areas(scenario: Scenario, scenario_path: Path) -> dict[str, float]:
    areas: dict[str, float] = {}
    geo = getattr(scenario, "geo", None)
    if geo is not None and geo.block_geojson:
        path = _resolve_path(scenario_path, geo.block_geojson)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TreeInventoryMappingError(f"Unable to read block GeoJSON: {exc}") from exc
        for feature in payload.get("features", []):
            if not isinstance(feature, Mapping):
                continue
            props = feature.get("properties") or {}
            if not isinstance(props, Mapping):
                continue
            block_id = props.get("block_id") or feature.get("id")
            area_ha = props.get("area_ha") or props.get("AREA_HA")
            area_m2 = props.get("area_m2") or props.get("AREA_M2")
            if isinstance(block_id, str):
                if isinstance(area_ha, (int, float)) and not isinstance(area_ha, bool):
                    areas[block_id] = float(area_ha)
                elif isinstance(area_m2, (int, float)) and not isinstance(area_m2, bool):
                    areas[block_id] = float(area_m2) / 10000.0
    for support in getattr(scenario, "lidar_support", None) or []:
        if support.support_unit == "block" and support.support_area_m2 is not None:
            areas.setdefault(support.support_id, float(support.support_area_m2) / 10000.0)
    for block in scenario.blocks:
        if block.id in areas:
            continue
        if block.volume_per_ha_m3 and block.volume_per_ha_m3 > 0 and block.work_required > 0:
            areas[block.id] = block.work_required / block.volume_per_ha_m3
    return areas


def _check_crs(scenario_crs: str | None, inventory_crs: str) -> None:
    if scenario_crs and scenario_crs.strip().lower() != inventory_crs.strip().lower():
        raise TreeInventoryMappingError(
            f"Scenario CRS {scenario_crs!r} does not match inventory CRS {inventory_crs!r}."
        )


def _check_pin(pin: TreeInventoryRef, inventory: TreeInventory, metadata_file: Path) -> None:
    if pin.inventory_sha256 != inventory.sha256:
        raise TreeInventoryMappingError("Tree inventory checksum does not match the scenario pin.")
    if pin.inventory_id != inventory.metadata.inventory_id:
        raise TreeInventoryMappingError("Tree inventory id does not match the scenario pin.")
    if pin.tree_count != len(inventory.rows):
        raise TreeInventoryMappingError("Tree inventory count does not match the scenario pin.")
    if pin.crs.strip().lower() != inventory.metadata.crs.strip().lower():
        raise TreeInventoryMappingError("Tree inventory CRS does not match the scenario pin.")
    if pin.review_status != inventory.metadata.review_status:
        raise TreeInventoryMappingError(
            "Tree inventory review status does not match the scenario pin."
        )
    if tuple(sorted(pin.block_ids)) != tuple(sorted({row.block_id for row in inventory.rows})):
        raise TreeInventoryMappingError(
            "Tree inventory block coverage does not match the scenario pin."
        )
    if pin.metadata_sha256 != _metadata_digest(metadata_file):
        raise TreeInventoryMappingError("Tree inventory metadata checksum does not match the pin.")


def _metadata_digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise TreeInventoryMappingError(f"Unable to read tree inventory metadata: {exc}") from exc


def _relative_path(scenario_path: Path, path: Path) -> str:
    try:
        return str(path.relative_to(scenario_path.parent))
    except ValueError:
        return str(path)


def _resolve_path(scenario_path: Path, path: str) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else (scenario_path.parent / candidate).resolve()


def _validate_and_replace(path: Path, text: str) -> None:
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".fhops-tree-inventory-",
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
    except Exception as exc:  # noqa: BLE001 - preserve the loader message
        temp_path.unlink(missing_ok=True)
        raise TreeInventoryRegistrationError(_format_error(exc)) from exc
