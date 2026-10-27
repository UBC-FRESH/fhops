"""Regression coverage for the Phase 8.31 MILP/rolling audit fixes (#157)."""

from __future__ import annotations

import pyomo.environ as pyo
import pytest

from fhops.model.milp.data import machine_slot_available
from fhops.model.milp.driver import (
    _extract_assignments,
    _solver_option_warnings,
    solve_operational_milp,
)
from fhops.planning.rolling import RollingIterationPlan, _lock_span_has_capacity
from fhops.scenario.contract import Problem, Scenario
from fhops.scenario.contract.models import ShiftCalendarEntry


def _calendar_scenario(*, day_available: int, shift_available: tuple[int, int]) -> Scenario:
    from tests.initial_state._scenarios import chain_scenario

    scenario = chain_scenario(num_days=1)
    scenario = scenario.model_copy(
        update={
            "schema_version": "1.0.0",
            "calendar": [
                entry.model_copy(update={"available": day_available}) for entry in scenario.calendar
            ],
            "shift_calendar": [
                ShiftCalendarEntry(machine_id="F1", day=1, shift_id=shift, available=available)
                for shift, available in zip(("S1", "S2"), shift_available, strict=True)
            ],
        }
    )
    return scenario


def test_machine_availability_requires_day_and_shift_calendar() -> None:
    from fhops.optimization.operational_problem import build_operational_problem

    ctx = build_operational_problem(
        Problem.from_scenario(_calendar_scenario(day_available=0, shift_available=(1, 1)))
    )
    bundle = ctx.bundle
    assert machine_slot_available(bundle, "F1", 1, "S1") is False
    assert machine_slot_available(bundle, "F1", 1, "S2") is False

    ctx = build_operational_problem(
        Problem.from_scenario(_calendar_scenario(day_available=1, shift_available=(0, 1)))
    )
    bundle = ctx.bundle
    assert machine_slot_available(bundle, "F1", 1, "S1") is False
    assert machine_slot_available(bundle, "F1", 1, "S2") is True


def test_phantom_fractional_assignment_is_not_exported() -> None:
    model = pyo.ConcreteModel()
    keys = [("F1", "B1", 1, "S1")]
    model.x = pyo.Var(keys, initialize=0.0)
    model.prod = pyo.Var(keys, initialize=0.0)
    model.x[keys[0]].set_value(7e-7)
    model.prod[keys[0]].set_value(5.0)
    assert _extract_assignments(model).empty

    model.x[keys[0]].set_value(1.0)
    frame = _extract_assignments(model)
    assert len(frame) == 1
    assert frame.iloc[0]["assigned"] == 1
    assert frame.iloc[0]["production"] == pytest.approx(5.0)


def test_negative_limits_and_invalid_gap_are_rejected() -> None:
    with pytest.raises(ValueError, match="time_limit"):
        solve_operational_milp(None, time_limit=-1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="gap"):
        solve_operational_milp(None, gap=1.5)  # type: ignore[arg-type]


def test_solver_option_log_warnings_are_surfaced() -> None:
    lines = [
        "Solving model",
        "ERROR: Option 'typo_option' is not recognized",
        "WARNING: option threads is outside its bounds",
        "Model status: optimal",
    ]
    warnings = _solver_option_warnings(lines)
    assert len(warnings) == 2


def test_non_terminal_role_may_exceed_terminal_remaining() -> None:
    from tests.initial_state._scenarios import chain_scenario

    scenario = chain_scenario(
        num_days=2,
        work_b1=40.0,
        initial_state={
            "blocks": [
                {
                    "block_id": "B1",
                    "role_remaining": {"feller_buncher": 90.0},
                    "staged_inventory": {"feller_buncher": 1.0},
                }
            ]
        },
    )
    assert scenario.initial_state is not None
    assert scenario.initial_state.blocks[0].role_remaining["feller_buncher"] == 90.0


def test_lock_span_without_block_window_has_no_capacity() -> None:
    from tests.initial_state._scenarios import chain_scenario

    scenario = chain_scenario(num_days=4)
    late = scenario.model_copy(
        update={
            "blocks": [block.model_copy(update={"earliest_start": 4}) for block in scenario.blocks]
        }
    )
    plan = RollingIterationPlan(iteration_index=0, start_day=1, horizon_days=4, lock_days=1)
    assert _lock_span_has_capacity(late, Problem.from_scenario(late), plan) is False
    assert _lock_span_has_capacity(scenario, Problem.from_scenario(scenario), plan) is True
