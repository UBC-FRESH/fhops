"""Harvest system registry models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Mapping

from fhops.costing.machine_rates import normalize_machine_role
from fhops.productivity.skidder_ft import DeckingCondition, TrailSpacingPattern


@dataclass(frozen=True)
class SystemJob:
    """A single job in a harvest system sequence."""

    name: str
    machine_role: str
    prerequisites: Sequence[str]
    productivity_overrides: Mapping[str, float | str] | None = None

    def __post_init__(self) -> None:
        normalised = normalize_machine_role(self.machine_role)
        if normalised:
            object.__setattr__(self, "machine_role", normalised)


@dataclass(frozen=True)
class HarvestSystem:
    """Harvest system definition with ordered jobs."""

    system_id: str
    jobs: Sequence[SystemJob]
    environment: str | None = None
    notes: str | None = None


def default_system_registry() -> Mapping[str, HarvestSystem]:
    """Return the default harvest system registry inspired by Jaffray (2025)."""
    return {
        "ground_fb_skid": HarvestSystem(
            system_id="ground_fb_skid",
            environment="ground-based",
            notes="Feller-buncher → grapple skidder → processor → loader/trucks.",
            jobs=[
                SystemJob("felling", "feller-buncher", []),
                SystemJob(
                    "primary_transport",
                    "grapple_skidder",
                    ["felling"],
                    productivity_overrides={
                        "skidder_trail_pattern": TrailSpacingPattern.SINGLE_GHOST_18M.value,
                        "skidder_decking_condition": DeckingCondition.CONSTRAINED.value,
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "ground_hand_shovel": HarvestSystem(
            system_id="ground_hand_shovel",
            environment="ground-based",
            notes="Hand fall → shovel logger → processor → loader/trucks.",
            jobs=[
                SystemJob("felling", "hand_faller", []),
                SystemJob(
                    "primary_transport",
                    "shovel_logger",
                    ["felling"],
                    productivity_overrides={
                        "shovel_passes": 3,
                        "shovel_swing_length": 15.0,
                        "shovel_strip_length": 90.0,
                        "shovel_volume_per_ha": 300.0,
                        "shovel_speed_index": 0.6,
                        "shovel_speed_return": 0.6,
                        "shovel_speed_serpentine": 0.6,
                        "shovel_effective_minutes": 45.0,
                        "shovel_slope_class": "uphill",
                        "shovel_bunching": "hand_scattered",
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "ground_fb_shovel": HarvestSystem(
            system_id="ground_fb_shovel",
            environment="ground-based",
            notes="Feller-buncher → shovel logger → processor → loader/trucks.",
            jobs=[
                SystemJob("felling", "feller-buncher", []),
                SystemJob(
                    "primary_transport",
                    "shovel_logger",
                    ["felling"],
                    productivity_overrides={
                        "shovel_passes": 4,
                        "shovel_swing_length": 16.15,
                        "shovel_strip_length": 100.0,
                        "shovel_volume_per_ha": 375.0,
                        "shovel_speed_index": 0.7,
                        "shovel_speed_return": 0.7,
                        "shovel_speed_serpentine": 0.7,
                        "shovel_effective_minutes": 50.0,
                        "shovel_slope_class": "level",
                        "shovel_bunching": "feller_bunched",
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "ctl": HarvestSystem(
            system_id="ctl",
            environment="cut-to-length",
            notes="Harvester processes at stump, forwarder hauls shortwood direct to trucks.",
            jobs=[
                SystemJob("felling_processing", "single_grip_harvester", []),
                SystemJob("primary_transport", "forwarder", ["felling_processing"]),
                SystemJob("loading", "loader", ["primary_transport"]),
            ],
        ),
        "steep_tethered": HarvestSystem(
            system_id="steep_tethered",
            environment="steep-slope mechanised",
            notes="Winch-assist harvester/feller → tethered shovel/skidder → processor → loader.",
            jobs=[
                SystemJob("felling", "tethered_harvester", []),
                SystemJob("primary_transport", "tethered_shovel_or_skidder", ["felling"]),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_standing": HarvestSystem(
            system_id="cable_standing",
            environment="cable-standing skyline",
            notes="Hand/mech fall → skyline yarder with chokers → landing processor/hand buck → loader.",
            jobs=[
                SystemJob("felling", "hand_or_mech_faller", []),
                SystemJob("primary_transport", "skyline_yarder", ["felling"]),
                SystemJob("processing", "landing_processor_or_hand_buck", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_running": HarvestSystem(
            system_id="cable_running",
            environment="cable-running skyline",
            notes="Hand/mech fall → grapple yarder → landing processor/hand buck → loader.",
            jobs=[
                SystemJob("felling", "hand_or_mech_faller", []),
                SystemJob("primary_transport", "grapple_yarder", ["felling"]),
                SystemJob("processing", "landing_processor_or_hand_buck", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "helicopter": HarvestSystem(
            system_id="helicopter",
            environment="helicopter",
            notes="Hand fallers → helicopter longline → landing/hand buck (or direct to water).",
            jobs=[
                SystemJob("felling", "hand_faller", []),
                SystemJob("primary_transport", "helicopter_longline", ["felling"]),
                SystemJob("processing", "hand_buck_or_processor", ["primary_transport"]),
                SystemJob("loading", "loader_or_water", ["processing"]),
            ],
        ),
    }


def system_productivity_overrides(
    system: HarvestSystem, machine_role: str
) -> dict[str, float | str] | None:
    normalized = normalize_machine_role(machine_role)
    if normalized is None:
        return None
    for job in system.jobs:
        if job.machine_role == normalized and job.productivity_overrides:
            return dict(job.productivity_overrides)
    return None


__all__ = [
    "SystemJob",
    "HarvestSystem",
    "default_system_registry",
    "system_productivity_overrides",
]
