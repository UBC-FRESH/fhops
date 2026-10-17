"""Operational MILP data bundle helpers.

The bundle is the solver-agnostic, JSON-serialisable snapshot of a :class:`Problem` consumed by the
operational MILP builder (:mod:`fhops.model.milp.operational`), the shared heuristic context
(:mod:`fhops.optimization.operational_problem`), and the ``fhops solve-mip-operational
--dump-bundle/--bundle-json`` CLI round trip.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from fhops.costing.machine_rates import normalize_machine_role
from fhops.scenario.contract import Problem
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scheduling.mobilisation import build_distance_lookup
from fhops.scheduling.systems import HarvestSystem, SystemJob, default_system_registry

ShiftKey = tuple[int, str]
MachineBlock = tuple[str, str]
BlockRole = tuple[str, str]
LockEntry = tuple[str, str, int, str | None]

DEFAULT_TRUCKLOAD_M3 = 30.0


@dataclass(frozen=True)
class SystemRoleConfig:
    """Description of a single role within a harvest system."""

    job_name: str
    role: str
    prerequisites: tuple[str, ...]
    upstream_roles: tuple[str, ...]
    buffer_shifts: float = 0.0
    is_loader: bool = False
    count: int = 1


@dataclass(frozen=True)
class SystemConfig:
    """Harvest system metadata required by the operational MILP."""

    system_id: str
    roles: tuple[SystemRoleConfig, ...]
    loader_batch_volume_m3: float = DEFAULT_TRUCKLOAD_M3


@dataclass(frozen=True)
class OperationalMilpBundle:
    """Normalized data extracted from a :class:`Problem` for MILP construction.

    Attributes
    ----------
    machines, blocks, days, shifts:
        Index sets (shift slots are ``(day, shift_id)`` tuples in solver order).
    machine_roles, machine_daily_hours, production_rates, work_required, windows,
    landing_for_block, landing_capacity, availability_day, availability_shift,
    objective_weights, block_system, systems, mobilisation_params, mobilisation_distances:
        Normalised scenario data (see :func:`build_operational_bundle`).
    locked_assignments:
        Tuple of ``(machine_id, block_id, day, shift_id | None)`` locks copied from
        ``Scenario.locked_assignments``. ``shift_id=None`` locks every available shift of the day.
        Empty by default.
    initial_staged_inventory:
        ``(block_id, role) -> m³`` output by ``role`` on the block but not yet consumed downstream
        (from ``Scenario.initial_state``). Empty by default (v1.0.0: inventories start at zero).
    initial_role_remaining:
        ``(block_id, role) -> m³`` the role may still output. Empty by default (each role may
        output the full ``work_required``).
    initial_role_shift_counts:
        ``(block_id, role) -> shifts`` already worked (head-start accounting). Empty by default.
    initial_machine_block:
        ``machine_id -> block_id`` occupied in the last worked slot before the horizon. Empty by
        default (first move is free).
    blackout_slots:
        Sorted ``(machine_id, day, shift_id)`` slots blocked by ``Scenario.timeline`` blackout
        windows (:func:`build_blackout_slots`). The operational MILP sets availability
        ``A_{m,s} = 0`` for them and the heuristics skip them. Empty without blackouts (and for
        bundles serialised before this field existed).
    unsequenced_blocks:
        Blocks without an explicit ``harvest_system_id``. They carry no sequencing obligations
        (any machine may work them and every machine's output counts towards ``work_required``),
        matching the heuristics and the playback sequencing tracker. ``block_system`` still maps
        them to the default system for role-order lookups. Empty for bundles serialised before
        this field existed (every block is then treated as sequenced).

    Notes
    -----
    ``work_required`` (block → terminal delivered volume) and ``production_rates``
    ((machine, block) → volume per shift assignment) are both in m³, matching
    ``SystemConfig.loader_batch_volume_m3``.
    """

    machines: tuple[str, ...]
    blocks: tuple[str, ...]
    days: tuple[int, ...]
    shifts: tuple[ShiftKey, ...]
    machine_roles: dict[str, str | None]
    machine_daily_hours: dict[str, float]
    production_rates: dict[MachineBlock, float]
    work_required: dict[str, float]
    windows: dict[str, tuple[int, int]]
    landing_for_block: dict[str, str]
    landing_capacity: dict[str, int]
    availability_day: dict[tuple[str, int], int]
    availability_shift: dict[tuple[str, int, str], int]
    objective_weights: ObjectiveWeights
    block_system: dict[str, str]
    systems: dict[str, SystemConfig]
    mobilisation_params: dict[str, dict[str, float]]
    mobilisation_distances: dict[tuple[str, str], float]
    locked_assignments: tuple[LockEntry, ...] = ()
    initial_staged_inventory: dict[BlockRole, float] = field(default_factory=dict)
    initial_role_remaining: dict[BlockRole, float] = field(default_factory=dict)
    initial_role_shift_counts: dict[BlockRole, int] = field(default_factory=dict)
    initial_machine_block: dict[str, str] = field(default_factory=dict)
    unsequenced_blocks: tuple[str, ...] = ()
    blackout_slots: tuple[tuple[str, int, str], ...] = ()

    def has_initial_state(self) -> bool:
        """Return ``True`` when any initial-state mapping is non-empty."""
        return bool(
            self.initial_staged_inventory
            or self.initial_role_remaining
            or self.initial_role_shift_counts
            or self.initial_machine_block
        )


def ordered_shift_keys(pb: Problem) -> tuple[tuple[int, str], ...]:
    """Return the problem's ``(day, shift_id)`` slots in chronological order.

    Parameters
    ----------
    pb:
        Problem whose ``shifts`` define the slot grid.

    Returns
    -------
    tuple[tuple[int, str], ...]
        Unique slots sorted by day; shifts within a day keep their ``Problem.shifts`` order (the
        ``timeline.shifts`` definition order, or ``shift_id`` order for shift calendars). The
        operational MILP (``prev(s)``), the heuristics, and playback all use this order, so a
        shift defined first is worked first even when its label sorts later (e.g. ``night`` before
        ``day``).
    """

    seen: set[tuple[int, str]] = set()
    keys: list[tuple[int, str]] = []
    for shift in sorted(pb.shifts, key=lambda s: s.day):
        key = (shift.day, shift.shift_id)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return tuple(keys)


def build_blackout_slots(pb: Problem) -> tuple[tuple[str, int, str], ...]:
    """Return the ``(machine_id, day, shift_id)`` slots blocked by timeline blackouts.

    Parameters
    ----------
    pb:
        Problem whose ``scenario.timeline.blackouts`` define the blocked days.

    Returns
    -------
    tuple[tuple[str, int, str], ...]
        Sorted slots. Every day of every ``BlackoutWindow`` (``start_day``..``end_day``,
        inclusive) blocks **every machine** (blackouts are fleet-wide, not per landing) in every
        slot of the problem's shift grid on that day (``pb.shifts``) plus the machine's own
        ``shift_calendar`` shifts for that day. Days without grid slots and calendar entries fall
        back to every ``timeline.shifts`` name, otherwise ``S1``. Empty when the scenario has no
        blackouts.

    Notes
    -----
    Shared by the operational MILP (availability ``A_{m,s} = 0``) and the heuristics
    (:attr:`fhops.optimization.operational_problem.OperationalProblem.blackout_shifts`), so both
    solver families block exactly the same slots. Playback does not cancel work in blackouts; it
    flags it (``PlaybackRecord.blackout_hit``).

    Until 1.0.1 (#115) a machine without ``shift_calendar`` entries on a blackout day was blocked
    only in the ``timeline.shifts`` names (or ``S1``) even when the grid came from other machines'
    shift calendars, so it could still work the blackout day. Including the grid slots makes the
    blackout fleet-wide on every grid; for scenarios whose machines all have calendar entries on
    the grid (or no shift calendar at all) the slot set is unchanged.
    """

    scenario = pb.scenario
    timeline = scenario.timeline
    if not timeline or not timeline.blackouts:
        return ()
    blackout: set[tuple[str, int, str]] = set()
    shift_lookup: dict[tuple[str, int], list[str]] = {}
    if scenario.shift_calendar:
        for entry in scenario.shift_calendar:
            shift_lookup.setdefault((entry.machine_id, entry.day), []).append(entry.shift_id)
    grid_by_day: dict[int, list[str]] = {}
    for day, shift_id in ordered_shift_keys(pb):
        grid_by_day.setdefault(day, []).append(shift_id)
    timeline_shift_ids = [shift_def.name for shift_def in timeline.shifts or []]
    fallback_shifts = timeline_shift_ids or ["S1"]
    for window in timeline.blackouts:
        for day in range(window.start_day, window.end_day + 1):
            grid_shifts = grid_by_day.get(day, [])
            for machine in scenario.machines:
                keys = list(shift_lookup.get((machine.id, day), [])) + grid_shifts
                for shift_id in keys or fallback_shifts:
                    blackout.add((machine.id, day, shift_id))
    return tuple(sorted(blackout))


def machine_slot_available(
    bundle: OperationalMilpBundle,
    machine_id: str,
    day: int,
    shift_id: str,
    blackout_slots: frozenset[tuple[str, int, str]] | None = None,
) -> bool:
    """Return the operational MILP availability ``A_{m,s}`` of a machine in a shift slot.

    Parameters
    ----------
    bundle:
        Operational bundle (uses ``availability_shift``, ``availability_day`` and
        ``blackout_slots``).
    machine_id, day, shift_id:
        Machine and ``(day, shift_id)`` slot.
    blackout_slots:
        Optional pre-built ``frozenset(bundle.blackout_slots)`` (avoids rebuilding it per call).

    Returns
    -------
    bool
        ``False`` in timeline blackout slots; otherwise the shift-calendar flag when the slot has
        one, else the day-calendar flag (default available).
    """

    blocked = blackout_slots if blackout_slots is not None else frozenset(bundle.blackout_slots)
    if (machine_id, day, shift_id) in blocked:
        return False
    flag = bundle.availability_shift.get((machine_id, day, shift_id))
    if flag is not None:
        return flag == 1
    return bundle.availability_day.get((machine_id, day), 1) == 1


def resolve_locked_slots(
    bundle: OperationalMilpBundle,
) -> tuple[dict[tuple[str, ShiftKey], str | None], tuple[str, ...]]:
    """Resolve ``bundle.locked_assignments`` into per-slot lock targets for the operational MILP.

    Parameters
    ----------
    bundle:
        Operational bundle with ``locked_assignments``.

    Returns
    -------
    tuple[dict, tuple[str, ...]]
        ``(targets, warnings)``. ``targets`` maps ``(machine_id, (day, shift_id))`` to the locked
        block (the MILP fixes ``x = 1`` there and ``x = 0`` on every other block) or to ``None``
        (the machine is pinned to ``x = 0`` on every block in that slot). A day lock
        (``shift_id=None``) covers every slot of its day; a shift lock only its slot.

        Pinned to ``None``:

        * slots where the machine is unavailable (calendar or timeline blackout), silently, as
          documented for day locks spanning unavailable shifts;
        * locks that contradict the model (block outside its window on that day, or a machine
          whose role is not part of the block's harvest system), with a warning;

        Skipped with a warning: locks naming an unknown machine/block, locks that match no slot
        of the grid, and a second lock on an already locked ``(machine, slot)`` (the first lock
        wins). Scenario validation rejects these cases for scenarios built through
        :class:`fhops.scenario.contract.Scenario`; the MILP resolves them so that a lock never
        makes the model infeasible.

    Notes
    -----
    Shared by the model builder (``locked_assignment`` constraints) and the warm-start overlay in
    :mod:`fhops.model.milp.driver`, so seeded incumbents respect exactly the same locks.
    """

    targets: dict[tuple[str, ShiftKey], str | None] = {}
    warnings_out: list[str] = []
    if not bundle.locked_assignments:
        return targets, ()
    machines = set(bundle.machines)
    blocks = set(bundle.blocks)
    unsequenced = set(bundle.unsequenced_blocks)
    blackout = frozenset(bundle.blackout_slots)
    for machine_id, block_id, lock_day, lock_shift in bundle.locked_assignments:
        label = f"lock ({machine_id}, {block_id}, day {lock_day}, shift {lock_shift or '*'})"
        if machine_id not in machines or block_id not in blocks:
            warnings_out.append(f"{label} ignored: unknown machine or block")
            continue
        slots = [
            slot
            for slot in bundle.shifts
            if slot[0] == lock_day and (lock_shift is None or slot[1] == lock_shift)
        ]
        if not slots:
            warnings_out.append(f"{label} ignored: no matching slot in the shift grid")
            continue
        earliest, latest = bundle.windows.get(block_id, (lock_day, lock_day))
        contradiction: str | None = None
        if not earliest <= lock_day <= latest:
            contradiction = f"day {lock_day} is outside the block window {earliest}-{latest}"
        elif block_id not in unsequenced:
            system = bundle.systems.get(bundle.block_system.get(block_id, ""))
            role = bundle.machine_roles.get(machine_id)
            system_roles = {cfg.role for cfg in system.roles} if system is not None else set()
            if not role or role not in system_roles:
                contradiction = (
                    f"machine role {role!r} is not part of the block's harvest system "
                    f"{bundle.block_system.get(block_id)!r}"
                )
        if contradiction is not None:
            warnings_out.append(f"{label} pinned to x=0: {contradiction}")
        for slot in slots:
            key = (machine_id, slot)
            if key in targets:
                if targets[key] != block_id:
                    warnings_out.append(
                        f"{label} ignored for slot {slot}: machine already locked to "
                        f"{targets[key]!r}"
                    )
                continue
            available = machine_slot_available(bundle, machine_id, slot[0], slot[1], blackout)
            targets[key] = block_id if available and contradiction is None else None
    return targets, tuple(warnings_out)


def build_operational_bundle(pb: Problem) -> OperationalMilpBundle:
    """Construct an :class:`OperationalMilpBundle` from a :class:`Problem`.

    Parameters
    ----------
    pb:
        Problem produced by :meth:`fhops.scenario.contract.Problem.from_scenario`.

    Returns
    -------
    OperationalMilpBundle
        Normalised bundle. ``Scenario.locked_assignments`` are copied into
        ``locked_assignments`` and ``Scenario.initial_state`` (when present) is flattened into the
        ``initial_*`` mappings keyed by ``(block_id, role)`` / ``machine_id``. Without locks or
        initial state those fields are empty and the bundle is identical to the v1.0.0 bundle.
    """

    sc = pb.scenario
    machines = tuple(machine.id for machine in sc.machines)
    blocks = tuple(block.id for block in sc.blocks)
    days = tuple(pb.days)
    shifts = ordered_shift_keys(pb)

    machine_roles = {machine.id: machine.role for machine in sc.machines}
    machine_daily_hours = {machine.id: machine.daily_hours for machine in sc.machines}
    production_rates = {(rate.machine_id, rate.block_id): rate.rate for rate in sc.production_rates}
    work_required = {block.id: block.work_required for block in sc.blocks}
    windows = {block.id: sc.window_for(block.id) for block in sc.blocks}
    landing_for_block = {block.id: block.landing_id for block in sc.blocks}
    landing_capacity = {landing.id: landing.daily_capacity for landing in sc.landings}

    availability_day: dict[tuple[str, int], int] = {}
    for day_entry in sc.calendar:
        availability_day[(day_entry.machine_id, day_entry.day)] = int(day_entry.available)
    availability_shift: dict[tuple[str, int, str], int] = {}
    if sc.shift_calendar:
        for shift_entry in sc.shift_calendar:
            availability_shift[(shift_entry.machine_id, shift_entry.day, shift_entry.shift_id)] = (
                int(shift_entry.available)
            )

    objective_weights = sc.objective_weights or ObjectiveWeights()
    mobilisation_params: dict[str, dict[str, float]] = {}
    mobilisation_distances: dict[tuple[str, str], float] = {}
    if sc.mobilisation:
        mobilisation_distances = build_distance_lookup(sc.mobilisation)
        for param in sc.mobilisation.machine_params:
            mobilisation_params[param.machine_id] = {
                "walk_cost_per_meter": param.walk_cost_per_meter,
                "move_cost_flat": param.move_cost_flat,
                "walk_threshold_m": param.walk_threshold_m,
                "setup_cost": param.setup_cost,
            }
    registry = sc.harvest_systems or dict(default_system_registry())
    system_configs = _build_system_configs(registry.values())
    default_system_id = next(iter(system_configs))
    default_registry = dict(default_system_registry())
    block_system: dict[str, str] = {}
    for block in sc.blocks:
        system_id = block.harvest_system_id or default_system_id
        if system_id not in system_configs:
            harvest_system = registry.get(system_id) or default_registry.get(system_id)
            if harvest_system is not None:
                system_configs[system_id] = _build_system_configs([harvest_system])[system_id]
            else:
                system_configs[system_id] = SystemConfig(
                    system_id=system_id,
                    roles=tuple(),
                    loader_batch_volume_m3=DEFAULT_TRUCKLOAD_M3,
                )
        block_system[block.id] = system_id

    locked_assignments: tuple[LockEntry, ...] = tuple(
        (lock.machine_id, lock.block_id, int(lock.day), lock.shift_id)
        for lock in (sc.locked_assignments or [])
    )
    initial_staged_inventory: dict[BlockRole, float] = {}
    initial_role_remaining: dict[BlockRole, float] = {}
    initial_role_shift_counts: dict[BlockRole, int] = {}
    initial_machine_block: dict[str, str] = {}
    if sc.initial_state is not None:
        for block_state in sc.initial_state.blocks:
            for role, volume in block_state.staged_inventory.items():
                initial_staged_inventory[(block_state.block_id, role)] = float(volume)
            for role, volume in block_state.role_remaining.items():
                initial_role_remaining[(block_state.block_id, role)] = float(volume)
            for role, count in block_state.role_shift_counts.items():
                initial_role_shift_counts[(block_state.block_id, role)] = int(count)
        initial_machine_block = sc.initial_state.last_block_by_machine()
    unsequenced_blocks = tuple(block.id for block in sc.blocks if not block.harvest_system_id)
    blackout_slots = build_blackout_slots(pb)

    return OperationalMilpBundle(
        machines=machines,
        blocks=blocks,
        days=days,
        shifts=shifts,
        machine_roles=machine_roles,
        machine_daily_hours=machine_daily_hours,
        production_rates=production_rates,
        work_required=work_required,
        windows=windows,
        landing_for_block=landing_for_block,
        landing_capacity=landing_capacity,
        availability_day=availability_day,
        availability_shift=availability_shift,
        objective_weights=objective_weights,
        block_system=block_system,
        systems=system_configs,
        mobilisation_params=mobilisation_params,
        mobilisation_distances=mobilisation_distances,
        locked_assignments=locked_assignments,
        initial_staged_inventory=initial_staged_inventory,
        initial_role_remaining=initial_role_remaining,
        initial_role_shift_counts=initial_role_shift_counts,
        initial_machine_block=initial_machine_block,
        unsequenced_blocks=unsequenced_blocks,
        blackout_slots=blackout_slots,
    )


def headstart_buffer_volumes(bundle: OperationalMilpBundle) -> dict[BlockRole, float]:
    """Return the head-start buffer volume ``B_{r,b}`` (m³) of every buffered role-block pair.

    Parameters
    ----------
    bundle:
        Operational bundle; uses ``block_system``, ``systems``, ``machine_roles`` and
        ``production_rates``.

    Returns
    -------
    dict[tuple[str, str], float]
        ``(block_id, role) -> m³`` for roles with ``buffer_shifts > 0`` and at least one upstream
        role. ``B = buffer_shifts × Σ`` rates (m³ per shift) of every machine of **all** upstream
        roles on the block; when no upstream machine has a positive rate, the role's own fleet rate
        (or 1.0) is used instead. Loader truckload thresholds are **not** included: a buffered
        loader must satisfy the head-start constraint and the separate truckload threshold
        (``loader_threshold``), i.e. the larger of ``B`` and ``min(q_batch, remaining volume)``.

    Notes
    -----
    The operational MILP (head-start constraint E8) and the sequencing tracker / heuristics share
    this helper, so a MILP plan and its playback apply the same buffer volume. For a role with
    several upstream roles (a join) the single value ``B`` -- computed from the *summed* upstream
    rates -- must be staged by **each** upstream role (the MILP has one ``head_start`` row per
    upstream role; the tracker compares the minimum staged volume with ``B``). A slower upstream
    role therefore needs more than ``buffer_shifts`` shifts to build its share of the buffer
    (e.g. rates 10 and 30 m³/shift with one head-start shift: each must stage 40 m³, four shifts
    of the slower role); see ``docs/howto/system_sequencing.rst``.
    """

    role_to_machines: dict[str, list[str]] = {}
    for machine_id, role in bundle.machine_roles.items():
        if role:
            role_to_machines.setdefault(role, []).append(machine_id)
    volumes: dict[BlockRole, float] = {}
    for block in bundle.blocks:
        system_cfg = bundle.systems.get(bundle.block_system.get(block, ""))
        if system_cfg is None:
            continue
        for role_cfg in system_cfg.roles:
            if role_cfg.buffer_shifts <= 0 or not role_cfg.upstream_roles:
                continue
            cap = sum(
                bundle.production_rates.get((machine_id, block), 0.0)
                for machine_id in role_to_machines.get(role_cfg.role, [])
            )
            if cap <= 0:
                cap = 1.0
            upstream_capacity = 0.0
            for upstream_role in role_cfg.upstream_roles:
                for machine_id in role_to_machines.get(upstream_role, []):
                    upstream_capacity += bundle.production_rates.get((machine_id, block), 0.0)
            reference_capacity = upstream_capacity if upstream_capacity > 0 else cap
            volumes[(block, role_cfg.role)] = role_cfg.buffer_shifts * reference_capacity
    return volumes


def _build_system_configs(systems: Iterable[HarvestSystem]) -> dict[str, SystemConfig]:
    configs: dict[str, SystemConfig] = {}
    for system in systems:
        role_configs: list[SystemRoleConfig] = []
        role_by_job: dict[str, str] = {job.name: job.machine_role for job in system.jobs}
        role_counts = {
            role: max(1, int(count)) for role, count in (system.role_counts or {}).items()
        }
        role_buffers = {
            (normalize_machine_role(role) or role): float(value)
            for role, value in (system.role_headstart_shifts or {}).items()
        }
        loader_batch = (
            float(system.loader_batch_volume_m3)
            if system.loader_batch_volume_m3 is not None
            else DEFAULT_TRUCKLOAD_M3
        )
        for job in system.jobs:
            upstream_list: list[str] = []
            for prereq in job.prerequisites:
                role_value = role_by_job.get(prereq)
                if role_value:
                    upstream_list.append(role_value)
            upstream_roles = tuple(upstream_list)
            role_configs.append(
                SystemRoleConfig(
                    job_name=job.name,
                    role=job.machine_role,
                    prerequisites=tuple(job.prerequisites),
                    upstream_roles=upstream_roles,
                    buffer_shifts=role_buffers.get(job.machine_role, 0.0),
                    is_loader=_is_loader_job(job),
                    count=role_counts.get(job.machine_role, 1),
                )
            )
        configs[system.system_id] = SystemConfig(
            system_id=system.system_id,
            roles=tuple(role_configs),
            loader_batch_volume_m3=loader_batch,
        )
    return configs


def _is_loader_job(job: SystemJob) -> bool:
    role = job.machine_role or ""
    name = job.name.lower()
    return role == "loader" or "load" in name


def bundle_to_dict(bundle: OperationalMilpBundle) -> dict[str, Any]:
    """Serialize an :class:`OperationalMilpBundle` into a JSON-friendly dict.

    The optional ``locked_assignments``, ``unsequenced_blocks``, ``blackout_slots`` and
    ``initial_state`` keys are emitted only when non-empty, so dumps of scenarios whose blocks all name a harvest system and
    carry no locks or initial state are unchanged from v1.0.0.
    """

    payload: dict[str, Any] = {
        "machines": list(bundle.machines),
        "blocks": list(bundle.blocks),
        "days": list(bundle.days),
        "shifts": [{"day": day, "shift_id": shift_id} for day, shift_id in bundle.shifts],
        "machine_roles": bundle.machine_roles,
        "machine_daily_hours": bundle.machine_daily_hours,
        "production_rates": [
            {"machine_id": m, "block_id": b, "rate": rate}
            for (m, b), rate in bundle.production_rates.items()
        ],
        "work_required": bundle.work_required,
        "windows": {blk: list(window) for blk, window in bundle.windows.items()},
        "landing_for_block": bundle.landing_for_block,
        "landing_capacity": bundle.landing_capacity,
        "availability_day": [
            {"machine_id": mach, "day": day, "available": available}
            for (mach, day), available in bundle.availability_day.items()
        ],
        "availability_shift": [
            {"machine_id": mach, "day": day, "shift_id": shift, "available": available}
            for (mach, day, shift), available in bundle.availability_shift.items()
        ],
        "objective_weights": {
            "production": bundle.objective_weights.production,
            "mobilisation": bundle.objective_weights.mobilisation,
            "transitions": bundle.objective_weights.transitions,
            "landing_surplus": bundle.objective_weights.landing_surplus,
        },
        "block_system": bundle.block_system,
        "systems": {
            system_id: {
                "system_id": cfg.system_id,
                "loader_batch_volume_m3": cfg.loader_batch_volume_m3,
                "roles": [
                    {
                        "job_name": role_cfg.job_name,
                        "role": role_cfg.role,
                        "prerequisites": list(role_cfg.prerequisites),
                        "upstream_roles": list(role_cfg.upstream_roles),
                        "buffer_shifts": role_cfg.buffer_shifts,
                        "is_loader": role_cfg.is_loader,
                        "count": role_cfg.count,
                    }
                    for role_cfg in cfg.roles
                ],
            }
            for system_id, cfg in bundle.systems.items()
        },
        "mobilisation_params": bundle.mobilisation_params,
        "mobilisation_distances": [
            {"prev_block": prev, "next_block": nxt, "distance": dist}
            for (prev, nxt), dist in bundle.mobilisation_distances.items()
        ],
    }
    if bundle.locked_assignments:
        payload["locked_assignments"] = [
            {"machine_id": mach, "block_id": blk, "day": day, "shift_id": shift_id}
            for mach, blk, day, shift_id in bundle.locked_assignments
        ]
    if bundle.unsequenced_blocks:
        payload["unsequenced_blocks"] = list(bundle.unsequenced_blocks)
    if bundle.blackout_slots:
        payload["blackout_slots"] = [
            {"machine_id": mach, "day": day, "shift_id": shift_id}
            for mach, day, shift_id in bundle.blackout_slots
        ]
    if bundle.has_initial_state():

        def _block_role_rows(mapping: Mapping[BlockRole, float | int]) -> list[dict[str, Any]]:
            return [
                {"block_id": blk, "role": role, "value": value}
                for (blk, role), value in mapping.items()
            ]

        payload["initial_state"] = {
            "staged_inventory": _block_role_rows(bundle.initial_staged_inventory),
            "role_remaining": _block_role_rows(bundle.initial_role_remaining),
            "role_shift_counts": _block_role_rows(bundle.initial_role_shift_counts),
            "machine_block": dict(bundle.initial_machine_block),
        }
    return payload


def bundle_from_dict(payload: Mapping[str, Any]) -> OperationalMilpBundle:
    """Reconstruct an :class:`OperationalMilpBundle` from ``bundle_to_dict`` output.

    Payloads written by v1.0.0 (without ``locked_assignments``/``unsequenced_blocks``/
    ``blackout_slots``/``initial_state`` keys) load with empty locks, blackouts and initial state,
    and every block sequenced.
    """

    machines = tuple(payload["machines"])
    blocks = tuple(payload["blocks"])
    days = tuple(payload["days"])
    shifts = tuple((entry["day"], entry["shift_id"]) for entry in payload["shifts"])

    production_rates: dict[MachineBlock, float] = {
        (entry["machine_id"], entry["block_id"]): float(entry["rate"])
        for entry in payload["production_rates"]
    }
    availability_day = {
        (entry["machine_id"], int(entry["day"])): int(entry["available"])
        for entry in payload["availability_day"]
    }
    availability_shift = {
        (entry["machine_id"], int(entry["day"]), entry["shift_id"]): int(entry["available"])
        for entry in payload["availability_shift"]
    }

    systems = {
        system_id: SystemConfig(
            system_id=system_id,
            loader_batch_volume_m3=float(
                system_data.get("loader_batch_volume_m3", DEFAULT_TRUCKLOAD_M3)
            ),
            roles=tuple(
                SystemRoleConfig(
                    job_name=role_data["job_name"],
                    role=role_data["role"],
                    prerequisites=tuple(role_data.get("prerequisites", [])),
                    upstream_roles=tuple(role_data.get("upstream_roles", [])),
                    buffer_shifts=float(role_data.get("buffer_shifts", 0.0)),
                    is_loader=bool(role_data.get("is_loader", False)),
                    count=int(role_data.get("count", 1)),
                )
                for role_data in system_data.get("roles", [])
            ),
        )
        for system_id, system_data in payload["systems"].items()
    }

    mobilisation_distances = {
        (entry["prev_block"], entry["next_block"]): float(entry["distance"])
        for entry in payload.get("mobilisation_distances", [])
    }
    mobilisation_params = {
        machine_id: {
            "walk_cost_per_meter": values.get("walk_cost_per_meter", 0.0),
            "move_cost_flat": values.get("move_cost_flat", 0.0),
            "walk_threshold_m": values.get("walk_threshold_m", 0.0),
            "setup_cost": values.get("setup_cost", 0.0),
        }
        for machine_id, values in payload.get("mobilisation_params", {}).items()
    }
    locked_assignments: tuple[LockEntry, ...] = tuple(
        (
            str(entry["machine_id"]),
            str(entry["block_id"]),
            int(entry["day"]),
            None if entry.get("shift_id") is None else str(entry["shift_id"]),
        )
        for entry in payload.get("locked_assignments", [])
    )
    initial_payload = payload.get("initial_state") or {}

    def _block_role_map(key: str) -> dict[BlockRole, float]:
        return {
            (str(row["block_id"]), str(row["role"])): float(row["value"])
            for row in initial_payload.get(key, [])
        }

    return OperationalMilpBundle(
        machines=machines,
        blocks=blocks,
        days=days,
        shifts=shifts,
        machine_roles=dict(payload["machine_roles"]),
        machine_daily_hours={
            mach: float(hours) for mach, hours in payload["machine_daily_hours"].items()
        },
        production_rates=production_rates,
        work_required={blk: float(value) for blk, value in payload["work_required"].items()},
        windows={blk: (window[0], window[1]) for blk, window in payload["windows"].items()},
        landing_for_block=dict(payload["landing_for_block"]),
        landing_capacity={
            landing: int(cap) for landing, cap in payload["landing_capacity"].items()
        },
        availability_day=availability_day,
        availability_shift=availability_shift,
        objective_weights=ObjectiveWeights(
            production=float(payload["objective_weights"]["production"]),
            mobilisation=float(payload["objective_weights"]["mobilisation"]),
            transitions=float(payload["objective_weights"]["transitions"]),
            landing_surplus=float(payload["objective_weights"]["landing_surplus"]),
        ),
        block_system=dict(payload["block_system"]),
        systems=systems,
        mobilisation_params=mobilisation_params,
        mobilisation_distances=mobilisation_distances,
        locked_assignments=locked_assignments,
        initial_staged_inventory=_block_role_map("staged_inventory"),
        initial_role_remaining=_block_role_map("role_remaining"),
        initial_role_shift_counts={
            key: int(value) for key, value in _block_role_map("role_shift_counts").items()
        },
        initial_machine_block={
            str(mach): str(blk) for mach, blk in initial_payload.get("machine_block", {}).items()
        },
        unsequenced_blocks=tuple(str(blk) for blk in payload.get("unsequenced_blocks", [])),
        blackout_slots=tuple(
            (str(entry["machine_id"]), int(entry["day"]), str(entry["shift_id"]))
            for entry in payload.get("blackout_slots", [])
        ),
    )


__all__ = [
    "OperationalMilpBundle",
    "SystemConfig",
    "SystemRoleConfig",
    "build_operational_bundle",
    "bundle_to_dict",
    "build_blackout_slots",
    "headstart_buffer_volumes",
    "machine_slot_available",
    "ordered_shift_keys",
    "resolve_locked_slots",
    "bundle_from_dict",
    "DEFAULT_TRUCKLOAD_M3",
]
