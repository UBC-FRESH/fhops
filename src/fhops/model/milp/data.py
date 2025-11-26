"""Operational MILP data bundle helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fhops.scenario.contract import Problem
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scheduling.systems import HarvestSystem, default_system_registry

ShiftKey = tuple[int, str]
MachineBlock = tuple[str, str]

DEFAULT_TRUCKLOAD_M3 = 30.0


@dataclass(frozen=True)
class SystemRoleConfig:
    """Description of a single role within a harvest system."""

    job_name: str
    role: str
    prerequisites: tuple[str, ...]
    upstream_roles: tuple[str, ...]
    buffer_shifts: float = 0.0


@dataclass(frozen=True)
class SystemConfig:
    """Harvest system metadata required by the operational MILP."""

    system_id: str
    roles: tuple[SystemRoleConfig, ...]
    loader_batch_volume_m3: float = DEFAULT_TRUCKLOAD_M3


@dataclass(frozen=True)
class OperationalMilpBundle:
    """Normalized data extracted from a :class:`Problem` for MILP construction."""

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


def build_operational_bundle(pb: Problem) -> OperationalMilpBundle:
    """Construct an :class:`OperationalMilpBundle` from a :class:`Problem`."""

    sc = pb.scenario
    machines = tuple(machine.id for machine in sc.machines)
    blocks = tuple(block.id for block in sc.blocks)
    days = tuple(pb.days)
    shifts = tuple((shift.day, shift.shift_id) for shift in pb.shifts)

    machine_roles = {machine.id: machine.role for machine in sc.machines}
    machine_daily_hours = {machine.id: machine.daily_hours for machine in sc.machines}
    production_rates = {(rate.machine_id, rate.block_id): rate.rate for rate in sc.production_rates}
    work_required = {block.id: block.work_required for block in sc.blocks}
    windows = {block.id: sc.window_for(block.id) for block in sc.blocks}
    landing_for_block = {block.id: block.landing_id for block in sc.blocks}
    landing_capacity = {landing.id: landing.daily_capacity for landing in sc.landings}

    availability_day: dict[tuple[str, int], int] = {}
    for entry in sc.calendar:
        availability_day[(entry.machine_id, entry.day)] = int(entry.available)
    availability_shift: dict[tuple[str, int, str], int] = {}
    if sc.shift_calendar:
        for entry in sc.shift_calendar:
            availability_shift[(entry.machine_id, entry.day, entry.shift_id)] = int(entry.available)

    objective_weights = sc.objective_weights or ObjectiveWeights()
    systems = sc.harvest_systems or dict(default_system_registry())
    system_configs = _build_system_configs(systems.values())

    default_system_id = next(iter(systems))
    block_system: dict[str, str] = {}
    for block in sc.blocks:
        system_id = block.harvest_system_id or default_system_id
        if system_id not in system_configs:
            # If the scenario references a system that is not present, fall back to default registry.
            system_configs[system_id] = _build_system_configs(
                [systems.get(system_id) or default_system_registry()[system_id]]
            )[system_id]
        block_system[block.id] = system_id

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
    )


def _build_system_configs(systems: Iterable[HarvestSystem]) -> dict[str, SystemConfig]:
    """Derive role definitions for each harvest system."""

    configs: dict[str, SystemConfig] = {}
    for system in systems:
        job_lookup: dict[str, SystemJobSnapshot] = {}
        for job in system.jobs:
            job_lookup[job.name] = SystemJobSnapshot(
                job.name, job.machine_role, tuple(job.prerequisites)
            )

        role_configs: list[SystemRoleConfig] = []
        for job in system.jobs:
            upstream_roles = tuple(
                job_lookup[prereq].role for prereq in job.prerequisites if prereq in job_lookup
            )
            role_configs.append(
                SystemRoleConfig(
                    job_name=job.name,
                    role=job.machine_role,
                    prerequisites=tuple(job.prerequisites),
                    upstream_roles=upstream_roles,
                    buffer_shifts=0.0,
                )
            )

        configs[system.system_id] = SystemConfig(
            system_id=system.system_id,
            roles=tuple(role_configs),
            loader_batch_volume_m3=DEFAULT_TRUCKLOAD_M3,
        )
    return configs


@dataclass(frozen=True)
class SystemJobSnapshot:
    """Lightweight snapshot of a :class:`SystemJob` to simplify prerequisite lookups."""

    name: str
    role: str
    prerequisites: tuple[str, ...]


__all__ = [
    "OperationalMilpBundle",
    "SystemConfig",
    "SystemRoleConfig",
    "build_operational_bundle",
    "DEFAULT_TRUCKLOAD_M3",
]
