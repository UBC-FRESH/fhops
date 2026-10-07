"""Shared sequencing tracker for KPI + playback enforcement."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from fhops.optimization.operational_problem import OperationalProblem, build_operational_problem
from fhops.scenario.contract import Problem

BLOCK_EPSILON = 1e-6
SEQUENCING_TOLERANCE = 1e-6
"""Absolute volume tolerance (m³) for inventory and head-start checks.

Operational-MILP plans satisfy their inventory constraints only up to the solver's feasibility
tolerance (HiGHS: 1e-7 on the scaled problem, observed up to ~5e-7 m³), so a tighter tolerance
flags spurious violations when MILP plans are replayed."""


@dataclass(slots=True)
class SequencingResult:
    """Outcome for a single machine/shift assignment."""

    production_units: float
    machine_role: str | None
    violation_reason: str | None
    block_completed: bool


@dataclass(slots=True)
class SequencingTracker:
    """Tracks staged volume and sequencing feasibility as playback iterates.

    The tracker replays assignments in chronological slot order (call :meth:`process` per
    assignment, then :meth:`finalize`) and applies the operational MILP sequencing rules
    (formulation E7/E8, ``docs/softwarex/manuscript/sections/includes/
    fhops_operational_formulation.md``):

    * Output staged in a shift slot ``(day, shift_id)`` becomes available to downstream roles from
      the **next slot** onward (E7: ``I_start(s) = I(prev(s))``; next shift of the same day in
      multi-shift scenarios, next day in single-shift scenarios).
    * A downstream role's production is capped by the staged upstream volume still available
      (E7 guard); machines of the same role in one slot draw from that volume in turn.
    * A buffered role (``role_headstart_shifts``) may only work when the upstream volume staged at
      the start of the slot is at least the head-start volume ``B_{r,b}`` (E8;
      :attr:`OperationalProblem.role_headstart_volume`), unless every upstream role had already
      output its whole remaining volume before the current slot (the buffer can no longer grow;
      output finished in the same slot does not count, matching the MILP's ``upstream_done``).
    * A loader may only work when the upstream volume staged at the start of the slot covers one
      truckload (``min(loader_batch_volume_m3, remaining block volume)``).
    * An assignment proposing no production (``proposed_production <= SEQUENCING_TOLERANCE``) is
      an idle slot: the head-start and truckload thresholds only apply to a role that produces
      (the MILP's ``role_active``), so it is never a ``missing_prereq`` violation (#125; e.g. a
      machine locked to a block that the MILP leaves idle because nothing is staged yet). Role
      violations (``unknown_role`` / ``forbidden_role``) are still reported. The heuristics always
      propose the machine's rate, so they are unaffected.

    Calls without ``shift_id`` treat each day as one slot (v1.0.0 behaviour).

    Attributes
    ----------
    ctx:
        Shared :class:`~fhops.optimization.operational_problem.OperationalProblem` context.
    debug:
        When ``True`` callers may request :meth:`debug_snapshot` for telemetry.
    remaining_work:
        ``block_id -> m³`` terminal volume still to deliver (starts at ``work_required``).
    role_inventory:
        ``(block_id, role) -> m³`` output by ``role`` and not yet consumed downstream. Starts from
        ``ctx.initial_role_inventory`` (``Scenario.initial_state`` staged inventory; empty by
        default).
    role_remaining:
        ``(block_id, role) -> m³`` output the role may still produce. Starts from
        ``ctx.role_work_required`` (``work_required`` or the carried-in ``role_remaining``).
    role_counts_total:
        ``(block_id, role) -> shifts`` worked before the current slot. Starts from
        ``ctx.initial_role_counts`` (empty by default). Reported for rolling-horizon state
        carry-forward; head-start checks use staged volume instead.

    Notes
    -----
    All volumes are m³. ``remaining_work`` starts at ``Block.work_required`` (terminal delivered
    volume) and is debited by the terminal role (or by any role for blocks without an explicit
    harvest system); ``role_remaining`` caps each role at the same volume; ``role_inventory``
    holds volume output by a role and not yet consumed downstream; ``delivered_total`` sums the
    terminal deliveries.
    """

    ctx: OperationalProblem
    debug: bool = False
    remaining_work: dict[str, float] = field(init=False)
    role_inventory: defaultdict[tuple[str, str], float] = field(init=False)
    role_inventory_today: defaultdict[tuple[str, str], float] = field(init=False)
    role_remaining: dict[tuple[str, str], float] = field(init=False)
    role_counts_total: defaultdict[tuple[str, str], int] = field(init=False)
    role_counts_day: defaultdict[tuple[str, str], int] = field(init=False)
    role_consumed_slot: defaultdict[tuple[str, str], float] = field(init=False)
    completed_blocks: set[str] = field(init=False)
    debug_violation_counts: Counter[str] = field(init=False)
    debug_first_violation_role: str | None = field(default=None, init=False)
    debug_first_violation_reason: str | None = field(default=None, init=False)
    debug_first_violation_block: str | None = field(default=None, init=False)
    debug_first_violation_day: int | None = field(default=None, init=False)
    debug_first_violation_detail: dict[str, Any] | None = field(default=None, init=False)
    _current_slot: tuple[int, str | None] | None = field(default=None, init=False)
    delivered_total: float = field(init=False)

    def __post_init__(self) -> None:
        self.remaining_work = dict(self.ctx.bundle.work_required)
        self.role_inventory = defaultdict(float, self.ctx.initial_role_inventory)
        self.role_inventory_today = defaultdict(float)
        self.role_remaining = dict(self.ctx.role_work_required)
        self.role_counts_total = defaultdict(int, self.ctx.initial_role_counts)
        self.role_counts_day = defaultdict(int)
        self.role_consumed_slot = defaultdict(float)
        self.completed_blocks = set()
        self.debug_violation_counts = Counter()
        self.delivered_total = 0.0

    def _roll_slot(self, day: int, shift_id: str | None) -> None:
        slot = (day, shift_id)
        if self._current_slot is None or slot == self._current_slot:
            self._current_slot = slot
            return
        for key, volume in self.role_inventory_today.items():
            self.role_inventory[key] += volume
        self.role_inventory_today.clear()
        for key, count in self.role_counts_day.items():
            self.role_counts_total[key] += count
        self.role_counts_day.clear()
        self.role_consumed_slot.clear()
        self._current_slot = slot

    def finalize(self) -> None:
        """Flush the current slot's counters (call once after iterating assignments)."""

        if self.role_counts_day:
            for key, count in self.role_counts_day.items():
                self.role_counts_total[key] += count
            self.role_counts_day.clear()
        if self.role_inventory_today:
            for key, volume in self.role_inventory_today.items():
                self.role_inventory[key] += volume
            self.role_inventory_today.clear()

    def process(
        self,
        day: int,
        machine_id: str,
        block_id: str,
        proposed_production: float,
        shift_id: str | None = None,
    ) -> SequencingResult:
        """Advance the sequencing state for a single assignment.

        Parameters
        ----------
        day:
            Scenario day of the assignment.
        machine_id, block_id:
            Assigned machine and block.
        proposed_production:
            Planned production (m³); capped by remaining volume and staged upstream inventory.
            A value ``<= SEQUENCING_TOLERANCE`` is an idle slot: no head-start/truckload check.
        shift_id:
            Shift label. Staged output is released when ``(day, shift_id)`` changes; omit it to
            treat the whole day as one slot.

        Returns
        -------
        SequencingResult
            Capped production, machine role, the first violation reason (``unknown_role``,
            ``forbidden_role``, ``missing_prereq``) and whether the block completed.
        """

        self._roll_slot(day, shift_id)

        bundle = self.ctx.bundle
        machine_roles = bundle.machine_roles
        allowed_roles = self.ctx.allowed_roles
        prereq_roles = self.ctx.prereq_roles

        role = machine_roles.get(machine_id)
        allowed = allowed_roles.get(block_id)
        violation_reason: str | None = None
        if allowed is not None:
            if role is None:
                violation_reason = "unknown_role"
            elif role not in allowed:
                violation_reason = "forbidden_role"

        prereq_set = prereq_roles.get((block_id, role)) if role is not None else None
        # Idle slot (no planned production): thresholds only bind a producing role (#125).
        idle = proposed_production <= SEQUENCING_TOLERANCE

        if prereq_set and not idle:
            assert role is not None
            buffer_volume = self.ctx.role_headstart_volume.get((block_id, role), 0.0)
            if buffer_volume > 0.0 and not self._upstream_exhausted(block_id, prereq_set):
                start_volume = self._slot_start_volume(block_id, prereq_set)
                if start_volume + SEQUENCING_TOLERANCE < buffer_volume:
                    violation_reason = violation_reason or "missing_prereq"
                    self._record_violation(
                        block_id,
                        role,
                        "missing_prereq",
                        day,
                        {
                            "available_volume": float(start_volume),
                            "buffer_requirement": float(buffer_volume),
                            "headstart_deficit": float(buffer_volume - start_volume),
                            "reason": "headstart",
                        },
                    )

        production_units = max(proposed_production, 0.0)
        explicit_block = block_id in self.ctx.blocks_with_explicit_system
        target_key = (block_id, role) if role is not None else None
        target_remaining = self.remaining_work.get(block_id, 0.0)
        if target_key and target_key in self.role_remaining:
            target_remaining = min(
                target_remaining, self.role_remaining.get(target_key, target_remaining)
            )
        production_units = min(production_units, target_remaining)

        if prereq_set and explicit_block:
            available_volume = min(
                self.role_inventory[(block_id, upstream_role)] for upstream_role in prereq_set
            )
            loader_requirement = 0.0
            if (block_id, role) in self.ctx.loader_roles and not idle:
                loader_requirement = min(
                    self.ctx.loader_batch_volume.get(block_id, 0.0),
                    self.remaining_work.get(block_id, 0.0),
                )
            shortfall: tuple[float, float] | None = None
            if available_volume + SEQUENCING_TOLERANCE < production_units:
                shortfall = (available_volume, production_units)
            elif loader_requirement > 0.0:
                # The truckload threshold applies to the volume staged at the start of the slot
                # (E8 compares I(prev(s)) with the loader batch), not to what other machines of
                # the same role have left in this slot.
                start_volume = self._slot_start_volume(block_id, prereq_set)
                if start_volume + SEQUENCING_TOLERANCE < loader_requirement:
                    shortfall = (start_volume, loader_requirement)
            if shortfall is not None:
                violation_reason = violation_reason or "missing_prereq"
                self._record_violation(
                    block_id,
                    role,
                    "missing_prereq",
                    day,
                    {
                        "available_volume": float(shortfall[0]),
                        "required_volume": float(shortfall[1]),
                        "reason": "inventory",
                    },
                )
            production_units = min(production_units, available_volume)
            for upstream_role in prereq_set:
                key = (block_id, upstream_role)
                consumed = min(production_units, self.role_inventory.get(key, 0.0))
                self.role_inventory[key] = max(
                    0.0, self.role_inventory.get(key, 0.0) - production_units
                )
                self.role_consumed_slot[key] += consumed

        if explicit_block and role is not None:
            self.role_inventory_today[(block_id, role)] += production_units

        if role is not None:
            self.role_counts_day[(block_id, role)] += 1

        deliverable = False
        if block_id not in self.ctx.blocks_with_explicit_system:
            deliverable = True
        elif role is None:
            deliverable = True
        elif self._is_terminal_role(block_id, role):
            deliverable = True
        if deliverable and production_units > 0:
            self.delivered_total += production_units

        if target_key and target_key in self.role_remaining:
            self.role_remaining[target_key] = max(
                0.0, self.role_remaining[target_key] - production_units
            )

        if self._is_terminal_role(block_id, role) or not target_key:
            if block_id in self.remaining_work:
                self.remaining_work[block_id] = max(
                    0.0, self.remaining_work[block_id] - production_units
                )
        block_completed = False
        if (
            block_id in self.remaining_work
            and self.remaining_work[block_id] <= BLOCK_EPSILON
            and block_id not in self.completed_blocks
        ):
            block_completed = True
            self.completed_blocks.add(block_id)

        return SequencingResult(
            production_units=production_units,
            machine_role=role,
            violation_reason=violation_reason,
            block_completed=block_completed,
        )

    def _slot_start_volume(self, block_id: str, prereq_set: frozenset[str]) -> float:
        """Staged upstream volume available at the start of the current slot (min over roles)."""

        return min(
            self.role_inventory[(block_id, upstream_role)]
            + self.role_consumed_slot.get((block_id, upstream_role), 0.0)
            for upstream_role in prereq_set
        )

    def _upstream_exhausted(self, block_id: str, prereq_set: frozenset[str]) -> bool:
        """``True`` when every upstream role finished its volume before the current slot (E8 waiver).

        Output staged by an upstream role in the current slot (``role_inventory_today``) is added
        back, so finishing the block in the same slot does not waive the head start: the MILP's
        ``upstream_done`` indicator uses cumulative output up to the previous slot.
        """

        return all(
            self.role_remaining.get((block_id, upstream_role), 0.0)
            + self.role_inventory_today.get((block_id, upstream_role), 0.0)
            <= SEQUENCING_TOLERANCE
            for upstream_role in prereq_set
        )

    def _record_violation(
        self,
        block_id: str,
        role: str | None,
        reason: str,
        day: int,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.debug_violation_counts[reason] += 1
        if self.debug_first_violation_reason is not None:
            return
        self.debug_first_violation_reason = reason
        self.debug_first_violation_role = role
        self.debug_first_violation_block = block_id
        self.debug_first_violation_day = day
        if detail:
            self.debug_first_violation_detail = dict(detail)

    def debug_snapshot(self) -> dict[str, Any]:
        """Aggregate sequencing debug metrics for watch/telemetry surfaces."""

        stats: dict[str, Any] = {}
        violation_total = int(sum(self.debug_violation_counts.values()))
        stats["sequencing_violation_count"] = violation_total
        if self.debug_violation_counts:
            stats["sequencing_violation_breakdown"] = dict(self.debug_violation_counts)
        if self.debug_first_violation_role:
            stats["sequencing_first_violation_role"] = self.debug_first_violation_role
        if self.debug_first_violation_reason:
            stats["sequencing_first_violation_reason"] = self.debug_first_violation_reason
        if self.debug_first_violation_block:
            stats["sequencing_first_violation_block"] = self.debug_first_violation_block
        if self.debug_first_violation_day is not None:
            stats["sequencing_first_violation_day"] = self.debug_first_violation_day
        if self.debug_first_violation_detail:
            for key, value in self.debug_first_violation_detail.items():
                stats[f"sequencing_first_violation_{key}"] = value
        role_inventory_totals: dict[str, float] = defaultdict(float)
        for (block, role), volume in self.role_inventory.items():
            if role:
                role_inventory_totals[role] += float(volume)
        if role_inventory_totals:
            stats["role_inventory_totals"] = dict(sorted(role_inventory_totals.items()))
        role_remaining_totals: dict[str, float] = defaultdict(float)
        for (block, role), remaining in self.role_remaining.items():
            if role:
                role_remaining_totals[role] += float(remaining)
        if role_remaining_totals:
            stats["role_remaining_totals"] = dict(sorted(role_remaining_totals.items()))
        stats["completed_blocks"] = len(self.completed_blocks)
        stats["remaining_work_total"] = sum(self.remaining_work.values())
        stats["delivered_total"] = float(self.delivered_total)
        if violation_total == 0:
            stats["sequencing_status"] = "clean"
        return stats

    def _is_terminal_role(self, block_id: str, role: str | None) -> bool:
        if block_id not in self.ctx.blocks_with_explicit_system:
            return True
        if role is None:
            return True
        system_id = self.ctx.bundle.block_system.get(block_id)
        if system_id is None:
            return True
        terminal = self.ctx.terminal_roles.get(system_id)
        if not terminal:
            return True
        return role in terminal


def build_sequencing_tracker(problem: Problem) -> SequencingTracker:
    """Create a sequencing tracker for the supplied problem.

    Parameters
    ----------
    problem:
        Problem whose scenario (including any ``initial_state``) seeds the tracker state.

    Returns
    -------
    SequencingTracker
        Fresh tracker; see :class:`SequencingTracker` for the initial-state seeding rules.
    """

    ctx = build_operational_problem(problem)
    return SequencingTracker(ctx=ctx)


def build_role_order_lookup(ctx: OperationalProblem) -> dict[tuple[str, str], int]:
    """Map (block, role) pairs to their order within each harvest system."""

    order_lookup: dict[tuple[str, str], int] = {}
    for block_id, system_id in ctx.bundle.block_system.items():
        system = ctx.bundle.systems.get(system_id)
        if system is None:
            continue
        for idx, role_cfg in enumerate(system.roles):
            role = role_cfg.role
            if role:
                order_lookup[(block_id, role)] = idx
    return order_lookup


def build_role_priority(ctx: OperationalProblem) -> dict[str, int]:
    """Return a scenario-wide role ordering derived from harvest systems."""

    priority: dict[str, int] = {}
    for system in ctx.bundle.systems.values():
        for idx, role_cfg in enumerate(system.roles):
            role = role_cfg.role
            if not role:
                continue
            priority[role] = min(priority.get(role, idx), idx)
    return priority
