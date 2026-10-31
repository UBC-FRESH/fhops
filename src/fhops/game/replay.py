"""Generate FHOPS 3D replay assets for a game attempt."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from fhops.ground_system import simulate_ground_system
from fhops.stem import ReferenceStemModel, build_stem_inventory
from fhops.tree_scene import write_tree_scene

from .careful_logging import DEFAULT_CAREFUL_LOGGING_CURVE

__all__ = ["ReplayError", "generate_replay"]


class ReplayError(RuntimeError):
    """Raised when replay assets cannot be generated."""


def _level(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "fhops.game.level.v1":
        raise ReplayError("Unsupported level manifest.")
    return data


def generate_replay(
    level_path: str | Path,
    choices: dict[str, Any],
    out_dir: str | Path,
) -> dict[str, Any]:
    """Generate scene + event assets for one finite choice combination."""
    level_file = Path(level_path).expanduser().resolve()
    level = _level(level_file)
    scenario = (level_file.parent / level["scenario"]).resolve()
    target = Path(out_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    model = ReferenceStemModel(
        form_factor=float(level["stem_form_factor"]),
        log_length_m=float(choices["log_length_m"]),
        stump_height_m=0.3,
        sawlog_min_dbh_cm=float(choices["sawlog_min_dbh_cm"]),
    )
    stems = build_stem_inventory(scenario, model=model)
    machine_ids = level["machine_ids"]
    skidders = tuple(machine_ids["skidders"])[: int(choices["skidder_count"])]
    productivity = 1.0
    if level.get("selection_cut", True):
        care = DEFAULT_CAREFUL_LOGGING_CURVE.get(float(choices["care_level"]))
        productivity = (
            DEFAULT_CAREFUL_LOGGING_CURVE.base_selection_cut_productivity_multiplier
            * care.care_productivity_multiplier
        )
    result = simulate_ground_system(
        scenario,
        block_id=stems.trees[0].block_id,
        feller_machine_id=str(machine_ids["feller"]),
        skidder_machine_ids=skidders,
        processor_machine_ids=tuple(machine_ids.get("processors", [])),
        loader_machine_id=str(machine_ids["loader"]),
        stem_inventory=stems,
        shift_days=30,
        hours_per_shift=20.0,
        feller_processing_time_multiplier=1.0 / productivity,
    )
    (target / "system_events.json").write_text(
        json.dumps(result.to_dict(), sort_keys=True) + "\n", encoding="utf-8"
    )
    assignment = target / "assignment.csv"
    with assignment.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["machine_id", "block_id", "day", "shift_id", "assigned", "production"])
        writer.writerow(
            [machine_ids["feller"], stems.trees[0].block_id, 1, "S1", 1, result.processed_volume_m3]
        )
    scene = write_tree_scene(
        scenario,
        assignment,
        target,
        lod_threshold=5000,
        generated_utc="2026-10-31T00:00:00+00:00",
    )
    viewer_source = Path(__file__).resolve().parents[3] / "examples/tree_system/viewer.html"
    if viewer_source.is_file():
        shutil.copyfile(viewer_source, target / "viewer.html")
    payload = {
        "schema_version": "fhops.game.replay.v1",
        "level_id": level["level_id"],
        "choices": choices,
        "duration_s": result.makespan_s,
        "tree_count": len(stems.trees),
        "processed_volume_m3": result.processed_volume_m3,
        "scene": scene.gltf_path.name,
        "events": "system_events.json",
        "viewer": "viewer.html",
    }
    (target / "replay.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
