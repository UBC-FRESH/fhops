"""Contract tests for the shared-kernel adapter over a FHOPS schedule."""

from __future__ import annotations

import random

import pytest

from fhops.optimization.heuristics import Schedule
from fhops.optimization.heuristics.common import evaluate_assignments
from fhops.optimization.meta import (
    FhopsOperator,
    FhopsProblem,
    schedule_assignments,
    slot_diff,
    solve_kernel_ils,
    solve_kernel_sa,
    solve_kernel_sa_fast,
    solve_kernel_sa_incremental,
    solve_kernel_tabu,
)
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)
from fhops.scenario.contract.models import ShiftCalendarEntry
from fhops.scenario.io.loaders import load_scenario


def _simple_problem() -> Problem:
    blocks = [
        Block(id="B1", landing_id="L1", work_required=8.0, earliest_start=1, latest_finish=3),
        Block(id="B2", landing_id="L1", work_required=6.0, earliest_start=1, latest_finish=3),
    ]
    machines = [Machine(id="M1", role="harvester"), Machine(id="M2", role="harvester")]
    landings = [Landing(id="L1", daily_capacity=2)]
    calendar = [
        CalendarEntry(machine_id=machine, day=day, available=True)
        for machine in ("M1", "M2")
        for day in (1, 2, 3)
    ]
    shift_calendar = [
        ShiftCalendarEntry(machine_id=machine, day=day, shift_id="AM", available=True)
        for machine in ("M1", "M2")
        for day in (1, 2, 3)
    ]
    production_rates = [
        ProductionRate(machine_id="M1", block_id="B1", rate=4.0),
        ProductionRate(machine_id="M1", block_id="B2", rate=3.0),
        ProductionRate(machine_id="M2", block_id="B1", rate=3.0),
        ProductionRate(machine_id="M2", block_id="B2", rate=4.0),
    ]
    return Problem.from_scenario(
        Scenario(
            name="kernel",
            num_days=3,
            blocks=blocks,
            machines=machines,
            landings=landings,
            calendar=calendar,
            shift_calendar=shift_calendar,
            production_rates=production_rates,
        )
    )


def test_adapter_exposes_a_weighted_kernel_registry() -> None:
    """The FHOPS operators appear in the kernel registry with their weights."""
    problem = FhopsProblem(_simple_problem())
    assert problem.registry.names()
    assert all(weight > 0.0 for weight in problem.registry.weights().values())
    assert problem.greedy_schedule().plan


def test_operator_apply_returns_a_schedule_and_in_place_is_refused() -> None:
    """The wrapper uses the copying path; the delta path is not implemented."""
    problem = FhopsProblem(_simple_problem())
    operator = FhopsOperator(
        problem.fhops_registry.get("swap"),
        problem.operational,
    )
    schedule = problem.greedy_schedule()
    candidate = operator.apply(schedule, random.Random(1), problem.candidates)
    assert candidate is None or isinstance(candidate, Schedule)
    with pytest.raises(NotImplementedError):
        operator.propose_inplace(schedule, random.Random(1), problem.candidates)


def test_slot_diff_reports_the_changed_machine_slots() -> None:
    """The tabu signature is the set of changed slots, not the whole schedule."""
    before = Schedule(
        plan={"M1": {(1, "AM"): "B1"}, "M2": {(1, "AM"): "B2"}},
        matrix={"M1": ["B1"], "M2": ["B2"]},
    )
    after = Schedule(
        plan={"M1": {(1, "AM"): "B2"}, "M2": {(1, "AM"): "B2"}},
        matrix={"M1": ["B2"], "M2": ["B2"]},
    )
    assert slot_diff(before, after) == frozenset({("M1", 1, "AM")})


def test_kernel_sa_returns_a_replayable_assignment_table() -> None:
    """The kernel result round-trips through the FHOPS exact planned score."""
    pb = _simple_problem()
    result = solve_kernel_sa(pb, iters=80, seed=5)
    assert list(result["assignments"].columns) == [
        "machine_id",
        "block_id",
        "day",
        "shift_id",
        "assigned",
    ]
    assert result["objective"] == pytest.approx(evaluate_assignments(pb, result["assignments"]))
    assert result["meta"]["solver"] == "kernel-sa"
    assert result["meta"]["iterations"] == 80


def test_kernel_sa_can_restrict_operators() -> None:
    """An explicit operator list is reflected in the run metadata."""
    result = solve_kernel_sa(
        _simple_problem(),
        iters=20,
        seed=1,
        operators=["swap"],
        operator_weights={"swap": 2.0},
    )
    assert result["meta"]["operators"] == {"swap": 2.0}


def test_empty_schedule_exports_an_empty_table() -> None:
    """An empty plan produces the assignment schema with no rows."""
    frame = schedule_assignments(Schedule(plan={}, matrix={}))
    assert frame.empty
    assert list(frame.columns) == [
        "machine_id",
        "block_id",
        "day",
        "shift_id",
        "assigned",
    ]


def test_kernel_tabu_returns_a_replayable_assignment_table() -> None:
    """The kernel tabu result round-trips through the FHOPS exact planned score."""
    pb = _simple_problem()
    result = solve_kernel_tabu(pb, iters=40, seed=3, samples=4)
    assert result["meta"]["solver"] == "kernel-tabu"
    assert result["meta"]["samples"] == 4
    assert result["objective"] == pytest.approx(evaluate_assignments(pb, result["assignments"]))


def test_kernel_ils_returns_a_replayable_assignment_table() -> None:
    """The kernel ILS result round-trips through the FHOPS exact planned score."""
    pb = _simple_problem()
    result = solve_kernel_ils(pb, iters=10, seed=4, perturbation=2)
    assert result["meta"]["solver"] == "kernel-ils"
    assert result["meta"]["perturbation"] == 2
    assert result["objective"] == pytest.approx(evaluate_assignments(pb, result["assignments"]))


def test_kernel_fast_path_replays_exactly() -> None:
    """The dirty-repair search path reports a full exact score and replays exactly."""
    pb = _simple_problem()
    result = solve_kernel_sa_fast(pb, iters=40, seed=6)
    assert result["meta"]["approximate_search"] is True
    assert result["meta"]["solver"] == "kernel-sa-fast"
    assert result["objective"] == pytest.approx(evaluate_assignments(pb, result["assignments"]))


def test_kernel_incremental_path_replays_exactly() -> None:
    """The block-separable incremental path reports a full exact score and replays exactly."""
    pb = _simple_problem()
    result = solve_kernel_sa_incremental(pb, iters=60, seed=8)
    assert result["meta"]["incremental_search"] is True
    assert result["meta"]["solver"] == "kernel-sa-incremental"
    assert result["objective"] == pytest.approx(evaluate_assignments(pb, result["assignments"]))


def test_tiny7_automatic_weight_overrides_are_recorded() -> None:
    """The adapter applies the same built-in Tiny7 weight overrides as the existing solvers."""
    pb = Problem.from_scenario(load_scenario("examples/tiny7/scenario.yaml"))
    problem = FhopsProblem(pb)
    assert problem.objective_weight_overrides == {
        "production": 1.0,
        "mobilisation": 0.2,
        "transitions": 0.1,
        "landing_surplus": 0.05,
    }
    overridden = FhopsProblem(pb, objective_weight_overrides={"landing_surplus": 0.0})
    assert overridden.objective_weight_overrides == {"landing_surplus": 0.0}
