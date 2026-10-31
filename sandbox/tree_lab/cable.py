"""Reference cable-yarder event model for the Tree Lab sandbox.

This is deliberately a sandbox model: it uses the published FHOPS cable
productivity helpers and TN-98 hand-falling regression, but it is not a
field-calibrated cable engineering model.  It gives the viewer a coherent
hand-fall → standing-skyline yarding event stream for the K80/Raven Creek
concept case.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fhops.productivity.cable_logging import (
    estimate_standing_skyline_turn_time_aubuchon1979,
)
from fhops.reference.tn98_handfalling import load_tn98_dataset
from fhops.stem import ReferenceStemModel
from fhops.tree_inventory import TreeRecord
from sandbox.tree_lab.cases import Case
from sandbox.tree_lab.harvest import DerivedInputs

CABLE_SCHEMA = "fhops.tree_lab.cable.v1"
DEFAULT_PAYLOAD_M3 = 6.0
DEFAULT_CREW_SIZE = 4.0
DEFAULT_LOGS_PER_TURN = 4.0
DEFAULT_AVERAGE_LOG_VOLUME_M3 = 0.45

__all__ = ["CableError", "build_cable_events", "write_cable_system"]


class CableError(RuntimeError):
    """Raised when the cable concept model cannot build a run."""


def _read_cut_trees(path: Path) -> list[tuple[TreeRecord, float]]:
    model = ReferenceStemModel()
    rows: list[tuple[TreeRecord, float]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            tree = TreeRecord(
                tree_id=row["tree_id"],
                block_id=row["block_id"],
                x_m=float(row["x_m"]),
                y_m=float(row["y_m"]),
                elevation_m=float(row["elevation_m"]),
                species_code=row["species_code"],
                dbh_cm=float(row["dbh_cm"]),
                height_m=float(row["height_m"]),
                crown_radius_m=float(row["crown_radius_m"]),
                status=row["status"],
                confidence=float(row["confidence"]),
                source_id=row["source_id"],
                source_tile_id=row["source_tile_id"],
                merchantable_height_m=(
                    float(row["merchantable_height_m"])
                    if row.get("merchantable_height_m")
                    else None
                ),
                defect=row.get("defect") or None,
                grade_hint=row.get("grade_hint") or None,
            )
            volume = model.evaluate(tree).merchantable_volume_m3
            rows.append((tree, volume))
    if not rows:
        raise CableError("The cable concept needs a non-empty cut list.")
    return rows


def _terrain_height(x: float, y: float, terrain: dict[str, Any]) -> float:
    origin = terrain.get("origin") or [0.0, 0.0]
    uphill = terrain.get("uphill") or [0.0, -1.0]
    slope = float(terrain.get("slope_percent") or 0.0) / 100.0
    base = float(terrain.get("base_m") or 0.0)
    return base + slope * (
        (x - float(origin[0])) * float(uphill[0]) + (y - float(origin[1])) * float(uphill[1])
    )


def _fall_minutes(dbh_cm: float) -> float:
    """TN-98 all-species cutting-time regression, in minutes per tree."""
    dataset = load_tn98_dataset()
    regression = dataset.regressions.get("all_species")
    if regression is None:
        return max(0.35, 0.0283 * dbh_cm)
    return max(0.35, regression.intercept_minutes + regression.slope_minutes_per_cm * dbh_cm)


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))


def _projection(
    point: dict[str, float], start: dict[str, float], end: dict[str, float]
) -> tuple[float, float]:
    dx = float(end["x"]) - float(start["x"])
    dy = float(end["y"]) - float(start["y"])
    length_sq = dx * dx + dy * dy
    if length_sq <= 0:
        return 0.0, 0.0
    t = (
        (float(point["x"]) - float(start["x"])) * dx + (float(point["y"]) - float(start["y"])) * dy
    ) / length_sq
    foot_x = float(start["x"]) + t * dx
    foot_y = float(start["y"]) + t * dy
    lateral = math.hypot(float(point["x"]) - foot_x, float(point["y"]) - foot_y)
    return t, lateral


def build_cable_events(case: Case, derived: DerivedInputs) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build an event stream and summary for one cable concept run."""
    manifest = case.manifest
    terrain = dict(manifest.get("terrain") or {})
    cable_spec = dict(manifest.get("cable") or {})
    if "yarder" not in cable_spec or "spar" not in cable_spec:
        raise CableError("Cable case needs cable.yarder and cable.spar coordinates.")
    yarder = {"x": float(cable_spec["yarder"]["x"]), "y": float(cable_spec["yarder"]["y"])}
    spar = {"x": float(cable_spec["spar"]["x"]), "y": float(cable_spec["spar"]["y"])}
    span_m = _distance(yarder, spar)
    if span_m <= 0:
        raise CableError("Cable span must be positive.")

    rows = _read_cut_trees(derived.cut_list)
    trees: list[dict[str, Any]] = []
    for tree, volume in rows:
        t, lateral = _projection({"x": tree.x_m, "y": tree.y_m}, yarder, spar)
        trees.append(
            {
                "tree": tree,
                "volume": volume,
                "t": t,
                "lateral": lateral,
            }
        )
    trees.sort(key=lambda item: (item["t"], item["lateral"], item["tree"].tree_id))

    # Group stems into payload-sized turns.  This is a reference grouping, not
    # an optimized cable layout.
    turns: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_volume = 0.0
    for item in trees:
        current.append(item)
        current_volume += float(item["volume"])
        if current_volume >= DEFAULT_PAYLOAD_M3 or len(current) >= 4:
            turns.append(current)
            current = []
            current_volume = 0.0
    if current:
        turns.append(current)

    events: list[dict[str, Any]] = []
    fall_cursor = 0.0
    tree_end: dict[str, float] = {}
    for item in trees:
        tree = item["tree"]
        duration = _fall_minutes(tree.dbh_cm) * 60.0
        start = fall_cursor
        end = start + duration
        fall_cursor = end
        events.append(
            {
                "machine": "H1",
                "type": "fall",
                "start_s": round(start, 3),
                "end_s": round(end, 3),
                "x0": round(tree.x_m, 3),
                "y0": round(tree.y_m, 3),
                "x1": round(tree.x_m, 3),
                "y1": round(tree.y_m, 3),
                "volume_m3": round(float(item["volume"]), 6),
                "logs": 0,
                "tree_ids": [tree.tree_id],
                "status": "falling",
                "distance_m": 0.0,
                "max_grade_percent": 0.0,
            }
        )
        tree_end[tree.tree_id] = end

    yard_cursor = 0.0
    for turn in turns:
        ready = max(tree_end[item["tree"].tree_id] for item in turn)
        start = max(yard_cursor, ready)
        payload = sum(float(item["volume"]) for item in turn)
        lateral = sum(float(item["lateral"]) for item in turn) / len(turn)
        logs = max(1.0, min(8.0, payload / DEFAULT_AVERAGE_LOG_VOLUME_M3))
        cycle_min = estimate_standing_skyline_turn_time_aubuchon1979(
            slope_distance_m=max(1.0, min(900.0, span_m)),
            lateral_distance_m=max(0.0, min(50.0, lateral)),
            logs_per_turn=logs,
            crew_size=DEFAULT_CREW_SIZE,
        )
        end = start + cycle_min * 60.0
        yard_cursor = end
        events.append(
            {
                "machine": "Y1",
                "type": "yard",
                "start_s": round(start, 3),
                "end_s": round(end, 3),
                "x0": round(yarder["x"], 3),
                "y0": round(yarder["y"], 3),
                "x1": round(yarder["x"], 3),
                "y1": round(yarder["y"], 3),
                "volume_m3": round(payload, 6),
                "logs": int(round(logs)),
                "tree_ids": [item["tree"].tree_id for item in turn],
                "status": "yarding",
                "distance_m": round(span_m, 3),
                "max_grade_percent": float(terrain.get("slope_percent") or 0.0),
            }
        )
        for item in turn:
            tree_end[item["tree"].tree_id] = end
        load_start = end
        load_end = load_start + 90.0
        events.append(
            {
                "machine": "L1",
                "type": "load",
                "start_s": round(load_start, 3),
                "end_s": round(load_end, 3),
                "x0": round(yarder["x"], 3),
                "y0": round(yarder["y"], 3),
                "x1": round(yarder["x"], 3),
                "y1": round(yarder["y"], 3),
                "volume_m3": round(payload, 6),
                "logs": int(round(logs)),
                "tree_ids": [item["tree"].tree_id for item in turn],
                "status": "loading",
                "distance_m": 0.0,
                "max_grade_percent": 0.0,
            }
        )

    events.sort(
        key=lambda event: (event["start_s"], event["end_s"], event["machine"], event["type"])
    )
    makespan = max((event["end_s"] for event in events), default=0.0)
    processed_volume = sum(float(item["volume"]) for item in trees)
    outline = []
    try:
        payload = json.loads(case.path("footprint").read_text(encoding="utf-8"))
        coords = payload["features"][0]["geometry"]["coordinates"][0]
        outline = [[round(float(x), 3), round(float(y), 3)] for x, y in coords]
    except Exception:  # noqa: BLE001 - optional visual outline
        outline = []

    machine_events: dict[str, list[dict[str, Any]]] = {"H1": [], "Y1": [], "L1": []}
    for event in events:
        machine_events[event["machine"]].append(event)
    summaries = {}
    for machine, machine_rows in machine_events.items():
        busy = sum(float(event["end_s"]) - float(event["start_s"]) for event in machine_rows)
        summaries[machine] = {
            "busy_s": round(busy, 3),
            "events": len(machine_rows),
            "utilisation": round(busy / makespan, 6) if makespan else 0.0,
        }

    tree_payload = [
        {
            "tree_id": item["tree"].tree_id,
            "x": round(item["tree"].x_m, 3),
            "y": round(item["tree"].y_m, 3),
            "dbh_cm": item["tree"].dbh_cm,
            "volume_m3": round(float(item["volume"]), 6),
            "logs": 0,
            "processed_s": round(tree_end[item["tree"].tree_id], 3),
        }
        for item in trees
    ]
    events_payload = {
        "schema_version": CABLE_SCHEMA,
        "system_id": "fhops-cable-concept-"
        + hashlib.sha256(
            json.dumps(
                {
                    "case": case.case_id,
                    "yarder": yarder,
                    "spar": spar,
                    "trees": [item["tree"].tree_id for item in trees],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16],
        "generated_utc": datetime.now(UTC).isoformat(),
        "case_id": case.case_id,
        "block_id": manifest["block_id"],
        "landing": yarder,
        "duration_s": round(makespan, 3),
        "makespan_s": round(makespan, 3),
        "tree_count": len(trees),
        "processed_volume_m3": round(processed_volume, 6),
        "unreachable_count": 0,
        "rate_model": "cable-standing-reference",
        "rate_provenance": {
            "felling": "TN-98 all-species hand-falling regression",
            "yarding": "Aubuchon (1982) standing-skyline turn-time helper",
            "note": "Sandbox reference model; not a field-calibrated cable engineering design.",
        },
        "terrain": {
            **terrain,
            "span_m": round(span_m, 3),
        },
        "cable": {
            **cable_spec,
            "span_m": round(span_m, 3),
            "yarder": yarder,
            "spar": spar,
        },
        "block_outline": outline,
        "machines": {
            "H1": {"type": "hand_faller"},
            "Y1": {"type": "cable_yarder"},
            "L1": {"type": "loader"},
        },
        "timeline": events,
        "events": events,
        "trees": tree_payload,
        "machine_summaries": summaries,
        "truck_events": [],
        "truck_summary": None,
        "landing_inventory_final_m3": 0.0,
        "landing_inventory_max_m3": 0.0,
        "warnings": [
            "Cable yarder is a sandbox reference model, not a calibrated engineering design.",
            "The 60% slope is a scenario assumption, not a DEM-derived measurement.",
        ],
        "caveats": [
            "Synthetic tree list; actual FEMIC forest-cover footprint.",
            "Reference cable layout and cycle model; not an operational plan.",
            "No operational, financial, or regulatory claim is made.",
        ],
    }
    summary_payload = {
        "schema_version": CABLE_SCHEMA,
        "system_id": events_payload["system_id"],
        "generated_utc": events_payload["generated_utc"],
        "case_id": case.case_id,
        "block_id": manifest["block_id"],
        "tree_count": len(trees),
        "processed_volume_m3": round(processed_volume, 6),
        "makespan_s": round(makespan, 3),
        "landing_inventory_max_m3": 0.0,
        "landing_inventory_final_m3": 0.0,
        "unreachable_count": 0,
        "machine_summaries": summaries,
        "truck_summary": None,
        "warnings": events_payload["warnings"],
        "caveats": events_payload["caveats"],
        "rate_model": events_payload["rate_model"],
        "rate_provenance": events_payload["rate_provenance"],
    }
    return events_payload, summary_payload


def write_cable_system(case: Case, derived: DerivedInputs, run_dir: Path) -> dict[str, Any]:
    """Write the cable event stream + summary and return a command record."""
    started = datetime.now(UTC)
    events, summary = build_cable_events(case, derived)
    system_dir = run_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "system_events.json").write_text(
        json.dumps(events, indent=2) + "\n", encoding="utf-8"
    )
    (system_dir / "system_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "command": ["sandbox.tree_lab.cable", case.case_id],
        "returncode": 0,
        "duration_s": round((datetime.now(UTC) - started).total_seconds(), 3),
        "timed_out": False,
        "stdout_tail": [
            f"cable concept: {summary['tree_count']} trees, {summary['processed_volume_m3']:.1f} m3"
        ],
        "stderr_tail": [],
    }
