"""Harvest prescriptions and derived cut lists for the Tree Lab sandbox.

A case inventory is the **stand**, and ``case.json.harvest`` declares the
treatment. The runner derives the cut list deterministically:

* ``clear_cut`` — every stem is cut;
* ``partial`` — a subset is cut according to a marking rule and a target
  basal-area fraction.

The derived cut list is written into the run directory and fed to
``fhops tree system`` / ``fhops tree scene``. FHOPS core has no leave-tree
concept, so this derivation lives in the sandbox and is recorded in ``run.json``.
"""

from __future__ import annotations

import csv
import json
import math
import random
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fhops.scenario.io import load_scenario
from fhops.stem import ReferenceStemModel
from fhops.tree_inventory import TreeInventory, TreeRecord, load_tree_inventory
from fhops.tree_mapping import register_tree_inventory
from sandbox.tree_lab.cases import Case, _relativize_pin, sha256_file

HARVEST_SCHEMA = "fhops.tree_lab.harvest.v1"
MARKING_RULES = ("all", "proportional", "from_below", "diameter_limit")
DEFAULT_RULE = "all"

__all__ = [
    "HARVEST_SCHEMA",
    "DerivedInputs",
    "HarvestError",
    "basal_area",
    "derive_cut",
    "derive_residual",
    "harvest_prescription",
    "select_cut",
    "write_run_inputs",
]

INVENTORY_FIELDS = [
    "tree_id",
    "block_id",
    "x_m",
    "y_m",
    "elevation_m",
    "species_code",
    "dbh_cm",
    "height_m",
    "crown_radius_m",
    "status",
    "confidence",
    "source_id",
    "source_tile_id",
    "merchantable_height_m",
    "defect",
    "grade_hint",
]


class HarvestError(RuntimeError):
    """Raised when a harvest prescription is invalid or cannot be applied."""


@dataclass(slots=True)
class DerivedInputs:
    """Inputs derived for one run.

    Attributes
    ----------
    scenario : Path
        Scenario with the derived cut-list inventory pinned.
    assignments : Path
        Assignments CSV for the cut list.
    cut_list : Path
        Derived cut-list inventory CSV.
    cut_count : int
        Number of trees cut.
    residual_count : int
        Number of trees left standing.
    cut_volume_m3 : float
        Merchantable volume of the cut list.
    stand_volume_m3 : float
        Merchantable volume of the whole stand.
    cut_basal_area_m2 : float
        Basal area removed.
    stand_basal_area_m2 : float
        Basal area of the whole stand.
    """

    scenario: Path
    assignments: Path
    cut_list: Path
    cut_count: int
    residual_count: int
    cut_volume_m3: float
    stand_volume_m3: float
    cut_basal_area_m2: float
    stand_basal_area_m2: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": str(self.scenario),
            "assignments": str(self.assignments),
            "cut_list": str(self.cut_list),
            "cut_count": self.cut_count,
            "residual_count": self.residual_count,
            "cut_volume_m3": round(self.cut_volume_m3, 6),
            "stand_volume_m3": round(self.stand_volume_m3, 6),
            "cut_basal_area_m2": round(self.cut_basal_area_m2, 6),
            "stand_basal_area_m2": round(self.stand_basal_area_m2, 6),
            "removed_basal_area_fraction": (
                round(self.cut_basal_area_m2 / self.stand_basal_area_m2, 6)
                if self.stand_basal_area_m2
                else None
            ),
        }


def basal_area(tree: TreeRecord) -> float:
    """Return one tree's basal area in square metres."""
    return math.pi / 4.0 * (tree.dbh_cm / 100.0) ** 2


def harvest_prescription(case: Case) -> dict[str, Any]:
    """Return the case's harvest block, defaulting to a clear cut."""
    harvest = case.manifest.get("harvest")
    if harvest is None:
        return {"type": "clear_cut", "marking_rule": "all", "target_basal_area_fraction": 1.0}
    if not isinstance(harvest, dict):
        raise HarvestError("case.json harvest must be an object.")
    kind = harvest.get("type")
    if kind not in ("clear_cut", "partial"):
        raise HarvestError(f"Unsupported harvest type {kind!r}.")
    if kind == "clear_cut":
        return {**harvest, "marking_rule": "all", "target_basal_area_fraction": 1.0}
    rule = harvest.get("marking_rule")
    if rule not in MARKING_RULES or rule == "all":
        raise HarvestError(f"Partial harvest needs a marking rule in {MARKING_RULES}.")
    target = harvest.get("target_basal_area_fraction")
    if not isinstance(target, (int, float)) or not 0 < float(target) < 1:
        raise HarvestError("target_basal_area_fraction must be between 0 and 1.")
    if rule == "diameter_limit" and "diameter_limit_cm" not in harvest:
        raise HarvestError("diameter_limit requires diameter_limit_cm.")
    return harvest


def select_cut(
    trees: list[TreeRecord],
    *,
    target_ba_fraction: float,
    rule: str,
    seed: int = 20261030,
    diameter_limit_cm: float | None = None,
) -> list[TreeRecord]:
    """Select the trees to remove for a target basal-area fraction.

    Parameters
    ----------
    trees : list[TreeRecord]
        Full stand.
    target_ba_fraction : float
        Fraction of stand basal area to remove, in ``(0, 1]``.
    rule : str
        ``all``, ``proportional``, ``from_below``, or ``diameter_limit``.
    seed : int, optional
        RNG seed for ``proportional``.
    diameter_limit_cm : float, optional
        Minimum DBH removed for ``diameter_limit``.

    Returns
    -------
    list[TreeRecord]
        The cut list, sorted by tree id.
    """
    if not 0 < target_ba_fraction <= 1:
        raise HarvestError("target_ba_fraction must be in (0, 1].")
    if rule == "all":
        return sorted(trees, key=lambda tree: tree.tree_id)
    if rule == "diameter_limit":
        if diameter_limit_cm is None:
            raise HarvestError("diameter_limit requires diameter_limit_cm.")
        return sorted(
            (tree for tree in trees if tree.dbh_cm >= diameter_limit_cm),
            key=lambda tree: tree.tree_id,
        )
    total = sum(basal_area(tree) for tree in trees)
    target = total * target_ba_fraction
    if rule == "proportional":
        order = list(trees)
        random.Random(seed).shuffle(order)
    elif rule == "from_below":
        order = sorted(trees, key=lambda tree: (tree.dbh_cm, tree.height_m))
    else:
        raise HarvestError(f"Unknown marking rule {rule!r}.")
    cut: list[TreeRecord] = []
    removed = 0.0
    for tree in order:
        cut.append(tree)
        removed += basal_area(tree)
        if removed >= target:
            break
    return sorted(cut, key=lambda tree: tree.tree_id)


def derive_cut(stand: TreeInventory, prescription: dict[str, Any]) -> list[TreeRecord]:
    """Apply a prescription to a stand and return the cut list."""
    return select_cut(
        list(stand.rows),
        target_ba_fraction=float(prescription.get("target_basal_area_fraction", 1.0)),
        rule=str(prescription.get("marking_rule", "all")),
        seed=int(prescription.get("seed", 20261030)),
        diameter_limit_cm=prescription.get("diameter_limit_cm"),
    )


def derive_residual(stand: TreeInventory, prescription: dict[str, Any]) -> list[TreeRecord]:
    """Return the trees left standing after the prescription."""
    cut_ids = {tree.tree_id for tree in derive_cut(stand, prescription)}
    return [tree for tree in stand.rows if tree.tree_id not in cut_ids]


def _write_cut_inventory(case_id: str, cut: list[TreeRecord], directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    inventory = directory / "cut_list.csv"
    with inventory.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVENTORY_FIELDS, lineterminator="\n")
        writer.writeheader()
        for tree in cut:
            writer.writerow(
                {
                    "tree_id": tree.tree_id,
                    "block_id": tree.block_id,
                    "x_m": tree.x_m,
                    "y_m": tree.y_m,
                    "elevation_m": tree.elevation_m,
                    "species_code": tree.species_code,
                    "dbh_cm": tree.dbh_cm,
                    "height_m": tree.height_m,
                    "crown_radius_m": tree.crown_radius_m,
                    "status": tree.status,
                    "confidence": tree.confidence,
                    "source_id": tree.source_id,
                    "source_tile_id": tree.source_tile_id,
                    "merchantable_height_m": "",
                    "defect": "",
                    "grade_hint": "",
                }
            )
    metadata = {
        "schema_version": "fhops.tree.inventory.v1",
        "inventory_id": f"{case_id}-cut-list",
        "generated_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_id": f"derived-{case_id}",
        "producer": "FHOPS Tree Lab harvest prescription",
        "method": "Derived cut list from a stand and a declared harvest prescription.",
        "crs": "EPSG:3005",
        "units": {"x_y": "m", "elevation": "m", "dbh": "cm", "height": "m", "crown_radius": "m"},
        "review_status": "not_reviewed",
        "block_ids": sorted({tree.block_id for tree in cut}),
        "tree_count": len(cut),
        "inventory_sha256": sha256_file(inventory),
        "caveats": ["Derived cut list; not a surveyed stand or tree map."],
    }
    meta_path = directory / "cut_list.meta.json"
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return inventory, meta_path


def _write_scenario(
    case: Case,
    scenario_dir: Path,
    inventory: Path,
    metadata: Path,
    *,
    block_id: str,
    volume: float,
    stem_count: int,
    area_ha: float,
) -> Path:
    source = load_scenario(case.path("scenario"))
    shutil.copytree(case.path("scenario").parent / "data", scenario_dir / "data")
    blocks_path = scenario_dir / "data" / "blocks.csv"
    with blocks_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0].keys()) if rows else []
    for row in rows:
        if row.get("id") == block_id:
            row["work_required"] = f"{volume:.6f}"
            row["avg_stem_size_m3"] = f"{volume / stem_count:.6f}" if stem_count else "0"
            row["volume_per_ha_m3"] = f"{volume / area_ha:.6f}" if area_ha else "0"
            row["stem_density_per_ha"] = f"{stem_count / area_ha:.6f}" if area_ha else "0"
    with blocks_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    scenario_path = scenario_dir / "scenario.yaml"
    scenario_path.write_text(
        f"""name: {case.label} (derived cut list)
num_days: {source.num_days}
start_date: {source.start_date or "2026-01-01"}
data:
  blocks: data/blocks.csv
  machines: data/machines.csv
  landings: data/landings.csv
  calendar: data/calendar.csv
  prod_rates: data/prod_rates.csv
  harvest_systems: data/harvest_systems.yaml
""",
        encoding="utf-8",
    )
    register_tree_inventory(scenario_path, inventory, metadata_path=metadata)
    _relativize_pin(scenario_path, inventory, metadata)
    return scenario_path


def write_run_inputs(case: Case, run_dir: Path) -> DerivedInputs:
    """Derive and write the cut-list scenario, inventory, and assignments."""
    prescription = harvest_prescription(case)
    stand = load_tree_inventory(case.path("inventory"), metadata_path=case.path("metadata"))
    cut = derive_cut(stand, prescription)
    if not cut:
        raise HarvestError("The harvest prescription selected no trees.")
    model = ReferenceStemModel()
    cut_volume = sum(model.evaluate(tree).merchantable_volume_m3 for tree in cut)
    stand_volume = sum(model.evaluate(tree).merchantable_volume_m3 for tree in stand.rows)
    cut_ba = sum(basal_area(tree) for tree in cut)
    stand_ba = sum(basal_area(tree) for tree in stand.rows)

    inputs_dir = run_dir / "inputs"
    inventory, metadata = _write_cut_inventory(case.case_id, cut, inputs_dir / "tree_inventory")
    scenario_path = _write_scenario(
        case,
        inputs_dir / "scenario",
        inventory,
        metadata,
        block_id=str(case.manifest["block_id"]),
        volume=cut_volume,
        stem_count=len(cut),
        area_ha=float(case.manifest.get("stand", {}).get("area_ha", 1.0)),
    )
    assignments = inputs_dir / "assignments.csv"
    with assignments.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["machine_id", "block_id", "day", "shift_id", "assigned", "production"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "machine_id": case.manifest["system_args"]["feller"],
                "block_id": case.manifest["block_id"],
                "day": 1,
                "shift_id": "S1",
                "assigned": 1,
                "production": f"{cut_volume:.6f}",
            }
        )
    return DerivedInputs(
        scenario=scenario_path,
        assignments=assignments,
        cut_list=inventory,
        cut_count=len(cut),
        residual_count=len(stand.rows) - len(cut),
        cut_volume_m3=cut_volume,
        stand_volume_m3=stand_volume,
        cut_basal_area_m2=cut_ba,
        stand_basal_area_m2=stand_ba,
    )
