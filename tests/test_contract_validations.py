import pytest
from pydantic import ValidationError

from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)
from fhops.scheduling.mobilisation import BlockDistance, MachineMobilisation, MobilisationConfig


def _base_scenario(**updates) -> Scenario:
    payload = dict(
        name="valid",
        num_days=3,
        blocks=[
            Block(id="B1", landing_id="L1", work_required=5.0, earliest_start=1, latest_finish=3),
        ],
        machines=[Machine(id="M1", daily_hours=8.0)],
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[CalendarEntry(machine_id="M1", day=1, available=1)],
        production_rates=[ProductionRate(machine_id="M1", block_id="B1", rate=2.0)],
    )
    payload.update(updates)
    return Scenario(**payload)


def test_block_work_must_be_non_negative():
    with pytest.raises(ValidationError, match="Block.work_required must be non-negative"):
        _base_scenario(
            blocks=[
                Block(id="B1", landing_id="L1", work_required=-1.0),
            ]
        )


def test_calendar_day_must_be_within_horizon():
    with pytest.raises(
        ValidationError, match="Calendar entry day 4 exceeds scenario horizon num_days=3"
    ):
        _base_scenario(calendar=[CalendarEntry(machine_id="M1", day=4, available=1)])
    with pytest.raises(ValidationError, match="CalendarEntry.available must be 0 or 1"):
        _base_scenario(calendar=[CalendarEntry(machine_id="M1", day=1, available=2)])


def test_production_rate_requires_valid_block_and_machine():
    with pytest.raises(ValidationError, match="unknown block_id=B2"):
        _base_scenario(production_rates=[ProductionRate(machine_id="M1", block_id="B2", rate=1.0)])
    with pytest.raises(ValidationError, match="unknown machine_id=M2"):
        _base_scenario(production_rates=[ProductionRate(machine_id="M2", block_id="B1", rate=1.0)])


def test_mobilisation_distances_must_reference_known_blocks():
    mobilisation = MobilisationConfig(
        machine_params=[
            MachineMobilisation(machine_id="M1", walk_cost_per_meter=0.0, move_cost_flat=0.0)
        ],
        distances=[BlockDistance(from_block="B1", to_block="B2", distance_m=100.0)],
    )
    with pytest.raises(
        ValidationError, match="Mobilisation distance references unknown block_id B1->B2"
    ):
        _base_scenario(mobilisation=mobilisation)


def test_mobilisation_machine_params_must_reference_known_machine():
    mobilisation = MobilisationConfig(
        machine_params=[
            MachineMobilisation(
                machine_id="M2", walk_cost_per_meter=0.0, move_cost_flat=0.0, walk_threshold_m=10.0
            )
        ]
    )
    with pytest.raises(
        ValidationError, match="Mobilisation config references unknown machine_id=M2"
    ):
        _base_scenario(mobilisation=mobilisation)
