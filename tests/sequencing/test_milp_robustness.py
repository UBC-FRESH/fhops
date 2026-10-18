"""Operational-MILP robustness and correctness fixes from the 1.0.1 audit (#115).

* locks never make the model infeasible (idle locked machines, contradictory locks);
* roles with several upstream roles (joins) consume from per-upstream staged inventories;
* the loader truckload threshold follows the remaining block volume slot by slot;
* carried-in ``role_remaining`` larger than ``work_required`` is capped at ``W_b``;
* MILP plans of random linear and join systems replay without sequencing violations.
"""

from __future__ import annotations

import dataclasses
import random
from dataclasses import replace

import pandas as pd
import pytest

from fhops.evaluation.playback import run_playback
from fhops.model.milp.data import build_operational_bundle
from fhops.model.milp.driver import solve_operational_milp
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.operational_problem import build_operational_problem
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

from .test_milp_playback_alignment import ROLES, _terminal_production, pipeline_scenario


def _solve(scenario: Scenario, **kwargs) -> tuple[Problem, dict]:
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    result = solve_operational_milp(
        ctx.bundle, solver="highs", time_limit=60, context=ctx, **kwargs
    )
    return pb, result


def _replay(pb: Problem, assignments: pd.DataFrame) -> tuple[list, float]:
    playback = run_playback(pb, assignments)
    violations = [
        (r.day, r.shift_id, r.machine_id, r.metadata["sequencing_violation"])
        for r in playback.records
        if r.metadata.get("sequencing_violation")
    ]
    return violations, playback.delivered_total


def _assert_clean_replay(pb: Problem, result: dict) -> float:
    assert result["outcome"] == "optimal"
    planned = _terminal_production(build_operational_bundle(pb), result["assignments"])
    violations, delivered = _replay(pb, result["assignments"])
    assert violations == []
    assert delivered == pytest.approx(planned, abs=1e-5)
    return planned


def _with_locks(scenario: Scenario, locks: list[dict]) -> Scenario:
    return Scenario.model_validate({**scenario.model_dump(), "locked_assignments": locks})


# --- locks -------------------------------------------------------------------------------------


_FOUR_ROLE = dict(roles=ROLES, num_days=2, blocks={"B1": 100.0, "B2": 100.0})


@pytest.mark.parametrize(
    "lock",
    [
        pytest.param(
            {"machine_id": "LO1", "block_id": "B1", "day": 1, "shift_id": "S1"}, id="loader-shift"
        ),
        pytest.param({"machine_id": "LO1", "block_id": "B1", "day": 1}, id="loader-day"),
    ],
)
def test_locked_loader_without_staged_volume_is_feasible(lock: dict) -> None:
    # Nothing is staged for the loader on day 1 (S1); before #115 the lock forced the loader's
    # activation binary to 1 and its truckload threshold made the model infeasible.
    pb, result = _solve(_with_locks(pipeline_scenario(**_FOUR_ROLE), [lock]))
    assert result["outcome"] == "optimal"
    assert result["warnings"] == []
    frame = result["assignments"]
    locked = frame[(frame.machine_id == "LO1") & (frame.day == 1) & (frame.shift_id == "S1")]
    assert list(locked.block_id) == ["B1"]
    assert list(locked.assigned) == [1]
    assert locked["production"].sum() == pytest.approx(0.0)
    baseline = solve_operational_milp(
        build_operational_bundle(Problem.from_scenario(pipeline_scenario(**_FOUR_ROLE))),
        solver="highs",
        time_limit=60,
    )
    assert result["objective"] == pytest.approx(baseline["objective"], abs=1e-6)


@pytest.mark.parametrize("shift_id", [None, "S1"])
def test_locked_headstart_role_before_its_buffer_is_feasible(shift_id: str | None) -> None:
    scenario = pipeline_scenario(
        fleet={"feller_buncher": [("FE1", 50.0)], "grapple_skidder": [("GR1", 40.0)]},
        headstart={"grapple_skidder": 2.0},
        blocks={"B1": 300.0},
        num_days=2,
    )
    lock = {"machine_id": "GR1", "block_id": "B1", "day": 1}
    if shift_id:
        lock["shift_id"] = shift_id
    pb, result = _solve(_with_locks(scenario, [lock]))
    assert result["outcome"] == "optimal"
    frame = result["assignments"]
    day_one = frame[(frame.machine_id == "GR1") & (frame.day == 1)]
    assert (day_one["assigned"] == 1).all()
    # The skidder cannot work before 100 m³ are staged: locked but idle in S1.
    first = day_one[day_one.shift_id == "S1"]
    assert first["production"].sum() == pytest.approx(0.0)


def test_locks_exempt_only_locked_machines_from_activation() -> None:
    scenario = _with_locks(
        pipeline_scenario(**_FOUR_ROLE),
        [{"machine_id": "LO1", "block_id": "B1", "day": 1, "shift_id": "S1"}],
    )
    model = build_operational_model(
        build_operational_problem(Problem.from_scenario(scenario)).bundle
    )
    # Only machine of the role is locked in that slot: no upper activation link there ...
    assert ("loader", "B1", 1, "S1") not in model.role_active_upper
    # ... but unlocked slots/blocks keep the published coupling sum_m x <= |M(r)| g.
    assert ("loader", "B1", 1, "S2") in model.role_active_upper
    assert ("loader", "B2", 1, "S1") in model.role_active_upper


def test_contradictory_locks_are_pinned_with_warnings() -> None:
    scenario = pipeline_scenario(**_FOUR_ROLE)
    data = scenario.model_dump()
    data["blocks"][1]["earliest_start"] = 2
    pb = Problem.from_scenario(Scenario.model_validate(data))
    bundle = build_operational_problem(pb).bundle
    # Built directly on the bundle so scenario validation cannot reject them first.
    bundle = replace(
        bundle,
        locked_assignments=(
            ("FE1", "B2", 1, "S1"),  # B2 window starts on day 2
            ("FE1", "B1", 1, "S1"),  # second lock on the same slot: ignored
            ("LO1", "B1", 2, "S9"),  # no such slot
            ("GHOST", "B1", 1, None),  # unknown machine
        ),
    )
    result = solve_operational_milp(bundle, solver="highs", time_limit=60)
    assert result["outcome"] == "optimal"
    messages = " | ".join(result["warnings"])
    assert "outside the block window" in messages
    assert "already locked" in messages
    assert "no matching slot" in messages
    assert "unknown machine" in messages
    frame = result["assignments"]
    assert frame[(frame.machine_id == "FE1") & (frame.day == 1) & (frame.shift_id == "S1")].empty

    solo = HarvestSystem(system_id="solo", jobs=[SystemJob("felling", "feller_buncher", [])])
    data = pipeline_scenario(**_FOUR_ROLE).model_dump()
    data["blocks"][1]["harvest_system_id"] = "solo"
    data["harvest_systems"] = {**pipeline_scenario(**_FOUR_ROLE).harvest_systems, "solo": solo}
    bundle = build_operational_problem(Problem.from_scenario(Scenario.model_validate(data))).bundle
    bundle = replace(bundle, locked_assignments=(("LO1", "B2", 2, "S3"),))
    result = solve_operational_milp(bundle, solver="highs", time_limit=60)
    assert result["outcome"] == "optimal"
    assert any("not part of the block's harvest system" in w for w in result["warnings"])


# --- joins: per-upstream staged inventories ----------------------------------------------------


def _join_scenario(
    *,
    skidder_available: bool = True,
    staged: dict[str, float] | None = None,
    num_days: int = 3,
) -> Scenario:
    system = HarvestSystem(
        system_id="join",
        jobs=[
            SystemJob("felling", "feller_buncher", []),
            SystemJob("primary_transport", "grapple_skidder", []),
            SystemJob("processing", "processor", ["felling", "primary_transport"]),
        ],
    )
    machines = [
        Machine(id="F1", role="feller_buncher"),
        Machine(id="S1", role="grapple_skidder"),
        Machine(id="P1", role="processor"),
    ]
    state = (
        ScenarioInitialState(blocks=[BlockInitialState(block_id="B1", staged_inventory=staged)])
        if staged
        else None
    )
    return Scenario(
        name="join",
        num_days=num_days,
        blocks=[Block(id="B1", landing_id="L1", work_required=100.0, harvest_system_id="join")],
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=10)],
        calendar=[
            CalendarEntry(
                machine_id=m.id,
                day=d,
                available=0 if (m.id == "S1" and not skidder_available) else 1,
            )
            for m in machines
            for d in range(1, num_days + 1)
        ],
        production_rates=[
            ProductionRate(machine_id=m, block_id="B1", rate=rate)
            for m, rate in (("F1", 100.0), ("S1", 60.0), ("P1", 100.0))
        ],
        harvest_systems={"join": system},
        initial_state=state,
    )


def test_join_needs_output_of_every_upstream_role() -> None:
    # The skidder never works: v1.0.0/1.0.0 pooled the upstream outputs and processed the
    # feller's 100 m³ alone (playback then flagged the processor and delivered 0).
    pb, result = _solve(_join_scenario(skidder_available=False))
    assert _assert_clean_replay(pb, result) == pytest.approx(0.0)
    model = build_operational_model(build_operational_problem(pb).bundle)
    assert set(model.InventoryPairs) == {("feller_buncher", "B1"), ("grapple_skidder", "B1")}


def test_join_processes_min_of_upstream_outputs() -> None:
    pb, result = _solve(_join_scenario())
    planned = _assert_clean_replay(pb, result)
    frame = result["assignments"]
    roles = {"F1": "feller_buncher", "S1": "grapple_skidder", "P1": "processor"}
    totals = frame.assign(role=frame.machine_id.map(roles)).groupby("role")["production"].sum()
    assert totals["processor"] <= min(totals["feller_buncher"], totals["grapple_skidder"]) + 1e-6
    assert planned == pytest.approx(totals["processor"])


def test_join_initial_inventory_is_per_upstream_role() -> None:
    staged = {"feller_buncher": 50.0, "grapple_skidder": 20.0}
    pb, result = _solve(_join_scenario(staged=staged, num_days=1))
    model = build_operational_model(build_operational_problem(pb).bundle)
    meta = getattr(model, "_warm_start_meta")
    assert meta["initial_inventory_start"] == {
        ("feller_buncher", "B1"): pytest.approx(50.0),
        ("grapple_skidder", "B1"): pytest.approx(20.0),
    }
    # One slot: only the 20 m³ both upstream roles have staged can be processed.
    assert _assert_clean_replay(pb, result) == pytest.approx(20.0)


def test_linear_chain_inventory_is_indexed_by_upstream_role() -> None:
    pb = Problem.from_scenario(pipeline_scenario(roles=ROLES[:3]))
    model = build_operational_model(build_operational_bundle(pb))
    assert list(model.InventoryPairs) == [("feller_buncher", "B1"), ("grapple_skidder", "B1")]


# --- dynamic loader threshold ------------------------------------------------------------------


def _loader_tail_scenario(loader_rate: float) -> Scenario:
    return pipeline_scenario(
        roles=("feller_buncher", "loader"),
        fleet={"feller_buncher": [("FE1", 50.0)], "loader": [("LO1", loader_rate)]},
        blocks={"B1": 100.0},
        num_days=3,
        loader_batch=30.0,
    )


@pytest.mark.parametrize("loader_rate", [20.0, 29.0, 30.0, 45.0])
def test_loader_threshold_follows_remaining_volume(loader_rate: float) -> None:
    # 100 m³ with 30 m³ truckloads: the last 10 m³ (or 20 m³) are below a truckload. The static
    # min(q, W) threshold stranded them (objective 80 / 98 for loader rates 20 / 29); the tracker
    # rule min(q, W - delivered) lets the loader finish the block.
    pb, result = _solve(_loader_tail_scenario(loader_rate))
    assert result["objective"] == pytest.approx(100.0)
    assert _assert_clean_replay(pb, result) == pytest.approx(100.0)


def test_loader_tail_binaries_only_where_the_tail_is_reachable() -> None:
    bundle = build_operational_bundle(Problem.from_scenario(_loader_tail_scenario(20.0)))
    model = build_operational_model(bundle)
    tail_slots = sorted((day, shift) for _, day, shift in model.LoaderTailIndex)
    # The loader delivers at most 20 m³ per slot, so 70 m³ (W - q) are first exceeded before
    # the fifth slot; earlier slots use the plain truckload threshold.
    assert tail_slots[0] == (2, "S2")
    assert len(tail_slots) == 5
    small = build_operational_model(
        build_operational_bundle(
            Problem.from_scenario(
                pipeline_scenario(
                    roles=("feller_buncher", "loader"), blocks={"B1": 20.0}, loader_batch=30.0
                )
            )
        )
    )
    assert not hasattr(small, "loader_tail")  # block <= truckload: exact without binaries


# --- carried-in role_remaining above work_required ---------------------------------------------


def test_role_remaining_above_work_required_is_capped() -> None:
    # Audit case fuzz_incons seed 5: the feller may "still output" 69.4 m³ on a 54 m³ block.
    # Scenario/Problem validation rejects this since #118, so the valid scenario carries the
    # consistent cap (R = W) and the inconsistent 69.392 is injected into the MILP bundle to
    # exercise the defensive min(R, W) cap (#115); the plan must replay cleanly against the
    # consistent scenario.
    def state_with(feller_remaining: float) -> ScenarioInitialState:
        return ScenarioInitialState(
            blocks=[
                BlockInitialState(
                    block_id="B1",
                    role_remaining={
                        "feller_buncher": feller_remaining,
                        "grapple_skidder": 37.414,
                        "processor": 53.992,
                    },
                    staged_inventory={"feller_buncher": 31.978, "grapple_skidder": 16.578},
                )
            ]
        )

    def build(state: ScenarioInitialState) -> Scenario:
        return pipeline_scenario(
            roles=ROLES[:3],
            fleet={
                "feller_buncher": [("FE1", 47.622), ("FE2", 71.329)],
                "grapple_skidder": [("GR1", 35.021), ("GR2", 56.321)],
                "processor": [("PR1", 18.58), ("PR2", 72.522)],
            },
            headstart={"grapple_skidder": 1.0},
            blocks={"B1": 53.992},
            num_days=2,
            shifts=("S1", "S2"),
            initial_state=state,
        )

    with pytest.raises(ValueError, match="above the block's work_required"):
        build(state_with(69.392))
    pb = Problem.from_scenario(build(state_with(53.992)))
    ctx = build_operational_problem(pb)
    bundle = dataclasses.replace(
        ctx.bundle,
        initial_role_remaining={
            **ctx.bundle.initial_role_remaining,
            ("B1", "feller_buncher"): 69.392,
        },
    )
    result = solve_operational_milp(bundle, solver="highs", time_limit=60)
    _assert_clean_replay(pb, result)
    frame = result["assignments"]
    felled = frame[frame.machine_id.str.startswith("FE")]["production"].sum()
    assert felled <= 53.992 + 1e-6


# --- MILP -> playback replay fuzz (linear chains and joins) ------------------------------------

_POOL = ("feller_buncher", "grapple_skidder", "processor", "forwarder", "harvester", "delimber")


def _random_dag_scenario(seed: int) -> Scenario:
    """Random harvest system: linear chains and joins (several source roles), loaders, head
    starts, 1-3 shifts per day, occasional machine-days off."""

    rng = random.Random(seed)
    size = rng.randint(3, 5)
    roles = rng.sample(_POOL, size - 1)
    roles.append(
        "loader" if rng.random() < 0.6 else rng.choice([r for r in _POOL if r not in roles])
    )
    jobs: list[SystemJob] = []
    consumed: set[str] = set()
    for idx, role in enumerate(roles):
        if idx == 0 or (idx < len(roles) - 1 and rng.random() < 0.35):
            prereq: list[str] = []
        elif idx == len(roles) - 1:
            prereq = [f"j{j}" for j in range(idx) if f"j{j}" not in consumed] or [f"j{idx - 1}"]
        else:
            open_roles = [j for j in range(idx) if f"j{j}" not in consumed] or [idx - 1]
            prereq = [
                f"j{j}" for j in rng.sample(open_roles, min(len(open_roles), rng.choice([1, 1, 2])))
            ]
        consumed.update(prereq)
        jobs.append(SystemJob(f"j{idx}", role, prereq))
    headstart = {r: float(rng.choice([1, 2])) for r in roles[1:] if rng.random() < 0.35} or None
    system = HarvestSystem(
        system_id="dag",
        jobs=jobs,
        role_headstart_shifts=headstart,
        loader_batch_volume_m3=float(rng.choice([10, 30, 60])),
    )
    fleet = {
        r: [
            (f"{r[:3].upper()}{n + 1}", round(rng.uniform(10, 80), 3))
            for n in range(rng.randint(1, 2))
        ]
        for r in roles
    }
    machines = [Machine(id=mid, role=r) for r, items in fleet.items() for mid, _ in items]
    blocks = {f"B{i + 1}": round(rng.uniform(15, 220), 3) for i in range(rng.randint(1, 2))}
    num_days = rng.randint(2, 4)
    shifts = [f"S{i + 1}" for i in range(rng.randint(1, 3))]
    return Scenario(
        name=f"dag{seed}",
        num_days=num_days,
        blocks=[
            Block(id=b, landing_id="L1", work_required=w, harvest_system_id="dag")
            for b, w in blocks.items()
        ],
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=20)],
        calendar=[
            CalendarEntry(machine_id=m.id, day=d, available=0 if rng.random() < 0.1 else 1)
            for m in machines
            for d in range(1, num_days + 1)
        ],
        production_rates=[
            ProductionRate(machine_id=mid, block_id=b, rate=rate)
            for items in fleet.values()
            for mid, rate in items
            for b in blocks
        ],
        harvest_systems={"dag": system},
        timeline=TimelineConfig(
            shifts=[ShiftDefinition(name=s, hours=8.0, shifts_per_day=1) for s in shifts]
        ),
    )


def test_random_dag_generator_covers_joins_and_loaders() -> None:
    systems = [_random_dag_scenario(seed).harvest_systems["dag"] for seed in range(24)]
    assert any(any(len(job.prerequisites) > 1 for job in s.jobs) for s in systems)
    assert any(any(job.machine_role == "loader" for job in s.jobs) for s in systems)
    assert any(all(len(job.prerequisites) <= 1 for job in s.jobs) for s in systems)


@pytest.mark.parametrize("seed", range(24))
def test_random_dag_milp_plans_replay_clean(seed: int) -> None:
    pb, result = _solve(_random_dag_scenario(seed))
    _assert_clean_replay(pb, result)
