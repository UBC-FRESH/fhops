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

    def _tn157_running(system_id: str, notes: str) -> HarvestSystem:
        return HarvestSystem(
            system_id=system_id,
            environment="cable-running skyline",
            notes=notes,
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 52.5,
                    },
                ),
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
        )
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
        "ground_salvage_grapple": HarvestSystem(
            system_id="ground_salvage_grapple",
            environment="ground-based salvage",
            notes="ADV1N5 salvage chain (buck/burn sorting, double-ring debarkers, charcoal dust controls) with grapple skidding feeding roadside processing.",
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
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 42.5,
                    },
                ),
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
        "cable_standing_tr125_single": HarvestSystem(
            system_id="cable_standing_tr125_single",
            environment="cable-standing skyline",
            notes="TR125 single-span standing skyline (Skylead C40) for clearcut corridors.",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 42.5,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_yarder",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "tr125-single-span",
                        "skyline_lateral_distance_m": 25.0,
                        "skyline_payload_m3": 1.6,
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_standing_tr125_strip": HarvestSystem(
            system_id="cable_standing_tr125_strip",
            environment="cable-standing skyline",
            notes="TR125 multi-span standing skyline with intermediate supports for strip cuts (TR119).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 42.5,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_yarder",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "tr125-multi-span",
                        "skyline_lateral_distance_m": 40.0,
                        "skyline_payload_m3": 1.6,
                        "tr119_treatment": "strip_cut",
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_running": _tn157_running(
            "cable_running",
            "TN-157 combined (Cypress 7280B + UH14 backspar) defaults for running skyline corridors.",
        ),
        "cable_running_tn157_combined": _tn157_running(
            "cable_running_tn157_combined",
            "Explicit TN-157 combined preset (alias of cable_running) so datasets can reference the case directly.",
        ),
        "cable_highlead_tn147": HarvestSystem(
            system_id="cable_highlead_tn147",
            environment="cable-highlead skyline",
            notes="TN-147 Madill 009 highlead cases (hand fall → highlead grapple → landing processor → loader).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 50.0,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "grapple_yarder_model": "tn147",
                        "grapple_yarder_tn147_case": "combined",
                        "grapple_yarder_turn_volume_m3": 5.48,
                        "grapple_yarder_yarding_distance_m": 138.0,
                        "grapple_yarder_stems_per_cycle": 2.1,
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
        "cable_running_tr122_extended": HarvestSystem(
            system_id="cable_running_tr122_extended",
            environment="cable-running skyline",
            notes="TR-122 Roberts Creek extended-rotation treatment (SLH 78 running skyline).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 40.0,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "grapple_yarder_model": "tr122-extended",
                        "grapple_yarder_turn_volume_m3": 2.04,
                        "grapple_yarder_yarding_distance_m": 104.0,
                        "grapple_yarder_stems_per_cycle": 2.2,
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_running_tr122_shelterwood": HarvestSystem(
            system_id="cable_running_tr122_shelterwood",
            environment="cable-running skyline",
            notes="TR-122 Roberts Creek uniform shelterwood running skyline defaults.",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 40.0,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "grapple_yarder_model": "tr122-shelterwood",
                        "grapple_yarder_turn_volume_m3": 2.18,
                        "grapple_yarder_yarding_distance_m": 97.0,
                        "grapple_yarder_stems_per_cycle": 3.2,
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_running_tr122_clearcut": HarvestSystem(
            system_id="cable_running_tr122_clearcut",
            environment="cable-running skyline",
            notes="TR-122 Roberts Creek clearcut (short 106 m spans, 1.45 m³ cycle volume).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 40.0,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "grapple_yarder_model": "tr122-clearcut",
                        "grapple_yarder_turn_volume_m3": 1.45,
                        "grapple_yarder_yarding_distance_m": 106.0,
                        "grapple_yarder_stems_per_cycle": 2.6,
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_partial_tr127_block1": HarvestSystem(
            system_id="cable_partial_tr127_block1",
            environment="cable-standing skyline",
            notes="TR127 Block 1 standing skyline (two lateral distances) representing 65% retention trials.",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 42.5,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_yarder",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "tr127-block1",
                        "skyline_lateral_distance_m": 15.0,
                        "skyline_lateral_distance2_m": 6.0,
                        "tr119_treatment": "65_retention",
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_partial_tr127_block5": HarvestSystem(
            system_id="cable_partial_tr127_block5",
            environment="cable-standing skyline",
            notes="TR127 Block 5 (partial cut) with 70% retention defaults and TN-258 lateral guidance.",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 42.5,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_yarder",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "tr127-block5",
                        "skyline_lateral_distance_m": 16.0,
                        "skyline_num_logs": 3.0,
                        "skyline_payload_m3": 1.6,
                        "tr119_treatment": "70_retention",
                    },
                ),
                SystemJob("processing", "roadside_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_running_adv5n28_clearcut": HarvestSystem(
            system_id="cable_running_adv5n28_clearcut",
            environment="cable-running skyline",
            notes="ADV5N28 clearcut conversion (Madill 071 + motorized carriage replacing helicopter layout).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 52.5,
                    },
                ),
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
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 42.5,
                    },
                ),
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
        "cable_running_sr54": HarvestSystem(
            system_id="cable_running_sr54",
            environment="cable-running skyline",
            notes="SR-54 Washington 118A grapple yarder on mechanically bunched coastal second-growth.",
            jobs=[
                SystemJob("felling", "feller-buncher", []),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "grapple_yarder_model": "sr54",
                        "grapple_yarder_turn_volume_m3": 3.1,
                        "grapple_yarder_yarding_distance_m": 82.0,
                        "grapple_yarder_stems_per_cycle": 2.9,
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
        "cable_running_tr75_bunched": HarvestSystem(
            system_id="cable_running_tr75_bunched",
            environment="cable-running skyline",
            notes="TR-75 System 1 (mechanically felled/bunched Madill 084 + Hitachi UH14 backspar).",
            jobs=[
                SystemJob("felling", "feller-buncher", []),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "grapple_yarder_model": "tr75-bunched",
                        "grapple_yarder_turn_volume_m3": 1.29,
                        "grapple_yarder_yarding_distance_m": 71.0,
                        "grapple_yarder_stems_per_cycle": 2.18,
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
        "cable_running_tr75_handfelled": HarvestSystem(
            system_id="cable_running_tr75_handfelled",
            environment="cable-running skyline",
            notes="TR-75 System 2 (hand-felled second-growth yarded by Madill 084).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 45.0,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "grapple_yarder",
                    ["felling"],
                    productivity_overrides={
                        "grapple_yarder_model": "tr75-handfelled",
                        "grapple_yarder_turn_volume_m3": 1.28,
                        "grapple_yarder_yarding_distance_m": 76.6,
                        "grapple_yarder_stems_per_cycle": 1.41,
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
        "cable_running_fncy12": HarvestSystem(
            system_id="cable_running_fncy12",
            environment="cable-running skyline",
            notes="Thunderbird TMY45 + Mini-Mak II (FNCY12/TN258) intermediate-support skyline corridors.",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 52.5,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_yarder",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "fncy12-tmy45",
                        "skyline_logs_per_turn": 3.6,
                        "skyline_average_log_volume_m3": 1.15,
                        "skyline_crew_size": 5.5,
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
        "cable_micro_ecologger": HarvestSystem(
            system_id="cable_micro_ecologger",
            environment="cable-short-span skyline",
            notes="TN173 RMS Ecologger uphill skyline (≈0.34 m³ pieces, 2.9 logs/turn, four-person crew).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "hemlock",
                        "manual_falling_dbh_cm": 32.5,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_ecologger_tn173",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "tn173-ecologger",
                        "skyline_pieces_per_cycle": 2.9,
                        "skyline_piece_volume_m3": 0.34,
                        "skyline_crew_size": 4.0,
                    },
                ),
                SystemJob("processing", "hand_buck_or_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_micro_gabriel": HarvestSystem(
            system_id="cable_micro_gabriel",
            environment="cable-short-span skyline",
            notes="TN173 Gabriel truck yarder (0.16 m³ pieces, skid-pan highlead, road-portable).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "hemlock",
                        "manual_falling_dbh_cm": 32.5,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_gabriel_tn173",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "tn173-gabriel",
                        "skyline_pieces_per_cycle": 2.2,
                        "skyline_piece_volume_m3": 0.16,
                        "skyline_crew_size": 4.0,
                    },
                ),
                SystemJob("processing", "hand_buck_or_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_micro_christie": HarvestSystem(
            system_id="cable_micro_christie",
            environment="cable-short-span skyline",
            notes="TN173 Christie tower yarder hot-yarding (0.49 m³ pieces, two-person crew).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "hemlock",
                        "manual_falling_dbh_cm": 34.0,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_christie_tn173",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "tn173-christie",
                        "skyline_pieces_per_cycle": 1.3,
                        "skyline_piece_volume_m3": 0.49,
                        "skyline_crew_size": 2.0,
                    },
                ),
                SystemJob("processing", "hand_buck_or_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_micro_teletransporteur": HarvestSystem(
            system_id="cable_micro_teletransporteur",
            environment="cable-short-span skyline",
            notes="TN173 Télétransporteur self-propelled carriage (0.21 m³ pieces, two-person chaser/faller crew).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "hemlock",
                        "manual_falling_dbh_cm": 30.0,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_teletransporteur_tn173",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "tn173-teletransporteur",
                        "skyline_pieces_per_cycle": 3.9,
                        "skyline_piece_volume_m3": 0.21,
                        "skyline_crew_size": 2.0,
                    },
                ),
                SystemJob("processing", "hand_buck_or_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_micro_timbermaster": HarvestSystem(
            system_id="cable_micro_timbermaster",
            environment="cable-short-span skyline",
            notes="TN173 Smith Timbermaster downhill skyline (0.54 m³ pieces, trailer tower).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "hemlock",
                        "manual_falling_dbh_cm": 35.0,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_timbermaster_tn173",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "tn173-timbermaster-1985",
                        "skyline_pieces_per_cycle": 2.2,
                        "skyline_piece_volume_m3": 0.54,
                        "skyline_crew_size": 4.0,
                    },
                ),
                SystemJob("processing", "hand_buck_or_processor", ["primary_transport"]),
                SystemJob("loading", "loader", ["processing"]),
            ],
        ),
        "cable_micro_hi_skid": HarvestSystem(
            system_id="cable_micro_hi_skid",
            environment="cable-short-span skyline",
            notes="FERIC FNG73 Hi-Skid truck (100 m reach, self-loading/hauling).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "hemlock",
                        "manual_falling_dbh_cm": 22.5,
                    },
                ),
                SystemJob(
                    "primary_transport",
                    "skyline_hi_skid",
                    ["felling"],
                    productivity_overrides={
                        "skyline_model": "hi-skid",
                        "skyline_pieces_per_cycle": 1.0,
                        "skyline_piece_volume_m3": 0.24,
                        "skyline_crew_size": 1.0,
                    },
                ),
            ],
        ),
        "cable_salvage_grapple": HarvestSystem(
            system_id="cable_salvage_grapple",
            environment="cable-running salvage",
            notes="ADV1N5 salvage workflow for burned slopes (parallel bunching + grapple yarding, charcoal handling, portable mill prep).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_or_mech_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "douglas_fir",
                        "manual_falling_dbh_cm": 40.0,
                    },
                ),
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
        "helicopter": HarvestSystem(
            system_id="helicopter",
            environment="helicopter",
            notes="Hand fallers → helicopter longline → landing/hand buck (or direct to water).",
            jobs=[
                SystemJob(
                    "felling",
                    "hand_faller",
                    [],
                    productivity_overrides={
                        "manual_falling_enabled": True,
                        "manual_falling_species": "cedar",
                        "manual_falling_dbh_cm": 52.5,
                    },
                ),
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
        job_role = job.machine_role
        role_matches = job_role == normalized
        if not role_matches:
            if normalized == "skyline_yarder" and job_role.startswith("skyline_"):
                role_matches = True
            elif normalized == "grapple_yarder" and job_role.startswith("grapple_yarder"):
                role_matches = True
        if role_matches and job.productivity_overrides:
            return dict(job.productivity_overrides)
    return None


_ROAD_SOIL_PROFILES = ("fnrb3_d7h", "adv4n7_compaction")

SYSTEM_ROAD_DEFAULTS: dict[str, dict[str, object]] = {
    "cable_running": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 150.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_highlead_tn147": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 120.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_running_tr122_extended": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 130.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_running_tr122_shelterwood": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 140.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_running_tr122_clearcut": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 110.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_standing": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 90.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_standing_tr125_single": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 95.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_standing_tr125_strip": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 110.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_partial_tr127_block1": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 100.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_partial_tr127_block5": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 120.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_running_adv5n28_clearcut": {
        "machine_slug": "american_750c_line_dipper_shovel",
        "road_length_m": 420.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_running_adv5n28_shelterwood": {
        "machine_slug": "american_750c_line_dipper_shovel",
        "road_length_m": 320.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_running_fncy12": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 220.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_running_sr54": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 130.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_running_tr75_bunched": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 110.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_running_tr75_handfelled": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 110.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_salvage_grapple": {
        "machine_slug": "caterpillar_235_hydraulic_backhoe",
        "road_length_m": 160.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_micro_ecologger": {
        "machine_slug": "caterpillar_d8h_bulldozer",
        "road_length_m": 60.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_micro_gabriel": {
        "machine_slug": "caterpillar_d8h_bulldozer",
        "road_length_m": 60.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_micro_christie": {
        "machine_slug": "caterpillar_d8h_bulldozer",
        "road_length_m": 60.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_micro_teletransporteur": {
        "machine_slug": "caterpillar_d8h_bulldozer",
        "road_length_m": 60.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_micro_timbermaster": {
        "machine_slug": "caterpillar_d8h_bulldozer",
        "road_length_m": 60.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
    "cable_micro_hi_skid": {
        "machine_slug": "caterpillar_d8h_bulldozer",
        "road_length_m": 45.0,
        "include_mobilisation": True,
        "soil_profile_ids": list(_ROAD_SOIL_PROFILES),
    },
}


def get_system_road_defaults(system_id: str) -> Mapping[str, object] | None:
    defaults = SYSTEM_ROAD_DEFAULTS.get(system_id)
    if defaults is None:
        return None
    return dict(defaults)


__all__ = [
    "SystemJob",
    "HarvestSystem",
    "default_system_registry",
    "system_productivity_overrides",
    "get_system_road_defaults",
]
