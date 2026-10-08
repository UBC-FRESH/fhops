"""Third pre-release audit fixes for the heuristics (#158).

* Locked slots may idle: a locked slot produces what its staged input allows (up to
  ``ScheduleLock.production``) and is never a sequencing violation, as in the operational MILP
  (E13) and playback (audit MAJOR 1 / MINOR 4: a downstream-reservation pull left a later locked
  skidder slot without input, which the heuristics charged as a hard violation).
* Blocks whose harvest system has none of its roles in the fleet admit no machine (audit MAJOR 2:
  any machine could work them and the tracker credited volume that was never delivered).
* The repair caps production by the block's remaining volume as the tracker does (harvest systems
  with several terminal roles).
"""

from __future__ import annotations

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.evaluation.playback import run_playback
from fhops.evaluation.sequencing import SequencingTracker
from fhops.optimization.heuristics import solve_ils, solve_sa, solve_tabu
from fhops.optimization.heuristics.common import evaluate_assignments, evaluate_schedule
from fhops.optimization.heuristics.ils import _assignments_to_schedule
from fhops.optimization.operational_problem import (
    blocks_without_fleet_roles,
    build_operational_problem,
)
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
    ScheduleLock,
)
from fhops.scheduling.systems import HarvestSystem, SystemJob
from fhops.scheduling.timeline.models import ShiftDefinition, TimelineConfig

_C3 = HarvestSystem(
    system_id="c3",
    jobs=[
        SystemJob("felling", "feller_buncher", []),
        SystemJob("primary_transport", "grapple_skidder", ["felling"]),
        SystemJob("loading", "loader", ["primary_transport"]),
    ],
)


def _lockpull(locks: list[ScheduleLock] | None = None) -> Problem:
    """Feller -> skidder -> loader on one capacity-1 landing, 2 shifts x 4 days (audit lockpull)."""

    machines = [
        Machine(id="F1", role="feller_buncher"),
        Machine(id="K1", role="grapple_skidder"),
        Machine(id="L1M", role="loader"),
    ]
    days = 4
    scenario = Scenario(
        name="lockpull",
        num_days=days,
        blocks=[Block(id="B1", landing_id="L1", work_required=600, harvest_system_id="c3")],
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[
            CalendarEntry(machine_id=m.id, day=d, available=1)
            for m in machines
            for d in range(1, days + 1)
        ],
        production_rates=[
            ProductionRate(machine_id=m.id, block_id="B1", rate=100) for m in machines
        ],
        harvest_systems={"c3": _C3},
        timeline=TimelineConfig(
            shifts=[ShiftDefinition(name=n, hours=10, shifts_per_day=1) for n in ("S1", "S2")]
        ),
        locked_assignments=(
            locks if locks is not None else [ScheduleLock(machine_id="K1", block_id="B1", day=3)]
        ),
    )
    return Problem.from_scenario(scenario)


def _hard_violations(pb: Problem, assignments: pd.DataFrame) -> tuple[float, int, float]:
    debug: dict = {}
    score = evaluate_assignments(pb, assignments, build_operational_problem(pb), debug=debug)
    return score, int(debug["hard_violation_count"]), float(debug["delivered_total"])


@pytest.mark.parametrize(
    "solver",
    [
        lambda pb: solve_sa(pb, iters=600, seed=1),
        lambda pb: solve_ils(pb, iters=60, seed=1),
        lambda pb: solve_tabu(pb, iters=600, seed=1),
    ],
    ids=["sa", "ils", "tabu"],
)
def test_locked_slot_without_input_idles_instead_of_violating(solver) -> None:
    pb = _lockpull()
    result = solver(pb)
    score, violations, delivered = _hard_violations(pb, result["assignments"])
    # Before #158: -2200 with 2 violations (the locked skidder's second shift had no felled wood).
    assert violations == 0
    assert result["objective"] == pytest.approx(-200.0)
    assert score == pytest.approx(result["objective"])
    assert delivered == pytest.approx(200.0)


def test_repaired_hand_plan_keeps_its_value() -> None:
    pb = _lockpull()
    ctx = build_operational_problem(pb)
    rows = [
        ("F1", 1, "S1"),
        ("F1", 1, "S2"),
        ("F1", 2, "S1"),
        ("F1", 2, "S2"),
        ("K1", 3, "S1"),
        ("K1", 3, "S2"),
        ("L1M", 4, "S1"),
        ("L1M", 4, "S2"),
    ]
    hand = pd.DataFrame(
        [dict(machine_id=m, block_id="B1", day=d, shift_id=s, assigned=1) for m, d, s in rows]
    )
    debug: dict = {}
    score = evaluate_schedule(pb, _assignments_to_schedule(pb, hand), ctx, debug=debug)
    assert debug["hard_violation_count"] == 0
    assert score == pytest.approx(-200.0)


def _single_lock_problem(production: float | None) -> Problem:
    # The loader is locked on day 1, when nothing is staged yet; the skidder is locked on day 2.
    return _lockpull(
        [
            ScheduleLock(machine_id="L1M", block_id="B1", day=1, shift_id="S1"),
            ScheduleLock(
                machine_id="F1", block_id="B1", day=2, shift_id="S1", production=production
            ),
        ]
    )


def test_starved_locked_slot_is_not_a_violation_in_scoring_and_playback() -> None:
    pb = _single_lock_problem(None)
    plan = pd.DataFrame(
        [
            dict(machine_id="L1M", block_id="B1", day=1, shift_id="S1", assigned=1),
            dict(machine_id="F1", block_id="B1", day=2, shift_id="S1", assigned=1),
        ]
    )
    _score, violations, _delivered = _hard_violations(pb, plan)
    assert violations == 0
    records = list(run_playback(pb, plan).records)
    assert not any(record.metadata.get("sequencing_violation") for record in records)
    loader = next(record for record in records if record.machine_id == "L1M")
    assert loader.production_units == 0.0


@pytest.mark.parametrize(("production", "expected"), [(None, 100.0), (30.0, 30.0), (0.0, 0.0)])
def test_lock_production_caps_the_locked_slot(production, expected) -> None:
    pb = _single_lock_problem(production)
    ctx = build_operational_problem(pb)
    assert ctx.lock_production_for("F1", 2, "S1") == production
    assert ctx.lock_production_for("F1", 2, "S2") is None
    plan = pd.DataFrame([dict(machine_id="F1", block_id="B1", day=2, shift_id="S1", assigned=1)])
    debug: dict = {}
    evaluate_assignments(pb, plan, ctx, debug=debug)
    assert debug["hard_violation_count"] == 0
    assert debug["role_inventory_totals"]["feller_buncher"] == pytest.approx(expected)
    records = list(run_playback(pb, plan).records)
    assert records[0].production_units == pytest.approx(expected)
    # The heuristics honour the cap too: the locked slot's output is all the skidder can take.
    result = solve_sa(pb, iters=300, seed=3)
    _score, violations, _delivered = _hard_violations(pb, result["assignments"])
    assert violations == 0


def test_tracker_locked_mode_caps_by_staged_input() -> None:
    pb = _single_lock_problem(None)
    ctx = build_operational_problem(pb)
    tracker = SequencingTracker(ctx)
    felled = tracker.process(1, "F1", "B1", 40.0, "S1")
    assert felled.production_units == pytest.approx(40.0)
    # Next slot: 40 m3 staged; a locked skidder proposing 100 produces 40 without a violation,
    # an unlocked one is flagged.
    locked = tracker.process(1, "K1", "B1", 100.0, "S2", locked=True)
    assert locked.violation_reason is None
    assert locked.production_units == pytest.approx(40.0)
    unlocked = tracker.process(1, "K1", "B1", 100.0, "S2")
    assert unlocked.violation_reason == "missing_prereq"


def _phantom() -> Problem:
    system = HarvestSystem(
        system_id="fk",
        jobs=[
            SystemJob("felling", "feller_buncher", []),
            SystemJob("primary_transport", "grapple_skidder", ["felling"]),
        ],
    )
    days = 10
    scenario = Scenario(
        name="phantom",
        num_days=days,
        blocks=[
            Block(id="B1", landing_id="L1", work_required=50, harvest_system_id="fk"),
            Block(id="B2", landing_id="L1", work_required=50),
        ],
        machines=[Machine(id="H1", role="harvester")],
        landings=[Landing(id="L1", daily_capacity=2)],
        calendar=[CalendarEntry(machine_id="H1", day=d, available=1) for d in range(1, days + 1)],
        production_rates=[
            ProductionRate(machine_id="H1", block_id="B1", rate=40),
            ProductionRate(machine_id="H1", block_id="B2", rate=10),
        ],
        harvest_systems={"fk": system},
    )
    return Problem.from_scenario(scenario)


def test_block_without_fleet_roles_admits_no_machine() -> None:
    pb = _phantom()
    ctx = build_operational_problem(pb)
    assert ctx.allowed_roles["B1"] == frozenset()
    assert ctx.allowed_roles["B2"] is None
    assert set(blocks_without_fleet_roles(ctx)) == {"B1"}
    for solver in (
        lambda: solve_sa(pb, iters=200, seed=1),
        lambda: solve_tabu(pb, iters=200, seed=1),
        lambda: solve_ils(pb, iters=20, seed=1),
    ):
        assignments = solver()["assignments"]
        # Before #158 the harvester worked B1 and playback credited 400 m3 nobody delivered.
        assert set(assignments["block_id"]) == {"B2"}
        records = list(run_playback(pb, assignments).records)
        assert sum(record.production_units for record in records) == pytest.approx(50.0)


def test_validate_warns_about_blocks_without_fleet_roles(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "blocks.csv").write_text(
        "id,landing_id,work_required,harvest_system_id\nB1,L1,50,fk\nB2,L1,50,\n"
    )
    (data / "machines.csv").write_text("id,role\nH1,harvester\n")
    (data / "landings.csv").write_text("id,daily_capacity\nL1,2\n")
    (data / "calendar.csv").write_text(
        "machine_id,day,available\n" + "".join(f"H1,{d},1\n" for d in range(1, 4))
    )
    (data / "prod_rates.csv").write_text("machine_id,block_id,rate\nH1,B1,40\nH1,B2,10\n")
    system = {
        "system_id": "fk",
        "jobs": [
            {"name": "felling", "machine_role": "feller_buncher", "prerequisites": []},
            {"name": "skid", "machine_role": "grapple_skidder", "prerequisites": ["felling"]},
        ],
    }
    path = tmp_path / "scenario.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "name": "phantom",
                "num_days": 3,
                "data": {
                    "blocks": "data/blocks.csv",
                    "machines": "data/machines.csv",
                    "landings": "data/landings.csv",
                    "calendar": "data/calendar.csv",
                    "prod_rates": "data/prod_rates.csv",
                },
                "harvest_systems": {"fk": system},
            }
        )
    )
    result = CliRunner().invoke(app, ["validate", str(path)])
    assert result.exit_code == 0, result.output
    assert "Warning: block B1" in result.output
    assert "no machine may work the block" in result.output
    assert "block B2" not in result.output


def test_repair_caps_production_by_block_remaining_with_two_terminal_roles() -> None:
    # Delimber and processor are both terminal: once the locked delimber delivers the block, the
    # forwarder has nothing left to move. The repair used to credit it with its full rate, so the
    # buffered processor was scheduled and charged a head-start violation (fuzz seed 138).
    system = HarvestSystem(
        system_id="dag",
        jobs=[
            SystemJob("j0", "forwarder", []),
            SystemJob("j1", "delimber", []),
            SystemJob("j2", "processor", ["j0"]),
        ],
        role_headstart_shifts={"delimber": 1.0, "processor": 2.0},
        loader_batch_volume_m3=60.0,
    )
    machines = [
        Machine(id="FOR1", role="forwarder"),
        Machine(id="DEL1", role="delimber"),
        Machine(id="PRO1", role="processor"),
    ]
    rates = {"FOR1": 77.327, "DEL1": 69.396, "PRO1": 19.423}
    scenario = Scenario(
        name="two_terminal",
        num_days=4,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=45.823,
                harvest_system_id="dag",
                earliest_start=1,
                latest_finish=4,
            )
        ],
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=3)],
        calendar=[
            CalendarEntry(machine_id=m.id, day=d, available=0 if (m.id, d) == ("FOR1", 1) else 1)
            for m in machines
            for d in range(1, 5)
        ],
        production_rates=[
            ProductionRate(machine_id=m.id, block_id="B1", rate=rates[m.id]) for m in machines
        ],
        harvest_systems={"dag": system},
        timeline=TimelineConfig(
            shifts=[ShiftDefinition(name=n, hours=8, shifts_per_day=1) for n in ("S1", "S2", "S3")]
        ),
        locked_assignments=[ScheduleLock(machine_id="DEL1", block_id="B1", day=1, shift_id="S1")],
    )
    pb = Problem.from_scenario(scenario)
    result = solve_sa(pb, iters=400, seed=1)
    score, violations, delivered = _hard_violations(pb, result["assignments"])
    assert violations == 0
    assert delivered == pytest.approx(45.823)
    assert score == pytest.approx(result["objective"])
