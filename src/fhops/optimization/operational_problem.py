"""Shared operational problem context for heuristics and MILP consumers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from dataclasses import replace as dc_replace
from typing import TYPE_CHECKING

from fhops.model.milp.data import (
    OperationalMilpBundle,
    build_operational_bundle,
    headstart_buffer_volumes,
    ordered_shift_keys,
)
from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import MachineMobilisation, build_distance_lookup

if TYPE_CHECKING:  # pragma: no cover - circular import guard
    from fhops.optimization.heuristics.sa import Schedule

    Sanitizer = Callable[[Schedule], Schedule]
else:  # pragma: no cover - runtime placeholder

    class Schedule:  # type: ignore[too-many-ancestors]
        ...

    Sanitizer = Callable[[object], object]

HARD_VIOLATION_PENALTY_FLOOR = 1000.0
"""Minimum heuristic penalty per hard violation (the v1.0.0 flat penalty)."""


@dataclass(frozen=True)
class OperationalProblem:
    """Precomputed scenario metadata shared across heuristic solvers.

    Attributes
    ----------
    problem, bundle:
        Source :class:`Problem` and its :class:`OperationalMilpBundle`.
    allowed_roles, prereq_roles, machines_by_role, role_headstarts, loader_batch_volume,
    loader_roles, terminal_roles, blocks_with_explicit_system:
        Harvest-system role metadata derived from the bundle.
    role_work_required:
        Initial remaining output per ``(block_id, role)`` for explicit-system blocks:
        ``work_required`` by default, overridden by ``initial_state`` ``role_remaining`` values.
    blackout_shifts:
        ``(machine_id, day, shift_id)`` slots blocked by timeline blackouts (the bundle's
        ``blackout_slots``; the operational MILP treats the same slots as unavailable).
    locked_assignments:
        Day-level locks ``(machine_id, day) -> block_id`` (``ScheduleLock.shift_id is None``).
    locked_shift_assignments:
        Shift-level locks ``(machine_id, day, shift_id) -> block_id``. Use :meth:`lock_for` to
        query both lock maps.
    mobilisation_params, distance_lookup:
        Mobilisation parameters per machine and the block-to-block distance lookup.
    shift_keys, shift_index:
        Ordered ``(day, shift_id)`` slots and their positional index.
    initial_role_inventory:
        ``(block_id, role) -> m³`` staged output carried in from ``initial_state`` (explicit-system
        blocks only). Empty by default.
    initial_role_counts:
        ``(block_id, role) -> shifts`` already worked, seeding head-start accounting. Empty by
        default.
    initial_machine_block:
        ``machine_id -> block_id`` occupied before the horizon; the first move away from it is
        charged mobilisation. Empty by default.
    role_headstart_volume:
        ``(block_id, role) -> m³`` head-start buffer volume ``B_{r,b}`` of the operational MILP
        (:func:`fhops.model.milp.data.headstart_buffer_volumes`) for explicit-system blocks. A
        buffered role may only work in a slot when the staged upstream volume at the start of the
        slot is at least this value. Empty when no role has ``buffer_shifts > 0``.
    multi_shift_days:
        Days with more than one ``(day, shift_id)`` slot in ``shift_keys``. Empty for
        single-shift scenarios. Informational since 1.0.1 (#140): the heuristic landing guard
        applies on every day when ``landing_surplus`` is weighted 0 (1.0.1 pre-releases applied
        it on these days only, #116).
    max_production_rate:
        Largest ``production_rates`` entry (m³ per shift), used by
        :meth:`hard_violation_penalty`. ``0.0`` when no rate is positive.
    max_move_cost:
        Upper bound on the cost of one machine move (``setup_cost + max(walk_cost_per_meter ·
        walk_threshold_m, move_cost_flat)`` maximised over the machines' mobilisation
        parameters), used by :meth:`hard_violation_penalty`. ``0.0`` without mobilisation
        parameters.
    locked_production, locked_shift_production:
        ``ScheduleLock.production`` values (m³ per slot) of day-level and shift-level locks that
        carry one; query them with :meth:`lock_production_for`. Empty by default.

    Notes
    -----
    ``allowed_roles`` maps each explicit-system block to the roles of its harvest system that the
    fleet provides. When the fleet provides none of them the set is **empty** and no machine may
    work the block (since 1.0.1, #158; it used to be ``None``, which let any machine work the
    block and produce volume that was never delivered). ``None`` means unrestricted (blocks
    without a harvest system).
    """

    problem: Problem
    bundle: OperationalMilpBundle
    allowed_roles: Mapping[str, frozenset[str] | None]
    prereq_roles: Mapping[tuple[str, str], frozenset[str]]
    machines_by_role: Mapping[str, tuple[str, ...]]
    blackout_shifts: frozenset[tuple[str, int, str]]
    locked_assignments: Mapping[tuple[str, int], str]
    mobilisation_params: Mapping[str, MachineMobilisation]
    distance_lookup: Mapping[tuple[str, str], float]
    blocks_with_explicit_system: frozenset[str]
    role_headstarts: Mapping[tuple[str, str], float]
    loader_batch_volume: Mapping[str, float]
    loader_roles: frozenset[tuple[str, str]]
    role_work_required: Mapping[tuple[str, str], float]
    terminal_roles: Mapping[str, frozenset[str]]
    shift_keys: tuple[tuple[int, str], ...]
    shift_index: Mapping[tuple[int, str], int]
    locked_shift_assignments: Mapping[tuple[str, int, str], str] = field(default_factory=dict)
    initial_role_inventory: Mapping[tuple[str, str], float] = field(default_factory=dict)
    initial_role_counts: Mapping[tuple[str, str], int] = field(default_factory=dict)
    initial_machine_block: Mapping[str, str] = field(default_factory=dict)
    role_headstart_volume: Mapping[tuple[str, str], float] = field(default_factory=dict)
    multi_shift_days: frozenset[int] = frozenset()
    max_production_rate: float = 0.0
    max_move_cost: float = 0.0
    locked_production: Mapping[tuple[str, int], float] = field(default_factory=dict)
    locked_shift_production: Mapping[tuple[str, int, str], float] = field(default_factory=dict)

    def hard_violation_penalty(self) -> float:
        """Return the heuristic penalty charged per hard violation (objective units).

        The heuristic evaluator charges this amount for every assignment that breaks a hard rule
        (unavailable or blacked-out slot, broken lock, forbidden role, harvest window, zero rate,
        sequencing violation, and a landing overload when ``landing_surplus`` is weighted 0).

        Returns
        -------
        float
            ``max(1000, 2 · ω_prod · r_max + ω_mob · c_max + 1)`` with the bundle's (possibly
            overridden) weights, ``r_max`` =
            :attr:`max_production_rate` and ``c_max`` = :attr:`max_move_cost`.

        Notes
        -----
        One assignment can raise the heuristic objective directly by at most
        ``2 · ω_prod · r_max`` (its output counts as delivered and is no longer charged as
        leftover) plus ``ω_mob · c_max`` (with non-metric move costs, an extra stop can replace a
        flat-rate move by two walks); it cannot reduce the transition count. The penalty strictly
        exceeds that bound, so a plan never scores higher by keeping a violating assignment for its
        own production or mobilisation effect (audit MINOR-E, #140: with a flat 1000 an SA plan
        overloading a landing whose extra machine-shift was worth more than 1000 beat the MILP's
        hard optimum). Indirect effects through downstream sequencing are not bounded; avoidable
        violations are removed by the repair pass in any case. Scenarios whose largest rate is
        below about 500 m³ per shift keep the v1.0.0 penalty of 1000.
        """

        weights = self.bundle.objective_weights
        bound = (
            2.0 * max(weights.production, 0.0) * self.max_production_rate
            + max(weights.mobilisation, 0.0) * self.max_move_cost
        )
        return max(HARD_VIOLATION_PENALTY_FLOOR, bound + 1.0)

    def lock_for(self, machine_id: str, day: int, shift_id: str) -> str | None:
        """Return the block locked for ``machine_id`` in slot ``(day, shift_id)`` (or ``None``).

        Shift-level locks take precedence over day-level locks (scenario validation forbids both
        for the same machine/day).
        """

        if self.locked_shift_assignments:
            block_id = self.locked_shift_assignments.get((machine_id, day, shift_id))
            if block_id is not None:
                return block_id
        return self.locked_assignments.get((machine_id, day))

    def lock_production_for(self, machine_id: str, day: int, shift_id: str) -> float | None:
        """Return the ``ScheduleLock.production`` cap (m³) of a locked slot, if one is given.

        ``None`` when the slot is not locked or its lock carries no planned production. A
        day-level lock's value applies to each of its slots. The heuristics and playback use it
        as an upper bound on the locked slot's production (``0`` keeps the locked slot idle).
        """

        if self.locked_shift_production:
            value = self.locked_shift_production.get((machine_id, day, shift_id))
            if value is not None:
                return value
            if (machine_id, day, shift_id) in self.locked_shift_assignments:
                return None
        return self.locked_production.get((machine_id, day))

    def build_sanitizer(self, schedule_cls: type[Schedule]) -> Sanitizer:
        """Return a schedule sanitizer enforcing locks, availability, and landing caps.

        The sanitizer drops unlocked assignments to unavailable or blacked-out slots, forbidden
        roles, and landings already at capacity in that slot. A landing with capacity 0 admits no
        unlocked machine when ``landing_surplus`` is weighted 0 (hard capacity, as in the MILP);
        with a soft capacity it is not capped here (pre-#140 behaviour, kept so soft-mode results
        do not change).
        """

        sanitize_cell = self._sanitizer_cell_rule()

        def sanitizer(schedule: Schedule) -> Schedule:
            landing_usage: dict[tuple[int, str, str], int] = {}
            plan: dict[str, dict[tuple[int, str], str | None]] = {}
            for machine_id, assignments in schedule.plan.items():
                plan[machine_id] = {
                    slot: sanitize_cell(machine_id, slot, block_id, landing_usage)
                    for slot, block_id in assignments.items()
                }
            return schedule_cls(plan=plan)

        return sanitizer

    def build_sanitizer_preview(
        self, plan: Mapping[str, Mapping[tuple[int, str], str | None]]
    ) -> SanitizerPreview:
        """Return a :class:`SanitizerPreview` of the :meth:`build_sanitizer` rules for ``plan``.

        Parameters
        ----------
        plan:
            Base machine → ``(day, shift_id)`` → block plan (an operator's current schedule). It
            must not be mutated while the preview is in use.

        Returns
        -------
        SanitizerPreview
            Predicts, for a few edited cells of ``plan``, what the sanitizer would return without
            copying or sanitizing the whole plan (#151).
        """

        return SanitizerPreview(plan, self._sanitizer_cell_rule())

    def _sanitizer_cell_rule(
        self,
    ) -> Callable[[str, tuple[int, str], str | None, dict[tuple[int, str, str], int]], str | None]:
        """Return the per-cell rule shared by :meth:`build_sanitizer` and the preview.

        The returned function maps ``(machine_id, (day, shift_id), block_id, landing_usage)`` to
        the sanitized block and updates ``landing_usage`` (``(day, shift_id, landing_id)`` →
        machines admitted so far) in place. Cells of one slot must be passed in plan machine
        order: the sanitizer admits machines to a landing in that order. Decisions depend only on
        the cell itself and the earlier cells of the same slot.
        """

        bundle = self.bundle
        machine_roles = bundle.machine_roles
        allowed_roles = self.allowed_roles
        has_locks = bool(self.locked_assignments or self.locked_shift_assignments)
        lock_for = self.lock_for
        shift_availability = bundle.availability_shift
        day_availability = bundle.availability_day
        blackout = self.blackout_shifts
        landing_of = bundle.landing_for_block
        landing_cap = bundle.landing_capacity
        hard_landing = bundle.objective_weights.landing_surplus == 0.0

        def sanitize_cell(
            machine_id: str,
            slot: tuple[int, str],
            block_id: str | None,
            landing_usage: dict[tuple[int, str, str], int],
        ) -> str | None:
            day, shift_id = slot
            if has_locks:
                locked_block = lock_for(machine_id, day, shift_id)
                if locked_block is not None:
                    return locked_block
            if block_id is None:
                return None
            allowed = allowed_roles.get(block_id)
            if (
                shift_availability.get((machine_id, day, shift_id), 1) == 0
                or day_availability.get((machine_id, day), 1) == 0
                or (machine_id, day, shift_id) in blackout
                or (allowed is not None and machine_roles.get(machine_id) not in allowed)
            ):
                return None
            landing_id = landing_of.get(block_id)
            if landing_id is not None:
                cap = landing_cap.get(landing_id, 0)
                key = (day, shift_id, landing_id)
                used = landing_usage.get(key, 0)
                if (cap > 0 or hard_landing) and used >= cap:
                    return None
                landing_usage[key] = used + 1
            return block_id

        return sanitize_cell


class SanitizerPreview:
    """Predict the operator sanitizer's output for small edits of one base plan (#151).

    Operators such as block insertion, cross exchange and mobilisation shake try candidate moves
    until the sanitized candidate differs from the current plan and keeps the moved assignment.
    Under a binding hard landing capacity most tries are rejected, and building and sanitizing a
    full candidate per try made these operators (and the heuristics) several times slower after
    #140. The sanitizer decides every slot independently (locks, calendar, blackouts, roles, and
    landing capacity admitted in plan machine order), so the outcome of a try only depends on
    the edited slots and on whether the base plan itself is a sanitizer fixed point elsewhere.

    Parameters
    ----------
    plan:
        Base plan (machine → ``(day, shift_id)`` → block or ``None``), not copied.
    sanitize_cell:
        Per-cell rule from :meth:`OperationalProblem._sanitizer_cell_rule`.
    """

    __slots__ = ("_plan", "_machines", "_cell", "_changed_slots")

    def __init__(
        self,
        plan: Mapping[str, Mapping[tuple[int, str], str | None]],
        sanitize_cell: Callable[
            [str, tuple[int, str], str | None, dict[tuple[int, str, str], int]], str | None
        ],
    ) -> None:
        self._plan = plan
        self._machines = list(plan)
        self._cell = sanitize_cell
        self._changed_slots: set[tuple[int, str]] | None = None

    def _base_changed_slots(self) -> set[tuple[int, str]]:
        # Slots in which the sanitizer would change the base plan itself (computed once).
        if self._changed_slots is None:
            usage: dict[tuple[int, str, str], int] = {}
            cell = self._cell
            changed: set[tuple[int, str]] = set()
            for machine_id in self._machines:
                for slot, block_id in self._plan[machine_id].items():
                    if cell(machine_id, slot, block_id, usage) != block_id:
                        changed.add(slot)
            self._changed_slots = changed
        return self._changed_slots

    def outcome(
        self, edits: Sequence[tuple[str, tuple[int, str], str | None]]
    ) -> tuple[bool, dict[tuple[str, tuple[int, str]], str | None]] | None:
        """Return what sanitizing the edited base plan would produce.

        Parameters
        ----------
        edits:
            ``(machine_id, (day, shift_id), block_id)`` cell assignments applied to a copy of the
            base plan in order (a later edit of the same cell wins).

        Returns
        -------
        tuple[bool, dict] | None
            ``(unchanged, values)``: ``unchanged`` is ``True`` when the sanitized edited plan
            equals the base plan (as compared by the operators), ``values`` maps each edited cell
            to its sanitized block. ``None`` when an edit addresses a machine or slot missing from
            the base plan (the caller then builds and sanitizes the candidate itself).
        """

        plan = self._plan
        overrides: dict[tuple[str, tuple[int, str]], str | None] = {}
        for machine_id, slot, block_id in edits:
            machine_plan = plan.get(machine_id)
            if machine_plan is None or slot not in machine_plan:
                return None
            overrides[(machine_id, slot)] = block_id
        slots = {slot for _machine_id, slot in overrides}
        # The edited slots after sanitizing equal the base plan's (``same``), and no other slot
        # is changed by the sanitizer (checked only when needed: one pass over the base plan).
        same = True
        values: dict[tuple[str, tuple[int, str]], str | None] = {}
        cell = self._cell
        for slot in slots:
            usage: dict[tuple[int, str, str], int] = {}
            for machine_id in self._machines:
                machine_plan = plan[machine_id]
                if slot not in machine_plan:
                    continue
                base_block = machine_plan[slot]
                key = (machine_id, slot)
                edited = key in overrides
                value = cell(machine_id, slot, overrides[key] if edited else base_block, usage)
                if edited:
                    values[key] = value
                if same and value != base_block:
                    same = False
        return same and self._base_changed_slots() <= slots, values


def build_operational_problem(pb: Problem) -> OperationalProblem:
    """Construct an :class:`OperationalProblem` for the provided :class:`Problem`.

    Parameters
    ----------
    pb:
        Problem produced by :meth:`fhops.scenario.contract.Problem.from_scenario`.

    Returns
    -------
    OperationalProblem
        Shared context. When ``pb.scenario.initial_state`` is set, ``role_work_required`` reflects
        the carried-in ``role_remaining`` values and the ``initial_*`` mappings are populated;
        otherwise the context is identical to v1.0.0.
    """

    bundle = build_operational_bundle(pb)
    explicit_blocks = frozenset(block.id for block in pb.scenario.blocks if block.harvest_system_id)
    (
        allowed_roles,
        prereq_roles,
        machines_by_role,
        headstarts,
        role_work_required,
        terminal_roles,
    ) = _derive_role_metadata(bundle, explicit_blocks)
    for key, remaining in bundle.initial_role_remaining.items():
        if key in role_work_required:
            role_work_required[key] = remaining
    initial_role_inventory = {
        key: volume
        for key, volume in bundle.initial_staged_inventory.items()
        if key[0] in explicit_blocks
    }
    initial_role_counts = {
        key: count
        for key, count in bundle.initial_role_shift_counts.items()
        if key[0] in explicit_blocks
    }
    role_headstart_volume = {
        key: volume
        for key, volume in headstart_buffer_volumes(bundle).items()
        if key[0] in explicit_blocks and key in headstarts
    }
    blackout = frozenset(bundle.blackout_slots)
    locked, locked_shift, locked_production, locked_shift_production = _build_lock_maps(pb)
    mobilisation_params = _build_mobilisation_params(pb)
    distance_lookup = bundle.mobilisation_distances or build_distance_lookup(
        pb.scenario.mobilisation
    )
    loader_batch_volume, loader_roles = _build_loader_metadata(bundle)
    shift_keys = ordered_shift_keys(pb)
    shift_index = {key: idx for idx, key in enumerate(shift_keys)}
    slots_per_day: dict[int, int] = defaultdict(int)
    for day, _shift_id in shift_keys:
        slots_per_day[day] += 1
    multi_shift_days = frozenset(day for day, count in slots_per_day.items() if count > 1)
    max_production_rate = max(
        (float(value) for value in bundle.production_rates.values() if value > 0.0), default=0.0
    )
    max_move_cost = max(
        (
            float(params.setup_cost)
            + max(
                float(params.walk_cost_per_meter) * float(params.walk_threshold_m),
                float(params.move_cost_flat),
            )
            for params in mobilisation_params.values()
        ),
        default=0.0,
    )
    return OperationalProblem(
        problem=pb,
        bundle=bundle,
        allowed_roles=allowed_roles,
        prereq_roles=prereq_roles,
        machines_by_role=machines_by_role,
        blackout_shifts=blackout,
        locked_assignments=locked,
        mobilisation_params=mobilisation_params,
        distance_lookup=distance_lookup,
        blocks_with_explicit_system=explicit_blocks,
        role_headstarts=headstarts,
        loader_batch_volume=loader_batch_volume,
        loader_roles=loader_roles,
        role_work_required=role_work_required,
        terminal_roles=terminal_roles,
        shift_keys=shift_keys,
        shift_index=shift_index,
        locked_shift_assignments=locked_shift,
        initial_role_inventory=initial_role_inventory,
        initial_role_counts=initial_role_counts,
        initial_machine_block=dict(bundle.initial_machine_block),
        role_headstart_volume=role_headstart_volume,
        multi_shift_days=multi_shift_days,
        max_production_rate=max_production_rate,
        max_move_cost=max(max_move_cost, 0.0),
        locked_production=locked_production,
        locked_shift_production=locked_shift_production,
    )


def blocks_without_fleet_roles(ctx: OperationalProblem) -> dict[str, str]:
    """Return blocks whose harvest system the fleet cannot work or cannot deliver.

    Parameters
    ----------
    ctx:
        Operational context of the scenario.

    Returns
    -------
    dict[str, str]
        ``block_id -> reason`` for blocks with an explicit harvest system where (a) no machine
        has any role of the system (``allowed_roles`` is empty: no machine may work the block,
        #158), or (b) no machine has a terminal role of the system (upstream roles may work but
        nothing is delivered). ``fhops validate`` prints these as warnings.
    """

    bundle = ctx.bundle
    fleet_roles = {role for role in bundle.machine_roles.values() if role}
    issues: dict[str, str] = {}
    for block_id in bundle.blocks:
        if block_id not in ctx.blocks_with_explicit_system:
            continue
        system_id = bundle.block_system.get(block_id)
        system = bundle.systems.get(system_id) if system_id else None
        if system is None:
            continue
        system_roles = sorted({cfg.role for cfg in system.roles if cfg.role})
        if not system_roles:
            continue
        if ctx.allowed_roles.get(block_id) == frozenset():
            issues[block_id] = (
                f"harvest system {system_id!r} needs roles {', '.join(system_roles)}; no machine "
                "has any of them, so no machine may work the block"
            )
            continue
        terminal = sorted(ctx.terminal_roles.get(system.system_id, frozenset()))
        if terminal and not fleet_roles.intersection(terminal):
            issues[block_id] = (
                f"harvest system {system_id!r}: no machine has its terminal role(s) "
                f"{', '.join(terminal)}, so the block's volume cannot be delivered"
            )
    return issues


def override_objective_weights(
    ctx: OperationalProblem,
    overrides: Mapping[str, float],
) -> OperationalProblem:
    """Return a copy of ``ctx`` with objective weights updated per the overrides."""

    if not overrides:
        return ctx
    new_weights = ctx.bundle.objective_weights.model_copy(update=dict(overrides))
    new_bundle = dc_replace(ctx.bundle, objective_weights=new_weights)
    return dc_replace(ctx, bundle=new_bundle)


def _derive_role_metadata(
    bundle: OperationalMilpBundle,
    explicit_blocks: frozenset[str],
) -> tuple[
    dict[str, frozenset[str] | None],
    dict[tuple[str, str], frozenset[str]],
    dict[str, tuple[str, ...]],
    dict[tuple[str, str], float],
    dict[tuple[str, str], float],
    dict[str, frozenset[str]],
]:
    allowed_roles: dict[str, frozenset[str] | None] = {}
    prereq_roles: dict[tuple[str, str], frozenset[str]] = {}
    headstart_shifts: dict[tuple[str, str], float] = {}
    role_work_required: dict[tuple[str, str], float] = {}
    system_terminal_roles: dict[str, frozenset[str]] = {}
    machine_roles = bundle.machine_roles
    available_roles = {role for role in machine_roles.values() if role}
    machines_by_role: dict[str, list[str]] = {}
    for machine_id, role in machine_roles.items():
        if role:
            machines_by_role.setdefault(role, []).append(machine_id)

    for block_id in bundle.blocks:
        system_id = bundle.block_system.get(block_id)
        system = bundle.systems.get(system_id) if system_id else None
        if system is None:
            allowed_roles[block_id] = None
            continue
        role_names = [rc.role for rc in system.roles if rc.role]
        if block_id not in explicit_blocks:
            allowed_roles[block_id] = None
            continue
        if not role_names:
            allowed_roles[block_id] = None
            continue
        if available_roles:
            role_names = [role for role in role_names if role in available_roles]
        # A system none of whose roles is in the fleet admits no machine (empty set, #158; it
        # was ``None``, i.e. any role, before, so machines produced volume nobody delivered).
        allowed_roles[block_id] = frozenset(role_names)
        if not available_roles:
            continue
        for role_cfg in system.roles:
            role = role_cfg.role
            if not role or role not in available_roles:
                continue
            prereqs = tuple(
                upstream for upstream in role_cfg.upstream_roles if upstream in available_roles
            )
            buffer_value = role_cfg.buffer_shifts or 0.0
            if buffer_value > 0:
                headstart_shifts[(block_id, role)] = buffer_value
            if prereqs:
                prereq_roles[(block_id, role)] = frozenset(prereqs)
            if block_id in explicit_blocks:
                role_work_required[(block_id, role)] = bundle.work_required.get(block_id, 0.0)

    machines_by_role_tuple = {
        role: tuple(sorted(machine_ids)) for role, machine_ids in machines_by_role.items()
    }
    for system in bundle.systems.values():
        downstream: dict[str, set[str]] = defaultdict(set)
        for role_cfg in system.roles:
            role = role_cfg.role
            if not role:
                continue
            for upstream in role_cfg.upstream_roles:
                downstream[upstream].add(role)
        terminal = {
            role_cfg.role
            for role_cfg in system.roles
            if role_cfg.role and not downstream.get(role_cfg.role)
        }
        system_terminal_roles[system.system_id] = frozenset(terminal)

    return (
        allowed_roles,
        prereq_roles,
        machines_by_role_tuple,
        headstart_shifts,
        role_work_required,
        system_terminal_roles,
    )


def _build_loader_metadata(
    bundle: OperationalMilpBundle,
) -> tuple[dict[str, float], frozenset[tuple[str, str]]]:
    loader_batch: dict[str, float] = {}
    loader_roles: set[tuple[str, str]] = set()
    systems = bundle.systems
    for block_id, system_id in bundle.block_system.items():
        system = systems.get(system_id)
        if system is None:
            continue
        loader_batch[block_id] = system.loader_batch_volume_m3
        for role_cfg in system.roles:
            if role_cfg.is_loader and role_cfg.role:
                loader_roles.add((block_id, role_cfg.role))
    return loader_batch, frozenset(loader_roles)


def _build_lock_maps(
    pb: Problem,
) -> tuple[
    dict[tuple[str, int], str],
    dict[tuple[str, int, str], str],
    dict[tuple[str, int], float],
    dict[tuple[str, int, str], float],
]:
    """Return day/shift lock maps and the ``ScheduleLock.production`` values they carry."""

    locks = getattr(pb.scenario, "locked_assignments", None)
    if not locks:
        return {}, {}, {}, {}
    day_locks: dict[tuple[str, int], str] = {}
    shift_locks: dict[tuple[str, int, str], str] = {}
    day_production: dict[tuple[str, int], float] = {}
    shift_production: dict[tuple[str, int, str], float] = {}
    for lock in locks:
        shift_id = getattr(lock, "shift_id", None)
        production = getattr(lock, "production", None)
        if shift_id is None:
            day_locks[(lock.machine_id, lock.day)] = lock.block_id
            if production is not None:
                day_production[(lock.machine_id, lock.day)] = float(production)
        else:
            shift_locks[(lock.machine_id, lock.day, shift_id)] = lock.block_id
            if production is not None:
                shift_production[(lock.machine_id, lock.day, shift_id)] = float(production)
    return day_locks, shift_locks, day_production, shift_production


def _build_mobilisation_params(pb: Problem) -> dict[str, MachineMobilisation]:
    mobilisation = pb.scenario.mobilisation
    if mobilisation is None:
        return {}
    return {param.machine_id: param for param in mobilisation.machine_params}
