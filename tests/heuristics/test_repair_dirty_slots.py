from __future__ import annotations

from fhops.optimization.heuristics.common import (
    _repair_schedule_cover_blocks,
    _set_assignment,
    init_greedy_schedule,
)
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario


def test_repair_limit_only_touches_dirty_slots(tmp_path):
    pb = Problem.from_scenario(load_scenario("examples/tiny7/scenario.yaml"))
    ctx = build_operational_problem(pb)
    sched = init_greedy_schedule(pb, ctx)

    # Use the first shift and two different machines.
    day, shift_id = ctx.shift_keys[0]
    dirty_machine = pb.scenario.machines[0].id
    untouched_machine = pb.scenario.machines[1].id
    untouched_block = sched.plan[untouched_machine][(day, shift_id)]

    # Clear the dirty slot via the helper so bookkeeping stays consistent.
    _set_assignment(sched, dirty_machine, day, shift_id, None, ctx)

    stats: dict[str, float] = {}
    _repair_schedule_cover_blocks(
        pb,
        sched,
        ctx,
        limit_to_dirty_slots=True,
        repair_stats=stats,
    )

    # Dirty slot should be refilled and removed from dirty tracking.
    assert sched.plan[dirty_machine][(day, shift_id)] is not None
    assert (dirty_machine, day, shift_id) not in sched.dirty_slots

    # The untouched slot must remain unchanged because it was never marked dirty.
    assert sched.plan[untouched_machine][(day, shift_id)] == untouched_block
    assert stats.get("slots_processed") >= 1.0
    assert stats.get("slots_processed") <= stats.get("slots_visited")
    assert stats.get("machines_touched") == 1.0
