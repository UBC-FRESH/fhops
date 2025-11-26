"""Operational MILP data bundle helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fhops.scenario.contract import Problem
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scheduling.systems import HarvestSystem, SystemJob, default_system_registry

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
    is_loader: bool = False


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
    registry = sc.harvest_systems or dict(default_system_registry())
    system_configs = _build_system_configs(registry.values())

    default_system_id = next(iter(system_configs))
    block_system: dict[str, str | None] = {}
    for block in sc.blocks:
        system_id = block.harvest_system_id or default_system_id
        if system_id not in system_configs:
            # fallback to default registry if scenario references unknown ID
            system_configs[system_id] = _build_system_configs(
                [registry.get(system_id) or default_system_registry()[system_id]]
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
    configs: dict[str, SystemConfig] = {}
    for system in systems:
        role_configs: list[SystemRoleConfig] = []
        role_by_job: dict[str, str] = {job.name: job.machine_role for job in system.jobs}
        for job in system.jobs:
            upstream_roles = tuple(
                role_by_job.get(prereq) for prereq in job.prerequisites if prereq in role_by_job
            )
            role_configs.append(
                SystemRoleConfig(
                    job_name=job.name,
                    role=job.machine_role,
                    prerequisites=tuple(job.prerequisites),
                    upstream_roles=upstream_roles,
                    buffer_shifts=0.0,
                    is_loader=_is_loader_job(job),
                )
            )
        configs[system.system_id] = SystemConfig(
            system_id=system.system_id,
            roles=tuple(role_configs),
            loader_batch_volume_m3=DEFAULT_TRUCKLOAD_M3,
        )
    return configs


def _is_loader_job(job: SystemJob) -> bool:
    role = job.machine_role or ""
    name = job.name.lower()
    return role == "loader" or "load" in name


__all__ = [
    "OperationalMilpBundle",
    "SystemConfig",
    "SystemRoleConfig",
    "build_operational_bundle",
    "DEFAULT_TRUCKLOAD_M3",
]
