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
    build_role_priority,
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

    work = bundle.work_required
    totals.leftover = 0.0
    for block_id, required in work.items():
        block_contribution = totals.blocks.get(block_id)
        value = block_contribution.leftover if block_contribution is not None else required
        if value > BLOCK_COMPLETION_EPS:
            totals.leftover += value

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


def slot_diff(a: Schedule, b: Schedule) -> list[Slot]:
    """Return the ``(machine, day, shift)`` slots where two schedules differ.

    Parameters
    ----------
    a, b : Schedule
        The two schedules.

    Returns
    -------
    list of Slot
        The differing slots.
    """
    changed: list[Slot] = []
    for machine_id in set(a.plan) | set(b.plan):
        plan_a = a.plan.get(machine_id, {})
        plan_b = b.plan.get(machine_id, {})
        for key in set(plan_a) | set(plan_b):
            if plan_a.get(key) != plan_b.get(key):
                changed.append((machine_id, key[0], key[1]))
    return changed


class SeparableEvaluator:
    """Incremental, block-separable scorer for the heuristic objective.

    A block's contribution (delivered, leftover, hard penalties) depends only on its own assigned
    slots and its landing, because the scenarios pair one landing with each block and the tracker's
    state is keyed by ``(block, role)``. The evaluator caches each block's contribution and resolves
    each slot once, and recomputes only the blocks and machines a move touches.

    Parameters
    ----------
    pb : Problem
        The scenario.
    ctx : OperationalProblem
        Shared solver context.
    """

    def __init__(self, pb: Problem, ctx: OperationalProblem) -> None:
        self.pb = pb
        self.ctx = ctx
        self._landing_of = ctx.bundle.landing_for_block
        self._landing_cap = ctx.bundle.landing_capacity
        self._rates = ctx.bundle.production_rates
        self._weights = ctx.bundle.objective_weights
        self._hard = ctx.hard_violation_penalty()
        self._work = ctx.bundle.work_required
        role_priority = build_role_priority(ctx)
        ordered = sorted(
            pb.scenario.machines,
            key=lambda m: (role_priority.get(ctx.bundle.machine_roles.get(m.id) or "", 999), m.id),
        )
        self._machine_order = {machine.id: index for index, machine in enumerate(ordered)}
        self._slot_base: dict[Slot, float] = {}
        self._slot_block: dict[Slot, str | None] = {}
        self._slots_by_block: dict[str, list[Slot]] = defaultdict(list)
        self._block_contrib: dict[str, BlockContribution] = {}
        self._base_penalty = 0.0
        self._seq_penalty = 0.0
        self.last: Schedule | None = None

    def _block_contribution(
        self, sched: Schedule, block_id: str, slots: list[Slot]
    ) -> BlockContribution:
        """Replay one block's slots (with its landing cap) and return its contribution."""
        contribution = BlockContribution()
        tracker = SequencingTracker(self.ctx, debug=False)
        landing_id = self._landing_of.get(block_id)
        cap = max(self._landing_cap.get(landing_id, 0), 0) if landing_id is not None else 0
        hard_landing = self._weights.landing_surplus == 0.0 and landing_id is not None
        ordered = sorted(
            slots,
            key=lambda slot: (
                self.ctx.shift_index[(slot[1], slot[2])],
                self._machine_order[slot[0]],
            ),
        )
        used = 0
        current_slot: tuple[int, str] | None = None
        for machine_id, day, shift_id in ordered:
            slot_key = (day, shift_id)
            if slot_key != current_slot:
                current_slot = slot_key
                used = 0
            used += 1
            if hard_landing and used > cap:
                contribution.penalty += self._hard
                continue
            rate_value = self._rates.get((machine_id, block_id), 0.0)
            result = tracker.process(day, machine_id, block_id, rate_value, shift_id)
            if result.violation_reason:
                contribution.penalty += self._hard
        tracker.finalize()
        contribution.delivered = tracker.delivered_total
        contribution.leftover = tracker.remaining_work.get(block_id, 0.0)
        return contribution

    def _resolve_into_cache(
        self, sched: Schedule, machine_id: str, day: int, shift_id: str
    ) -> None:
        """Resolve one slot and refresh the base-penalty, slot-block, and block-slot caches."""
        slot: Slot = (machine_id, day, shift_id)
        penalty, block_id, feeds = _resolve_slot(
            self.pb, self.ctx, sched, machine_id, day, shift_id
        )
        self._base_penalty += penalty - self._slot_base.get(slot, 0.0)
        self._slot_base[slot] = penalty
        previous = self._slot_block.get(slot)
        if previous is not None and slot in self._slots_by_block.get(previous, []):
            self._slots_by_block[previous].remove(slot)
        resolved = block_id if (block_id is not None and feeds) else None
        self._slot_block[slot] = resolved
        if resolved is not None:
            self._slots_by_block.setdefault(resolved, []).append(slot)

    def build(self, sched: Schedule) -> float:
        """Build the cache from ``sched`` and return its objective.

        Parameters
        ----------
        sched : Schedule
            The schedule to cache.

        Returns
        -------
        float
            The objective.
        """
        self._slot_base = {}
        self._slot_block = {}
        self._slots_by_block = defaultdict(list)
        self._block_contrib = {}
        self._base_penalty = 0.0
        for day, shift_id in self.ctx.shift_keys:
            for machine in self.pb.scenario.machines:
                self._resolve_into_cache(sched, machine.id, day, shift_id)
        self._seq_penalty = 0.0
        for block_id, slots in self._slots_by_block.items():
            contribution = self._block_contribution(sched, block_id, slots)
            self._block_contrib[block_id] = contribution
            self._seq_penalty += contribution.penalty
        _ensure_mobilisation_stats(sched, self.ctx)
        self.last = sched
        return self.score(sched)

    def score(self, sched: Schedule) -> float:
        """Combine the cache into the objective; recomputes no block contributions.

        Parameters
        ----------
        sched : Schedule
            The schedule the cache describes.

        Returns
        -------
        float
            The objective.
        """
        w = self._weights
        delivered = sum(c.delivered for c in self._block_contrib.values())
        leftover = 0.0
        for block_id, required in self._work.items():
            contribution = self._block_contrib.get(block_id)
            value = contribution.leftover if contribution is not None else required
            if value > BLOCK_COMPLETION_EPS:
                leftover += value
        mob = sum(sched.mobilisation_cache[m.id].cost for m in self.pb.scenario.machines)
        trans = sum(sched.mobilisation_cache[m.id].transitions for m in self.pb.scenario.machines)
        score = w.production * (delivered - LEFTOVER_PENALTY_FACTOR * leftover)
        score -= w.mobilisation * mob
        score -= w.transitions * trans
        score -= self._base_penalty + self._seq_penalty
        return score

    def score_after_move(self, sched: Schedule, changed_slots: list[Slot]) -> float:
        """Score ``sched`` incrementally after a move that changed ``changed_slots``.

        Recomputes only the blocks in the changed slots (and the machines they touch). The cached
        contributions of every other block are reused. The caller must pass every slot where
        ``sched`` differs from the schedule last built.

        Parameters
        ----------
        sched : Schedule
            The schedule reached by the move.
        changed_slots : list of Slot
            The slots that changed since the last build.

        Returns
        -------
        float
            The objective.
        """
        touched: set[str] = set()
        for machine_id, day, shift_id in changed_slots:
            slot: Slot = (machine_id, day, shift_id)
            previous = self._slot_block.get(slot)
            if previous is not None:
                touched.add(previous)
            self._resolve_into_cache(sched, machine_id, day, shift_id)
            resolved = self._slot_block.get(slot)
            if resolved is not None:
                touched.add(resolved)
        for block_id in touched:
            old = self._block_contrib.get(block_id)
            if old is not None:
                self._seq_penalty -= old.penalty
            slots = self._slots_by_block.get(block_id, [])
            if slots:
                contribution = self._block_contribution(sched, block_id, slots)
                self._block_contrib[block_id] = contribution
                self._seq_penalty += contribution.penalty
            else:
                self._block_contrib.pop(block_id, None)
        _ensure_mobilisation_stats(sched, self.ctx)
        self.last = sched
        return self.score(sched)
