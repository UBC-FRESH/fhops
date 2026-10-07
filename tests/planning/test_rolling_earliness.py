"""Rolling-horizon MILP deferral and window-failure flags (#141)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from fhops.planning import (
    RollingHorizonConfig,
    RollingInfeasibleError,
    RollingIterationPlan,
    SolverOutput,
    compute_rolling_kpis,
    run_rolling_horizon,
    solve_rolling_plan,
    summarize_plan,
)
from fhops.planning import rolling as rolling_module
from fhops.planning.rolling import MILPSolver, StubSolver
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
    ScheduleLock,
)


def defer_scenario(num_days: int = 10) -> Scenario:
    """Audit repro ``defer.py``: one machine, 300 m³ at 100 m³/day; three days of work."""

    return Scenario(
        name="defer",
        num_days=num_days,
        blocks=[Block(id="B1", landing_id="L1", work_required=300)],
        machines=[Machine(id="F1", role="feller_buncher")],
        landings=[Landing(id="L1", daily_capacity=2)],
        calendar=[
            CalendarEntry(machine_id="F1", day=day, available=1) for day in range(1, num_days + 1)
        ],
        production_rates=[ProductionRate(machine_id="F1", block_id="B1", rate=100)],
    )


def _config(scenario: Scenario, master: int, sub: int, lock: int) -> RollingHorizonConfig:
    return RollingHorizonConfig(
        scenario=scenario, master_days=master, subproblem_days=sub, lock_days=lock
    )


class DeferringSolver:
    """Plans all work on the last day of each window (a tied optimum of the base objective)."""

    name = "deferring"

    def __call__(
        self,
        scenario: Scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments: Sequence[ScheduleLock],
    ) -> SolverOutput:
        day = plan.horizon_days
        locks = [
            ScheduleLock(machine_id="F1", block_id="B1", day=d, shift_id="S1", production=0.0)
            for d in range(1, day)
        ]
        locks.append(
            ScheduleLock(machine_id="F1", block_id="B1", day=day, shift_id="S1", production=100.0)
        )
        return SolverOutput(assignments=locks, objective=0.0)


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_rolling_milp_does_not_defer_work_past_the_lock_span() -> None:
    scenario = defer_scenario()
    result = solve_rolling_plan(
        scenario,
        master_days=10,
        subproblem_days=6,
        lock_days=1,
        solver="mip",
        mip_solver="highs",
        mip_time_limit=30,
    )

    worked = sorted(lock.day for lock in result.locked_assignments if (lock.production or 0) > 0)
    assert worked == [1, 2, 3]
    assert result.empty_windows == []
    assert result.no_solution_windows == []
    assert result.metadata["mip_earliness"] is True
    kpis = compute_rolling_kpis(scenario, result).rolling_kpis
    assert float(kpis["total_production"]) == pytest.approx(300.0)
    summary = summarize_plan(result)
    first = summary["iterations"][0]
    # Window objectives are the base objective (production − leftover), not the tie-break.
    assert first["objective"] == pytest.approx(300.0)
    assert first["locked_production"] == pytest.approx(100.0)
    assert any(str(w).startswith("earliness=applied") for w in first["warnings"])


def test_milp_hook_applies_earliness_only_when_the_lock_span_is_shorter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[bool, int | None]] = []
    real = rolling_module.solve_operational_milp

    def capture(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen.append((kwargs["earliness"], kwargs["earliness_time_limit"]))
        return real(*args, **kwargs)

    monkeypatch.setattr(rolling_module, "solve_operational_milp", capture)
    scenario = defer_scenario(num_days=4)
    partial = RollingIterationPlan(iteration_index=0, start_day=1, horizon_days=4, lock_days=2)
    covered = RollingIterationPlan(iteration_index=0, start_day=1, horizon_days=4, lock_days=4)
    MILPSolver(solver="highs", time_limit=10)(scenario, partial, locked_assignments=[])
    MILPSolver(solver="highs", time_limit=10)(scenario, covered, locked_assignments=[])
    MILPSolver(solver="highs", time_limit=10, earliness=False)(
        scenario, partial, locked_assignments=[]
    )
    MILPSolver(solver="highs", time_limit=10, earliness_time_limit=3)(
        scenario, partial, locked_assignments=[]
    )
    assert seen == [(True, None), (False, None), (False, None), (True, 3)]


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_idle_lock_span_is_flagged_empty() -> None:
    """Locks without production count as an idle lock span (#141; #117 counted locks only)."""

    result = run_rolling_horizon(_config(defer_scenario(), 10, 6, 1), DeferringSolver())
    first = result.iteration_summaries[0]
    assert first.locked_assignments == 1
    assert first.locked_production == 0.0
    assert first.planned_delivered == pytest.approx(100.0)
    assert first.empty is True
    assert 0 in result.empty_windows
    assert "producing 0.000 m³" in (first.warnings or [""])[-1]


def test_fail_on_empty_window_stops_on_empty_windows() -> None:
    with pytest.warns(UserWarning, match="empty window"):
        with pytest.raises(RollingInfeasibleError, match="empty window") as excinfo:
            run_rolling_horizon(
                _config(defer_scenario(), 10, 6, 1), DeferringSolver(), fail_on_empty_window=True
            )
    error = excinfo.value
    assert error.iteration_index == 0
    assert error.partial_result is not None
    assert [s.status for s in error.partial_result.iteration_summaries] == ["solved"]

    with pytest.warns(UserWarning, match="empty window"):
        with pytest.raises(RollingInfeasibleError, match="fail_on_empty_window"):
            run_rolling_horizon(
                _config(defer_scenario(), 10, 6, 1), StubSolver(), fail_on_empty_window=True
            )


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_fail_on_no_solution_ignores_empty_windows() -> None:
    result = run_rolling_horizon(
        _config(defer_scenario(), 10, 6, 1), DeferringSolver(), fail_on_no_solution=True
    )
    assert result.empty_windows
    assert result.metadata["fail_on_no_solution"] is True
    assert result.metadata["fail_on_empty_window"] is False


@pytest.mark.parametrize("flag", ["fail_on_no_solution", "fail_on_empty_window"])
def test_failure_flags_stop_on_solver_errors(flag: str) -> None:
    class FailingSolver:
        name = "failing"

        def __call__(self, scenario, plan, *, locked_assignments):  # type: ignore[no-untyped-def]
            return SolverOutput(
                assignments=[], has_solution=False, error="ApplicationError: crashed"
            )

    with pytest.warns(UserWarning, match="solver failed"):
        with pytest.raises(RollingInfeasibleError, match=f"crashed.*{flag}=True") as excinfo:
            run_rolling_horizon(
                _config(defer_scenario(), 10, 6, 1), FailingSolver(), **{flag: True}
            )
    summaries = excinfo.value.partial_result.iteration_summaries  # type: ignore[union-attr]
    assert [s.error for s in summaries] == ["ApplicationError: crashed"]


@pytest.mark.parametrize("max_iterations", [0, -1])
def test_max_iterations_must_be_positive(max_iterations: int) -> None:
    with pytest.raises(ValueError, match="max_iterations must be >= 1"):
        run_rolling_horizon(
            _config(defer_scenario(), 10, 6, 1), StubSolver(), max_iterations=max_iterations
        )


def test_milp_hook_availability() -> None:
    assert MILPSolver(solver="highs").available() is True
    assert MILPSolver(solver="nosuchsolver").available() is False
