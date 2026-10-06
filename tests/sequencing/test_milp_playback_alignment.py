"""Operational-MILP plans replay without sequencing violations (#109).

Each test covers one root cause of the MILP/playback mismatch found on the Jaffray ka_6
scenario (three shifts per day) and on randomised pipelines:

* staged output released per *day* instead of per *shift slot* (formulation E7);
* solver feasibility noise (~1e-7 m³) flagged as inventory shortfalls;
* loader truckload threshold checked against what earlier loaders left in the slot instead of the
  volume staged at the start of the slot (E8);
* head-start buffers counted in shifts (tracker) instead of staged volume (MILP E8);
* MILP upstream roles producing more than the block holds ("phantom" volume used to meet buffer
  thresholds), now capped (E10b) with a buffer waiver once upstream roles are exhausted;
* blocks without ``harvest_system_id`` sequenced by the MILP but not by the tracker;
* shift slots replayed in label order instead of the problem's shift order;
* rolling-horizon locks replayed at the full production rate instead of the MILP plan.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

import pandas as pd
import pytest

from fhops.evaluation.playback import run_playback
from fhops.evaluation.sequencing import build_sequencing_tracker
from fhops.model.milp.data import (
    build_operational_bundle,
    bundle_from_dict,
    bundle_to_dict,
    headstart_buffer_volumes,
)
from fhops.model.milp.driver import solve_operational_milp
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.operational_problem import build_operational_problem
from fhops.planning import compute_rolling_kpis, solve_rolling_plan
from fhops.scenario.contract import (
    Block,
    BlockInitialState,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
    ScenarioInitialState,
)
from fhops.scheduling.systems import HarvestSystem, SystemJob
from fhops.scheduling.timeline.models import ShiftDefinition, TimelineConfig

ROLES = ("feller_buncher", "grapple_skidder", "processor", "loader")
JOBS = ("felling", "primary_transport", "processing", "loading")


def pipeline_scenario(
    *,
    roles: Sequence[str] = ROLES[:2],
    fleet: dict[str, list[tuple[str, float]]] | None = None,
    blocks: dict[str, float] | None = None,
    num_days: int = 1,
    shifts: Sequence[str] | None = ("S1", "S2", "S3"),
    headstart: dict[str, float] | None = None,
    loader_batch: float | None = None,
    sequenced: bool = True,
    initial_state: ScenarioInitialState | None = None,
) -> Scenario:
    """Linear pipeline ``roles[0] → roles[1] → …`` on one landing.

    ``fleet`` maps role -> ``[(machine_id, rate m³/shift)]`` (default: one machine per role at
    50 m³/shift); ``blocks`` maps block id -> ``work_required`` (default ``{"B1": 100}``).
    ``shifts`` are timeline shift names (``None`` = day-indexed ``S1`` grid).
    """

    jobs = [
        SystemJob(JOBS[ROLES.index(role)], role, [JOBS[ROLES.index(roles[i - 1])]] if i else [])
        for i, role in enumerate(roles)
    ]
    system = HarvestSystem(
        system_id="pipe",
        jobs=jobs,
        role_headstart_shifts=headstart,
        loader_batch_volume_m3=loader_batch,
    )
    fleet = fleet or {role: [(f"{role[:2].upper()}1", 50.0)] for role in roles}
    blocks = blocks or {"B1": 100.0}
    machines = [Machine(id=mid, role=role) for role, items in fleet.items() for mid, _ in items]
    timeline = (
        TimelineConfig(
            shifts=[ShiftDefinition(name=s, hours=8.0, shifts_per_day=1) for s in shifts]
        )
        if shifts
        else None
    )
    return Scenario(
        name="pipeline",
        num_days=num_days,
        blocks=[
            Block(
                id=bid,
                landing_id="L1",
                work_required=work,
                harvest_system_id="pipe" if sequenced else None,
            )
            for bid, work in blocks.items()
        ],
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=20)],
        calendar=[
            CalendarEntry(machine_id=m.id, day=d, available=1)
            for m in machines
            for d in range(1, num_days + 1)
        ],
        production_rates=[
            ProductionRate(machine_id=mid, block_id=bid, rate=rate)
            for items in fleet.values()
            for mid, rate in items
            for bid in blocks
        ],
        harvest_systems={"pipe": system},
        timeline=timeline,
        initial_state=initial_state,
    )


def _terminal_production(bundle, assignments: pd.DataFrame) -> float:
    terminal: dict[str, set[str]] = {}
    for system_id, cfg in bundle.systems.items():
        upstream = {u for role_cfg in cfg.roles for u in role_cfg.upstream_roles}
        terminal[system_id] = {role_cfg.role for role_cfg in cfg.roles} - upstream
    total = 0.0
    for row in assignments.itertuples():
        role = bundle.machine_roles.get(row.machine_id)
        if row.block_id in bundle.unsequenced_blocks or role in terminal.get(
            bundle.block_system[row.block_id], set()
        ):
            total += float(row.production)
    return total


def _solve_and_replay(scenario: Scenario) -> tuple[pd.DataFrame, float, object]:
    pb = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(pb)
    result = solve_operational_milp(bundle, solver="highs", time_limit=30)
    assert result["termination_condition"].lower() == "optimal"
    assignments = result["assignments"]
    playback = run_playback(pb, assignments)
    return assignments, _terminal_production(bundle, assignments), playback


def _violations(playback) -> list[tuple[int, str, str, str]]:
    return [
        (r.day, r.shift_id, r.machine_id, r.metadata["sequencing_violation"])
        for r in playback.records
        if r.metadata.get("sequencing_violation")
    ]


def _assert_clean(scenario: Scenario) -> tuple[pd.DataFrame, float]:
    assignments, terminal, playback = _solve_and_replay(scenario)
    assert _violations(playback) == []
    assert playback.delivered_total == pytest.approx(terminal, abs=1e-5)
    return assignments, terminal


# --- staged output is released per shift slot --------------------------------------------


def test_tracker_releases_staged_output_at_next_shift() -> None:
    pb = Problem.from_scenario(pipeline_scenario(shifts=("S1", "S2")))
    tracker = build_sequencing_tracker(pb)
    assert tracker.process(1, "FE1", "B1", 50.0, "S1").violation_reason is None
    same_slot = tracker.process(1, "GR1", "B1", 50.0, "S1")
    assert same_slot.violation_reason == "missing_prereq"
    assert same_slot.production_units == pytest.approx(0.0)
    next_shift = tracker.process(1, "GR1", "B1", 50.0, "S2")
    assert next_shift.violation_reason is None
    assert next_shift.production_units == pytest.approx(50.0)


def test_tracker_without_shift_id_keeps_day_release() -> None:
    tracker = build_sequencing_tracker(Problem.from_scenario(pipeline_scenario(shifts=None)))
    tracker.process(1, "FE1", "B1", 50.0)
    assert tracker.process(1, "GR1", "B1", 50.0).violation_reason == "missing_prereq"
    assert tracker.process(2, "GR1", "B1", 50.0).violation_reason is None


def test_multi_shift_milp_plan_replays_clean() -> None:
    # One day, three shifts: delivering anything requires same-day shift-to-shift hand-offs.
    scenario = pipeline_scenario(roles=ROLES[:3], blocks={"B1": 60.0})
    assignments, terminal = _assert_clean(scenario)
    assert terminal == pytest.approx(50.0)
    assert set(assignments["shift_id"]) == {"S1", "S2", "S3"}


# --- solver noise --------------------------------------------------------------------------


def test_tracker_tolerates_solver_feasibility_noise() -> None:
    state = ScenarioInitialState(
        blocks=[BlockInitialState(block_id="B1", staged_inventory={"feller_buncher": 12.8629995})]
    )
    tracker = build_sequencing_tracker(
        Problem.from_scenario(pipeline_scenario(initial_state=state))
    )
    result = tracker.process(1, "GR1", "B1", 12.863, "S1")
    assert result.violation_reason is None
    assert result.production_units == pytest.approx(12.8629995)


# --- loader truckload threshold uses the slot-start inventory ------------------------------


def _loader_tracker(staged: float):
    scenario = pipeline_scenario(
        roles=("processor", "loader"),
        fleet={"processor": [("PR1", 50.0)], "loader": [("LO1", 40.0), ("LO2", 40.0)]},
        loader_batch=30.0,
        initial_state=ScenarioInitialState(
            blocks=[BlockInitialState(block_id="B1", staged_inventory={"processor": staged})]
        ),
    )
    return build_sequencing_tracker(Problem.from_scenario(scenario))


def test_loader_threshold_checks_slot_start_volume() -> None:
    tracker = _loader_tracker(40.0)
    assert tracker.process(1, "LO1", "B1", 30.0, "S1").violation_reason is None
    # Only 10 m³ remain for LO2, below one truckload, but 40 m³ were staged at the slot start
    # (MILP E8 compares I(prev(s)) with the batch for the whole role).
    second = tracker.process(1, "LO2", "B1", 10.0, "S1")
    assert second.violation_reason is None
    assert second.production_units == pytest.approx(10.0)


def test_loader_threshold_still_flags_short_staging() -> None:
    tracker = _loader_tracker(20.0)
    assert tracker.process(1, "LO1", "B1", 20.0, "S1").violation_reason == "missing_prereq"


def test_milp_two_loaders_replay_clean() -> None:
    scenario = pipeline_scenario(
        roles=("processor", "loader"),
        fleet={"processor": [("PR1", 80.0)], "loader": [("LO1", 50.0), ("LO2", 15.0)]},
        blocks={"B1": 160.0},
        loader_batch=30.0,
        num_days=2,
    )
    _assert_clean(scenario)


# --- head-start buffers are staged volume ---------------------------------------------------


def _headstart_scenario(**kwargs) -> Scenario:
    return pipeline_scenario(
        fleet={"feller_buncher": [("FE1", 50.0)], "grapple_skidder": [("GR1", 40.0)]},
        headstart={"grapple_skidder": 2.0},
        **kwargs,
    )


def test_headstart_volume_matches_milp_buffer() -> None:
    pb = Problem.from_scenario(_headstart_scenario())
    ctx = build_operational_problem(pb)
    assert ctx.role_headstart_volume == {("B1", "grapple_skidder"): pytest.approx(100.0)}
    assert headstart_buffer_volumes(ctx.bundle) == ctx.role_headstart_volume
    model = build_operational_model(ctx.bundle)
    con = model.head_start["grapple_skidder", "B1", "feller_buncher", 1, "S2"]
    coefficients = {str(v): c for v, c in zip(*_linear_terms(con.body), strict=True)}
    assert abs(coefficients["role_active[grapple_skidder,B1,1,S2]"]) == pytest.approx(100.0)


def _linear_terms(expr):
    from pyomo.repn import generate_standard_repn

    repn = generate_standard_repn(expr)
    return repn.linear_vars, repn.linear_coefs


@pytest.mark.parametrize(
    ("staged", "role_remaining", "counts", "violation"),
    [
        (60.0, {}, {}, "missing_prereq"),
        (60.0, {}, {"feller_buncher": 5}, "missing_prereq"),  # shift counts no longer matter
        (100.0, {}, {}, None),
        (60.0, {"feller_buncher": 0.0}, {}, None),  # upstream exhausted: buffer waived
    ],
)
def test_tracker_headstart_uses_staged_volume(staged, role_remaining, counts, violation) -> None:
    state = ScenarioInitialState(
        blocks=[
            BlockInitialState(
                block_id="B1",
                staged_inventory={"feller_buncher": staged},
                role_remaining=role_remaining,
                role_shift_counts=counts,
            )
        ]
    )
    scenario = _headstart_scenario(blocks={"B1": 200.0}, initial_state=state)
    tracker = build_sequencing_tracker(Problem.from_scenario(scenario))
    assert tracker.process(1, "GR1", "B1", 40.0, "S1").violation_reason == violation


def test_milp_headstart_plan_replays_clean() -> None:
    _assert_clean(_headstart_scenario(blocks={"B1": 300.0}, num_days=2))


# --- role output caps and the drained-pipeline waiver --------------------------------------


def _role_totals(assignments: pd.DataFrame, scenario: Scenario) -> dict[str, float]:
    roles = {m.id: m.role for m in scenario.machines}
    return (
        assignments.assign(role=assignments["machine_id"].map(roles))
        .groupby("role")["production"]
        .sum()
        .to_dict()
    )


def test_milp_upstream_output_capped_by_block_volume() -> None:
    # Buffer (2 shifts x 50 m³ = 100 m³) exceeds the block (60 m³): v1.0.0 felled phantom volume
    # to meet it; now the feller stops at 60 m³ and the buffer is waived once felling is done.
    scenario = _headstart_scenario(blocks={"B1": 60.0}, num_days=2)
    assignments, terminal = _assert_clean(scenario)
    assert terminal == pytest.approx(60.0)
    totals = _role_totals(assignments, scenario)
    assert totals["feller_buncher"] <= 60.0 + 1e-6


def test_milp_loader_finishes_block_smaller_than_one_truckload() -> None:
    scenario = pipeline_scenario(
        roles=("feller_buncher", "loader"), blocks={"B1": 20.0}, loader_batch=30.0
    )
    assignments, terminal = _assert_clean(scenario)
    assert terminal == pytest.approx(20.0)
    assert _role_totals(assignments, scenario)["feller_buncher"] <= 20.0 + 1e-6


# --- blocks without harvest_system_id -----------------------------------------------------


def test_unsequenced_blocks_have_no_role_obligations() -> None:
    scenario = pipeline_scenario(sequenced=False, blocks={"B1": 80.0}, shifts=("S1",))
    pb = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(pb)
    assert bundle.unsequenced_blocks == ("B1",)
    assert bundle_from_dict(bundle_to_dict(bundle)).unsequenced_blocks == ("B1",)
    assignments, terminal = _assert_clean(scenario)
    # Both machines work the only slot; all output counts towards the block.
    assert terminal == pytest.approx(80.0)
    assert set(assignments["machine_id"]) == {"FE1", "GR1"}


def test_sequenced_bundle_dump_has_no_unsequenced_key() -> None:
    bundle = build_operational_bundle(Problem.from_scenario(pipeline_scenario()))
    assert "unsequenced_blocks" not in bundle_to_dict(bundle)


# --- shift order --------------------------------------------------------------------------


def test_shift_order_follows_timeline_definition() -> None:
    scenario = pipeline_scenario(shifts=("night", "day"), blocks={"B1": 40.0})
    pb = Problem.from_scenario(scenario)
    assert build_operational_problem(pb).shift_keys == ((1, "night"), (1, "day"))
    assert build_operational_bundle(pb).shifts == ((1, "night"), (1, "day"))
    assignments, terminal = _assert_clean(scenario)
    assert terminal == pytest.approx(40.0)
    feller = assignments[assignments["machine_id"] == "FE1"]
    assert list(feller["shift_id"]) == ["night"]


# --- randomised pipelines ----------------------------------------------------------------


def _random_pipeline(seed: int) -> Scenario:
    rng = random.Random(seed)
    roles = ROLES[: rng.randint(2, 4)]
    fleet = {
        role: [
            (f"{role[:2].upper()}{k + 1}", round(rng.uniform(10, 80), 3))
            for k in range(rng.randint(1, 2))
        ]
        for role in roles
    }
    headstart = {role: float(rng.choice([1, 2])) for role in roles[1:] if rng.random() < 0.4}
    return pipeline_scenario(
        roles=roles,
        fleet=fleet,
        blocks={f"B{i + 1}": round(rng.uniform(20, 200), 3) for i in range(rng.randint(1, 2))},
        num_days=rng.randint(2, 3),
        shifts=[f"S{i + 1}" for i in range(rng.randint(1, 3))],
        headstart=headstart or None,
        loader_batch=float(rng.choice([10, 30])),
    )


@pytest.mark.parametrize("seed", range(8))
def test_random_pipeline_milp_plans_replay_clean(seed: int) -> None:
    _assert_clean(_random_pipeline(seed))


# --- rolling horizon ----------------------------------------------------------------------


def test_rolling_milp_locks_replay_planned_production() -> None:
    scenario = pipeline_scenario(roles=ROLES[:3], blocks={"B1": 400.0}, num_days=4)
    result = solve_rolling_plan(
        scenario, master_days=4, subproblem_days=2, lock_days=1, solver="mip", mip_time_limit=30
    )
    assert all(lock.production is not None for lock in result.locked_assignments)
    comparison = compute_rolling_kpis(scenario, result)
    kpis = comparison.rolling_kpis.to_dict()
    assert kpis["sequencing_violation_count"] == 0
    assert "production" in comparison.rolling_assignments.columns
    roles = {m.id: m.role for m in scenario.machines}
    planned_terminal = sum(
        lock.production or 0.0
        for lock in result.locked_assignments
        if roles[lock.machine_id] == "processor"
    )
    assert kpis["total_production"] == pytest.approx(planned_terminal, abs=1e-5)
    assert planned_terminal > 0


# --- warm starts seed the new waiver variables --------------------------------------------


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(_headstart_scenario(blocks={"B1": 60.0}, num_days=2), id="headstart"),
        pytest.param(
            pipeline_scenario(
                roles=("feller_buncher", "loader"), blocks={"B1": 20.0}, loader_batch=30.0
            ),
            id="loader-small-block",
        ),
    ],
)
def test_warm_start_from_milp_plan_is_accepted(scenario: Scenario) -> None:
    ctx = build_operational_problem(Problem.from_scenario(scenario))
    cold = solve_operational_milp(ctx.bundle, solver="highs", time_limit=30)
    warm = solve_operational_milp(
        ctx.bundle,
        solver="highs",
        time_limit=30,
        incumbent_assignments=cold["assignments"],
        context=ctx,
    )
    assert warm["warm_start"]["accepted"] is True
    assert warm["objective"] == pytest.approx(cold["objective"], abs=1e-6)
