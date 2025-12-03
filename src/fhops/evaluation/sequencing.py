"""Shared sequencing tracker for KPI + playback enforcement."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from fhops.optimization.operational_problem import OperationalProblem, build_operational_problem
from fhops.scenario.contract import Problem

BLOCK_EPSILON = 1e-6


@dataclass(slots=True)
class SequencingResult:
    """Outcome for a single machine/shift assignment."""

    production_units: float
    machine_role: str | None
    violation_reason: str | None
    block_completed: bool


@dataclass(slots=True)
class SequencingTracker:
    """Tracks staged volume and sequencing feasibility as playback iterates."""

    ctx: OperationalProblem
    debug: bool = False
    remaining_work: dict[str, float] = field(init=False)
    role_inventory: defaultdict[tuple[str, str], float] = field(init=False)
    role_inventory_today: defaultdict[tuple[str, str], float] = field(init=False)
    role_remaining: dict[tuple[str, str], float] = field(init=False)
    role_counts_total: defaultdict[tuple[str, str], int] = field(init=False)
    role_counts_day: defaultdict[tuple[str, str], int] = field(init=False)
    completed_blocks: set[str] = field(init=False)
    debug_violation_counts: Counter[str] = field(init=False)
    debug_first_violation_role: str | None = field(default=None, init=False)
    debug_first_violation_reason: str | None = field(default=None, init=False)
    debug_first_violation_block: str | None = field(default=None, init=False)
    debug_first_violation_day: int | None = field(default=None, init=False)
    debug_first_violation_detail: dict[str, Any] | None = field(default=None, init=False)
    _current_day: int | None = field(default=None, init=False)
    delivered_total: float = field(init=False)

    def __post_init__(self) -> None:
        self.remaining_work = dict(self.ctx.bundle.work_required)
        self.role_inventory = defaultdict(float)
        self.role_inventory_today = defaultdict(float)
        self.role_remaining = dict(self.ctx.role_work_required)
        self.role_counts_total = defaultdict(int)
        self.role_counts_day = defaultdict(int)
        self.completed_blocks = set()
        self.debug_violation_counts = Counter()
        self.delivered_total = 0.0

    def _roll_day(self, day: int) -> None:
        if self._current_day is None or day == self._current_day:
            self._current_day = day
            return
        for key, volume in self.role_inventory_today.items():
            self.role_inventory[key] += volume
        self.role_inventory_today.clear()
        for key, count in self.role_counts_day.items():
            self.role_counts_total[key] += count
        self.role_counts_day.clear()
        self._current_day = day

    def finalize(self) -> None:
        """Flush any remaining day counters (call once after iterating assignments)."""

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
    ) -> SequencingResult:
        """Advance the sequencing state for a single assignment."""

        self._roll_day(day)

        bundle = self.ctx.bundle
        machine_roles = bundle.machine_roles
        allowed_roles = self.ctx.allowed_roles
        prereq_roles = self.ctx.prereq_roles
        role_headstarts = self.ctx.role_headstarts

        role = machine_roles.get(machine_id)
        allowed = allowed_roles.get(block_id)
        violation_reason: str | None = None
        if allowed is not None:
            if role is None:
                violation_reason = "unknown_role"
            elif role not in allowed:
                violation_reason = "forbidden_role"

        prereq_set = prereq_roles.get((block_id, role)) if role is not None else None

        if prereq_set:
            assert role is not None
            role_key = (block_id, role)
            buffer = role_headstarts.get((block_id, role), 0.0)
            if buffer > 0.0:
                available_units = min(
                    self.role_counts_total[(block_id, prereq)] for prereq in prereq_set
                )
                required_buffer = self.role_counts_total[role_key] + buffer
                if available_units + 1e-9 < required_buffer:
                    violation_reason = violation_reason or "missing_prereq"
                    self._record_violation(
                        block_id,
                        role,
                        "missing_prereq",
                        day,
                        {
                            "available_units": float(available_units),
                            "buffer_requirement": float(required_buffer),
                            "headstart_deficit": float(required_buffer - available_units),
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
            if (block_id, role) in self.ctx.loader_roles:
                loader_requirement = min(
                    self.ctx.loader_batch_volume.get(block_id, 0.0),
                    self.remaining_work.get(block_id, 0.0),
                )
            required_volume = production_units
            if loader_requirement > 0.0:
                required_volume = max(required_volume, loader_requirement)
            if available_volume + 1e-9 < required_volume:
                violation_reason = violation_reason or "missing_prereq"
                self._record_violation(
                    block_id,
                    role,
                    "missing_prereq",
                    day,
                    {
                        "available_volume": float(available_volume),
                        "required_volume": float(required_volume),
                        "reason": "inventory",
                    },
                )
            production_units = min(production_units, available_volume)
            for upstream_role in prereq_set:
                key = (block_id, upstream_role)
                self.role_inventory[key] = max(
                    0.0, self.role_inventory.get(key, 0.0) - production_units
                )

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
    """Create a sequencing tracker for the supplied problem."""

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
