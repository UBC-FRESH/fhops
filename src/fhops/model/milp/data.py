"""Operational MILP data bundle helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from fhops.scenario.contract import Problem
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scheduling.mobilisation import build_distance_lookup
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
    count: int = 1


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
    mobilisation_params: dict[str, dict[str, float]]
    mobilisation_distances: dict[tuple[str, str], float]


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
    )


def _build_system_configs(systems: Iterable[HarvestSystem]) -> dict[str, SystemConfig]:
    configs: dict[str, SystemConfig] = {}
    for system in systems:
        role_configs: list[SystemRoleConfig] = []
        role_by_job: dict[str, str] = {job.name: job.machine_role for job in system.jobs}
        role_counts = {
            role: max(1, int(count)) for role, count in (system.role_counts or {}).items()
        }
        role_buffers = {
            role: float(value) for role, value in (system.role_headstart_shifts or {}).items()
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
    """Serialize an :class:`OperationalMilpBundle` into a JSON-friendly dict."""

    return {
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
            "landing_slack": bundle.objective_weights.landing_slack,
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


def bundle_from_dict(payload: Mapping[str, Any]) -> OperationalMilpBundle:
    """Reconstruct an :class:`OperationalMilpBundle` from ``bundle_to_dict`` output."""

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
            landing_slack=float(payload["objective_weights"]["landing_slack"]),
        ),
        block_system=dict(payload["block_system"]),
        systems=systems,
        mobilisation_params=mobilisation_params,
        mobilisation_distances=mobilisation_distances,
    )


__all__ = [
    "OperationalMilpBundle",
    "SystemConfig",
    "SystemRoleConfig",
    "build_operational_bundle",
    "bundle_to_dict",
    "bundle_from_dict",
    "DEFAULT_TRUCKLOAD_M3",
]
