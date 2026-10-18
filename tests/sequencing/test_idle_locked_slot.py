"""Idle assignments are not sequencing violations (#125).

The operational MILP may keep a locked machine on its block without producing (``x = 1``,
``p = 0``) when nothing is staged for it yet. Head-start and truckload thresholds only bind a role
that produces (``role_active``), so playback must not flag such an idle slot as
``missing_prereq``. Producing without the staged volume is still a violation.
"""

from __future__ import annotations

import pandas as pd
import pytest

from fhops.evaluation import compute_kpis
from fhops.evaluation.playback import run_playback
from fhops.model.milp.driver import solve_operational_milp
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem, ScheduleLock

from .test_milp_playback_alignment import ROLES, pipeline_scenario


def _row(machine: str, day: int, shift: str, production: float | None) -> dict[str, object]:
    row: dict[str, object] = dict(
        machine_id=machine, block_id="B1", day=day, shift_id=shift, assigned=1
    )
    row["production"] = production
    return row


def _violations(pb: Problem, plan: pd.DataFrame) -> list[tuple[int, str, str, str]]:
    result = run_playback(pb, plan)
    return [
        (r.day, r.shift_id, r.machine_id, r.metadata["sequencing_violation"])
        for r in result.records
        if r.metadata.get("sequencing_violation")
    ]


def test_idle_headstart_slot_is_not_a_violation() -> None:
    # Skidder with a one-shift head start (B = 50 m³) assigned in S1 before anything is felled.
    pb = Problem.from_scenario(pipeline_scenario(headstart={"grapple_skidder": 1.0}))
    idle = pd.DataFrame([_row("FE1", 1, "S1", 50.0), _row("GR1", 1, "S1", 0.0)])
    assert _violations(pb, idle) == []
    producing = pd.DataFrame([_row("FE1", 1, "S1", 50.0), _row("GR1", 1, "S1", 10.0)])
    assert _violations(pb, producing) == [(1, "S1", "GR1", "missing_prereq")]
    # Rate-based rows (no planned production) still propose the full rate and are flagged.
    rate_based = pd.DataFrame([_row("FE1", 1, "S1", None), _row("GR1", 1, "S1", None)])
    assert _violations(pb, rate_based) == [(1, "S1", "GR1", "missing_prereq")]


def test_idle_loader_slot_is_not_a_violation() -> None:
    pb = Problem.from_scenario(pipeline_scenario(roles=ROLES[:2] + ("loader",), loader_batch=30.0))
    plan = pd.DataFrame([_row("FE1", 1, "S1", 50.0), _row("LO1", 1, "S1", 0.0)])
    assert _violations(pb, plan) == []
    plan = pd.DataFrame([_row("FE1", 1, "S1", 50.0), _row("LO1", 1, "S2", 1.0)])
    assert _violations(pb, plan)[0][2:] == ("LO1", "missing_prereq")


def test_milp_idle_locked_machine_replays_without_violation() -> None:
    # Skidder locked to B1 on the first slot: the MILP must idle it (nothing staged yet).
    scenario = pipeline_scenario(headstart={"grapple_skidder": 1.0}).model_copy(
        update={
            "locked_assignments": [
                ScheduleLock(machine_id="GR1", block_id="B1", day=1, shift_id="S1")
            ]
        }
    )
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    result = solve_operational_milp(ctx.bundle, solver="highs", context=ctx)
    assert result["outcome"] == "optimal"
    frame = result["assignments"]
    locked = frame[(frame.machine_id == "GR1") & (frame.shift_id == "S1") & (frame.day == 1)]
    assert len(locked) == 1
    assert locked.iloc[0]["block_id"] == "B1"
    assert locked.iloc[0]["production"] == pytest.approx(0.0, abs=1e-6)
    kpis = compute_kpis(pb, frame)
    assert int(kpis["sequencing_violation_count"]) == 0
