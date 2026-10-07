"""Rolling-horizon state carry-forward, locks, blackouts, and hook telemetry (#92)."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import pytest

from fhops.evaluation import compute_kpis
from fhops.evaluation.playback import assignments_to_records
from fhops.evaluation.sequencing import SequencingTracker, build_sequencing_tracker
from fhops.model.milp.driver import solve_operational_milp
from fhops.optimization.heuristics.sa import solve_sa
from fhops.optimization.operational_problem import build_operational_problem
from fhops.planning import (
    RollingHorizonConfig,
    RollingIterationPlan,
    SolverOutput,
    carry_forward_state,
    compute_rolling_kpis,
    get_solver_hook,
    run_rolling_horizon,
    slice_scenario_for_window,
    solve_rolling_plan,
)
from fhops.planning.rolling import MILPSolver, resolve_operational_mip_solver
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
from fhops.scenario.contract.models import ObjectiveWeights, ShiftCalendarEntry
from fhops.scenario.io import load_scenario
from fhops.scheduling.mobilisation import BlockDistance, MachineMobilisation, MobilisationConfig
from fhops.scheduling.systems import HarvestSystem, SystemJob
from fhops.scheduling.timeline.models import BlackoutWindow, ShiftDefinition, TimelineConfig

TINY7 = "examples/tiny7/scenario.yaml"

CHAIN = HarvestSystem(
    system_id="chain",
    jobs=[
        SystemJob("felling", "feller_buncher", []),
        SystemJob("primary_transport", "grapple_skidder", ["felling"]),
    ],
)
SOLO = HarvestSystem(system_id="solo", jobs=[SystemJob("felling", "feller_buncher", [])])


def _mobilisation(machine_ids: Sequence[str], block_ids: Sequence[str]) -> MobilisationConfig:
    return MobilisationConfig(
        machine_params=[
            MachineMobilisation(
                machine_id=machine_id,
                walk_cost_per_meter=0.05,
                move_cost_flat=200.0,
                walk_threshold_m=1000.0,
                setup_cost=5.0,
            )
            for machine_id in machine_ids
        ],
        distances=[
            BlockDistance(from_block=a, to_block=b, distance_m=300.0)
            for a in block_ids
            for b in block_ids
            if a != b
        ],
    )


def _scenario(
    *,
    system: HarvestSystem,
    machines: list[Machine],
    blocks: list[Block],
    rates: dict[tuple[str, str], float],
    num_days: int,
    shifts: Sequence[str] | None = None,
    **extra: object,
) -> Scenario:
    calendar = [
        CalendarEntry(machine_id=m.id, day=day, available=1)
        for m in machines
        for day in range(1, num_days + 1)
    ]
    shift_calendar = None
    if shifts:
        shift_calendar = [
            ShiftCalendarEntry(machine_id=m.id, day=day, shift_id=shift_id, available=1)
            for m in machines
            for day in range(1, num_days + 1)
            for shift_id in shifts
        ]
    return Scenario(
        name="rolling-carry",
        num_days=num_days,
        blocks=blocks,
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=6)],
        calendar=calendar,
        shift_calendar=shift_calendar,
        production_rates=[
            ProductionRate(machine_id=m, block_id=b, rate=r) for (m, b), r in rates.items()
        ],
        harvest_systems={system.system_id: system},
        mobilisation=_mobilisation([m.id for m in machines], [b.id for b in blocks]),
        objective_weights=ObjectiveWeights(production=1.0, mobilisation=0.1),
        **extra,  # type: ignore[arg-type]
    )


def solo_scenario(num_days: int = 6, **extra: object) -> Scenario:
    """Two fellers; B1 (150 m³, 100 m³/shift) finishes in the first 2-day window, B2 is large."""

    machines = [
        Machine(id="F1", role="feller_buncher", operating_cost=1.0),
        Machine(id="F2", role="feller_buncher", operating_cost=1.0),
    ]
    blocks = [
        Block(id="B1", landing_id="L1", work_required=150.0, harvest_system_id="solo"),
        Block(id="B2", landing_id="L1", work_required=5000.0, harvest_system_id="solo"),
    ]
    rates = {
        ("F1", "B1"): 100.0,
        ("F2", "B1"): 100.0,
        ("F1", "B2"): 40.0,
        ("F2", "B2"): 40.0,
    }
    return _scenario(
        system=SOLO, machines=machines, blocks=blocks, rates=rates, num_days=num_days, **extra
    )


def chain_scenario(num_days: int = 6, **extra: object) -> Scenario:
    """Feller → skidder chain on two blocks (staged inventory and head-start counts carry over)."""

    machines = [
        Machine(id="F1", role="feller_buncher", operating_cost=1.0),
        Machine(id="S1", role="grapple_skidder", operating_cost=1.0),
    ]
    blocks = [
        Block(id="B1", landing_id="L1", work_required=180.0, harvest_system_id="chain"),
        Block(id="B2", landing_id="L1", work_required=400.0, harvest_system_id="chain"),
    ]
    rates = {
        ("F1", "B1"): 70.0,
        ("F1", "B2"): 60.0,
        ("S1", "B1"): 50.0,
        ("S1", "B2"): 45.0,
    }
    return _scenario(
        system=CHAIN, machines=machines, blocks=blocks, rates=rates, num_days=num_days, **extra
    )


class RecordingSolver:
    """Wrap a solver hook and record the scenarios it receives."""

    def __init__(self, inner: object) -> None:
        self.inner = inner
        self.name = getattr(inner, "name", "recording")
        self.calls: list[tuple[RollingIterationPlan, Scenario, list[ScheduleLock]]] = []

    def __call__(
        self,
        scenario: Scenario,
        plan: RollingIterationPlan,
        *,
        locked_assignments: Sequence[ScheduleLock],
    ) -> SolverOutput:
        self.calls.append((plan, scenario.model_copy(deep=True), list(locked_assignments)))
        return self.inner(scenario, plan, locked_assignments=locked_assignments)  # type: ignore[operator]


def _hook(kind: str) -> object:
    if kind == "sa":
        return get_solver_hook("sa", sa_iters=150, sa_seed=7)
    return get_solver_hook("mip", mip_solver="highs", mip_time_limit=10)


def _run(
    scenario: Scenario, kind: str, *, master: int, sub: int, lock: int
) -> tuple[RecordingSolver, list[ScheduleLock]]:
    recorder = RecordingSolver(_hook(kind))
    config = RollingHorizonConfig(
        scenario=scenario, master_days=master, subproblem_days=sub, lock_days=lock
    )
    result = run_rolling_horizon(config, recorder)
    return recorder, result.locked_assignments


def _fresh_replay(base: Scenario, locks: Sequence[ScheduleLock], through_day: int):
    """Independent tracker replay of the stitched plan (playback rule) up to ``through_day``."""

    problem = Problem.from_scenario(base)
    rows = [
        {
            "machine_id": lock.machine_id,
            "block_id": lock.block_id,
            "day": lock.day,
            "shift_id": lock.shift_id,
            "assigned": 1,
            "production": lock.production,  # MILP locks carry their planned production (#109)
        }
        for lock in locks
        if lock.day <= through_day
    ]
    if not rows:
        return build_sequencing_tracker(problem)
    frame = pd.DataFrame(rows)
    if frame["production"].isna().all():
        frame = frame.drop(columns=["production"])
    records = assignments_to_records(problem, frame)
    list(records)
    tracker: SequencingTracker = records.sequencing_tracker  # type: ignore[attr-defined]
    return tracker


def _assert_window_matches_replay(
    base: Scenario, window: Scenario, locks: Sequence[ScheduleLock], start_day: int
) -> None:
    replay = _fresh_replay(base, locks, start_day - 1)
    window_ctx = build_operational_problem(Problem.from_scenario(window))
    # Remaining terminal volume becomes work_required (finished blocks stay at 0).
    for block in window.blocks:
        expected = replay.remaining_work[block.id]
        expected = 0.0 if expected <= 1e-6 else expected
        assert block.work_required == pytest.approx(expected, abs=1e-6), block.id
    # The window's tracker starts exactly where the replay ended.
    for key, value in replay.role_remaining.items():
        expected = 0.0 if value <= 1e-6 else value
        assert window_ctx.role_work_required[key] == pytest.approx(expected, abs=1e-6), key
    terminal = {
        (block_id, role)
        for block_id, system_id in window_ctx.bundle.block_system.items()
        for role in window_ctx.terminal_roles.get(system_id, ())
    }
    for key, value in replay.role_inventory.items():
        if key in terminal:  # terminal output is delivered volume, not staged input
            assert key not in window_ctx.initial_role_inventory
            continue
        carried = window_ctx.initial_role_inventory.get(key, 0.0)
        assert carried == pytest.approx(value if value > 1e-6 else 0.0, abs=1e-6), key
    for key, count in replay.role_counts_total.items():
        if key in replay.role_remaining:
            assert window_ctx.initial_role_counts.get(key, 0) == count, key
    # Last block = last locked assignment in chronological slot order: by day, then the base
    # scenario's own shift order within the day (timeline definition order, e.g. night before
    # day), not the label order.
    slot_order = _slot_order(base)
    last_block: dict[str, str] = {}
    if base.initial_state is not None:
        last_block.update(base.initial_state.last_block_by_machine())
    for lock in sorted(
        (lock for lock in locks if lock.day < start_day),
        key=lambda item: slot_order[(item.day, item.shift_id or "S1")],
    ):
        last_block[lock.machine_id] = lock.block_id
    assert dict(window_ctx.initial_machine_block) == last_block


def _slot_order(scenario: Scenario) -> dict[tuple[int, str], int]:
    """Chronological slot index: days ascending, shifts in the scenario's within-day order."""

    shifts = sorted(Problem.from_scenario(scenario).shifts, key=lambda shift: shift.day)
    order: dict[tuple[int, str], int] = {}
    for shift in shifts:
        order.setdefault((shift.day, shift.shift_id), len(order))
    return order


# (a) ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["sa", "mip"])
def test_block_finished_in_first_window_is_not_replanned(kind: str) -> None:
    scenario = solo_scenario()
    recorder, locks = _run(scenario, kind, master=6, sub=2, lock=2)

    first_window_b1 = [lock for lock in locks if lock.block_id == "B1" and lock.day <= 2]
    assert first_window_b1, "B1 should be worked in the first window"
    second_plan, second_window, _ = recorder.calls[1]
    assert second_plan.start_day == 3
    b1 = next(block for block in second_window.blocks if block.id == "B1")
    assert b1.work_required == 0.0
    assert not [lock for lock in locks if lock.block_id == "B1" and lock.day > 2]
    kpis = compute_rolling_kpis(scenario, locks).rolling_kpis
    assert float(kpis["total_production"]) <= sum(b.work_required for b in scenario.blocks) + 1e-6


# (b) ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["sa", "mip"])
def test_window_state_equals_fresh_replay_tiny7(kind: str) -> None:
    scenario = load_scenario(TINY7)
    recorder, locks = _run(scenario, kind, master=7, sub=4, lock=2)
    assert len(recorder.calls) == 4
    for plan, window, _ in recorder.calls[1:]:
        _assert_window_matches_replay(scenario, window, locks, plan.start_day)
    # The first window is untouched.
    assert recorder.calls[0][1].initial_state is None
    assert [b.work_required for b in recorder.calls[0][1].blocks] == [
        b.work_required for b in scenario.blocks
    ]


@pytest.mark.parametrize("kind", ["sa", "mip"])
def test_window_state_equals_fresh_replay_with_user_initial_state_and_shifts(kind: str) -> None:
    user_state = ScenarioInitialState(
        blocks=[
            BlockInitialState(
                block_id="B1",
                role_remaining={"feller_buncher": 40.0},
                staged_inventory={"feller_buncher": 60.0},
                role_shift_counts={"feller_buncher": 2},
            )
        ],
        machines=[MachineInitialState(machine_id="S1", last_block_id="B2")],
    )
    scenario = chain_scenario(num_days=6, shifts=("S1", "S2"), initial_state=user_state)
    recorder, locks = _run(scenario, kind, master=6, sub=3, lock=2)

    # Window 0 receives the user's initial state verbatim.
    assert recorder.calls[0][1].initial_state == user_state
    for plan, window, _ in recorder.calls[1:]:
        _assert_window_matches_replay(scenario, window, locks, plan.start_day)

    # The stitched-plan KPIs replay from the same base state as the carried windows.
    final = carry_forward_state(scenario, locks, through_day=6)
    kpis = compute_rolling_kpis(scenario, locks).rolling_kpis
    assert float(kpis["remaining_work_total"]) == pytest.approx(
        sum(final.remaining_work.values()), abs=1e-6
    )


@pytest.mark.parametrize("kind", ["sa", "mip"])
def test_window_state_equals_fresh_replay_with_night_before_day(kind: str) -> None:
    timeline = TimelineConfig(
        shifts=[
            ShiftDefinition(name="night", hours=8.0, shifts_per_day=1),
            ShiftDefinition(name="day", hours=8.0, shifts_per_day=1),
        ]
    )
    scenario = chain_scenario(num_days=6, timeline=timeline)
    assert _slot_order(scenario)[(1, "night")] < _slot_order(scenario)[(1, "day")]
    recorder, locks = _run(scenario, kind, master=6, sub=3, lock=1)
    assert {lock.shift_id for lock in locks} <= {"night", "day"}
    for plan, window, _ in recorder.calls[1:]:
        _assert_window_matches_replay(scenario, window, locks, plan.start_day)


def test_carry_forward_state_omits_defaults() -> None:
    scenario = chain_scenario(num_days=4)
    locks = [
        ScheduleLock(machine_id="F1", block_id="B1", day=1, shift_id="S1"),
        ScheduleLock(machine_id="S1", block_id="B2", day=1, shift_id="S1"),
    ]
    state = carry_forward_state(scenario, locks, through_day=1)
    assert state.remaining_work == {"B1": 180.0, "B2": 400.0}
    assert state.initial_state is not None
    b1 = state.initial_state.block_state("B1")
    assert b1 is not None
    assert b1.role_remaining == {"feller_buncher": 110.0}
    assert b1.staged_inventory == {"feller_buncher": 70.0}  # skidder output is terminal
    assert b1.role_shift_counts == {"feller_buncher": 1}
    # The skidder had nothing to move on B2: only its shift count and position are carried.
    b2 = state.initial_state.block_state("B2")
    assert b2 is not None
    assert b2.role_remaining == {} and b2.staged_inventory == {}
    assert b2.role_shift_counts == {"grapple_skidder": 1}
    assert state.initial_state.last_block_by_machine() == {"F1": "B1", "S1": "B2"}
    empty = carry_forward_state(scenario, [], through_day=0)
    assert empty.initial_state is None
    assert empty.remaining_work == {"B1": 180.0, "B2": 400.0}


# (c) ---------------------------------------------------------------------------------------------
def test_single_window_rolling_matches_direct_sa() -> None:
    scenario = load_scenario(TINY7)
    rolling = solve_rolling_plan(
        scenario, master_days=7, subproblem_days=7, lock_days=7, solver="sa", sa_iters=120
    )
    direct = solve_sa(Problem.from_scenario(scenario), iters=120, seed=42)
    direct_rows = direct["assignments"]
    direct_keys = {
        (r.machine_id, r.block_id, int(r.day), r.shift_id)
        for r in direct_rows.itertuples(index=False)
        if r.assigned
    }
    rolling_keys = {
        (lock.machine_id, lock.block_id, lock.day, lock.shift_id)
        for lock in rolling.locked_assignments
    }
    assert rolling_keys == direct_keys
    assert rolling.iteration_summaries[0].objective == pytest.approx(direct["objective"])


def test_single_window_rolling_matches_direct_milp() -> None:
    scenario = load_scenario(TINY7)
    rolling = solve_rolling_plan(
        scenario,
        master_days=7,
        subproblem_days=7,
        lock_days=7,
        solver="mip",
        mip_solver="highs",
        mip_time_limit=30,
    )
    ctx = build_operational_problem(Problem.from_scenario(scenario))
    direct = solve_operational_milp(ctx.bundle, solver="highs", time_limit=30, context=ctx)
    direct_rows = direct["assignments"]
    direct_keys = {
        (r.machine_id, r.block_id, int(r.day), r.shift_id)
        for r in direct_rows.itertuples(index=False)
        if r.assigned
    }
    rolling_keys = {
        (lock.machine_id, lock.block_id, lock.day, lock.shift_id)
        for lock in rolling.locked_assignments
    }
    assert rolling.iteration_summaries[0].objective == pytest.approx(direct["objective"], abs=1e-6)
    assert rolling_keys == direct_keys


# (d) ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["sa", "mip"])
def test_stitched_kpis_bounded_and_close_to_full_horizon(kind: str) -> None:
    scenario = load_scenario(TINY7)
    if kind == "mip":
        # tiny7's capacity-1 landings are a hard per-slot limit for the MILP since #125
        # (landing_surplus weight 0; SA auto-applies a soft 0.05 weight to tiny7), which stops
        # it from finishing the blocks. This test is about the rolling mechanics, so the
        # landings are made non-binding.
        scenario = scenario.model_copy(
            update={
                "landings": [
                    landing.model_copy(update={"daily_capacity": len(scenario.machines)})
                    for landing in scenario.landings
                ]
            }
        )
    total = sum(block.work_required for block in scenario.blocks)
    kwargs: dict[str, object] = (
        {"solver": "sa", "sa_iters": 200, "sa_seed": 42}
        if kind == "sa"
        else {"solver": "mip", "mip_solver": "highs", "mip_time_limit": 10}
    )
    full = solve_rolling_plan(scenario, master_days=7, subproblem_days=7, lock_days=7, **kwargs)  # type: ignore[arg-type]
    full_kpis = compute_rolling_kpis(scenario, full).rolling_kpis
    full_delivered = float(full_kpis["total_production"])
    # The full-horizon solves finish tiny7 (no gap to explain away).
    assert full_delivered == pytest.approx(total, rel=1e-6)
    roles = {machine.id: machine.role for machine in scenario.machines}

    # tiny7 is a four-role chain; sub_days=4 covers the chain, 6 covers chain + lock span.
    for sub, lock in ((4, 2), (6, 3)):
        rolling = solve_rolling_plan(
            scenario,
            master_days=7,
            subproblem_days=sub,
            lock_days=lock,
            **kwargs,  # type: ignore[arg-type]
        )
        rolling_kpis = compute_rolling_kpis(scenario, rolling).rolling_kpis
        delivered = float(rolling_kpis["total_production"])
        assert delivered <= total + 1e-6
        assert float(rolling_kpis["remaining_work_total"]) == pytest.approx(
            total - delivered, abs=1e-6
        )
        assert int(rolling_kpis["sequencing_violation_count"]) == 0
        assert rolling.empty_windows == [] and rolling.no_solution_windows == []
        # Per-window locked deliveries add up to the stitched-plan KPI.
        assert sum(s.locked_delivered or 0.0 for s in rolling.iteration_summaries) == (
            pytest.approx(delivered, abs=1e-6)
        )
        if kind == "sa":
            # Windows at least as long as the chain: SA rolling stays within 5% of full horizon.
            assert delivered >= 0.95 * full_delivered, (sub, lock)
        else:
            # Since #109 MILP locks carry their planned production: the stitched plan replays
            # cleanly and delivers exactly what the window MILPs planned on locked days.
            planned = sum(
                lock_.production or 0.0
                for lock_ in rolling.locked_assignments
                if roles[lock_.machine_id] == "loader"
            )
            assert delivered == pytest.approx(planned, abs=1e-6)
            if sub >= 6:
                # Windows longer than chain + lock span lose < 1% (no terminal value otherwise;
                # see the documented short-window limitation for sub_days=4).
                assert delivered >= 0.99 * full_delivered
            else:
                assert delivered > 0.5 * full_delivered
        # Window telemetry reports the carried remaining volume, never above the base total.
        starts = [summary.remaining_work_start for summary in rolling.iteration_summaries]
        assert starts[0] == pytest.approx(total)
        assert all(value is not None and value <= total + 1e-6 for value in starts)
        assert starts == sorted(starts, reverse=True)


# (e) ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["sa", "mip"])
def test_user_locks_survive_all_iterations(kind: str) -> None:
    user_locks = [
        ScheduleLock(machine_id="F2", block_id="B2", day=2),
        ScheduleLock(machine_id="F1", block_id="B1", day=5),
    ]
    scenario = solo_scenario(num_days=6, locked_assignments=user_locks)
    recorder, locks = _run(scenario, kind, master=6, sub=3, lock=2)

    stitched = {(lock.machine_id, lock.block_id, lock.day) for lock in locks}
    for lock in user_locks:
        assert (lock.machine_id, lock.block_id, lock.day) in stitched
    # Every window that covers a lock day receives the rebased lock (scenario and hook argument).
    for plan, window, passed in recorder.calls:
        expected = {
            (lock.machine_id, lock.block_id, lock.day - plan.start_day + 1, lock.shift_id)
            for lock in user_locks
            if plan.start_day <= lock.day <= plan.end_day
        }
        got = {
            (lock.machine_id, lock.block_id, lock.day, lock.shift_id)
            for lock in window.locked_assignments or []
        }
        assert got == expected
        assert {(lk.machine_id, lk.block_id, lk.day, lk.shift_id) for lk in passed} == expected
    # No machine works another block on a locked day.
    for lock in user_locks:
        same_day = {
            lk.block_id for lk in locks if lk.machine_id == lock.machine_id and lk.day == lock.day
        }
        assert same_day == {lock.block_id}


def test_hooks_merge_locks_instead_of_overwriting() -> None:
    scenario = solo_scenario(
        num_days=2, locked_assignments=[ScheduleLock(machine_id="F1", block_id="B2", day=1)]
    )
    plan = RollingIterationPlan(iteration_index=0, start_day=1, horizon_days=2, lock_days=2)
    extra = [ScheduleLock(machine_id="F2", block_id="B2", day=2)]
    for hook in (_hook("sa"), _hook("mip")):
        output = hook(scenario, plan, locked_assignments=extra)  # type: ignore[operator]
        keys = {(lk.machine_id, lk.block_id, lk.day) for lk in output.assignments}
        assert ("F1", "B2", 1) in keys
        assert ("F2", "B2", 2) in keys
        assert not {k for k in keys if k[0] == "F1" and k[2] == 1 and k[1] != "B2"}
    # The input scenario is not mutated by the hooks.
    assert scenario.locked_assignments == [ScheduleLock(machine_id="F1", block_id="B2", day=1)]


# (f) ---------------------------------------------------------------------------------------------
def test_blackouts_are_rebased_into_window_coordinates() -> None:
    timeline = TimelineConfig(
        shifts=[ShiftDefinition(name="S1", hours=10.0, shifts_per_day=1)],
        blackouts=[
            BlackoutWindow(start_day=2, end_day=2, reason="early"),
            BlackoutWindow(start_day=4, end_day=5, reason="storm"),
        ],
    )
    scenario = solo_scenario(num_days=8, timeline=timeline)

    def window(start: int, days: int) -> Scenario:
        plan = RollingIterationPlan(
            iteration_index=1, start_day=start, horizon_days=days, lock_days=2
        )
        return slice_scenario_for_window(scenario, plan)

    def spans(sc: Scenario) -> list[tuple[int, int, str | None]]:
        assert sc.timeline is not None
        return [(b.start_day, b.end_day, b.reason) for b in sc.timeline.blackouts]

    assert spans(window(1, 3)) == [(2, 2, "early")]
    assert spans(window(3, 3)) == [(2, 3, "storm")]
    assert spans(window(5, 3)) == [(1, 1, "storm")]
    assert spans(window(6, 3)) == []
    assert spans(window(1, 8)) == spans(scenario)

    # SA honours blackouts, so the stitched plan never works a base blackout day.
    recorder, locks = _run(scenario, "sa", master=8, sub=3, lock=2)
    assert locks
    assert not [lock for lock in locks if lock.day in {2, 4, 5}]
    assert spans(recorder.calls[1][1]) == [(2, 3, "storm")]  # window starting on day 3


# (g) ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["sa", "mip"])
def test_multi_shift_locks_keep_shift_id_without_duplicates(kind: str) -> None:
    user_locks = [ScheduleLock(machine_id="F1", block_id="B2", day=3, shift_id="S2")]
    scenario = solo_scenario(num_days=4, shifts=("S1", "S2"), locked_assignments=user_locks)
    _, locks = _run(scenario, kind, master=4, sub=2, lock=1)

    assert locks
    assert all(lock.shift_id in {"S1", "S2"} for lock in locks)
    keys = [(lock.machine_id, lock.day, lock.shift_id) for lock in locks]
    assert len(keys) == len(set(keys))
    assert ("F1", "B2", 3, "S2") in {
        (lk.machine_id, lk.block_id, lk.day, lk.shift_id) for lk in locks
    }
    frame = compute_rolling_kpis(scenario, locks).rolling_assignments
    expected_columns = ["machine_id", "block_id", "day", "shift_id", "assigned"]
    if kind == "mip":  # MILP locks carry their planned production (#109)
        expected_columns.append("production")
    assert list(frame.columns) == expected_columns
    assert not frame.duplicated(["machine_id", "day", "shift_id"]).any()
    # Two shifts a day: replaying the stitched plan never delivers more than both shifts can.
    kpis = compute_kpis(Problem.from_scenario(scenario), frame)
    assert float(kpis["total_production"]) <= 2 * 100.0 * 4 * 2 + 1e-6


# (h) ---------------------------------------------------------------------------------------------
def test_hook_runtime_recorded_and_auto_resolves_to_highs() -> None:
    assert resolve_operational_mip_solver("auto") == "highs"
    assert resolve_operational_mip_solver("AUTO") == "highs"
    assert resolve_operational_mip_solver("gurobi") == "gurobi"
    hook = MILPSolver(solver="auto", time_limit=10)
    assert hook.solver == "highs"
    assert hook.requested_solver == "auto"

    scenario = solo_scenario(num_days=4)
    mip = solve_rolling_plan(
        scenario, master_days=4, subproblem_days=2, lock_days=2, solver="mip", mip_time_limit=10
    )
    assert mip.metadata["mip_solver"] == "highs"
    sa = solve_rolling_plan(
        scenario, master_days=4, subproblem_days=2, lock_days=2, solver="sa", sa_iters=50
    )
    for result in (mip, sa):
        assert result.locked_assignments
        for summary in result.iteration_summaries:
            assert summary.runtime_s is not None and summary.runtime_s > 0.0


def test_lock_outside_block_window_is_reported() -> None:
    blocks_override = solo_scenario(num_days=6)
    blocks = [
        blocks_override.blocks[0].model_copy(update={"latest_finish": 2}),
        blocks_override.blocks[1],
    ]
    scenario = blocks_override.model_copy(
        update={
            "blocks": blocks,
            "locked_assignments": [ScheduleLock(machine_id="F1", block_id="B1", day=4)],
        }
    )
    plan = RollingIterationPlan(iteration_index=1, start_day=3, horizon_days=3, lock_days=2)
    from fhops.planning import RollingInfeasibleError

    with pytest.raises(RollingInfeasibleError, match="does not overlap"):
        slice_scenario_for_window(scenario, plan)
