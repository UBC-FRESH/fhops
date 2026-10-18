"""Rolling-horizon robustness (#117): windows without a plan, empty windows, lock windows, partial
shift calendars, slot order, and an independent replay of the carried state."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import pandas as pd
import pytest

from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics.sa import solve_sa
from fhops.planning import (
    RollingHorizonConfig,
    RollingInfeasibleError,
    RollingIterationPlan,
    RollingPlanResult,
    SolverOutput,
    carry_forward_state,
    compute_rolling_kpis,
    get_solver_hook,
    run_rolling_horizon,
    slice_scenario_for_window,
    solve_rolling_plan,
    summarize_plan,
)
from fhops.planning import rolling as rolling_module
from fhops.planning.rolling import MILPSolver, StubSolver
from fhops.scenario.contract import (
    Block,
    BlockInitialState,
    CalendarEntry,
    Landing,
    Machine,
    MachineInitialState,
    Problem,
    ProductionRate,
    Scenario,
    ScenarioInitialState,
    ScheduleLock,
)
from fhops.scenario.contract.models import ShiftCalendarEntry
from fhops.scheduling.systems import HarvestSystem, SystemJob
from fhops.scheduling.timeline.models import ShiftDefinition, TimelineConfig

ROLE_JOBS = {
    "feller_buncher": "felling",
    "grapple_skidder": "primary_transport",
    "processor": "processing",
}


def _chain_system(roles: Sequence[str], headstart: dict[str, float] | None = None) -> HarvestSystem:
    jobs = [
        SystemJob(ROLE_JOBS[role], role, [ROLE_JOBS[roles[i - 1]]] if i else [])
        for i, role in enumerate(roles)
    ]
    return HarvestSystem(system_id="chain", jobs=jobs, role_headstart_shifts=headstart)


def chain_scenario(
    *,
    roles: Sequence[str] = ("feller_buncher", "grapple_skidder"),
    blocks: dict[str, float] | None = None,
    rates: dict[tuple[str, str], float] | None = None,
    num_days: int = 6,
    shift_labels: Sequence[str] | None = None,
    timeline_shifts: Sequence[str] | None = None,
    shift_days: Sequence[int] | None = None,
    headstart: dict[str, float] | None = None,
    **extra: object,
) -> Scenario:
    """Linear chain, one machine per role (``F1``, ``S1``, ``P1``)."""

    blocks = blocks or {"B1": 400.0, "B2": 400.0}
    machine_ids = {"feller_buncher": "F1", "grapple_skidder": "S1", "processor": "P1"}
    machines = [Machine(id=machine_ids[role], role=role) for role in roles]
    if rates is None:
        rates = {}
        for machine in machines:
            for index, block_id in enumerate(blocks):
                rates[(machine.id, block_id)] = 100.0 if index == 0 else 50.0
    shift_calendar = None
    if shift_labels:
        days = shift_days if shift_days is not None else range(1, num_days + 1)
        shift_calendar = [
            ShiftCalendarEntry(machine_id=m.id, day=day, shift_id=label, available=1)
            for m in machines
            for day in days
            for label in shift_labels
        ]
    timeline = None
    if timeline_shifts:
        timeline = TimelineConfig(
            shifts=[
                ShiftDefinition(name=name, hours=8.0, shifts_per_day=1) for name in timeline_shifts
            ]
        )
    return Scenario(
        name="robustness",
        num_days=num_days,
        blocks=[
            Block(id=block_id, landing_id="L1", work_required=work, harvest_system_id="chain")
            for block_id, work in blocks.items()
        ],
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=6)],
        calendar=[
            CalendarEntry(machine_id=m.id, day=day, available=1)
            for m in machines
            for day in range(1, num_days + 1)
        ],
        shift_calendar=shift_calendar,
        timeline=timeline,
        production_rates=[
            ProductionRate(machine_id=m, block_id=b, rate=r) for (m, b), r in rates.items()
        ],
        harvest_systems={"chain": _chain_system(roles, headstart)},
        **extra,  # type: ignore[arg-type]
    )


def lockinfeas_scenario() -> Scenario:
    """Audit repro: a user skidder lock on day 3 is infeasible for a short window starting on day 3.

    With windows of 2 days and no overlap the window MILP for days 3-4 cannot stage felled wood on
    B2 before the locked skidder shift (head start of one shift), so it has no solution.
    """

    return chain_scenario(
        headstart={"grapple_skidder": 1.0},
        locked_assignments=[ScheduleLock(machine_id="S1", block_id="B2", day=3)],
    )


class RecordingSolver:
    def __init__(self, inner: object) -> None:
        self.inner = inner
        self.name = getattr(inner, "name", "recording")
        self.calls: list[tuple[RollingIterationPlan, Scenario]] = []

    def __call__(
        self,
        scenario: Scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments: Sequence[ScheduleLock],
    ) -> SolverOutput:
        self.calls.append((plan, scenario.model_copy(deep=True)))
        return self.inner(scenario, plan, locked_assignments=locked_assignments)  # type: ignore[operator]


def _mip_hook() -> object:
    return get_solver_hook("mip", mip_solver="highs", mip_time_limit=10)


def _config(scenario: Scenario, master: int, sub: int, lock: int) -> RollingHorizonConfig:
    return RollingHorizonConfig(
        scenario=scenario, master_days=master, subproblem_days=sub, lock_days=lock
    )


def _state_key(state):  # type: ignore[no-untyped-def]
    return (state.remaining_work, state.initial_state)


# (1) Windows without a solution ------------------------------------------------------------------
@pytest.fixture
def no_solution_on_second_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the second MILP window return a genuine no-solution driver result.

    Since #115 user locks no longer make a window infeasible (locked machines may idle), so the
    no-solution path is exercised by wrapping the real driver and returning the result shape the
    driver produces for a time limit without incumbent on its second call.
    """

    real_driver = rolling_module.solve_operational_milp
    calls = {"n": 0}

    def wrapped(*args: object, **kwargs: object) -> dict[str, object]:
        calls["n"] += 1
        if calls["n"] == 2:
            return {
                "objective": None,
                "production": 0.0,
                "assignments": pd.DataFrame(
                    columns=["machine_id", "block_id", "day", "shift_id", "assigned", "production"]
                ),
                "solver_status": "aborted",
                "termination_condition": "maxTimeLimit",
                "has_solution": False,
                "outcome": "no_solution",
            }
        return real_driver(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(rolling_module, "solve_operational_milp", wrapped)


@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.usefixtures("no_solution_on_second_window")
def test_infeasible_milp_window_is_recorded_and_left_idle() -> None:
    scenario = lockinfeas_scenario()
    recorder = RecordingSolver(_mip_hook())
    result = run_rolling_horizon(_config(scenario, 6, 2, 2), recorder)

    statuses = [summary.status for summary in result.iteration_summaries]
    assert statuses == ["solved", "no_solution", "solved"]
    failed = result.iteration_summaries[1]
    assert failed.has_solution is False
    assert failed.objective is None
    assert failed.locked_assignments == 0
    assert failed.locked_delivered == 0.0
    assert failed.planned_delivered == 0.0
    assert failed.empty is True
    assert failed.warnings is not None
    assert any("no solution" in message for message in failed.warnings)
    assert any("1 user lock(s)" in message for message in failed.warnings)
    assert result.no_solution_windows == [1]
    assert 1 in result.empty_windows
    assert any("Iteration 1 (days 3-4)" in message for message in result.warnings or [])
    # Machines idle on days 3-4 (the user lock is not applied either) ...
    assert not [lock for lock in result.locked_assignments if lock.day in (3, 4)]
    # ... so the carried state is unchanged across the idle span.
    before = carry_forward_state(scenario, result.locked_assignments, through_day=2)
    after = carry_forward_state(scenario, result.locked_assignments, through_day=4)
    assert _state_key(before) == _state_key(after)
    third_window = recorder.calls[2][1]
    assert {b.id: b.work_required for b in third_window.blocks} == before.remaining_work
    assert third_window.initial_state == before.initial_state
    # The run continues and the stitched plan stays clean.
    kpis = compute_rolling_kpis(scenario, result).rolling_kpis
    assert int(kpis["sequencing_violation_count"]) == 0
    assert float(kpis["total_production"]) > 0.0

    summary = summarize_plan(result)
    assert summary["no_solution_windows"] == 1
    assert summary["empty_windows"] == len(result.empty_windows) >= 1
    assert summary["no_solution_window_indices"] == [1]
    records = summary["iterations"]
    assert isinstance(records, list)
    assert records[1]["status"] == "no_solution" and records[1]["has_solution"] is False


@pytest.mark.usefixtures("no_solution_on_second_window")
def test_fail_on_empty_window_raises_with_partial_result() -> None:
    scenario = lockinfeas_scenario()
    with pytest.raises(RollingInfeasibleError, match=r"Iteration 1 \(days 3-4\)") as excinfo:
        with pytest.warns(UserWarning, match="no solution"):
            solve_rolling_plan(
                scenario,
                master_days=6,
                subproblem_days=2,
                lock_days=2,
                solver="mip",
                mip_solver="highs",
                mip_time_limit=10,
                fail_on_empty_window=True,
            )
    error = excinfo.value
    assert error.iteration_index == 1
    partial = error.partial_result
    assert partial is not None
    assert [s.status for s in partial.iteration_summaries] == ["solved", "no_solution"]
    assert partial.locked_assignments
    assert all(lock.day <= 2 for lock in partial.locked_assignments)
    assert partial.metadata["fail_on_empty_window"] is True


@pytest.mark.parametrize("shape", ["error", "future_no_solution", "objective_none"])
def test_milp_hook_reports_no_solution_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    """Driver results without a solution (incl. ``outcome="error"``, #141) are no_solution windows."""

    def fake_driver(*args: object, **kwargs: object) -> dict[str, object]:
        result: dict[str, object] = {
            "objective": None,
            "production": 0.0,
            "assignments": pd.DataFrame(
                columns=["machine_id", "block_id", "day", "shift_id", "assigned", "production"]
            ),
            "solver_status": "aborted",
            "termination_condition": "maxTimeLimit",
        }
        if shape == "future_no_solution":
            result["has_solution"] = False
        if shape == "error":
            result.update(
                has_solution=False,
                outcome="error",
                solver_status="error",
                termination_condition="error",
                solver_error="RuntimeError: A feasible solution was not found",
            )
        return result

    monkeypatch.setattr(rolling_module, "solve_operational_milp", fake_driver)
    scenario = chain_scenario(num_days=4)
    plan = RollingIterationPlan(iteration_index=0, start_day=1, horizon_days=4, lock_days=2)
    output = MILPSolver(solver="highs", time_limit=1)(scenario, plan, locked_assignments=[])
    assert output.has_solution is False
    assert list(output.assignments) == [] and output.objective is None
    assert output.warnings
    if shape == "error":
        assert "solver_error=RuntimeError: A feasible solution was not found" in output.warnings
        assert output.error == "RuntimeError: A feasible solution was not found"
    else:
        assert "termination_condition=maxTimeLimit" in output.warnings
        assert output.error is None

    with pytest.warns(UserWarning, match="no solution|solver failed"):
        result = run_rolling_horizon(
            _config(scenario, 4, 2, 2), MILPSolver(solver="highs", time_limit=1)
        )
    assert result.locked_assignments == []
    assert result.no_solution_windows == [0, 1]
    assert result.empty_windows == [0, 1]
    errors = [summary.error for summary in result.iteration_summaries]
    if shape == "error":
        assert errors == ["RuntimeError: A feasible solution was not found"] * 2
        assert "the solver failed (RuntimeError" in (result.warnings or [""])[0]
        assert summarize_plan(result)["iterations"][0]["error"] == errors[0]
    else:
        assert errors == [None, None]


def test_milp_hook_propagates_unexpected_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """#141: exceptions from the driver/model build are FHOPS defects and are not swallowed."""

    def fake_driver(*args: object, **kwargs: object) -> dict[str, object]:
        raise KeyError("bug in the model build")

    monkeypatch.setattr(rolling_module, "solve_operational_milp", fake_driver)
    scenario = chain_scenario(num_days=4)
    with pytest.raises(KeyError, match="bug in the model build") as excinfo:
        run_rolling_horizon(_config(scenario, 4, 2, 2), MILPSolver(solver="highs", time_limit=1))
    partial = getattr(excinfo.value, "partial_result", None)
    assert isinstance(partial, RollingPlanResult)
    assert partial.iteration_summaries == []


@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.parametrize("has_solution", [False, True])
def test_milp_hook_forwards_driver_solver_error_and_warnings(
    monkeypatch: pytest.MonkeyPatch, has_solution: bool
) -> None:
    """#124: the driver's ``solver_error`` and ``warnings`` reach SolverOutput / iterations."""

    lock_warning = "lock (F1, B1, day 1, shift *) pinned to x=0: day 1 is outside the block window"

    def fake_driver(*args: object, **kwargs: object) -> dict[str, object]:
        rows = [
            {"machine_id": "F1", "block_id": "B1", "day": 1, "shift_id": "S1"},
            {"machine_id": "F1", "block_id": "B1", "day": 2, "shift_id": "S1"},
        ]
        return {
            "objective": 1.0 if has_solution else None,
            "production": 0.0,
            "assignments": pd.DataFrame(
                [dict(row, assigned=1, production=100.0) for row in rows] if has_solution else [],
                columns=["machine_id", "block_id", "day", "shift_id", "assigned", "production"],
            ),
            "has_solution": has_solution,
            "outcome": "feasible" if has_solution else "error",
            "solver_status": "aborted" if has_solution else "unknown",
            "termination_condition": "maxTimeLimit" if has_solution else "unknown",
            "solver_error": None if has_solution else "ERROR:   Option 'threads' is set to 997",
            # Duplicates (also of the status line) are dropped.
            "warnings": [lock_warning, lock_warning, "termination_condition=maxTimeLimit"],
        }

    monkeypatch.setattr(rolling_module, "solve_operational_milp", fake_driver)
    scenario = chain_scenario(num_days=4)
    plan = RollingIterationPlan(iteration_index=0, start_day=1, horizon_days=4, lock_days=2)
    output = MILPSolver(solver="highs", time_limit=1)(scenario, plan, locked_assignments=[])
    assert output.has_solution is has_solution
    if has_solution:
        assert output.warnings == [
            "solver_status=aborted",
            "termination_condition=maxTimeLimit",
            lock_warning,
        ]
    else:
        assert output.warnings == [
            "solver_status=unknown",
            "termination_condition=unknown",
            "solver_error=ERROR:   Option 'threads' is set to 997",
            lock_warning,
            "termination_condition=maxTimeLimit",
        ]

    result = run_rolling_horizon(
        _config(scenario, 4, 2, 2), MILPSolver(solver="highs", time_limit=1)
    )
    for summary in result.iteration_summaries:
        assert summary.warnings is not None
        assert summary.warnings.count(lock_warning) == 1
        assert any(w.startswith("solver_error=") for w in summary.warnings) is not has_solution


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_milp_hook_forwards_real_highs_lock_warning() -> None:
    """A real driver warning that scenario validation still allows.

    A day lock on a day without any slot in the shift grid (the only ``shift_calendar`` entry of
    that day is unavailable) passes validation; the operational MILP ignores it with a warning.
    (Until #129 this test used a block with an unregistered ``harvest_system_id``, which scenario
    validation now rejects.)
    """

    scenario = Scenario(
        name="no-slot-lock",
        num_days=4,
        blocks=[Block(id="B1", landing_id="L1", work_required=200.0)],
        machines=[Machine(id="F1", role="feller_buncher")],
        landings=[Landing(id="L1", daily_capacity=2)],
        calendar=[CalendarEntry(machine_id="F1", day=day, available=1) for day in range(1, 5)],
        shift_calendar=[
            ShiftCalendarEntry(machine_id="F1", day=day, shift_id="S1", available=int(day != 1))
            for day in range(1, 5)
        ],
        production_rates=[ProductionRate(machine_id="F1", block_id="B1", rate=100.0)],
        locked_assignments=[ScheduleLock(machine_id="F1", block_id="B1", day=1)],
    )
    expected = "lock (F1, B1, day 1, shift *) ignored: no matching slot in the shift grid"
    plan = RollingIterationPlan(iteration_index=0, start_day=1, horizon_days=4, lock_days=2)
    output = MILPSolver(solver="highs", time_limit=30)(scenario, plan, locked_assignments=[])
    assert output.has_solution is True
    assert output.warnings is not None
    assert output.warnings.count(expected) == 1
    assert not any(w.startswith("solver_error=") for w in output.warnings)

    result = run_rolling_horizon(
        _config(scenario, 4, 4, 2), MILPSolver(solver="highs", time_limit=30)
    )
    first = result.iteration_summaries[0]
    assert first.warnings is not None and expected in first.warnings


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_hook_assignments_are_ignored_without_a_solution() -> None:
    def hook(scenario, plan, *, locked_assignments):  # type: ignore[no-untyped-def]
        return SolverOutput(
            assignments=[ScheduleLock(machine_id="F1", block_id="B1", day=1, shift_id="S1")],
            objective=12.0,
            has_solution=False,
        )

    result = run_rolling_horizon(_config(chain_scenario(num_days=4), 4, 2, 2), hook)
    assert result.locked_assignments == []
    assert all(s.objective is None for s in result.iteration_summaries)


# (2) Empty windows -------------------------------------------------------------------------------
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_zero_delivery_plan_is_flagged_as_empty() -> None:
    """A solved window whose plan delivers nothing (e.g. an all-zero incumbent) is flagged."""

    def zero_hook(scenario, plan, *, locked_assignments):  # type: ignore[no-untyped-def]
        locks = [
            ScheduleLock(machine_id="F1", block_id="B1", day=day, shift_id="S1", production=0.0)
            for day in range(1, plan.horizon_days + 1)
        ]
        return SolverOutput(assignments=locks, objective=0.0)

    result = run_rolling_horizon(_config(chain_scenario(num_days=4), 4, 2, 2), zero_hook)
    assert [s.status for s in result.iteration_summaries] == ["solved", "solved"]
    assert all(s.locked_assignments == 2 for s in result.iteration_summaries)
    assert all(s.planned_delivered == 0.0 for s in result.iteration_summaries)
    assert result.empty_windows == [0, 1]
    assert summarize_plan(result)["empty_windows"] == 2
    assert all(
        any("empty window" in w for w in s.warnings or []) for s in result.iteration_summaries
    )

    stub = run_rolling_horizon(_config(chain_scenario(num_days=4), 4, 2, 2), StubSolver())
    assert stub.empty_windows == [0, 1] and stub.no_solution_windows == []


def test_windows_without_remaining_work_are_not_empty() -> None:
    scenario = chain_scenario(
        roles=("feller_buncher",), blocks={"B1": 100.0}, rates={("F1", "B1"): 100.0}, num_days=4
    )
    for kind in ("sa", "mip"):
        hook = get_solver_hook("sa", sa_iters=100, sa_seed=3) if kind == "sa" else _mip_hook()
        result = run_rolling_horizon(_config(scenario, 4, 2, 2), hook)  # type: ignore[arg-type]
        assert result.iteration_summaries[0].locked_delivered == pytest.approx(100.0)
        assert result.iteration_summaries[1].remaining_work_start == 0.0
        assert result.empty_windows == [], kind


# (3) Locks outside their block's time window -----------------------------------------------------
@pytest.mark.parametrize("kind", ["sa", "mip"])
@pytest.mark.parametrize("sub,lock", [(6, 6), (3, 3), (2, 1)])
def test_lock_outside_block_window_rejected_up_front(kind: str, sub: int, lock: int) -> None:
    base = chain_scenario(roles=("feller_buncher",), num_days=6)
    blocks = [base.blocks[0].model_copy(update={"latest_finish": 2}), base.blocks[1]]
    # model_copy skips validation, like scenarios built before #118's contract checks.
    scenario = base.model_copy(
        update={
            "blocks": blocks,
            "locked_assignments": [ScheduleLock(machine_id="F1", block_id="B1", day=4)],
        }
    )
    recorder = RecordingSolver(get_solver_hook("sa", sa_iters=50) if kind == "sa" else _mip_hook())
    with pytest.raises(RollingInfeasibleError, match="F1->B1 on day 4 \\(block window 1-2\\)"):
        run_rolling_horizon(_config(scenario, 6, sub, lock), recorder)
    assert recorder.calls == []


@pytest.mark.parametrize("sub,lock", [(6, 6), (3, 3), (2, 1)])
def test_valid_lock_at_block_window_edge_never_hits_overlap_error(sub: int, lock: int) -> None:
    base = chain_scenario(roles=("feller_buncher",), num_days=6)
    blocks = [base.blocks[0].model_copy(update={"latest_finish": 2}), base.blocks[1]]
    scenario = Scenario.model_validate(
        {
            **{name: getattr(base, name) for name in Scenario.model_fields},
            "blocks": blocks,
            "locked_assignments": [ScheduleLock(machine_id="F1", block_id="B1", day=2)],
        }
    )
    result = solve_rolling_plan(
        scenario, master_days=6, subproblem_days=sub, lock_days=lock, solver="sa", sa_iters=50
    )
    assert ("F1", "B1", 2) in {
        (lk.machine_id, lk.block_id, lk.day) for lk in result.locked_assignments
    }


@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.parametrize(
    "sub,lock",
    [(6, 6), (2, 2), (3, 2)],
)
def test_downstream_user_lock_in_short_windows_does_not_crash(sub: int, lock: int) -> None:
    scenario = lockinfeas_scenario()
    for solver in ("sa", "mip"):
        result = solve_rolling_plan(
            scenario,
            master_days=6,
            subproblem_days=sub,
            lock_days=lock,
            solver=solver,
            sa_iters=300,
            mip_solver="highs",
            mip_time_limit=10,
        )
        kpis = compute_rolling_kpis(scenario, result).rolling_kpis
        assert int(kpis["sequencing_violation_count"]) == 0
        # Since #115 a user lock never makes a MILP window infeasible: every window solves and
        # the lock is applied (the locked machine may idle).
        assert result.no_solution_windows == []
        assert ("S1", "B2", 3) in {
            (lk.machine_id, lk.block_id, lk.day) for lk in result.locked_assignments
        }
        if solver == "mip" and sub == 2:
            # Nothing is staged on B2 in the 2-day window starting on day 3, so the MILP idles
            # the locked skidder; an idle slot is not a sequencing violation (#125).
            (locked,) = [
                lk
                for lk in result.locked_assignments
                if (lk.machine_id, lk.block_id, lk.day) == ("S1", "B2", 3)
            ]
            assert locked.production == pytest.approx(0.0, abs=1e-6)


# (4) Partial shift calendars ---------------------------------------------------------------------
def shiftcal_scenario() -> Scenario:
    """Audit repro: the shift calendar covers days 1-4 only (2 fellers x 2 shifts x 100 m³)."""

    machines = [Machine(id="F1", role="feller_buncher"), Machine(id="F2", role="feller_buncher")]
    return Scenario(
        name="shiftcal",
        num_days=8,
        blocks=[Block(id="B1", landing_id="L1", work_required=5000.0)],
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=4)],
        calendar=[
            CalendarEntry(machine_id=m.id, day=d, available=1)
            for m in machines
            for d in range(1, 9)
        ],
        shift_calendar=[
            ShiftCalendarEntry(machine_id=m.id, day=d, shift_id=s, available=1)
            for m in machines
            for d in range(1, 5)
            for s in ("S1", "S2")
        ],
        production_rates=[
            ProductionRate(machine_id=m.id, block_id="B1", rate=100.0) for m in machines
        ],
    )


def test_window_outside_partial_shift_calendar_has_no_shifts() -> None:
    scenario = shiftcal_scenario()
    late = slice_scenario_for_window(
        scenario, RollingIterationPlan(iteration_index=1, start_day=5, horizon_days=4, lock_days=4)
    )
    assert Problem.from_scenario(late).shifts == []
    assert late.shift_calendar and all(entry.available == 0 for entry in late.shift_calendar)
    straddling = slice_scenario_for_window(
        scenario, RollingIterationPlan(iteration_index=1, start_day=3, horizon_days=4, lock_days=2)
    )
    assert sorted({(s.day, s.shift_id) for s in Problem.from_scenario(straddling).shifts}) == [
        (1, "S1"),
        (1, "S2"),
        (2, "S1"),
        (2, "S2"),
    ]


@pytest.mark.parametrize("kind", ["sa", "mip"])
def test_partial_shift_calendar_rolling_matches_direct_capacity(kind: str) -> None:
    scenario = shiftcal_scenario()
    direct = solve_sa(Problem.from_scenario(scenario), iters=300, seed=1)
    direct_delivered = float(
        compute_kpis(Problem.from_scenario(scenario), direct["assignments"])["total_production"]
    )
    assert direct_delivered == pytest.approx(1600.0)

    with pytest.warns(UserWarning, match="window skipped"):
        result = solve_rolling_plan(
            scenario,
            master_days=8,
            subproblem_days=4,
            lock_days=4,
            solver=kind,
            sa_iters=300,
            mip_solver="highs",
            mip_time_limit=10,
        )
    assert not [lock for lock in result.locked_assignments if lock.day > 4]
    assert [s.status for s in result.iteration_summaries] == ["solved", "skipped"]
    assert result.iteration_summaries[1].runtime_s is None
    delivered = float(compute_rolling_kpis(scenario, result).rolling_kpis["total_production"])
    assert delivered == pytest.approx(1600.0)


# Slot order (night shift defined before the day shift) -------------------------------------------
def test_last_block_follows_scenario_shift_order_not_labels() -> None:
    scenario = chain_scenario(
        roles=("feller_buncher",), num_days=4, timeline_shifts=("night", "day")
    )
    locks = [
        ScheduleLock(machine_id="F1", block_id="B1", day=1, shift_id="night"),
        ScheduleLock(machine_id="F1", block_id="B2", day=1, shift_id="day"),
    ]
    state = carry_forward_state(scenario, locks, through_day=1)
    assert state.initial_state is not None
    # "day" sorts before "night" but is worked after it.
    assert state.initial_state.last_block_by_machine() == {"F1": "B2"}
    assert _hand_replay(scenario, locks, through_day=1).last_block == {"F1": "B2"}


@pytest.mark.parametrize("kind", ["sa", "mip"])
def test_rolling_with_night_day_shifts_matches_slot_order(kind: str) -> None:
    scenario = chain_scenario(num_days=6, timeline_shifts=("night", "day"))
    hook = get_solver_hook("sa", sa_iters=150, sa_seed=7) if kind == "sa" else _mip_hook()
    recorder = RecordingSolver(hook)
    result = run_rolling_horizon(_config(scenario, 6, 3, 1), recorder)
    assert result.locked_assignments
    assert {lock.shift_id for lock in result.locked_assignments} <= {"night", "day"}
    for plan, window in recorder.calls[1:]:
        _assert_window_matches_hand_replay(scenario, window, result.locked_assignments, plan)


# Independent replay ------------------------------------------------------------------------------
class HandState:
    def __init__(self) -> None:
        self.remaining: dict[str, float] = {}
        self.role_remaining: dict[tuple[str, str], float] = {}
        self.inventory: dict[tuple[str, str], float] = {}
        self.counts: dict[tuple[str, str], int] = {}
        self.last_block: dict[str, str] = {}


def _hand_slot_order(scenario: Scenario) -> dict[tuple[int, str], int]:
    """Days ascending; within a day shift-calendar labels sorted, else timeline order, else S1."""

    if scenario.shift_calendar:
        per_day: dict[int, set[str]] = defaultdict(set)
        for entry in scenario.shift_calendar:
            if entry.available:
                per_day[entry.day].add(entry.shift_id)
        labels_for = {day: sorted(labels) for day, labels in per_day.items()}
    else:
        names = [s.name for s in scenario.timeline.shifts] if scenario.timeline else ["S1"]
        labels_for = {day: list(names) for day in range(1, scenario.num_days + 1)}
    order: dict[tuple[int, str], int] = {}
    for day in sorted(labels_for):
        for label in labels_for[day]:
            order[(day, label)] = len(order)
    return order


def _hand_replay(
    scenario: Scenario, locks: Sequence[ScheduleLock], *, through_day: int
) -> HandState:
    """Linear-chain state machine written from the documented playback rules (no FHOPS replay).

    Every block uses the single linear ``chain`` system without head starts or loaders. Slots run
    in chronological order; within a slot upstream roles go first (then machine id). An assignment
    proposes its lock's ``production`` (else ``min(rate, remaining terminal volume)``), capped by
    the remaining terminal volume, the role's remaining output, and the upstream output staged in
    *earlier* slots; output becomes available downstream from the next slot.
    """

    assert scenario.harvest_systems is not None
    system = scenario.harvest_systems["chain"]
    chain = [job.machine_role for job in system.jobs]
    terminal = chain[-1]
    role_of = {m.id: m.role for m in scenario.machines}
    rate = {(r.machine_id, r.block_id): r.rate for r in scenario.production_rates}
    slot_order = _hand_slot_order(scenario)

    state = HandState()
    for block in scenario.blocks:
        state.remaining[block.id] = block.work_required
        for role in chain:
            state.role_remaining[(block.id, role)] = block.work_required
            state.inventory[(block.id, role)] = 0.0
            state.counts[(block.id, role)] = 0
    if scenario.initial_state is not None:
        for entry in scenario.initial_state.blocks:
            for role, value in entry.role_remaining.items():
                state.role_remaining[(entry.block_id, role)] = value
            for role, value in entry.staged_inventory.items():
                state.inventory[(entry.block_id, role)] = value
            for role, count in entry.role_shift_counts.items():
                state.counts[(entry.block_id, role)] = count
        state.last_block.update(scenario.initial_state.last_block_by_machine())

    def key(lock: ScheduleLock) -> tuple[int, int, str]:
        return (
            slot_order[(lock.day, lock.shift_id or "S1")],
            chain.index(role_of[lock.machine_id]),
            lock.machine_id,
        )

    staged_this_slot: dict[tuple[str, str], float] = defaultdict(float)
    current_slot: int | None = None
    for lock in sorted((lk for lk in locks if lk.day <= through_day), key=key):
        slot = slot_order[(lock.day, lock.shift_id or "S1")]
        if slot != current_slot:
            for item, volume in staged_this_slot.items():
                state.inventory[item] += volume
            staged_this_slot.clear()
            current_slot = slot
        block_id, role = lock.block_id, role_of[lock.machine_id]
        index = chain.index(role)
        proposed = (
            lock.production
            if lock.production is not None
            else min(rate.get((lock.machine_id, block_id), 0.0), state.remaining[block_id])
        )
        produced = min(proposed, state.remaining[block_id], state.role_remaining[(block_id, role)])
        if index > 0:
            upstream = (block_id, chain[index - 1])
            produced = min(produced, state.inventory[upstream])
            state.inventory[upstream] -= produced
        produced = max(produced, 0.0)
        staged_this_slot[(block_id, role)] += produced
        state.role_remaining[(block_id, role)] -= produced
        if role == terminal:
            state.remaining[block_id] -= produced
        state.counts[(block_id, role)] += 1
        state.last_block[lock.machine_id] = block_id
    for item, volume in staged_this_slot.items():
        state.inventory[item] += volume
    return state


def _assert_state_matches_hand(scenario: Scenario, carried, hand: HandState) -> None:  # type: ignore[no-untyped-def]
    assert scenario.harvest_systems is not None
    chain = [job.machine_role for job in scenario.harvest_systems["chain"].jobs]
    for block_id, value in hand.remaining.items():
        assert carried.remaining_work[block_id] == pytest.approx(value, abs=1e-6), block_id
    initial = carried.initial_state
    for block in scenario.blocks:
        entry = initial.block_state(block.id) if initial is not None else None
        for role in chain:
            role_remaining = (entry.role_remaining if entry else {}).get(
                role, carried.remaining_work[block.id]
            )
            assert role_remaining == pytest.approx(
                hand.role_remaining[(block.id, role)], abs=1e-6
            ), (block.id, role)
            if role != chain[-1]:
                staged = (entry.staged_inventory if entry else {}).get(role, 0.0)
                assert staged == pytest.approx(hand.inventory[(block.id, role)], abs=1e-6), (
                    block.id,
                    role,
                )
            counts = (entry.role_shift_counts if entry else {}).get(role, 0)
            assert counts == hand.counts[(block.id, role)], (block.id, role)
    last_block = initial.last_block_by_machine() if initial is not None else {}
    assert dict(last_block) == hand.last_block


def _assert_window_matches_hand_replay(
    scenario: Scenario,
    window: Scenario,
    locks: Sequence[ScheduleLock],
    plan: RollingIterationPlan,
) -> None:
    hand = _hand_replay(scenario, locks, through_day=plan.start_day - 1)
    assert {b.id: b.work_required for b in window.blocks} == pytest.approx(
        {b: (0.0 if v <= 1e-6 else v) for b, v in hand.remaining.items()}, abs=1e-6
    )
    carried = carry_forward_state(scenario, locks, through_day=plan.start_day - 1)
    assert window.initial_state == carried.initial_state
    _assert_state_matches_hand(scenario, carried, hand)


HAND_CASES = {
    "two_roles_single_shift": dict(num_days=6),
    "three_roles_single_shift": dict(
        roles=("feller_buncher", "grapple_skidder", "processor"), num_days=6
    ),
    "two_roles_two_shifts": dict(num_days=4, shift_labels=("S1", "S2")),
    "three_roles_two_shifts_user_state": dict(
        roles=("feller_buncher", "grapple_skidder", "processor"),
        num_days=4,
        shift_labels=("S1", "S2"),
        initial_state=ScenarioInitialState(
            blocks=[
                BlockInitialState(
                    block_id="B1",
                    role_remaining={"feller_buncher": 250.0, "grapple_skidder": 300.0},
                    staged_inventory={"feller_buncher": 50.0, "grapple_skidder": 100.0},
                    role_shift_counts={"feller_buncher": 3},
                )
            ],
            machines=[MachineInitialState(machine_id="S1", last_block_id="B2")],
        ),
    ),
}


@pytest.mark.parametrize("kind", ["sa", "mip"])
@pytest.mark.parametrize("case", sorted(HAND_CASES))
def test_carried_state_matches_independent_replay(kind: str, case: str) -> None:
    scenario = chain_scenario(**HAND_CASES[case])  # type: ignore[arg-type]
    hook = get_solver_hook("sa", sa_iters=200, sa_seed=11) if kind == "sa" else _mip_hook()
    recorder = RecordingSolver(hook)
    master = scenario.num_days
    result = run_rolling_horizon(_config(scenario, master, 3, 1), recorder)
    locks = result.locked_assignments
    assert locks
    staged_seen = False
    for plan, window in recorder.calls[1:]:
        _assert_window_matches_hand_replay(scenario, window, locks, plan)
        hand_start = _hand_replay(scenario, locks, through_day=plan.start_day - 1)
        staged_seen |= any(volume > 1e-6 for volume in hand_start.inventory.values())
    assert staged_seen, "the comparison should cover carried staged inventory"
    # Final state and the stitched-plan KPIs agree with the hand replay as well.
    hand = _hand_replay(scenario, locks, through_day=master)
    final = carry_forward_state(scenario, locks, through_day=master)
    _assert_state_matches_hand(scenario, final, hand)
    total = sum(block.work_required for block in scenario.blocks)
    kpis = compute_rolling_kpis(scenario, result).rolling_kpis
    assert float(kpis["total_production"]) == pytest.approx(
        total - sum(hand.remaining.values()), abs=1e-6
    )
    # Per-iteration telemetry is consistent with the hand replay.
    for summary in result.iteration_summaries:
        start = _hand_replay(scenario, locks, through_day=summary.start_day - 1)
        end = _hand_replay(scenario, locks, through_day=summary.start_day + summary.lock_days - 1)
        assert summary.remaining_work_start == pytest.approx(
            sum(start.remaining.values()), abs=1e-6
        )
        assert summary.locked_delivered == pytest.approx(
            sum(start.remaining.values()) - sum(end.remaining.values()), abs=1e-6
        )
