import pyomo.environ as pyo
import pytest

from fhops.optimization.heuristics import solve_sa
from fhops.optimization.mip.builder import build_model
from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ObjectiveWeights,
    ProductionRate,
    Problem,
    Scenario,
    ScheduleLock,
)
from fhops.scheduling.mobilisation import (
    BlockDistance,
    MachineMobilisation,
    MobilisationConfig,
)


def _base_scenario() -> Scenario:
    return Scenario(
        name="locking",
        num_days=2,
        blocks=[
            Block(id="B1", landing_id="L1", work_required=2.0, earliest_start=1, latest_finish=2),
            Block(id="B2", landing_id="L1", work_required=2.0, earliest_start=1, latest_finish=2),
        ],
        machines=[Machine(id="M1"), Machine(id="M2")],
        landings=[Landing(id="L1", daily_capacity=2)],
        calendar=[
            CalendarEntry(machine_id="M1", day=1, available=1),
            CalendarEntry(machine_id="M1", day=2, available=1),
            CalendarEntry(machine_id="M2", day=1, available=1),
            CalendarEntry(machine_id="M2", day=2, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="M1", block_id="B1", rate=2.0),
            ProductionRate(machine_id="M1", block_id="B2", rate=2.0),
            ProductionRate(machine_id="M2", block_id="B1", rate=2.0),
            ProductionRate(machine_id="M2", block_id="B2", rate=2.0),
        ],
    )


def test_mip_respects_locked_assignments():
    scenario = _base_scenario().model_copy(
        update={"locked_assignments": [ScheduleLock(machine_id="M1", block_id="B1", day=1)]}
    )
    model = build_model(Problem.from_scenario(scenario))
    assert model.x["M1", "B1", 1].fixed
    assert pyo.value(model.x["M1", "B1", 1]) == 1.0
    # All other blocks for that machine/day must be fixed to zero
    assert pyo.value(model.x["M1", "B2", 1]) == 0.0


def test_sa_respects_locked_assignments():
    scenario = _base_scenario().model_copy(
        update={"locked_assignments": [ScheduleLock(machine_id="M2", block_id="B2", day=1)]}
    )
    res = solve_sa(Problem.from_scenario(scenario), iters=200, seed=3)
    assignments = res["assignments"]
    locked_rows = assignments[(assignments["machine_id"] == "M2") & (assignments["day"] == 1)]
    assert locked_rows.iloc[0]["block_id"] == "B2"


def test_objective_weights_adjust_mobilisation_penalty():
    mobilisation = MobilisationConfig(
        machine_params=[
            MachineMobilisation(
                machine_id="M1",
                walk_cost_per_meter=0.0,
                move_cost_flat=5.0,
                walk_threshold_m=0.0,
                setup_cost=0.0,
            )
        ],
        distances=[
            BlockDistance(from_block="B1", to_block="B2", distance_m=100.0),
            BlockDistance(from_block="B2", to_block="B1", distance_m=100.0),
            BlockDistance(from_block="B1", to_block="B1", distance_m=0.0),
            BlockDistance(from_block="B2", to_block="B2", distance_m=0.0),
        ],
    )
    scenario = _base_scenario().model_copy(
        update={
            "mobilisation": mobilisation,
            "objective_weights": ObjectiveWeights(production=1.0, mobilisation=2.0),
        }
    )
    model = build_model(Problem.from_scenario(scenario))
    # Simulate a move from B1 to B2 for M1
    model.x["M1", "B1", 1].value = 1.0
    model.x["M1", "B2", 2].value = 1.0
    model.prod["M1", "B1", 1].value = 2.0
    model.prod["M1", "B2", 2].value = 2.0
    if hasattr(model, "y"):
        model.y["M1", "B1", "B2", 2].value = 1.0
    obj_val = pyo.value(model.obj.expr)
    # Production contribution 4.0 minus mobilisation weight (2 * 5)
    assert obj_val == pytest.approx( -6.0 + 4.0)
