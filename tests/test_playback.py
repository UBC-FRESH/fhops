from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from fhops.evaluation.playback import (
    PlaybackConfig,
    assignments_to_records,
    run_playback,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.scheduling.mobilisation import (
    BlockDistance,
    MachineMobilisation,
    MobilisationConfig,
)
from fhops.scheduling.systems import HarvestSystem, SystemJob


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "regression"
SCENARIO_PATH = FIXTURE_DIR / "regression.yaml"
BASELINE_PATH = FIXTURE_DIR / "baseline.yaml"

with BASELINE_PATH.open("r", encoding="utf-8") as handle:
    BASELINE = yaml.safe_load(handle)

REFERENCE_ASSIGNMENTS = [
    {
        "machine_id": entry["machine_id"],
        "block_id": entry["block_id"],
        "day": int(entry["day"]),
        "shift_id": entry.get("shift_id"),
        "assigned": entry.get("assigned", 1),
    }
    for entry in BASELINE["reference_assignments"]
]


def regression_problem() -> Problem:
    scenario = load_scenario(SCENARIO_PATH)
    mobilisation = MobilisationConfig(
        machine_params=[
            MachineMobilisation(
                machine_id="F1",
                walk_cost_per_meter=0.01,
                move_cost_flat=5.0,
                walk_threshold_m=100.0,
                setup_cost=1.0,
            ),
            MachineMobilisation(
                machine_id="P1",
                walk_cost_per_meter=0.02,
                move_cost_flat=6.0,
                walk_threshold_m=100.0,
                setup_cost=1.5,
            ),
        ],
        distances=[
            BlockDistance(from_block="B1", to_block="B1", distance_m=0.0),
            BlockDistance(from_block="B2", to_block="B2", distance_m=0.0),
            BlockDistance(from_block="B1", to_block="B2", distance_m=500.0),
            BlockDistance(from_block="B2", to_block="B1", distance_m=500.0),
        ],
    )
    harvest_system = HarvestSystem(
        system_id="ground_sequence",
        jobs=[
            SystemJob(name="felling", machine_role="feller", prerequisites=[]),
            SystemJob(name="processing", machine_role="processor", prerequisites=["felling"]),
        ],
    )
    scenario = scenario.model_copy(
        update={
            "mobilisation": mobilisation,
            "harvest_systems": {"ground_sequence": harvest_system},
        }
    )
    return Problem.from_scenario(scenario)


def test_assignments_to_records_marks_block_completion():
    pb = regression_problem()
    df = pd.DataFrame(REFERENCE_ASSIGNMENTS)

    records = list(assignments_to_records(pb, df))
    completed = {rec.block_id for rec in records if rec.metadata.get("block_completed")}

    assert {"B1", "B2"}.issubset(completed)
    assert all(rec.metadata["production_source"] in {"rate", "column"} for rec in records)


def test_assignments_to_records_flags_sequencing_violation():
    pb = regression_problem()
    df = pd.DataFrame(
        [
            {"machine_id": "P1", "block_id": "B1", "day": 1, "shift_id": "S1", "assigned": 1},
        ]
    )

    records = list(assignments_to_records(pb, df))
    assert len(records) == 1
    assert records[0].metadata.get("sequencing_violation") == "missing_prereq"


def test_run_playback_reports_idle_hours():
    pb = regression_problem()
    df = pd.DataFrame(
        [
            {"machine_id": "F1", "block_id": "B1", "day": 2, "shift_id": "S1", "assigned": 1},
        ]
    )

    playback = run_playback(pb, df, config=PlaybackConfig(include_idle_records=True))

    shift_map = {
        (summary.machine_id, summary.day, summary.shift_id): summary
        for summary in playback.shift_summaries
    }
    idle_entry = shift_map[("P1", 2, "S1")]
    assert idle_entry.available_hours > 0
    assert idle_entry.total_hours == pytest.approx(0.0)
    assert idle_entry.idle_hours == pytest.approx(idle_entry.available_hours)

    day_map = {summary.day: summary for summary in playback.day_summaries}
    day2 = day_map[2]
    assert day2.available_hours > day2.total_hours
    assert day2.idle_hours == pytest.approx(day2.available_hours - day2.total_hours)
