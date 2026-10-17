"""Block-separable scoring for the FHOPS heuristics (P10 parity foundation).

``_score_plan`` walks every shift and machine once, feeding a single ``SequencingTracker``. Its
state is keyed by ``(block_id, role)`` and does not couple blocks, so the objective can be computed
block by block: replay each block's own slots through its own tracker, then add the per-machine
mobilisation and the per-``(landing, shift)`` capacity term. ``score_separable`` does exactly that,
and the P10 parity test asserts it equals ``_score_plan`` to 1e-9 on the example ladder.

This module is the correctness foundation for the incremental evaluator: once the per-block
contribution is exact, it can be cached and only dirty blocks recomputed after a move.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fhops.evaluation.sequencing import SequencingTracker

from .common import (
    BLOCK_COMPLETION_EPS,
    LEFTOVER_PENALTY_FACTOR,
    _ensure_mobilisation_stats,
    _no_lock,
)

if TYPE_CHECKING:
    from fhops.optimization.operational_problem import OperationalProblem
    from fhops.scenario.contract import Problem

    from .common import Schedule

Slot = tuple[str, int, str]


@dataclass
class BlockContribution:
    """One block's share of the objective.

    Attributes
    ----------
    delivered : float
        Terminal volume delivered by the block (m³).
    leftover : float
        Remaining terminal volume, counted only above ``BLOCK_COMPLETION_EPS`` (m³).
    penalty : float
        Hard penalties charged to the block's slots (sequencing violations), in objective units.
    """

    delivered: float = 0.0
    leftover: float = 0.0
    penalty: float = 0.0


@dataclass
class SeparableTotals:
    """The components of ``_score_plan``'s objective, computed block by block."""

    delivered: float = 0.0
    leftover: float = 0.0
    penalty: float = 0.0
    landing_surplus: float = 0.0
    mobilisation: float = 0.0
    transitions: float = 0.0
    blocks: dict[str, BlockContribution] = field(default_factory=dict)


def _resolve_slot(
    pb: Problem, ctx: OperationalProblem, sched: Schedule, machine_id: str, day: int, shift_id: str
) -> tuple[float, str | None, bool]:
    """Resolve one slot to its hard penalty, block, and whether it feeds the tracker.

    Applies the same checks ``_score_plan`` applies ahead of the tracker (unavailable slot, broken
    lock, forbidden role, out-of-window day, zero rate). Locked slots resolve to the locked block.

    Parameters
    ----------
    pb : Problem
        The scenario.
    ctx : OperationalProblem
        Shared solver context.
    sched : Schedule
        The schedule under evaluation.
    machine_id : str
        Machine of the slot.
    day, shift_id : int, str
        Slot coordinates.

    Returns
    -------
    tuple of (float, str or None, bool)
        The hard penalty, the resolved block (``None`` for an idle or pinned-idle slot), and whether
        the slot reaches the sequencing tracker (``False`` when it is idle or penalised).
    """
    bundle = ctx.bundle
    block_id = sched.plan[machine_id][(day, shift_id)]
    hard = ctx.hard_violation_penalty()
    if (
        bundle.availability_shift.get((machine_id, day, shift_id), 1) == 0
        or bundle.availability_day.get((machine_id, day), 1) == 0
        or (machine_id, day, shift_id) in ctx.blackout_shifts
    ):
        return (hard if block_id is not None else 0.0), None, False
    lock_for = (
        ctx.lock_for if (ctx.locked_assignments or ctx.locked_shift_assignments) else _no_lock
    )
    locked_block = lock_for(machine_id, day, shift_id)
    if locked_block is not None:
        if block_id is not None and block_id != locked_block:
            return hard, locked_block, False
        return 0.0, locked_block, True
    if block_id is None:
        return 0.0, None, False
    role = bundle.machine_roles.get(machine_id)
    allowed = ctx.allowed_roles.get(block_id)
    if allowed is not None and role is not None and role not in allowed:
        return hard, block_id, False
    earliest, latest = bundle.windows[block_id]
    if day < earliest or day > latest:
        return hard, block_id, False
    if bundle.production_rates.get((machine_id, block_id), 0.0) <= 0.0:
        return hard, block_id, False
    return 0.0, block_id, True


def score_separable(
    pb: Problem, sched: Schedule, ctx: OperationalProblem
) -> tuple[float, SeparableTotals]:
    """Score ``sched`` block by block; equals ``_score_plan`` (P10 parity foundation).

    Parameters
    ----------
    pb : Problem
        The scenario.
    sched : Schedule
        The schedule under evaluation.
    ctx : OperationalProblem
        Shared solver context.

    Returns
    -------
    tuple of (float, SeparableTotals)
        The objective and its components.
    """
    sc = pb.scenario
    bundle = ctx.bundle
    weights = bundle.objective_weights
    hard_penalty = ctx.hard_violation_penalty()
    landing_of = bundle.landing_for_block
    landing_cap = bundle.landing_capacity

    totals = SeparableTotals()
    block_slots: dict[str, list[Slot]] = defaultdict(list)
    landing_used: dict[tuple[str, int, str], int] = defaultdict(int)
    hard_landing_skip: set[Slot] = set()

    # Pass 1: resolve each slot, group by block, and accumulate the landing load per slot.
    for day, shift_id in ctx.shift_keys:
        for machine in sc.machines:
            machine_id = machine.id
            penalty, block_id, feeds = _resolve_slot(pb, ctx, sched, machine_id, day, shift_id)
            totals.penalty += penalty
            if block_id is None or not feeds:
                continue
            slot = (machine_id, day, shift_id)
            block_slots[block_id].append(slot)
            landing_id = landing_of.get(block_id)
            if landing_id is not None and landing_id in landing_cap:
                key = (landing_id, day, shift_id)
                landing_used[key] += 1
                excess = max(0, landing_used[key] - max(landing_cap.get(landing_id, 0), 0))
                if excess > 0:
                    if weights.landing_surplus == 0.0:
                        totals.penalty += hard_penalty
                        hard_landing_skip.add(slot)
                    else:
                        totals.landing_surplus += excess

    # Pass 2: replay each block's slots through its own tracker.
    for block_id, slots in block_slots.items():
        tracker = SequencingTracker(ctx, debug=False)
        contribution = BlockContribution()
        ordered = sorted(slots, key=lambda slot: ctx.shift_index[(slot[1], slot[2])])
        for machine_id, day, shift_id in ordered:
            if (machine_id, day, shift_id) in hard_landing_skip:
                continue
            rate_value = bundle.production_rates.get((machine_id, block_id), 0.0)
            result = tracker.process(day, machine_id, block_id, rate_value, shift_id)
            if result.violation_reason:
                totals.penalty += hard_penalty
                contribution.penalty += hard_penalty
        tracker.finalize()
        contribution.delivered = tracker.delivered_total
        contribution.leftover = tracker.remaining_work.get(block_id, 0.0)
        totals.delivered += contribution.delivered
        totals.blocks[block_id] = contribution

    totals.leftover = sum(
        contribution.leftover
        for contribution in totals.blocks.values()
        if contribution.leftover > BLOCK_COMPLETION_EPS
    )

    _ensure_mobilisation_stats(sched, ctx)
    totals.mobilisation = sum(sched.mobilisation_cache[machine.id].cost for machine in sc.machines)
    totals.transitions = sum(
        sched.mobilisation_cache[machine.id].transitions for machine in sc.machines
    )

    score = weights.production * (totals.delivered - LEFTOVER_PENALTY_FACTOR * totals.leftover)
    score -= weights.mobilisation * totals.mobilisation
    score -= weights.transitions * totals.transitions
    score -= weights.landing_surplus * totals.landing_surplus
    score -= totals.penalty
    return score, totals
