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
                        "grapple_skidder_model": "adv6n7",
                        "skidder_trail_pattern": TrailSpacingPattern.SINGLE_GHOST_18M.value,
                        "skidder_decking_condition": DeckingCondition.CONSTRAINED.value,
                        "skidder_extraction_distance_m": 85.0,
                        "skidder_adv6n7_decking_mode": "skidder_loader",
                        "skidder_adv6n7_payload_m3": 7.69,
                        "skidder_adv6n7_utilisation": 0.85,
                        "skidder_adv6n7_delay_minutes": 0.12,
                        "skidder_adv6n7_support_ratio": 0.4,
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob(
                    "loading",
                    "loader",
                    ["processing"],
                    productivity_overrides={
                        "loader_model": "tn261",
                        "loader_piece_size_m3": 1.05,
                        "loader_distance_m": 115.0,
                        "loader_slope_percent": 8.0,
                        "loader_bunched": True,
                        "loader_delay_multiplier": 0.95,
                    },
                ),
            ],
        ),
        "ground_fb_loader_liveheel": HarvestSystem(
            system_id="ground_fb_loader_liveheel",
            environment="ground-based",
            notes="Feller-buncher → grapple skidder → processor → Barko live-heel loader (TN-46).",
            jobs=[
                SystemJob("felling", "feller-buncher", []),
                SystemJob(
                    "primary_transport",
                    "grapple_skidder",
                    ["felling"],
                    productivity_overrides={
                        "grapple_skidder_model": "adv6n7",
                        "skidder_trail_pattern": TrailSpacingPattern.SINGLE_GHOST_18M.value,
                        "skidder_decking_condition": DeckingCondition.CONSTRAINED.value,
                        "skidder_extraction_distance_m": 85.0,
                        "skidder_adv6n7_decking_mode": "skidder_loader",
                        "skidder_adv6n7_payload_m3": 7.69,
                        "skidder_adv6n7_utilisation": 0.85,
                        "skidder_adv6n7_delay_minutes": 0.12,
                        "skidder_adv6n7_support_ratio": 0.4,
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob(
                    "loading",
                    "loader",
                    ["processing"],
                    productivity_overrides={
                        "loader_model": "barko450",
                        "loader_barko_scenario": "ground_skid_block",
                    },
                ),
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
                SystemJob(
                    "loading",
                    "loader",
                    ["processing"],
                    productivity_overrides={
                        "loader_model": "adv5n1",
                        "loader_distance_m": 90.0,
                        "loader_slope_class": "0_10",
                        "loader_payload_m3": 2.77,
                        "loader_utilisation": 0.93,
                    },
                ),
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
        "thinning_adv1n12_forwarder": HarvestSystem(
            system_id="thinning_adv1n12_forwarder",
            environment="commercial thinning",
            notes="Valmet 901C + 646 shortwood thinning (ADV1N12) with extended forwarding distances.",
            jobs=[
                SystemJob(
                    "felling_processing",
                    "single_grip_harvester",
                    [],
                    productivity_overrides={
                        "ctl_harvester_model": "adv5n30",
                        "ctl_removal_fraction": 0.5,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "forwarder",
                    ["felling_processing"],
                    productivity_overrides={
                        "forwarder_model": "adv1n12-shortwood",
                        "forwarder_extraction_distance_m": 350.0,
                    },
                ),
                SystemJob("loading", "loader", ["primary_transport"]),
            ],
        ),
        "thinning_adv1n12_fulltree": HarvestSystem(
            system_id="thinning_adv1n12_fulltree",
            environment="commercial thinning",
            notes="Semi-mechanized lop-and-scatter thinning (ADV1N12) with Timberjack 240 cable skidder.",
            jobs=[
                SystemJob("felling", "hand_faller", []),
                SystemJob(
                    "primary_transport",
                    "grapple_skidder",
                    ["felling"],
                    productivity_overrides={
                        "grapple_skidder_model": "adv1n12-fulltree",
                        "skidder_extraction_distance_m": 225.0,
                        "skidder_trail_pattern": TrailSpacingPattern.SINGLE_GHOST_18M.value,
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
                SystemJob(
                    "felling_processing",
                    "single_grip_harvester",
                    [],
                    productivity_overrides={
                        "ctl_harvester_model": "kellogg1994",
                        "ctl_dbh_cm": 23.0,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "forwarder",
                    ["felling_processing"],
                    productivity_overrides={
                        "forwarder_model": "kellogg-sawlog",
                        "forwarder_volume_per_load_m3": 8.2,
                        "forwarder_distance_out_m": 320.0,
                        "forwarder_travel_in_unit_m": 78.0,
                        "forwarder_distance_in_m": 320.0,
                    },
                ),
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
                SystemJob(
                    "loading",
                    "loader",
                    ["processing"],
                    productivity_overrides={
                        "loader_model": "adv2n26",
                        "loader_travel_empty_m": 320.0,
                        "loader_stems_per_cycle": 18.0,
                        "loader_stem_volume_m3": 1.35,
                        "loader_utilisation": 0.77,
                    },
                ),
            ],
        ),
        "cable_standing": HarvestSystem(
            system_id="cable_standing",
            environment="cable-standing skyline",
            notes="Hand/mech fall → skyline yarder with chokers → landing processor/hand buck → loader.",
            jobs=[
                SystemJob("felling", "hand_or_mech_faller", []),
                SystemJob(
                    "primary_transport",
                    "skyline_yarder",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "aubuchon-kramer",
                        "skyline_logs_per_turn": 3.8,
                        "skyline_average_log_volume_m3": 0.45,
                        "skyline_crew_size": 4.0,
                        "skyline_carriage_height_m": 11.0,
                        "skyline_chordslope_percent": -15.0,
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_running": HarvestSystem(
            system_id="cable_running",
            environment="cable-running skyline",
            notes="Hand/mech fall → grapple yarder → landing processor/hand buck → loader.",
            jobs=[
                SystemJob("felling", "hand_or_mech_faller", []),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "mcneel-running",
                        "skyline_horizontal_distance_m": 280.0,
                        "skyline_vertical_distance_m": 40.0,
                        "skyline_pieces_per_cycle": 3.0,
                        "skyline_piece_volume_m3": 1.8,
                        "skyline_running_variant": "yarder_a",
                        "grapple_yarder_model": "tn157",
                        "grapple_yarder_tn157_case": "combined",
                        "grapple_yarder_turn_volume_m3": 3.8,
                        "grapple_yarder_yarding_distance_m": 83.0,
                    },
                ),
                SystemJob(
                    "processing",
                    "roadside_processor",
                    ["primary_transport"],
                    productivity_overrides={
                        "processor_model": "adv7n3",
                        "processor_adv7n3_machine": "hyundai_210",
                    },
                ),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_running_adv5n28_clearcut": HarvestSystem(
            system_id="cable_running_adv5n28_clearcut",
            environment="cable-running skyline",
            notes="ADV5N28 clearcut conversion (Madill 071 + motorized carriage replacing helicopter layout).",
            jobs=[
                SystemJob("felling", "hand_or_mech_faller", []),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "mcneel-running",
                        "skyline_horizontal_distance_m": 400.0,
                        "skyline_vertical_distance_m": 60.0,
                        "skyline_pieces_per_cycle": 3.0,
                        "skyline_piece_volume_m3": 1.8,
                        "skyline_running_variant": "yarder_a",
                        "grapple_yarder_model": "adv5n28-clearcut",
                        "grapple_yarder_turn_volume_m3": 2.2,
                        "grapple_yarder_yarding_distance_m": 480.0,
                    },
                ),
                SystemJob(
                    "processing",
                    "roadside_processor",
                    ["primary_transport"],
                    productivity_overrides={
                        "processor_model": "adv7n3",
                        "processor_adv7n3_machine": "john_deere_892",
                    },
                ),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_running_adv5n28_shelterwood": HarvestSystem(
            system_id="cable_running_adv5n28_shelterwood",
            environment="cable-running skyline",
            notes="ADV5N28 irregular-shelterwood conversion (long downhill spans through riparian corridors).",
            jobs=[
                SystemJob("felling", "hand_or_mech_faller", []),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "mcneel-running",
                        "skyline_horizontal_distance_m": 350.0,
                        "skyline_vertical_distance_m": 55.0,
                        "skyline_pieces_per_cycle": 3.0,
                        "skyline_piece_volume_m3": 1.6,
                        "skyline_running_variant": "yarder_a",
                        "grapple_yarder_model": "adv5n28-shelterwood",
                        "grapple_yarder_turn_volume_m3": 1.8,
                        "grapple_yarder_yarding_distance_m": 330.0,
                    },
                ),
                SystemJob(
                    "processing",
                    "roadside_processor",
                    ["primary_transport"],
                    productivity_overrides={
                        "processor_model": "adv7n3",
                        "processor_adv7n3_machine": "hyundai_210",
                    },
                ),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "helicopter": HarvestSystem(
            system_id="helicopter",
            environment="helicopter",
            notes="Hand fallers → helicopter longline → landing/hand buck (or direct to water).",
            jobs=[
                SystemJob("felling", "hand_faller", []),
                SystemJob(
                    "primary_transport",
                    "helicopter_longline",
                    ["felling"],
                    productivity_overrides={
                        "helicopter_model": "bell214b",
                        "helicopter_flight_distance_m": 900.0,
                        "helicopter_load_factor": 0.7,
                        "helicopter_delay_minutes": 0.5,
                        "helicopter_weight_to_volume": 2700.0,
                    },
                ),
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
