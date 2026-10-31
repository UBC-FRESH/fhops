"""Generate deterministic synthetic AFRF and MKRF demo cases for the Tree Lab.

The generator produces a complete FHOPS scenario (CSV inputs, scenario YAML, and
a ``fhops.tree.inventory.v1`` tree list with metadata) for two public research
forests:

* AFRF Gavin Lake (``AFRF_GAVIN_485``, 6.91 ha, age 77 in 2019, ``SBSdw1``);
* Malcolm Knapp Research Forest (``MKRF_MATURE_868``, 6.14 ha, age 74 in 2020,
  ``CWHdm``).

What is real and what is synthetic
----------------------------------
Real: the stand-level attributes above are published research-forest values,
and the case centre is the public forest location reprojected to BC Albers
(EPSG:3005).

Synthetic: the tree list, the block footprint rectangle, the elevation surface,
and every machine parameter. The footprint is a placeholder rectangle of the
published block area centred on the forest location; it is **not** the surveyed
block polygon. The tree list is a plot-conditioned synthetic sample, not an
ITD/ITC product and not a tree map.

Volume reconciliation uses :class:`fhops.stem.ReferenceStemModel`, the same
reference model the FHOPS tree-scale pipeline uses, so the block
``work_required`` matches the merchantable total exactly.

Usage
-----
``python -m sandbox.scripts.generate_cases --out sandbox/cases``
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fhops.stem import ReferenceStemModel
from fhops.tree_inventory import TREE_INVENTORY_SCHEMA, TreeRecord

CRS = "EPSG:3005"
SCHEMA_VERSION = "fhops.tree_lab.case.v1"
NUM_DAYS = 7


@dataclass(frozen=True, slots=True)
class SpeciesProfile:
    """Allometric placeholder for one species.

    Attributes
    ----------
    code : str
        FHOPS species code preserved verbatim in the inventory.
    weight : float
        Relative sampling weight in the synthetic tree list.
    height_a, height_b : float
        Placeholder height-diameter curve ``height = a * dbh ** b``.
    crown_a, crown_b : float
        Placeholder crown-radius curve ``radius = a * dbh + b``.
    """

    code: str
    weight: float
    height_a: float
    height_b: float
    crown_a: float
    crown_b: float


@dataclass(frozen=True, slots=True)
class CaseSpec:
    """Inputs describing one synthetic demo case.

    Attributes
    ----------
    case_id : str
        Stable sandbox case identifier.
    label : str
        Human-readable case label shown in the UI.
    block_id : str
        FHOPS block identifier.
    landing_id : str
        FHOPS landing identifier.
    area_ha : float
        Published block area in hectares.
    age_years : int
        Published stand age and reference year.
    bec_zone : str
        Published biogeoclimatic variant.
    latitude, longitude : float
        Public research-forest centre in WGS84 degrees.
    tree_count : int
        Number of synthetic sample trees to generate.
    dbh_median_cm, dbh_sigma : float
        Lognormal diameter parameters in centimetres.
    elevation_base_m : float
        Synthetic ground elevation at the south-west corner in metres.
    slope_percent : float
        Reported (not simulated) ground slope used in block evidence.
    species : tuple[SpeciesProfile, ...]
        Species mix for the synthetic list.
    seed : int
        Deterministic RNG seed.
    system_args : dict[str, Any]
        Machine/system parameters passed to ``fhops tree system``.
    """

    case_id: str
    label: str
    block_id: str
    landing_id: str
    area_ha: float
    age_years: int
    bec_zone: str
    latitude: float
    longitude: float
    tree_count: int
    dbh_median_cm: float
    dbh_sigma: float
    elevation_base_m: float
    slope_percent: float
    species: tuple[SpeciesProfile, ...]
    seed: int
    system_args: dict[str, Any]


def _afrf_species() -> tuple[SpeciesProfile, ...]:
    return (
        SpeciesProfile("Fd", 0.45, 1.35, 0.85, 0.075, 0.6),
        SpeciesProfile("Pl", 0.25, 1.50, 0.78, 0.055, 0.5),
        SpeciesProfile("Sw", 0.15, 1.45, 0.80, 0.070, 0.5),
        SpeciesProfile("At", 0.08, 1.20, 0.85, 0.065, 0.5),
        SpeciesProfile("Bl", 0.07, 1.30, 0.82, 0.060, 0.4),
    )


def _mkrf_species() -> tuple[SpeciesProfile, ...]:
    return (
        SpeciesProfile("Cw", 0.35, 1.35, 0.85, 0.080, 0.7),
        SpeciesProfile("Hw", 0.30, 1.45, 0.82, 0.075, 0.6),
        SpeciesProfile("Fd", 0.15, 1.35, 0.85, 0.075, 0.6),
        SpeciesProfile("Bg", 0.10, 1.40, 0.82, 0.070, 0.6),
        SpeciesProfile("Dr", 0.10, 1.15, 0.85, 0.065, 0.5),
    )


def case_specs() -> tuple[CaseSpec, ...]:
    """Return the two demo case specifications."""
    return (
        CaseSpec(
            case_id="afrf-gavin",
            label="AFRF Gavin Lake — synthetic tree list",
            block_id="AFRF_GAVIN_485",
            landing_id="L1",
            area_ha=6.91,
            age_years=77,
            bec_zone="SBSdw1",
            latitude=52.4667,
            longitude=-121.6167,
            tree_count=900,
            dbh_median_cm=34.0,
            dbh_sigma=0.28,
            elevation_base_m=780.0,
            slope_percent=9.0,
            species=_afrf_species(),
            seed=20261030,
            system_args={
                "feller": "H1",
                "skidders": ["H2", "H3"],
                "processors": ["H5"],
                "loader": "H4",
                "bunch_volume_m3": 8.0,
                "rate_model": "calibrated",
                "shift_days": 5,
                "shifts_per_day": 2,
                "hours_per_shift": 10,
                "truck_capacity_m3": 30.0,
                "truck_count": 2,
                "truck_cycle_s": 3600.0,
                "landing_capacity_m3": 120.0,
                "skidder_capacity_m3": 40.0,
            },
        ),
        CaseSpec(
            case_id="mkrf",
            label="MKRF Malcolm Knapp — synthetic tree list",
            block_id="MKRF_MATURE_868",
            landing_id="L1",
            area_ha=6.14,
            age_years=74,
            bec_zone="CWHdm",
            latitude=49.2667,
            longitude=-122.5667,
            tree_count=800,
            dbh_median_cm=46.0,
            dbh_sigma=0.26,
            elevation_base_m=320.0,
            slope_percent=18.0,
            species=_mkrf_species(),
            seed=20261031,
            system_args={
                "feller": "H1",
                "skidders": ["H2", "H3"],
                "processors": ["H5"],
                "loader": "H4",
                "bunch_volume_m3": 10.0,
                "rate_model": "calibrated",
                "shift_days": 5,
                "shifts_per_day": 2,
                "hours_per_shift": 10,
                "truck_capacity_m3": 30.0,
                "truck_count": 2,
                "truck_cycle_s": 5400.0,
                "landing_capacity_m3": 120.0,
                "skidder_capacity_m3": 40.0,
            },
        ),
    )


def _project(latitude: float, longitude: float) -> tuple[float, float]:
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    x, y = transformer.transform(longitude, latitude)
    return float(x), float(y)


def _pick_species(rng: random.Random, spec: CaseSpec) -> SpeciesProfile:
    total = sum(item.weight for item in spec.species)
    target = rng.random() * total
    cumulative = 0.0
    for item in spec.species:
        cumulative += item.weight
        if target <= cumulative:
            return item
    return spec.species[-1]


def _make_trees(spec: CaseSpec) -> list[TreeRecord]:
    rng = random.Random(spec.seed)
    cx, cy = _project(spec.latitude, spec.longitude)
    area_m2 = spec.area_ha * 10_000.0
    aspect = 1.3
    width = math.sqrt(area_m2 * aspect)
    height = area_m2 / width
    x0 = cx - width / 2.0
    y0 = cy - height / 2.0
    cols = max(1, round(math.sqrt(spec.tree_count * aspect)))
    rows = max(1, math.ceil(spec.tree_count / cols))
    dx = width / cols
    dy = height / rows

    trees: list[TreeRecord] = []
    for index in range(spec.tree_count):
        row, col = divmod(index, cols)
        if row >= rows:
            break
        jitter_x = rng.uniform(-0.35, 0.35) * dx
        jitter_y = rng.uniform(-0.35, 0.35) * dy
        # Two gentle clumps so the scene is not a perfect lattice.
        clump = 6.0 * math.sin(col / 7.0) * math.cos(row / 9.0)
        x = min(x0 + width - 0.5, max(x0 + 0.5, x0 + (col + 0.5) * dx + jitter_x + clump))
        y = min(y0 + height - 0.5, max(y0 + 0.5, y0 + (row + 0.5) * dy + jitter_y + clump))
        species = _pick_species(rng, spec)
        dbh = min(95.0, max(12.0, rng.lognormvariate(math.log(spec.dbh_median_cm), spec.dbh_sigma)))
        height_m = species.height_a * dbh**species.height_b
        height_m *= rng.uniform(0.92, 1.08)
        crown = max(0.6, (species.crown_a * dbh + species.crown_b) * rng.uniform(0.85, 1.15))
        elevation = (
            spec.elevation_base_m
            + 0.04 * (x - x0)
            + 0.03 * (y - y0)
            + 1.5 * math.sin(x / 40.0)
            + rng.uniform(-0.4, 0.4)
        )
        status = "live" if rng.random() > 0.03 else rng.choice(("snag", "dead"))
        trees.append(
            TreeRecord(
                tree_id=f"T{index + 1:05d}",
                block_id=spec.block_id,
                x_m=round(x, 2),
                y_m=round(y, 2),
                elevation_m=round(elevation, 2),
                species_code=species.code,
                dbh_cm=round(dbh, 1),
                height_m=round(height_m, 1),
                crown_radius_m=round(crown, 2),
                status=status,
                confidence=round(rng.uniform(0.82, 0.97), 2),
                source_id=f"synthetic-{spec.case_id}",
                source_tile_id="T01",
                merchantable_height_m=None,
                defect=None,
                grade_hint=None,
            )
        )
    return trees


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_inventory(
    spec: CaseSpec, case_dir: Path, trees: list[TreeRecord], total_volume: float
) -> tuple[Path, Path]:
    inventory = case_dir / "tree_inventory" / "tree_inventory.csv"
    fields = [
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
    rows = [
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
        for tree in trees
    ]
    _write_csv(inventory, fields, rows)
    digest = _sha256(inventory)
    metadata = {
        "schema_version": TREE_INVENTORY_SCHEMA,
        "inventory_id": f"{spec.case_id}-synthetic",
        "generated_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_id": f"synthetic-{spec.case_id}",
        "producer": "FHOPS Tree Lab synthetic generator",
        "method": (
            "Plot-conditioned deterministic synthetic point list; "
            "not an ITD/ITC segmentation product."
        ),
        "crs": CRS,
        "units": {
            "x_y": "m",
            "elevation": "m",
            "dbh": "cm",
            "height": "m",
            "crown_radius": "m",
        },
        "review_status": "not_reviewed",
        "block_ids": [spec.block_id],
        "tree_count": len(trees),
        "inventory_sha256": digest,
        "caveats": [
            "Synthetic tree list; not a surveyed stand, tree map, or ITD/ITC product.",
            "Block footprint is a placeholder rectangle of the published area, not the surveyed polygon.",
            f"Merchantable volume computed with the FHOPS reference stem model: {total_volume:.3f} m3.",
        ],
    }
    meta_path = inventory.with_name("tree_inventory.meta.json")
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return inventory, meta_path


def _write_scenario(spec: CaseSpec, case_dir: Path, total_volume: float, tree_count: int) -> Path:
    data_dir = case_dir / "scenario" / "data"
    avg_stem = total_volume / tree_count
    volume_per_ha = total_volume / spec.area_ha
    density = tree_count / spec.area_ha

    _write_csv(
        data_dir / "blocks.csv",
        [
            "id",
            "landing_id",
            "harvest_system_id",
            "work_required",
            "earliest_start",
            "latest_finish",
            "avg_stem_size_m3",
            "volume_per_ha_m3",
            "stem_density_per_ha",
            "ground_slope_percent",
        ],
        [
            {
                "id": spec.block_id,
                "landing_id": spec.landing_id,
                "harvest_system_id": "ground_fb_skid",
                "work_required": f"{total_volume:.6f}",
                "earliest_start": 1,
                "latest_finish": NUM_DAYS,
                "avg_stem_size_m3": f"{avg_stem:.6f}",
                "volume_per_ha_m3": f"{volume_per_ha:.6f}",
                "stem_density_per_ha": f"{density:.6f}",
                "ground_slope_percent": f"{spec.slope_percent:.1f}",
            }
        ],
    )
    _write_csv(
        data_dir / "machines.csv",
        ["id", "crew", "daily_hours", "operating_cost", "role"],
        [
            {
                "id": "H1",
                "crew": "CH1",
                "daily_hours": 24.0,
                "operating_cost": 950.0,
                "role": "feller_buncher",
            },
            {
                "id": "H2",
                "crew": "CH2",
                "daily_hours": 24.0,
                "operating_cost": 950.0,
                "role": "grapple_skidder",
            },
            {
                "id": "H3",
                "crew": "CH3",
                "daily_hours": 24.0,
                "operating_cost": 950.0,
                "role": "grapple_skidder",
            },
            {
                "id": "H5",
                "crew": "CH5",
                "daily_hours": 24.0,
                "operating_cost": 950.0,
                "role": "roadside_processor",
            },
            {
                "id": "H4",
                "crew": "CH4",
                "daily_hours": 24.0,
                "operating_cost": 950.0,
                "role": "loader",
            },
        ],
    )
    _write_csv(
        data_dir / "landings.csv",
        ["id", "daily_capacity"],
        [{"id": spec.landing_id, "daily_capacity": 1}],
    )
    _write_csv(
        data_dir / "calendar.csv",
        ["machine_id", "day", "available"],
        [
            {"machine_id": machine, "day": day, "available": 1}
            for machine in ("H1", "H2", "H3", "H4", "H5")
            for day in range(1, NUM_DAYS + 1)
        ],
    )
    _write_csv(
        data_dir / "prod_rates.csv",
        ["machine_id", "block_id", "rate"],
        [{"machine_id": "H1", "block_id": spec.block_id, "rate": 1000.0}],
    )
    (data_dir / "harvest_systems.yaml").write_text(
        """ground_fb_skid:
  system_id: ground_fb_skid
  loader_batch_volume_m3: 30.0
  role_headstart_shifts:
    roadside_processor: 0.0
    loader: 0.0
  role_counts:
    feller_buncher: 2
    grapple_skidder: 1
    roadside_processor: 3
    loader: 3
  jobs:
  - name: felling
    machine_role: feller_buncher
    prerequisites: []
  - name: primary_transport
    machine_role: grapple_skidder
    prerequisites:
    - felling
  - name: processing
    machine_role: roadside_processor
    prerequisites:
    - primary_transport
  - name: loading
    machine_role: loader
    prerequisites:
    - processing
""",
        encoding="utf-8",
    )
    scenario = case_dir / "scenario" / "scenario.yaml"
    scenario.write_text(
        f"""name: {spec.label}
num_days: {NUM_DAYS}
start_date: '2026-01-01'
data:
  blocks: data/blocks.csv
  machines: data/machines.csv
  landings: data/landings.csv
  calendar: data/calendar.csv
  prod_rates: data/prod_rates.csv
  harvest_systems: data/harvest_systems.yaml

geo:
  crs: {CRS}
  notes: Synthetic footprint rectangle of the published block area; not a surveyed polygon.
""",
        encoding="utf-8",
    )
    return scenario


def _write_case_manifest(
    spec: CaseSpec, case_dir: Path, total_volume: float, tree_count: int
) -> Path:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "case_id": spec.case_id,
        "label": spec.label,
        "block_id": spec.block_id,
        "landing_id": spec.landing_id,
        "scenario": "scenario/scenario.yaml",
        "inventory": "tree_inventory/tree_inventory.csv",
        "metadata": "tree_inventory/tree_inventory.meta.json",
        "assignments": "assignments.csv",
        "system_args": spec.system_args,
        "terrain": {"dem": None, "road": None},
        "stand": {
            "area_ha": spec.area_ha,
            "age_years": spec.age_years,
            "bec_zone": spec.bec_zone,
            "centre_wgs84": [spec.longitude, spec.latitude],
            "crs": CRS,
            "tree_count": tree_count,
            "merchantable_volume_m3": round(total_volume, 6),
            "volume_per_ha_m3": round(total_volume / spec.area_ha, 3),
        },
        "provenance": {
            "tree_list": "synthetic",
            "stand_footprint": "synthetic placeholder rectangle (published area, not the surveyed polygon)",
            "stand_attributes": "published research-forest values",
            "review_status": "not_reviewed",
        },
        "caveats": [
            "Synthetic tree list; not a surveyed stand or tree map.",
            "Reference machine model; not an operational plan.",
            "Block footprint is a placeholder rectangle, not the surveyed polygon.",
        ],
    }
    path = case_dir / "case.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def _write_assignments(spec: CaseSpec, case_dir: Path, total_volume: float) -> Path:
    path = case_dir / "assignments.csv"
    _write_csv(
        path,
        ["machine_id", "block_id", "day", "shift_id", "assigned", "production"],
        [
            {
                "machine_id": spec.system_args["feller"],
                "block_id": spec.block_id,
                "day": 1,
                "shift_id": "S1",
                "assigned": 1,
                "production": f"{total_volume:.6f}",
            }
        ],
    )
    return path


def generate_case(spec: CaseSpec, out_root: Path) -> dict[str, Any]:
    """Generate one case directory and return a summary payload."""
    case_dir = out_root / spec.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    trees = _make_trees(spec)
    model = ReferenceStemModel()
    total_volume = sum(model.evaluate(tree).merchantable_volume_m3 for tree in trees)
    inventory, metadata = _write_inventory(spec, case_dir, trees, total_volume)
    scenario = _write_scenario(spec, case_dir, total_volume, len(trees))
    _write_case_manifest(spec, case_dir, total_volume, len(trees))
    assignments = _write_assignments(spec, case_dir, total_volume)
    return {
        "case_id": spec.case_id,
        "case_dir": str(case_dir),
        "tree_count": len(trees),
        "merchantable_volume_m3": round(total_volume, 6),
        "volume_per_ha_m3": round(total_volume / spec.area_ha, 3),
        "scenario": str(scenario),
        "inventory": str(inventory),
        "metadata": str(metadata),
        "assignments": str(assignments),
    }


def main(argv: list[str] | None = None) -> int:
    """Generate every demo case under ``out``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("sandbox/cases"),
        help="Case root directory (default: sandbox/cases).",
    )
    args = parser.parse_args(argv)
    results = [generate_case(spec, args.out) for spec in case_specs()]
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
