"""Shared sequencing tracker for KPI + playback enforcement."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

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
    remaining_work: dict[str, float] = field(init=False)
    role_inventory: defaultdict[tuple[str, str], float] = field(init=False)
    role_counts_total: defaultdict[tuple[str, str], int] = field(init=False)
    role_counts_day: defaultdict[tuple[str, str], int] = field(init=False)
    completed_blocks: set[str] = field(init=False)
    _current_day: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.remaining_work = dict(self.ctx.bundle.work_required)
        self.role_inventory = defaultdict(float)
        self.role_counts_total = defaultdict(int)
        self.role_counts_day = defaultdict(int)
        self.completed_blocks = set()

    def _roll_day(self, day: int) -> None:
        if self._current_day is None or day == self._current_day:
            self._current_day = day
            return
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
            available_units = min(
                self.role_counts_total[(block_id, prereq)] for prereq in prereq_set
            )
            required_units = self.role_counts_total[role_key] + self.role_counts_day[role_key] + 1
            if available_units < required_units:
                violation_reason = violation_reason or "missing_prereq"
            buffer = role_headstarts.get((block_id, role), 0.0)
            if buffer > 0.0:
                required_buffer = self.role_counts_total[role_key] + buffer
                if available_units + 1e-9 < required_buffer:
                    violation_reason = violation_reason or "missing_prereq"

        production_units = max(proposed_production, 0.0)
        explicit_block = block_id in self.ctx.blocks_with_explicit_system

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
            production_units = min(production_units, available_volume)
            for upstream_role in prereq_set:
                key = (block_id, upstream_role)
                self.role_inventory[key] = max(
                    0.0, self.role_inventory.get(key, 0.0) - production_units
                )

        if explicit_block and role is not None:
            self.role_inventory[(block_id, role)] += production_units

        if role is not None:
            self.role_counts_day[(block_id, role)] += 1

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
