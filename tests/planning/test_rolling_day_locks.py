"""Day-level locks on multi-shift scenarios in rolling replay, exports and solvers (#125).

A lock without ``shift_id`` means "every available shift of that day on that block" in the
operational MILP (#115) and the heuristics. Rolling replay/carry-forward and exports used to pass
such locks to playback unlabelled, which collapsed them onto ``S1`` (FHOPS 1.0.0) or, since #116,
made playback reject them on multi-shift scenarios. They are now expanded to the day's available
shift slots everywhere.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import pytest
from test_rolling_robustness import chain_scenario

from fhops.optimization.heuristics.sa import solve_sa
from fhops.planning import (
    RollingHorizonConfig,
    RollingIterationPlan,
    RollingPlanResult,
    SolverOutput,
    carry_forward_state,
    compute_rolling_kpis,
    rolling_assignments_dataframe,
    run_rolling_horizon,
    solve_rolling_plan,
)
from fhops.scenario.contract import Problem, Scenario, ScheduleLock

SHIFTS = ("S1", "S2", "S3")


def _scenario(*, unavailable: Sequence[tuple[str, int, str]] = (), **kwargs: object) -> Scenario:
    scenario = chain_scenario(shift_labels=SHIFTS, num_days=4, **kwargs)  # type: ignore[arg-type]
    if not unavailable:
        return scenario
    blocked = set(unavailable)
    calendar = [
        entry.model_copy(update={"available": 0})
        if (entry.machine_id, entry.day, entry.shift_id) in blocked
        else entry
        for entry in scenario.shift_calendar or []
    ]
    payload = {name: getattr(scenario, name) for name in Scenario.model_fields}
    payload["shift_calendar"] = calendar
    return Scenario.model_validate(payload)


def _shift_locks(machine: str, block: str, day: int, shifts: Sequence[str]) -> list[ScheduleLock]:
    return [
        ScheduleLock(machine_id=machine, block_id=block, day=day, shift_id=shift)
        for shift in shifts
    ]


def test_carry_forward_expands_day_lock_to_every_shift() -> None:
    scenario = _scenario()
    day_locks = [
        ScheduleLock(machine_id="F1", block_id="B1", day=1),
        ScheduleLock(machine_id="S1", block_id="B1", day=2),
    ]
    explicit = _shift_locks("F1", "B1", 1, SHIFTS) + _shift_locks("S1", "B1", 2, SHIFTS)
    state = carry_forward_state(scenario, day_locks, through_day=2)
    assert state == carry_forward_state(scenario, explicit, through_day=2)
    # Three feller shifts (300 m³) felled, three skidder shifts (300 m³) skidded.
    assert state.remaining_work["B1"] == pytest.approx(100.0)


def test_day_lock_skips_unavailable_shifts() -> None:
    scenario = _scenario(unavailable=[("F1", 1, "S2")])
    day_lock = [ScheduleLock(machine_id="F1", block_id="B1", day=1)]
    explicit = _shift_locks("F1", "B1", 1, ("S1", "S3"))
    assert carry_forward_state(scenario, day_lock, through_day=1) == carry_forward_state(
        scenario, explicit, through_day=1
    )
    frame = rolling_assignments_dataframe(
        RollingPlanResult(locked_assignments=day_lock, iteration_summaries=[], metadata={}),
        scenario=scenario,
    )
    assert list(frame["shift_id"]) == ["S1", "S3"]
    assert set(frame["day"]) == {1}


def test_day_lock_with_production_on_multi_shift_day_is_rejected() -> None:
    scenario = _scenario()
    lock = ScheduleLock(machine_id="F1", block_id="B1", day=1, production=50.0)
    with pytest.raises(ValueError, match="give one lock per shift"):
        carry_forward_state(scenario, [lock], through_day=1)
    # Unambiguous when only one shift of the day is available: the production stays on it.
    single = _scenario(unavailable=[("F1", 1, "S1"), ("F1", 1, "S3")])
    state = carry_forward_state(single, [lock], through_day=1)
    assert state.initial_state is not None
    (block_state,) = state.initial_state.blocks
    assert block_state.staged_inventory == {"feller_buncher": pytest.approx(50.0)}


def test_compute_rolling_kpis_expands_day_locks() -> None:
    scenario = _scenario()
    day_locks = [ScheduleLock(machine_id="F1", block_id="B1", day=1)]
    comparison = compute_rolling_kpis(
        scenario, day_locks, baseline_assignments=_shift_locks("F1", "B1", 1, SHIFTS)
    )
    assert len(comparison.rolling_assignments) == 3
    assert comparison.delta_totals is not None
    assert comparison.delta_totals["total_production_delta"] == pytest.approx(0.0)
    result = RollingPlanResult(locked_assignments=day_locks, iteration_summaries=[], metadata={})
    kpis = compute_rolling_kpis(scenario, result).rolling_kpis
    assert kpis["total_production"] == pytest.approx(0.0)  # felled, not yet delivered
    assert int(kpis["sequencing_violation_count"]) == 0


class _DayLockHook:
    """Custom hook that reports day-level assignments (no ``shift_id``)."""

    name = "daylock"

    def __call__(
        self,
        scenario: Scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments: Sequence[ScheduleLock],
    ) -> SolverOutput:
        locks = [
            ScheduleLock(machine_id="F1", block_id="B1", day=day)
            for day in range(1, plan.horizon_days + 1)
        ]
        return SolverOutput(assignments=locks, objective=None, runtime_s=None)


@pytest.mark.filterwarnings("ignore:.*empty window:UserWarning")
def test_rolling_run_expands_hook_day_locks() -> None:
    scenario = _scenario(unavailable=[("F1", 2, "S3")])
    config = RollingHorizonConfig(scenario=scenario, master_days=4, subproblem_days=2, lock_days=2)
    result = run_rolling_horizon(config, _DayLockHook())
    slots = [(lk.day, lk.shift_id) for lk in result.locked_assignments]
    expected = [(d, s) for d in range(1, 5) for s in SHIFTS if (d, s) != (2, "S3")]
    assert slots == expected
    frame = rolling_assignments_dataframe(result)
    assert frame["shift_id"].notna().all()
    # Felled volume: 11 feller shifts at 100 m³ on a 400 m³ block -> 400 m³ staged, none left.
    state = carry_forward_state(scenario, result.locked_assignments, through_day=4)
    assert state.initial_state is not None
    assert state.initial_state.blocks[0].role_remaining["feller_buncher"] == pytest.approx(0.0)


@pytest.mark.parametrize("solver", ["sa", "mip"])
def test_solvers_apply_day_lock_to_every_available_shift(solver: str) -> None:
    scenario = _scenario(
        unavailable=[("S1", 2, "S2")],
        locked_assignments=[ScheduleLock(machine_id="S1", block_id="B2", day=2)],
    )
    result = solve_rolling_plan(
        scenario,
        master_days=4,
        subproblem_days=4,
        lock_days=4,
        solver=solver,
        sa_iters=200,
        mip_solver="highs",
        mip_time_limit=30,
    )
    worked = {
        (lk.shift_id, lk.block_id)
        for lk in result.locked_assignments
        if lk.machine_id == "S1" and lk.day == 2
    }
    assert worked == {("S1", "B2"), ("S3", "B2")}
    kpis = compute_rolling_kpis(scenario, result).rolling_kpis
    assert int(kpis["sequencing_violation_count"]) == 0


def test_heuristic_plan_matches_milp_day_lock_slots() -> None:
    scenario = _scenario(
        unavailable=[("F1", 1, "S2")],
        locked_assignments=[ScheduleLock(machine_id="F1", block_id="B2", day=1)],
    )
    pb = Problem.from_scenario(scenario)
    assignments = solve_sa(pb, iters=100, seed=3)["assignments"]
    day1 = assignments[(assignments.machine_id == "F1") & (assignments.day == 1)]
    assert sorted(zip(day1.shift_id, day1.block_id, strict=True)) == [("S1", "B2"), ("S3", "B2")]
    assert isinstance(assignments, pd.DataFrame)


def test_day_lock_on_unavailable_single_shift_day_is_idle() -> None:
    # Single-shift scenario, F1 unavailable on day 1: the MILP pins the lock to idle, so the
    # replay must not credit the feller's output (it did before #125).
    scenario = chain_scenario()
    calendar = [
        entry.model_copy(update={"available": 0})
        if (entry.machine_id, entry.day) == ("F1", 1)
        else entry
        for entry in scenario.calendar
    ]
    payload = {name: getattr(scenario, name) for name in Scenario.model_fields}
    payload["calendar"] = calendar
    scenario = Scenario.model_validate(payload)
    lock = ScheduleLock(machine_id="F1", block_id="B1", day=1)
    state = carry_forward_state(scenario, [lock], through_day=1)
    assert state.initial_state is None
    assert state.remaining_work == {"B1": 400.0, "B2": 400.0}
