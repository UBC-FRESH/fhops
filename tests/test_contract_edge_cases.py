from pathlib import Path

import pytest
from pydantic import ValidationError

from fhops.optimization.heuristics import solve_sa
from fhops.optimization.mip.builder import build_model
from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    CrewAssignment,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)
from fhops.scenario.io import load_scenario
from fhops.scheduling.mobilisation import BlockDistance, MachineMobilisation, MobilisationConfig
from fhops.scheduling.timeline.models import BlackoutWindow, ShiftDefinition, TimelineConfig


def build_scenario(**overrides) -> Scenario:
    base = dict(
        name="edge",
        num_days=5,
        blocks=[
            Block(id="B1", landing_id="L1", work_required=5.0, earliest_start=1, latest_finish=5),
            Block(id="B2", landing_id="L1", work_required=2.0, earliest_start=2, latest_finish=4),
        ],
        machines=[Machine(id="M1"), Machine(id="M2")],
        landings=[Landing(id="L1", daily_capacity=2)],
        calendar=[
            CalendarEntry(machine_id="M1", day=1, available=1),
            CalendarEntry(machine_id="M2", day=2, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="M1", block_id="B1", rate=2.0),
            ProductionRate(machine_id="M2", block_id="B2", rate=1.0),
        ],
    )
    base.update(overrides)
    return Scenario(**base)


@pytest.mark.parametrize(
    "work_required",
    [-1.0, -0.1],
)
def test_blocks_reject_negative_work(work_required):
    with pytest.raises(ValidationError, match="Block.work_required must be non-negative"):
        build_scenario(blocks=[Block(id="B1", landing_id="L1", work_required=work_required)])


@pytest.mark.parametrize(
    "day",
    [0, -1],
)
def test_calendar_day_must_be_positive(day):
    with pytest.raises(ValidationError, match="CalendarEntry.day must be >= 1"):
        build_scenario(calendar=[CalendarEntry(machine_id="M1", day=day, available=1)])


@pytest.mark.parametrize(
    "available",
    [-1, 2],
)
def test_calendar_available_is_flag(available):
    with pytest.raises(ValidationError, match="CalendarEntry.available must be 0 or 1"):
        build_scenario(calendar=[CalendarEntry(machine_id="M1", day=1, available=available)])


@pytest.mark.parametrize(
    "latest_finish",
    [6, 10],
)
def test_block_latest_finish_cannot_exceed_horizon(latest_finish):
    with pytest.raises(ValidationError, match="latest_finish exceeds num_days"):
        build_scenario(
            blocks=[
                Block(
                    id="B1",
                    landing_id="L1",
                    work_required=1.0,
                    earliest_start=1,
                    latest_finish=latest_finish,
                )
            ]
        )


@pytest.mark.parametrize(
    "machine_id,block_id,match",
    [
        ("M3", "B1", "unknown machine_id"),
        ("M1", "B3", "unknown block_id"),
    ],
)
def test_production_rate_rejects_unknown_ids(machine_id, block_id, match):
    with pytest.raises(ValidationError, match=match):
        build_scenario(
            production_rates=[ProductionRate(machine_id=machine_id, block_id=block_id, rate=1.0)]
        )


@pytest.mark.parametrize(
    "distances",
    [
        [BlockDistance(from_block="B3", to_block="B1", distance_m=10.0)],
        [BlockDistance(from_block="B1", to_block="B4", distance_m=10.0)],
    ],
)
def test_mobilisation_distances_require_known_blocks(distances):
    mobilisation = MobilisationConfig(
        machine_params=[
            MachineMobilisation(machine_id="M1", walk_cost_per_meter=0.0, move_cost_flat=0.0)
        ],
        distances=distances,
    )
    with pytest.raises(ValidationError, match="Mobilisation distance references unknown block_id"):
        build_scenario(mobilisation=mobilisation)


@pytest.mark.parametrize(
    "crew_assignments,match",
    [
        ([CrewAssignment(crew_id="C1", machine_id="M3")], "unknown machine_id"),
        (
            [
                CrewAssignment(crew_id="C1", machine_id="M1"),
                CrewAssignment(crew_id="C1", machine_id="M1"),
            ],
            "Duplicate crew_id",
        ),
    ],
)
def test_crew_assignment_edge_cases(crew_assignments, match):
    with pytest.raises(ValidationError, match=match):
        build_scenario(crew_assignments=crew_assignments)


def test_mip_blackout_enforcement():
    timeline = TimelineConfig(
        shifts=[ShiftDefinition(name="day", hours=10.0, shifts_per_day=1)],
        blackouts=[BlackoutWindow(start_day=4, end_day=4, reason="maintenance")],
    )
    scenario = build_scenario(timeline=timeline)
    model = build_model(Problem.from_scenario(scenario))
    assert model.mach_one_block["M1", 4].upper == 0.0


def test_sa_respects_blackouts():
    timeline = TimelineConfig(
        shifts=[ShiftDefinition(name="day", hours=10.0, shifts_per_day=1)],
        blackouts=[BlackoutWindow(start_day=1, end_day=1, reason="storm")],
    )
    scenario = Scenario(
        name="blackout-sa",
        num_days=2,
        blocks=[
            Block(id="B1", landing_id="L1", work_required=2.0, earliest_start=1, latest_finish=2)
        ],
        machines=[Machine(id="M1")],
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[
            CalendarEntry(machine_id="M1", day=1, available=1),
            CalendarEntry(machine_id="M1", day=2, available=1),
        ],
        production_rates=[ProductionRate(machine_id="M1", block_id="B1", rate=2.0)],
        timeline=timeline,
    )
    result = solve_sa(Problem.from_scenario(scenario), iters=200, seed=7)
    assignments = result["assignments"]
    assert not (assignments[assignments["day"] == 1].any().any())
    assert (assignments["day"] == 2).any()


def test_geojson_validation_errors(tmp_path):
    scenario_dir = tmp_path / "scenario"
    scenario_dir.mkdir()
    (scenario_dir / "blocks.csv").write_text("id,landing_id,work_required\nB1,L1,1.0\n")
    (scenario_dir / "machines.csv").write_text("id\nM1\n")
    (scenario_dir / "landings.csv").write_text("id\nL1\n")
    (scenario_dir / "calendar.csv").write_text("machine_id,day,available\nM1,1,1\n")
    (scenario_dir / "production_rates.csv").write_text("machine_id,block_id,rate\nM1,B1,1.0\n")
    (scenario_dir / "scenario.yaml").write_text(
        "\n".join(
            [
                "name: geo-invalid",
                "num_days: 1",
                "schema_version: 1.0.0",
                "data:",
                "  blocks: blocks.csv",
                "  machines: machines.csv",
                "  landings: landings.csv",
                "  calendar: calendar.csv",
                "  prod_rates: production_rates.csv",
                f"geo_block_path: {Path('tests/data/geo/invalid.geojson').resolve()}",
            ]
        )
        + "\n"
    )
    with pytest.raises(Exception, match="GeoJSON"):
        load_scenario(scenario_dir / "scenario.yaml")


def test_calendar_reference_unknown_machine():
    with pytest.raises(ValidationError, match="unknown machine_id=M3"):
        build_scenario(calendar=[CalendarEntry(machine_id="M3", day=1, available=1)])


@pytest.mark.parametrize(
    "rate",
    [-10.0, -0.5],
)
def test_production_rate_non_negative(rate):
    with pytest.raises(ValidationError, match="ProductionRate.rate must be non-negative"):
        build_scenario(production_rates=[ProductionRate(machine_id="M1", block_id="B1", rate=rate)])
