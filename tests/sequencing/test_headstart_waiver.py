"""Head-start waiver uses upstream output *before* the current slot (#116).

The operational MILP waives the head-start buffer (E8) through ``upstream_done``, which compares
upstream output cumulated up to the previous slot with the role's remaining volume. The tracker and
the heuristic repair used the upstream remaining volume *after* upstream machines had already
worked in the current slot, so an upstream role finishing a block in the same slot waived the
buffer for its downstream role in that very slot (a plan the MILP rejects).
"""

from __future__ import annotations

import pandas as pd

from fhops.evaluation.playback import run_playback
from fhops.evaluation.sequencing import build_sequencing_tracker
from fhops.optimization.heuristics.common import Schedule, evaluate_schedule
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem

from .test_milp_playback_alignment import pipeline_scenario


def _scenario(num_days: int = 3):
    # feller FE1 -> skidder GR1 (50 m³/shift each); head start 1 shift => B = 50 m³; 70 m³ block.
    return pipeline_scenario(
        shifts=None, num_days=num_days, blocks={"B1": 70.0}, headstart={"grapple_skidder": 1.0}
    )


def test_same_slot_upstream_finish_does_not_waive_headstart() -> None:
    pb = Problem.from_scenario(_scenario())
    plan = pd.DataFrame(
        [
            dict(
                machine_id="FE1", block_id="B1", day=1, shift_id="S1", assigned=1, production=50.0
            ),
            dict(
                machine_id="GR1", block_id="B1", day=2, shift_id="S1", assigned=1, production=40.0
            ),
            # Day 3 starts with 10 m³ staged (< B = 50); the feller finishes the last 20 m³ in the
            # same slot, which must not waive the buffer for the skidder in that slot.
            dict(
                machine_id="FE1", block_id="B1", day=3, shift_id="S1", assigned=1, production=20.0
            ),
            dict(
                machine_id="GR1", block_id="B1", day=3, shift_id="S1", assigned=1, production=10.0
            ),
        ]
    )
    result = run_playback(pb, plan)
    violations = [
        (r.day, r.machine_id, r.metadata.get("sequencing_violation"))
        for r in result.records
        if r.metadata.get("sequencing_violation")
    ]
    assert violations == [(3, "GR1", "missing_prereq")]


def test_waiver_applies_once_upstream_finished_in_an_earlier_slot() -> None:
    tracker = build_sequencing_tracker(Problem.from_scenario(_scenario(num_days=4)))
    assert tracker.process(1, "FE1", "B1", 50.0, "S1").violation_reason is None
    assert tracker.process(2, "GR1", "B1", 40.0, "S1").violation_reason is None
    assert tracker.process(2, "FE1", "B1", 20.0, "S1").violation_reason is None
    # Day 3: 30 m³ staged (< B) but the feller finished before this slot -> waived.
    third = tracker.process(3, "GR1", "B1", 50.0, "S1")
    assert third.violation_reason is None
    assert third.production_units == 30.0


def _schedule(pb: Problem, rows: dict[tuple[str, int], str | None]) -> Schedule:
    ctx = build_operational_problem(pb)
    plan = {
        machine.id: {key: rows.get((machine.id, key[0])) for key in ctx.shift_keys}
        for machine in pb.scenario.machines
    }
    return Schedule(plan=plan)


def _slow_skidder_scenario(num_days: int, feller_off: tuple[int, ...] = ()):
    # FE1 50 m³/shift, GR1 10 m³/shift, B = 1 x 50 m³, 70 m³ block.
    scenario = pipeline_scenario(
        shifts=None,
        num_days=num_days,
        blocks={"B1": 70.0},
        headstart={"grapple_skidder": 1.0},
        fleet={"feller_buncher": [("FE1", 50.0)], "grapple_skidder": [("GR1", 10.0)]},
    )
    calendar = [
        entry.model_copy(update={"available": 0})
        if entry.machine_id == "FE1" and entry.day in feller_off
        else entry
        for entry in scenario.calendar
    ]
    return scenario.model_copy(update={"calendar": calendar})


def test_repair_drops_same_slot_waiver_assignment() -> None:
    # Day 3 starts with 40 m³ staged (>= GR1's 10 m³, < B = 50 m³) and FE1 finishes the block
    # (last 20 m³) in that same slot: the buffer is not waived, so the repair drops GR1 on day 3.
    pb = Problem.from_scenario(_slow_skidder_scenario(3, feller_off=(2,)))
    ctx = build_operational_problem(pb)
    schedule = _schedule(
        pb, {("FE1", 1): "B1", ("GR1", 2): "B1", ("FE1", 3): "B1", ("GR1", 3): "B1"}
    )
    debug: dict[str, object] = {}
    evaluate_schedule(pb, schedule, ctx, debug=debug)
    assert schedule.plan["FE1"][(3, "S1")] == "B1"
    assert schedule.plan["GR1"][(3, "S1")] is None
    assert debug["sequencing_violation_count"] == 0


def test_repair_keeps_assignment_when_upstream_finished_earlier() -> None:
    # FE1 finishes on day 2; from day 5 the staged volume is below B, and the waiver applies.
    pb = Problem.from_scenario(_slow_skidder_scenario(6))
    ctx = build_operational_problem(pb)
    rows: dict[tuple[str, int], str | None] = {("FE1", 1): "B1", ("FE1", 2): "B1"}
    rows.update({("GR1", day): "B1" for day in range(2, 7)})
    schedule = _schedule(pb, rows)
    debug: dict[str, object] = {}
    evaluate_schedule(pb, schedule, ctx, debug=debug)
    assert all(schedule.plan["GR1"][(day, "S1")] == "B1" for day in range(2, 7))
    assert debug["sequencing_violation_count"] == 0
