#!/usr/bin/env python
"""Generate the redistributable scale hauling case under ``examples/hauling_scale/``.

The case has 13 blocks, 3 sort yards, 4 contractors, 60 trucks, 3 log sorts, and about 90
truckloads per day. It is intentionally synthetic; it is shaped like the thesis case for scale
testing, not a reproduction of the confidential company data.

Run from the repository root::

    python scripts/generate_hauling_scale_case.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples" / "hauling_scale"

BLOCKS = [f"b{index:02d}" for index in range(1, 14)]
YARDS = ["y1", "y2", "y3"]
SORTS = [
    ("fir_saw", "fir_saw", True),
    ("hemlock_pulp", "hemlock_pulp", True),
    ("mixed_unsorted", "mixed_unsorted", False),
]
CONTRACTORS = ["c1", "c2", "c3", "c4"]
TRUCK_TYPES = [
    ("highway", 45.0, 120.0, 1.2, 1.8, True, True),
    ("offhighway", 60.0, 180.0, 1.5, 2.2, False, True),
]
# 5 blocks of fir (480 m3), 4 blocks of hemlock (600 m3), 4 blocks of mixed (600 m3).
BLOCK_SORT = {
    **{block: "fir_saw" for block in BLOCKS[:5]},
    **{block: "hemlock_pulp" for block in BLOCKS[5:9]},
    **{block: "mixed_unsorted" for block in BLOCKS[9:]},
}
BLOCK_VOLUME = {
    **{block: 480.0 for block in BLOCKS[:5]},
    **{block: 600.0 for block in BLOCKS[5:]},
}


def main() -> None:
    """Write the scale-case CSVs, GeoJSON, and scenario YAML."""
    OUT.mkdir(parents=True, exist_ok=True)
    _write_blocks()
    _write_machines()
    _write_landings()
    _write_calendar()
    _write_production_rates()
    _write_geometry()
    (OUT / "scenario.yaml").write_text(_scenario_yaml(), encoding="utf-8")
    print(f"Wrote {OUT}")


def _write_blocks() -> None:
    with (OUT / "blocks.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "id",
                "landing_id",
                "work_required",
                "earliest_start",
                "latest_finish",
                "avg_stem_size_m3",
                "volume_per_ha_m3",
                "stem_density_per_ha",
                "ground_slope_percent",
            ]
        )
        for index, block in enumerate(BLOCKS):
            writer.writerow(
                [
                    block,
                    f"l{(index % 3) + 1}",
                    BLOCK_VOLUME[block],
                    1,
                    2,
                    0.4,
                    300,
                    650,
                    12 + (index % 10),
                ]
            )


def _write_machines() -> None:
    with (OUT / "machines.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "crew", "daily_hours", "operating_cost", "role"])
        for block in BLOCKS:
            writer.writerow([f"ldr_{block}", "load", 10, 0, "loader"])
        for yard in YARDS:
            writer.writerow([f"ldr_{yard}", "yard", 10, 0, "loader"])


def _write_landings() -> None:
    with (OUT / "landings.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "daily_capacity"])
        for index in range(1, 4):
            writer.writerow([f"l{index}", 2])


def _write_calendar() -> None:
    with (OUT / "calendar.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["machine_id", "day", "available"])
        machines = [f"ldr_{block}" for block in BLOCKS] + [f"ldr_{yard}" for yard in YARDS]
        for machine in machines:
            for day in (1, 2):
                writer.writerow([machine, day, 1])


def _write_production_rates() -> None:
    with (OUT / "production_rates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["machine_id", "block_id", "rate"])


def _write_geometry() -> None:
    features = []
    for index, block in enumerate(BLOCKS):
        column = index % 5
        row = index // 5
        x0 = 500000.0 + column * 1200.0
        y0 = 5500000.0 + row * 1200.0
        features.append(
            {
                "type": "Feature",
                "properties": {"block_id": block},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x0, y0],
                            [x0 + 1000.0, y0],
                            [x0 + 1000.0, y0 + 1000.0],
                            [x0, y0 + 1000.0],
                            [x0, y0],
                        ]
                    ],
                },
            }
        )
    payload = {"type": "FeatureCollection", "features": features}
    (OUT / "blocks.geojson").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _scenario_yaml() -> str:
    payload = {
        "name": "Hauling scale case",
        "num_days": 2,
        "schema_version": "1.1.0",
        "data": {
            "blocks": "blocks.csv",
            "machines": "machines.csv",
            "landings": "landings.csv",
            "calendar": "calendar.csv",
            "prod_rates": "production_rates.csv",
        },
        "geo_block_path": "blocks.geojson",
        "geo_crs": "EPSG:3005",
        "hauling": {
            "planning_horizon_days": 2,
            "start_day": 1,
            "log_sorts": [
                {"id": sort_id, "product_id": product_id, "sorted": sorted_flag}
                for sort_id, product_id, sorted_flag in SORTS
            ],
            "contractors": [
                {"id": contractor, "preferred_daily_truckloads": 20.0} for contractor in CONTRACTORS
            ],
            "truck_types": [
                {
                    "id": type_id,
                    "capacity_m3": capacity,
                    "fixed_cost": fixed,
                    "variable_cost_per_minute": variable,
                    "overtime_cost_per_minute": overtime,
                    "can_carry_sorted": can_sorted,
                    "can_carry_unsorted": can_unsorted,
                }
                for type_id, capacity, fixed, variable, overtime, can_sorted, can_unsorted in TRUCK_TYPES
            ],
            "trucks": _trucks(),
            "depots": [{"id": "depot", "name": "Central depot"}],
            "depot_legs": _depot_legs(),
            "sort_yards": [
                {
                    "id": yard,
                    "facility_id": f"mill_{yard}",
                    "unsorted_storage_m3": 20000,
                    "sorted_processing_m3_per_day": 5000,
                    "unsorted_processing_m3_per_day": 3000,
                    "total_processing_m3_per_day": 8000,
                    "initial_unsorted_inventory_m3": 0,
                    "initial_water_inventory_m3": 0,
                }
                for yard in YARDS
            ],
            "loader_locations": [
                {
                    "loader_id": f"ldr_{block}",
                    "location_id": block,
                    "location_kind": "pickup",
                    "service_minutes": 22,
                }
                for block in BLOCKS
            ]
            + [
                {
                    "loader_id": f"ldr_{yard}",
                    "location_id": yard,
                    "location_kind": "delivery",
                    "service_minutes": 18,
                }
                for yard in YARDS
            ],
            "supply": [
                {
                    "block_id": block,
                    "log_sort_id": BLOCK_SORT[block],
                    "sorted_m3": BLOCK_VOLUME[block]
                    if BLOCK_SORT[block] != "mixed_unsorted"
                    else 0,
                    "unsorted_m3": BLOCK_VOLUME[block]
                    if BLOCK_SORT[block] == "mixed_unsorted"
                    else 0,
                }
                for block in BLOCKS
            ],
            "demand": [
                {
                    "yard_id": yard,
                    "log_sort_id": sort_id,
                    "day": day,
                    "volume_m3": 400.0,
                }
                for yard in YARDS
                for sort_id, _product_id, _sorted_flag in SORTS
                for day in (1, 2)
            ],
            "haul_arcs": _haul_arcs(),
            "driver_policy": {
                "regular_minutes": 510,
                "max_overtime_minutes": 300,
                "overtime_violation_penalty_per_minute": 1000,
            },
            "roadside_inventory_penalty_per_m3": 25,
            "loader_travel_cost_per_km": 0,
            "default_loader_service_minutes": 20,
        },
    }
    return yaml.safe_dump(payload, sort_keys=False, width=100)


def _trucks() -> list[dict[str, object]]:
    trucks = []
    for contractor in CONTRACTORS:
        for index in range(1, 11):
            trucks.append(
                {
                    "id": f"{contractor}_h{index}",
                    "contractor_id": contractor,
                    "truck_type_id": "highway",
                }
            )
        for index in range(1, 6):
            trucks.append(
                {
                    "id": f"{contractor}_o{index}",
                    "contractor_id": contractor,
                    "truck_type_id": "offhighway",
                }
            )
    return trucks


def _depot_legs() -> list[dict[str, object]]:
    rows = []
    for type_id, *_rest in TRUCK_TYPES:
        for index, block in enumerate(BLOCKS):
            rows.append(
                {
                    "depot_id": "depot",
                    "location_id": block,
                    "truck_type_id": type_id,
                    "travel_minutes": 15 + (index % 5) * 3,
                }
            )
        for index, yard in enumerate(YARDS):
            rows.append(
                {
                    "depot_id": "depot",
                    "location_id": yard,
                    "truck_type_id": type_id,
                    "travel_minutes": 12 + index * 4,
                }
            )
    return rows


def _haul_arcs() -> list[dict[str, object]]:
    rows = []
    for index, block in enumerate(BLOCKS):
        for yard_index, yard in enumerate(YARDS):
            travel = 30 + index * 2 + yard_index * 8
            for type_id, *_rest in TRUCK_TYPES:
                rows.append(
                    {
                        "block_id": block,
                        "yard_id": yard,
                        "truck_type_id": type_id,
                        "travel_minutes": travel,
                        "distance_km": round(travel / 1.2, 1),
                    }
                )
    return rows


if __name__ == "__main__":
    main()
