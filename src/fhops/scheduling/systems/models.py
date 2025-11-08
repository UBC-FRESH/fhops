"""Harvest system registry models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SystemJob:
    """A single job in a harvest system sequence."""

    name: str
    machine_role: str
    prerequisites: Sequence[str]


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
                SystemJob("primary_transport", "grapple_skidder", ["felling"]),
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
                SystemJob("primary_transport", "shovel_logger", ["felling"]),
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
                SystemJob("primary_transport", "shovel_logger", ["felling"]),
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


__all__ = ["SystemJob", "HarvestSystem", "default_system_registry"]
