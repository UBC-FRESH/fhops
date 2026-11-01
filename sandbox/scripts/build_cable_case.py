"""Build the synthetic K80/Raven Creek cable-yarder demo case.

The footprint is the actual FEMIC forest-cover stand ``FOREST_COV=666`` from the
MKRF instance.  The tree list is synthetic and conditioned on the published
stand attributes; it is not a tree map or a harvest-block inventory.

The cable system is a *sandbox reference model* built on the published
TR-125/Aubuchon cable-yarding helpers.  It is not field-calibrated and does not
change FHOPS core.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import Point, shape

from fhops.stem import ReferenceStemModel
from fhops.tree_inventory import TREE_INVENTORY_SCHEMA, TreeRecord
from sandbox.tree_lab.cases import ensure_pinned, load_case, validate_case

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "sandbox" / "cases" / "mkrf-k80-cable"
CASE_ID = "mkrf-k80-cable"
BLOCK_ID = "MKRF_K80_666"
LANDING_ID = "K80_L1"
CRS = "EPSG:3005"
BASE_ELEVATION_M = 300.0
SLOPE_PERCENT = 60.0
TREE_COUNT = 900
AGE_YEARS = 74
AREA_HA = 7.7931
BEC_ZONE = "CWHvm1"
SEED = 20261030

SPECIES = (
    # code, weight, height a/b, crown a/b
    ("Hw", 0.45, 1.45, 0.82, 0.075, 0.6),
    ("Fd", 0.30, 1.35, 0.85, 0.075, 0.6),
    ("Cw", 0.15, 1.35, 0.85, 0.080, 0.7),
    ("Bg", 0.10, 1.40, 0.82, 0.070, 0.6),
)
FIELDS = [
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _pick_species(rng: random.Random) -> tuple[str, float, float, float, float, float]:
    target = rng.random() * sum(item[1] for item in SPECIES)
    acc = 0.0
    for item in SPECIES:
        acc += item[1]
        if target <= acc:
            return item
    return SPECIES[-1]


def _terrain_height(x: float, y: float, origin: tuple[float, float]) -> float:
    # uphill = south; the K80 road/yarder is at the south/high edge, the spar
    # and creek are at the north/low edge.
    return BASE_ELEVATION_M + (SLOPE_PERCENT / 100.0) * (origin[1] - y)


def _make_trees(polygon: Any, origin: tuple[float, float]) -> list[TreeRecord]:
    rng = random.Random(SEED)
    minx, miny, maxx, maxy = polygon.bounds
    trees: list[TreeRecord] = []
    while len(trees) < TREE_COUNT:
        x = rng.uniform(minx, maxx)
        y = rng.uniform(miny, maxy)
        if not polygon.buffer(-1.5).contains(Point(x, y)):
            continue
        code, _weight, height_a, height_b, crown_a, crown_b = _pick_species(rng)
        dbh = min(95.0, max(12.0, rng.lognormvariate(math.log(45.0), 0.26)))
        height = height_a * dbh**height_b * rng.uniform(0.92, 1.08)
        crown = max(0.6, (crown_a * dbh + crown_b) * rng.uniform(0.85, 1.15))
        trees.append(
            TreeRecord(
                tree_id=f"T{len(trees) + 1:05d}",
                block_id=BLOCK_ID,
                x_m=round(x, 2),
                y_m=round(y, 2),
                elevation_m=round(_terrain_height(x, y, origin), 2),
                species_code=code,
                dbh_cm=round(dbh, 1),
                height_m=round(height, 1),
                crown_radius_m=round(crown, 2),
                status="live" if rng.random() > 0.02 else "snag",
                confidence=round(rng.uniform(0.82, 0.97), 2),
                source_id=f"synthetic-{CASE_ID}",
                source_tile_id="FEMIC-666",
                merchantable_height_m=None,
                defect=None,
                grade_hint=None,
            )
        )
    return trees


def _write_inventory(
    case_dir: Path, trees: list[TreeRecord], total_volume: float, source_props: dict[str, Any]
) -> tuple[Path, Path]:
    inventory = case_dir / "tree_inventory" / "tree_inventory.csv"
    _write_csv(
        inventory,
        FIELDS,
        [
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
        ],
    )
    metadata = {
        "schema_version": TREE_INVENTORY_SCHEMA,
        "inventory_id": f"{CASE_ID}-synthetic",
        "generated_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_id": f"synthetic-{CASE_ID}",
        "producer": "FHOPS Tree Lab synthetic generator",
        "method": (
            "Deterministic synthetic point list inside the actual FEMIC forest-cover "
            "polygon; not an ITD/ITC product or tree map."
        ),
        "crs": CRS,
        "units": {"x_y": "m", "elevation": "m", "dbh": "cm", "height": "m", "crown_radius": "m"},
        "review_status": "not_reviewed",
        "block_ids": [BLOCK_ID],
        "tree_count": len(trees),
        "inventory_sha256": _sha256(inventory),
        "stand_source": source_props,
        "caveats": [
            "Synthetic tree list; not a surveyed stand or tree map.",
            "Footprint is the actual FEMIC forest-cover polygon, not a surveyed harvest block.",
            "The 60% slope is a scenario assumption for the cable demonstration.",
            f"Merchantable volume computed with the FHOPS reference stem model: {total_volume:.3f} m3.",
        ],
    }
    meta_path = inventory.with_name("tree_inventory.meta.json")
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return inventory, meta_path


def _write_scenario(case_dir: Path, total_volume: float, tree_count: int, label: str) -> None:
    data = case_dir / "scenario" / "data"
    avg_stem = total_volume / tree_count
    volume_per_ha = total_volume / AREA_HA
    density = tree_count / AREA_HA
    _write_csv(
        data / "blocks.csv",
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
                "id": BLOCK_ID,
                "landing_id": LANDING_ID,
                "harvest_system_id": "cable_standing_tr125",
                "work_required": f"{total_volume:.6f}",
                "earliest_start": 1,
                "latest_finish": 10,
                "avg_stem_size_m3": f"{avg_stem:.6f}",
                "volume_per_ha_m3": f"{volume_per_ha:.6f}",
                "stem_density_per_ha": f"{density:.6f}",
                "ground_slope_percent": f"{SLOPE_PERCENT:.1f}",
            }
        ],
    )
    _write_csv(
        data / "machines.csv",
        ["id", "crew", "daily_hours", "operating_cost", "role"],
        [
            {
                "id": "H1",
                "crew": "CF",
                "daily_hours": 24.0,
                "operating_cost": 900.0,
                "role": "hand_faller",
            },
            {
                "id": "Y1",
                "crew": "CY",
                "daily_hours": 24.0,
                "operating_cost": 2200.0,
                "role": "skyline_yarder",
            },
            {
                "id": "L1",
                "crew": "CL",
                "daily_hours": 24.0,
                "operating_cost": 900.0,
                "role": "loader",
            },
        ],
    )
    _write_csv(
        data / "landings.csv", ["id", "daily_capacity"], [{"id": LANDING_ID, "daily_capacity": 1}]
    )
    _write_csv(
        data / "calendar.csv",
        ["machine_id", "day", "available"],
        [
            {"machine_id": machine, "day": day, "available": 1}
            for machine in ("H1", "Y1", "L1")
            for day in range(1, 11)
        ],
    )
    _write_csv(
        data / "prod_rates.csv",
        ["machine_id", "block_id", "rate"],
        [{"machine_id": "H1", "block_id": BLOCK_ID, "rate": 1000.0}],
    )
    (data / "harvest_systems.yaml").write_text(
        """cable_standing_tr125:
  system_id: cable_standing_tr125
  loader_batch_volume_m3: 1.8
  role_counts:
    hand_faller: 1
    skyline_yarder: 1
    loader: 1
  jobs:
  - name: felling
    machine_role: hand_faller
    prerequisites: []
  - name: primary_transport
    machine_role: skyline_yarder
    prerequisites:
    - felling
  - name: loading
    machine_role: loader
    prerequisites:
    - primary_transport
""",
        encoding="utf-8",
    )
    (case_dir / "scenario" / "scenario.yaml").write_text(
        f"""name: {label}
num_days: 10
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
  notes: Actual FEMIC forest-cover stand 666 footprint; synthetic tree list and 60% scenario slope.
""",
        encoding="utf-8",
    )


def _write_assignments(case_dir: Path, total_volume: float) -> None:
    _write_csv(
        case_dir / "assignments.csv",
        ["machine_id", "block_id", "day", "shift_id", "assigned", "production"],
        [
            {
                "machine_id": "H1",
                "block_id": BLOCK_ID,
                "day": 1,
                "shift_id": "S1",
                "assigned": 1,
                "production": f"{total_volume:.6f}",
            }
        ],
    )


def _write_manifest(
    case_dir: Path,
    footprint: dict[str, Any],
    total_volume: float,
    tree_count: int,
    centre: tuple[float, float],
    bounds: tuple[float, float, float, float],
) -> None:
    lon, lat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform(*centre)
    minx, miny, maxx, maxy = bounds
    yarder = {"x": round((minx + maxx) / 2.0, 2), "y": round(miny - 25.0, 2)}
    spar = {"x": round((minx + maxx) / 2.0, 2), "y": round(maxy + 25.0, 2)}
    manifest = {
        "schema_version": "fhops.tree_lab.case.v1",
        "case_id": CASE_ID,
        "label": "MKRF K80 / Raven Creek — steep cable-yarder concept (FEMIC stand 666)",
        "block_id": BLOCK_ID,
        "landing_id": LANDING_ID,
        "scenario": "scenario/scenario.yaml",
        "inventory": "tree_inventory/tree_inventory.csv",
        "metadata": "tree_inventory/tree_inventory.meta.json",
        "assignments": "assignments.csv",
        "footprint": "footprint.geojson",
        "system_kind": "cable_standing",
        "system_args": {
            "feller": "H1",
            "skidders": ["Y1"],
            "processors": [],
            "loader": "L1",
            "bunch_volume_m3": 1.8,
            "rate_model": "reference",
            "shift_days": 10,
            "shifts_per_day": 1,
            "hours_per_shift": 10,
            "truck_capacity_m3": 30.0,
            "truck_count": 1,
            "truck_cycle_s": 3600.0,
            "landing_capacity_m3": 20.0,
        },
        "terrain": {
            "dem": None,
            "road": None,
            "slope_percent": SLOPE_PERCENT,
            "uphill": [0.0, -1.0],
            "base_m": BASE_ELEVATION_M,
            "origin": [round(centre[0], 2), round(centre[1], 2)],
            "bounds": [round(minx, 2), round(miny, 2), round(maxx, 2), round(maxy, 2)],
            "visual": "synthetic planar slope for the concept scene",
        },
        "cable": {
            "yarder": yarder,
            "spar": spar,
            "yarder_position": "K80 road / south high edge",
            "spar_position": "beyond north treeline near Raven Creek",
            "span_m": round(abs(spar["y"] - yarder["y"]), 1),
            "spar_height_m": 42.0,
            "model": "standing skyline; Aubuchon (1982) turn-time helper",
            "note": "Reference concept layout; not a surveyed road/landing or engineering design.",
        },
        "stand": {
            "area_ha": AREA_HA,
            "age_years": AGE_YEARS,
            "bec_zone": BEC_ZONE,
            "centre_wgs84": [round(lon, 6), round(lat, 6)],
            "crs": CRS,
            "tree_count": tree_count,
            "merchantable_volume_m3": round(total_volume, 6),
            "volume_per_ha_m3": round(total_volume / AREA_HA, 3),
            "forest_cover_id": footprint["forest_cover_id"],
            "operability": footprint["operability"],
            "slope_percent": SLOPE_PERCENT,
        },
        "provenance": {
            "stand_geometry": "actual FEMIC forest-cover polygon (FOREST_COV=666) from the MKRF instance",
            "stand_attributes": "published FEMIC MKRF attributes: 7.7931 ha, age 74 in 2020, CWHvm1, Low Operability",
            "tree_list": "synthetic deterministic point list inside the actual stand polygon",
            "slope": "60% scenario assumption for the cable concept; not a measured DEM slope",
            "cable_model": "sandbox reference model using FHOPS cable-logging helpers; not field-calibrated",
            "review_status": "not_reviewed",
        },
        "harvest": {"type": "clear_cut", "marking_rule": "all", "target_basal_area_fraction": 1.0},
        "caveats": [
            "Footprint is an actual FEMIC forest-cover stand polygon, but the tree list is synthetic.",
            "Not a surveyed harvest block, tree map, road design, or operational plan.",
            "The 60% slope is a scenario assumption, not a DEM-derived value.",
            "Cable yarder cycle and layout are a reference concept, not a calibrated engineering design.",
            "No operational, financial, or regulatory claim is made.",
        ],
    }
    (case_dir / "case.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    out = args.out
    footprint_path = out / "footprint.geojson"
    footprint_payload = None
    if footprint_path.is_file():
        footprint_payload = json.loads(footprint_path.read_text(encoding="utf-8"))
    if args.force and out.exists():
        import shutil

        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    if footprint_payload is None:
        raise SystemExit(
            f"Missing {footprint_path}; extract the FEMIC stand polygon before running --force."
        )
    if not footprint_path.is_file():
        footprint_path.write_text(json.dumps(footprint_payload, indent=2) + "\n", encoding="utf-8")
    feature = footprint_payload["features"][0]
    polygon = shape(feature["geometry"])
    centre = (polygon.centroid.x, polygon.centroid.y)
    source_props = feature["properties"]
    trees = _make_trees(polygon, centre)
    model = ReferenceStemModel()
    total_volume = sum(model.evaluate(tree).merchantable_volume_m3 for tree in trees)
    _write_inventory(out, trees, total_volume, source_props)
    _write_scenario(
        out, total_volume, len(trees), "MKRF K80 / Raven Creek — steep cable-yarder concept"
    )
    _write_manifest(out, source_props, total_volume, len(trees), centre, polygon.bounds)
    _write_assignments(out, total_volume)
    case = load_case(out)
    pin = ensure_pinned(case)
    report = validate_case(case)
    print(
        json.dumps(
            {
                "case": case.case_id,
                "trees": len(trees),
                "volume_m3": round(total_volume, 3),
                "area_ha": AREA_HA,
                "pin": pin,
                "valid": report["valid"],
                "errors": report["errors"],
            },
            indent=2,
        )
    )
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
