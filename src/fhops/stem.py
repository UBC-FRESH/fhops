"""Stem volume and log-bucking models for tree-scale FHOPS workflows.

The module provides a small pluggable model boundary and a clearly labelled
reference form-factor model. The reference model is a scaffold for the spatial
simulation path, not a calibrated operational taper/bucking system.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from fhops.scenario.io import load_scenario
from fhops.tree_inventory import TreeInventory, TreeRecord, load_tree_inventory
from fhops.tree_mapping import (
    DEFAULT_RECONCILIATION_TOLERANCE,
    map_tree_inventory,
)

STEM_SCHEMA = "fhops.tree.stems.v1"
DEFAULT_FORM_FACTOR = 0.45
DEFAULT_STUMP_HEIGHT_M = 0.3
DEFAULT_LOG_LENGTH_M = 4.9
DEFAULT_SAWLOG_MIN_DBH_CM = 20.0

__all__ = [
    "DEFAULT_FORM_FACTOR",
    "DEFAULT_LOG_LENGTH_M",
    "DEFAULT_SAWLOG_MIN_DBH_CM",
    "DEFAULT_STUMP_HEIGHT_M",
    "LogRecord",
    "ReferenceStemModel",
    "StemInventory",
    "StemModelError",
    "StemResult",
    "StemBlockSummary",
    "build_stem_inventory",
    "write_stem_inventory",
]


class StemModelError(RuntimeError):
    """Raised when a stem model cannot evaluate a tree."""


class StemModel(Protocol):
    """Protocol for pluggable stem-volume and bucking models.

    Attributes
    ----------
    name : str
        Stable model name.
    version : str
        Model version.
    provenance : str
        Human-readable model provenance and limits.
    """

    @property
    def name(self) -> str:
        """Stable model name."""
        ...

    @property
    def version(self) -> str:
        """Model version."""
        ...

    @property
    def provenance(self) -> str:
        """Human-readable model provenance and limits."""
        ...

    def evaluate(self, tree: TreeRecord) -> StemResult:
        """Evaluate one tree and return volume and log rows."""
        ...


@dataclass(frozen=True)
class LogRecord:
    """One bucked log.

    Attributes
    ----------
    tree_id : str
        Parent tree identifier.
    block_id : str
        Parent block identifier.
    log_id : str
        Deterministic log identifier.
    log_index : int
        One-based log position from the stump upward.
    length_m : float
        Log length in metres.
    volume_m3 : float
        Log volume in cubic metres.
    product : str
        Simple product class (``sawlog`` or ``pulp``).
    grade_hint : str | None
        Producer grade hint, when supplied.
    """

    tree_id: str
    block_id: str
    log_id: str
    log_index: int
    length_m: float
    volume_m3: float
    product: str
    grade_hint: str | None

    def to_dict(self) -> dict[str, object]:
        """Return the log as a JSON-serializable mapping."""
        return {
            "tree_id": self.tree_id,
            "block_id": self.block_id,
            "log_id": self.log_id,
            "log_index": self.log_index,
            "length_m": self.length_m,
            "volume_m3": self.volume_m3,
            "product": self.product,
            "grade_hint": self.grade_hint,
        }


@dataclass(frozen=True)
class StemResult:
    """Volume and log rows for one tree.

    Attributes
    ----------
    tree_id : str
        Tree identifier.
    block_id : str
        Block identifier.
    species_code : str
        Producer species code.
    dbh_cm : float
        Diameter at breast height.
    height_m : float
        Total height.
    gross_volume_m3 : float
        Gross stem volume.
    merchantable_volume_m3 : float
        Merchantable stem volume.
    logs : tuple[LogRecord, ...]
        Bucked log rows.
    model_name : str
        Model name.
    model_version : str
        Model version.
    model_provenance : str
        Model provenance and limits.
    """

    tree_id: str
    block_id: str
    species_code: str
    dbh_cm: float
    height_m: float
    gross_volume_m3: float
    merchantable_volume_m3: float
    logs: tuple[LogRecord, ...]
    model_name: str
    model_version: str
    model_provenance: str

    def to_dict(self) -> dict[str, object]:
        """Return the tree result as a JSON-serializable mapping."""
        return {
            "tree_id": self.tree_id,
            "block_id": self.block_id,
            "species_code": self.species_code,
            "dbh_cm": self.dbh_cm,
            "height_m": self.height_m,
            "gross_volume_m3": self.gross_volume_m3,
            "merchantable_volume_m3": self.merchantable_volume_m3,
            "log_count": len(self.logs),
            "logs": [log.to_dict() for log in self.logs],
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_provenance": self.model_provenance,
        }


@dataclass(frozen=True)
class StemBlockSummary:
    """Volume and log summary for one block.

    Attributes
    ----------
    block_id : str
        Block identifier.
    tree_count : int
        Number of evaluated trees.
    gross_volume_m3 : float
        Sum of gross stem volume.
    merchantable_volume_m3 : float
        Sum of merchantable volume.
    log_count : int
        Number of log rows.
    product_counts : dict[str, int]
        Log counts by product.
    species_counts : dict[str, int]
        Tree counts by species.
    work_required_m3 : float | None
        Scenario terminal volume.
    volume_status : str
        ``ok``, ``warning``, or ``unknown``.
    volume_difference_fraction : float | None
        Relative difference from ``work_required``.
    """

    block_id: str
    tree_count: int
    gross_volume_m3: float
    merchantable_volume_m3: float
    log_count: int
    product_counts: dict[str, int]
    species_counts: dict[str, int]
    work_required_m3: float | None
    volume_status: str
    volume_difference_fraction: float | None

    def to_dict(self) -> dict[str, object]:
        """Return the block summary as a JSON-serializable mapping."""
        return {
            "block_id": self.block_id,
            "tree_count": self.tree_count,
            "gross_volume_m3": self.gross_volume_m3,
            "merchantable_volume_m3": self.merchantable_volume_m3,
            "log_count": self.log_count,
            "product_counts": self.product_counts,
            "species_counts": self.species_counts,
            "work_required_m3": self.work_required_m3,
            "volume_status": self.volume_status,
            "volume_difference_fraction": self.volume_difference_fraction,
        }


@dataclass(frozen=True)
class StemInventory:
    """Stem results and block reconciliation for one pinned inventory.

    Attributes
    ----------
    stem_id : str
        Deterministic stem-run identifier.
    generated_utc : str
        Generation timestamp.
    scenario_path : Path
        Scenario YAML.
    inventory_id : str
        Inventory identifier.
    inventory_sha256 : str
        Inventory digest.
    model_name : str
        Model name.
    model_version : str
        Model version.
    model_provenance : str
        Model provenance and limits.
    tolerance : float
        Relative reconciliation tolerance.
    trees : tuple[StemResult, ...]
        Per-tree results.
    blocks : tuple[StemBlockSummary, ...]
        Per-block summaries.
    warnings : tuple[str, ...]
        Non-fatal observations.
    caveats : tuple[str, ...]
        Model and screening caveats.
    """

    stem_id: str
    generated_utc: str
    scenario_path: Path
    inventory_id: str
    inventory_sha256: str
    model_name: str
    model_version: str
    model_provenance: str
    tolerance: float
    trees: tuple[StemResult, ...]
    blocks: tuple[StemBlockSummary, ...]
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the stem manifest as a JSON-serializable mapping."""
        return {
            "schema_version": STEM_SCHEMA,
            "stem_id": self.stem_id,
            "generated_utc": self.generated_utc,
            "scenario_path": str(self.scenario_path),
            "inventory_id": self.inventory_id,
            "inventory_sha256": self.inventory_sha256,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_provenance": self.model_provenance,
            "tolerance": self.tolerance,
            "tree_count": len(self.trees),
            "log_count": sum(len(tree.logs) for tree in self.trees),
            "gross_volume_m3": sum(tree.gross_volume_m3 for tree in self.trees),
            "merchantable_volume_m3": sum(tree.merchantable_volume_m3 for tree in self.trees),
            "trees": [tree.to_dict() for tree in self.trees],
            "blocks": [block.to_dict() for block in self.blocks],
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
        }


@dataclass(frozen=True)
class ReferenceStemModel:
    """Reference form-factor stem model.

    This model exists to exercise the volume/bucking pipeline. It is **not** a
    calibrated species-specific taper or merchantability model.

    Attributes
    ----------
    form_factor : float
        Multiplier applied to basal area times height.
    stump_height_m : float
        Stump height excluded from the merchantable stem.
    log_length_m : float
        Target log length.
    sawlog_min_dbh_cm : float
        Minimum DBH for the ``sawlog`` product class.
    """

    name: str = "reference_form_factor"
    version: str = "0.1.0"
    provenance: str = (
        "Reference form-factor model; synthetic scaffold, not a calibrated "
        "species-specific taper or merchantability model."
    )
    form_factor: float = DEFAULT_FORM_FACTOR
    stump_height_m: float = DEFAULT_STUMP_HEIGHT_M
    log_length_m: float = DEFAULT_LOG_LENGTH_M
    sawlog_min_dbh_cm: float = DEFAULT_SAWLOG_MIN_DBH_CM

    def __post_init__(self) -> None:
        for field, value in (
            ("form_factor", self.form_factor),
            ("stump_height_m", self.stump_height_m),
            ("log_length_m", self.log_length_m),
            ("sawlog_min_dbh_cm", self.sawlog_min_dbh_cm),
        ):
            if not math.isfinite(value) or value <= 0:
                raise StemModelError(f"{field} must be positive and finite.")

    def evaluate(self, tree: TreeRecord) -> StemResult:
        """Evaluate one tree with the reference form-factor model."""
        if not math.isfinite(tree.dbh_cm) or tree.dbh_cm <= 0:
            raise StemModelError(f"Tree {tree.tree_id!r} has invalid DBH.")
        if not math.isfinite(tree.height_m) or tree.height_m <= 0:
            raise StemModelError(f"Tree {tree.tree_id!r} has invalid height.")
        basal_area_m2 = math.pi / 4.0 * (tree.dbh_cm / 100.0) ** 2
        gross = self.form_factor * basal_area_m2 * tree.height_m
        merchantable_height = tree.merchantable_height_m or tree.height_m
        merchantable_length = merchantable_height - self.stump_height_m
        if merchantable_length <= 0:
            raise StemModelError(
                f"Tree {tree.tree_id!r} has no merchantable length after the stump."
            )
        if merchantable_height > tree.height_m + 1e-9:
            raise StemModelError(f"Tree {tree.tree_id!r} merchantable height exceeds total height.")
        merchantable = gross * merchantable_length / tree.height_m
        product = "sawlog" if tree.dbh_cm >= self.sawlog_min_dbh_cm else "pulp"
        logs = self._buck(tree, merchantable_length, merchantable, product)
        return StemResult(
            tree_id=tree.tree_id,
            block_id=tree.block_id,
            species_code=tree.species_code,
            dbh_cm=tree.dbh_cm,
            height_m=tree.height_m,
            gross_volume_m3=gross,
            merchantable_volume_m3=merchantable,
            logs=logs,
            model_name=self.name,
            model_version=self.version,
            model_provenance=self.provenance,
        )

    def _buck(
        self,
        tree: TreeRecord,
        merchantable_length: float,
        merchantable_volume: float,
        product: str,
    ) -> tuple[LogRecord, ...]:
        lengths: list[float] = []
        remaining = merchantable_length
        while remaining > 1e-9:
            length = min(self.log_length_m, remaining)
            lengths.append(length)
            remaining -= length
        if not lengths:
            lengths = [merchantable_length]
        volume_per_m = merchantable_volume / merchantable_length
        return tuple(
            LogRecord(
                tree_id=tree.tree_id,
                block_id=tree.block_id,
                log_id=f"{tree.tree_id}-L{index:02d}",
                log_index=index,
                length_m=length,
                volume_m3=volume_per_m * length,
                product=product,
                grade_hint=tree.grade_hint,
            )
            for index, length in enumerate(lengths, start=1)
        )


def build_stem_inventory(
    scenario_path: str | Path,
    *,
    model: StemModel | None = None,
    tolerance: float = DEFAULT_RECONCILIATION_TOLERANCE,
    require_reconciled: bool = False,
    generated_utc: str | None = None,
) -> StemInventory:
    """Derive stem volumes and log rows for a pinned tree inventory.

    Parameters
    ----------
    scenario_path : str | Path
        Scenario YAML with a tree-inventory pin.
    model : StemModel | None, optional
        Stem model. Defaults to :class:`ReferenceStemModel`.
    tolerance : float, optional
        Relative tolerance for block-volume reconciliation.
    require_reconciled : bool, optional
        Refuse when a block volume warning occurs.
    generated_utc : str | None, optional
        Generation timestamp.

    Returns
    -------
    StemInventory
        Per-tree volumes, logs, block summaries, and warnings.

    Raises
    ------
    StemModelError
        If a tree cannot be evaluated or strict reconciliation fails.
    """
    if not math.isfinite(tolerance) or tolerance < 0:
        raise StemModelError("Reconciliation tolerance must be finite and non-negative.")
    scenario_file = Path(scenario_path).expanduser().resolve()
    try:
        mapping = map_tree_inventory(scenario_file, tolerance=tolerance)
        scenario = load_scenario(scenario_file)
    except Exception as exc:  # noqa: BLE001 - preserve dependency error text
        raise StemModelError(str(exc)) from exc
    pin = scenario.tree_inventory
    if pin is None:
        raise StemModelError("Scenario has no tree_inventory pin.")
    inventory = _load_pinned_inventory(scenario_file, pin.inventory_path, pin.metadata_path)
    selected_model = model or ReferenceStemModel()
    trees = tuple(selected_model.evaluate(row) for row in inventory.rows)
    by_block: dict[str, list[StemResult]] = {}
    for tree in trees:
        by_block.setdefault(tree.block_id, []).append(tree)
    blocks: list[StemBlockSummary] = []
    warnings: list[str] = []
    for block in scenario.blocks:
        results = by_block.get(block.id, [])
        gross = sum(result.gross_volume_m3 for result in results)
        merchantable = sum(result.merchantable_volume_m3 for result in results)
        logs = [log for result in results for log in result.logs]
        status, difference = _volume_status(merchantable, block.work_required, tolerance)
        if status == "warning":
            warnings.append(f"{block.id}: merchantable volume differs from work_required")
        blocks.append(
            StemBlockSummary(
                block_id=block.id,
                tree_count=len(results),
                gross_volume_m3=gross,
                merchantable_volume_m3=merchantable,
                log_count=len(logs),
                product_counts=dict(Counter(log.product for log in logs)),
                species_counts=dict(Counter(result.species_code for result in results)),
                work_required_m3=block.work_required if block.work_required > 0 else None,
                volume_status=status,
                volume_difference_fraction=difference,
            )
        )
    warning_blocks = [block.block_id for block in blocks if block.volume_status == "warning"]
    if mapping.blocks_without_trees:
        warnings.append("Blocks without trees: " + ", ".join(mapping.blocks_without_trees))
    if require_reconciled and warning_blocks:
        raise StemModelError(
            "Stem volume reconciliation failed for block(s): " + ", ".join(warning_blocks)
        )
    timestamp = generated_utc or datetime.now(UTC).isoformat()
    material = {
        "inventory_id": inventory.metadata.inventory_id,
        "inventory_sha256": inventory.sha256,
        "model": selected_model.name,
        "model_version": selected_model.version,
        "trees": [tree.to_dict() for tree in trees],
        "blocks": [block.to_dict() for block in blocks],
    }
    stem_id = (
        "fhops-stems-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    return StemInventory(
        stem_id=stem_id,
        generated_utc=timestamp,
        scenario_path=scenario_file,
        inventory_id=inventory.metadata.inventory_id,
        inventory_sha256=inventory.sha256,
        model_name=selected_model.name,
        model_version=selected_model.version,
        model_provenance=selected_model.provenance,
        tolerance=tolerance,
        trees=trees,
        blocks=tuple(blocks),
        warnings=tuple(warnings),
        caveats=(
            "Reference form-factor model only; not an operational taper or merchantability model.",
            "Log products and grades are simple placeholders for the simulation path.",
            *pin.caveats,
        ),
    )


def write_stem_inventory(stem: StemInventory, out_dir: Path) -> dict[str, Path]:
    """Write stem log rows and the stem manifest.

    Parameters
    ----------
    stem : StemInventory
        Stem result.
    out_dir : Path
        Output directory.

    Returns
    -------
    dict[str, Path]
        Paths keyed by ``logs``, ``blocks``, and ``manifest``.
    """
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    logs_path = output / "tree_stems.csv"
    log_columns = (
        "tree_id",
        "block_id",
        "log_id",
        "log_index",
        "length_m",
        "volume_m3",
        "product",
        "grade_hint",
    )
    with logs_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=log_columns, extrasaction="ignore")
        writer.writeheader()
        for tree in stem.trees:
            writer.writerows(log.to_dict() for log in tree.logs)
    blocks_path = output / "tree_stem_blocks.csv"
    block_columns = (
        "block_id",
        "tree_count",
        "gross_volume_m3",
        "merchantable_volume_m3",
        "log_count",
        "work_required_m3",
        "volume_status",
        "volume_difference_fraction",
    )
    with blocks_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=block_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(block.to_dict() for block in stem.blocks)
    manifest_path = output / "tree_stems.json"
    manifest_path.write_text(
        json.dumps(stem.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"logs": logs_path, "blocks": blocks_path, "manifest": manifest_path}


def _load_pinned_inventory(
    scenario_path: Path,
    inventory_path: str,
    metadata_path: str,
) -> TreeInventory:
    inventory = Path(inventory_path)
    metadata = Path(metadata_path)
    if not inventory.is_absolute():
        inventory = (scenario_path.parent / inventory).resolve()
    if not metadata.is_absolute():
        metadata = (scenario_path.parent / metadata).resolve()
    scenario = load_scenario(scenario_path)
    return load_tree_inventory(
        inventory,
        metadata_path=metadata,
        block_ids=set(scenario.block_ids()),
    )


def _volume_status(observed: float, expected: float, tolerance: float) -> tuple[str, float | None]:
    if expected <= 0:
        return "unknown", None
    difference = (observed - expected) / expected
    return ("ok" if abs(difference) <= tolerance else "warning"), difference
