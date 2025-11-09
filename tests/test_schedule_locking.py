import pyomo.environ as pyo
import pytest

from fhops.optimization.heuristics import solve_sa
from fhops.optimization.heuristics.sa import Schedule, _evaluate
from fhops.optimization.mip.builder import build_model
from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ObjectiveWeights,
    Problem,
    ProductionRate,
    Scenario,
    ScheduleLock,
)
from fhops.scheduling.mobilisation import (
    BlockDistance,
    MachineMobilisation,
    MobilisationConfig,
)


def _shift_tuple(pb: Problem, day: int, shift_id: str | None = None) -> tuple[int, str]:
    candidates = [shift for shift in pb.shifts if shift.day == day]
    if not candidates:
        raise KeyError(f"No shift defined for day={day}")
    if shift_id is None:
        return (candidates[0].day, candidates[0].shift_id)
    for shift in candidates:
        if shift.shift_id == shift_id:
            return (shift.day, shift.shift_id)
    raise KeyError(f"Shift {shift_id!r} not found for day={day}")


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
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)
    shift = _shift_tuple(pb, 1)
    assert model.x["M1", "B1", shift].fixed
    assert pyo.value(model.x["M1", "B1", shift]) == 1.0
    # All other blocks for that machine/day must be fixed to zero
    assert pyo.value(model.x["M1", "B2", shift]) == 0.0


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
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)
    for mach in model.M:
        for blk in model.B:
            for day, shift_id in model.S:
                model.x[mach, blk, (day, shift_id)].value = 0.0
                model.prod[mach, blk, (day, shift_id)].value = 0.0
    shift1 = _shift_tuple(pb, 1)
    shift2 = _shift_tuple(pb, 2)
    model.x["M1", "B1", shift1].value = 1.0
    model.x["M1", "B2", shift2].value = 1.0
    model.prod["M1", "B1", shift1].value = 2.0
    model.prod["M1", "B2", shift2].value = 2.0
    if hasattr(model, "y") and hasattr(model, "S_transition"):
        for mach in model.M:
            for prev_blk in model.B:
                for curr_blk in model.B:
                    for day, shift_id in model.S_transition:
                        model.y[mach, prev_blk, curr_blk, (day, shift_id)].value = 0.0
        model.y["M1", "B1", "B2", shift2].value = 1.0
    obj_val = pyo.value(model.obj.expr)
    assert obj_val == pytest.approx(4.0 - 2.0 * 5.0)


def test_transition_weight_penalises_moves_mip():
    scenario = _base_scenario().model_copy(
        update={
            "objective_weights": ObjectiveWeights(
                production=1.0, mobilisation=0.0, transitions=3.0
            ),
            "mobilisation": None,
        }
    )
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)
    for mach in model.M:
        for blk in model.B:
            for day, shift_id in model.S:
                model.x[mach, blk, (day, shift_id)].value = 0.0
                model.prod[mach, blk, (day, shift_id)].value = 0.0
    shift1 = _shift_tuple(pb, 1)
    shift2 = _shift_tuple(pb, 2)
    model.x["M1", "B1", shift1].value = 1.0
    model.x["M1", "B2", shift2].value = 1.0
    model.prod["M1", "B1", shift1].value = 2.0
    model.prod["M1", "B2", shift2].value = 2.0
    if hasattr(model, "y") and hasattr(model, "S_transition"):
        for mach in model.M:
            for prev_blk in model.B:
                for curr_blk in model.B:
                    for day, shift_id in model.S_transition:
                        model.y[mach, prev_blk, curr_blk, (day, shift_id)].value = 0.0
        model.y["M1", "B1", "B2", shift2].value = 1.0
    obj_val = pyo.value(model.obj.expr)
    assert obj_val == pytest.approx(4.0 - 3.0 * 1.0)


def test_transition_weight_penalises_moves_sa():
    scenario = _base_scenario().model_copy(
        update={
            "objective_weights": ObjectiveWeights(
                production=1.0, mobilisation=0.0, transitions=2.0
            ),
            "mobilisation": None,
        }
    )
    pb = Problem.from_scenario(scenario)
    plan = {
        "M1": {1: "B1", 2: "B2"},
        "M2": {1: None, 2: None},
    }
    score = _evaluate(pb, Schedule(plan=plan))
    assert score == pytest.approx(4.0 - 2.0 * 1.0)


def test_landing_slack_penalty_mip():
    scenario = _base_scenario().model_copy(
        update={
            "landings": [Landing(id="L1", daily_capacity=1)],
            "objective_weights": ObjectiveWeights(
                production=1.0, mobilisation=0.0, landing_slack=2.0
            ),
            "mobilisation": None,
        }
    )
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)
    for mach in model.M:
        for blk in model.B:
            for day, shift_id in model.S:
                model.x[mach, blk, (day, shift_id)].value = 0.0
                model.prod[mach, blk, (day, shift_id)].value = 0.0
    shift1 = _shift_tuple(pb, 1)
    model.x["M1", "B1", shift1].value = 1.0
    model.x["M2", "B2", shift1].value = 1.0
    model.prod["M1", "B1", shift1].value = 2.0
    model.prod["M2", "B2", shift1].value = 2.0
    for mach in model.M:
        for blk in model.B:
            for day, shift_id in model.S:
                if (day, shift_id) != shift1:
                    model.prod[mach, blk, (day, shift_id)].value = 0.0
    if hasattr(model, "landing_slack"):
        for landing_id in model.L:
            for day, shift_id in model.S:
                model.landing_slack[landing_id, (day, shift_id)].value = 0.0
        model.landing_slack["L1", shift1].value = 1.0
    obj_val = pyo.value(model.obj.expr)
    assert obj_val == pytest.approx(4.0 - 2.0 * 1.0)


def test_landing_slack_penalty_sa():
    scenario = _base_scenario().model_copy(
        update={
            "landings": [Landing(id="L1", daily_capacity=1)],
            "objective_weights": ObjectiveWeights(
                production=1.0, mobilisation=0.0, landing_slack=3.0
            ),
            "mobilisation": None,
        }
    )
    pb = Problem.from_scenario(scenario)
    plan = {
        "M1": {1: "B1", 2: None},
        "M2": {1: "B2", 2: None},
    }
    score = _evaluate(pb, Schedule(plan=plan))
    # Two machines on one landing (capacity 1) -> slack 1 penalised
    assert score == pytest.approx(4.0 - 3.0 * 1.0)
