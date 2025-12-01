"""Shared operational problem context for heuristics and MILP consumers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from typing import TYPE_CHECKING

from fhops.model.milp.data import OperationalMilpBundle, build_operational_bundle
from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import MachineMobilisation, build_distance_lookup

if TYPE_CHECKING:  # pragma: no cover - circular import guard
    from fhops.optimization.heuristics.sa import Schedule

    Sanitizer = Callable[[Schedule], Schedule]
else:  # pragma: no cover - runtime placeholder

    class Schedule:  # type: ignore[too-many-ancestors]
        ...

    Sanitizer = Callable[[object], object]


@dataclass(frozen=True)
class OperationalProblem:
    """Precomputed scenario metadata shared across heuristic solvers."""

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

    def build_sanitizer(self, schedule_cls: type[Schedule]) -> Sanitizer:
        """Return a schedule sanitizer enforcing locks, availability, and landing caps."""

        bundle = self.bundle
        machine_roles = bundle.machine_roles
        allowed_roles = self.allowed_roles
        locked = self.locked_assignments
        shift_availability = bundle.availability_shift
        day_availability = bundle.availability_day
        blackout = self.blackout_shifts
        landing_of = bundle.landing_for_block
        landing_cap = bundle.landing_capacity

        def sanitizer(schedule: Schedule) -> Schedule:
            landing_usage: dict[tuple[int, str, str], int] = {}
            plan: dict[str, dict[tuple[int, str], str | None]] = {}
            for machine_id, assignments in schedule.plan.items():
                role = machine_roles.get(machine_id)
                plan[machine_id] = {}
                for (day, shift_id), block_id in assignments.items():
                    lock_key = (machine_id, day)
                    if lock_key in locked:
                        plan[machine_id][(day, shift_id)] = locked[lock_key]
                        continue
                    shift_available = shift_availability.get((machine_id, day, shift_id), 1)
                    day_available = day_availability.get((machine_id, day), 1)
                    if block_id is None:
                        if shift_available == 0 or day_available == 0:
                            plan[machine_id][(day, shift_id)] = None
                        else:
                            plan[machine_id][(day, shift_id)] = None
                        continue
                    allowed = allowed_roles.get(block_id)
                    if (
                        shift_available == 0
                        or day_available == 0
                        or (machine_id, day, shift_id) in blackout
                        or (allowed is not None and role not in allowed)
                    ):
                        plan[machine_id][(day, shift_id)] = None
                        continue
                    landing_id = landing_of.get(block_id)
                    if landing_id is not None:
                        cap = landing_cap.get(landing_id, 0)
                        key = (day, shift_id, landing_id)
                        used = landing_usage.get(key, 0)
                        if cap > 0 and used >= cap:
                            plan[machine_id][(day, shift_id)] = None
                            continue
                        landing_usage[key] = used + 1
                    plan[machine_id][(day, shift_id)] = block_id
            return schedule_cls(plan=plan)

        return sanitizer


def build_operational_problem(pb: Problem) -> OperationalProblem:
    """Construct an :class:`OperationalProblem` for the provided :class:`Problem`."""

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
    blackout = _build_blackout_shifts(pb)
    locked = _build_locked_assignments(pb)
    mobilisation_params = _build_mobilisation_params(pb)
    distance_lookup = bundle.mobilisation_distances or build_distance_lookup(
        pb.scenario.mobilisation
    )
    loader_batch_volume, loader_roles = _build_loader_metadata(bundle)
    shift_keys = tuple(
        (shift.day, shift.shift_id)
        for shift in sorted(pb.shifts, key=lambda s: (s.day, s.shift_id))
    )
    shift_index = {key: idx for idx, key in enumerate(shift_keys)}
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
    )


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
        if available_roles:
            role_names = [role for role in role_names if role in available_roles]
        allowed_roles[block_id] = frozenset(role_names) if role_names else None
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


def _build_blackout_shifts(pb: Problem) -> frozenset[tuple[str, int, str]]:
    scenario = pb.scenario
    timeline = getattr(scenario, "timeline", None)
    if not timeline or not getattr(timeline, "blackouts", None):
        return frozenset()
    blackout: set[tuple[str, int, str]] = set()
    shift_lookup: dict[tuple[str, int], list[str]] = {}
    if scenario.shift_calendar:
        for entry in scenario.shift_calendar:
            shift_lookup.setdefault((entry.machine_id, entry.day), []).append(entry.shift_id)
    timeline_shift_ids = [shift_def.name for shift_def in getattr(timeline, "shifts", []) or []]
    fallback_shifts = timeline_shift_ids or ["S1"]
    for window in timeline.blackouts:
        for day in range(window.start_day, window.end_day + 1):
            for machine in scenario.machines:
                keys = shift_lookup.get((machine.id, day))
                if keys:
                    for shift_id in keys:
                        blackout.add((machine.id, day, shift_id))
                else:
                    for shift_id in fallback_shifts:
                        blackout.add((machine.id, day, shift_id))
    return frozenset(blackout)


def _build_locked_assignments(pb: Problem) -> dict[tuple[str, int], str]:
    locks = getattr(pb.scenario, "locked_assignments", None)
    if not locks:
        return {}
    return {(lock.machine_id, lock.day): lock.block_id for lock in locks}


def _build_mobilisation_params(pb: Problem) -> dict[str, MachineMobilisation]:
    mobilisation = pb.scenario.mobilisation
    if mobilisation is None:
        return {}
    return {param.machine_id: param for param in mobilisation.machine_params}
