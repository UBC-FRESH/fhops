"""Dataset inspection CLI commands."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from functools import lru_cache
from typing import Any

from click.core import ParameterSource
import typer
from rich import box
from rich.console import Console
from rich.table import Table

from fhops.core import FHOPSValueError
from fhops.costing import (
    MachineCostEstimate,
    estimate_unit_cost_from_distribution,
    estimate_unit_cost_from_stand,
)
from fhops.costing.inflation import TARGET_YEAR, inflate_value
from fhops.costing.machine_rates import (
    MachineRate,
    compose_default_rental_rate_for_role,
    get_machine_rate,
    load_machine_rate_index,
    select_usage_class_multiplier,
)
from fhops.productivity import (
    ALPACASlopeClass,
    ForwarderBCModel,
    ForwarderBCResult,
    Han2018SkidderMethod,
    TrailSpacingPattern,
    DeckingCondition,
    ADV6N7DeckingMode,
    LahrsenModel,
    ADV6N10HarvesterInputs,
    TN292HarvesterInputs,
    SkidderProductivityResult,
    SkidderSpeedProfile,
    ADV6N7SkidderResult,
    ShovelLoggerSessions2006Inputs,
    ShovelLoggerResult,
    HelicopterLonglineModel,
    HelicopterProductivityResult,
    alpaca_slope_multiplier,
    estimate_grapple_skidder_productivity_han2018,
    estimate_grapple_skidder_productivity_adv6n7,
    estimate_cable_skidder_productivity_adv1n12_full_tree,
    estimate_cable_skidder_productivity_adv1n12_two_phase,
    get_skidder_speed_profile,
    estimate_harvester_productivity_adv5n30,
    estimate_harvester_productivity_tn292,
    estimate_helicopter_longline_productivity,
    estimate_cable_skidding_productivity_unver_robust,
    estimate_cable_skidding_productivity_unver_robust_profile,
    estimate_cable_skidding_productivity_unver_spss,
    estimate_cable_skidding_productivity_unver_spss_profile,
    estimate_cable_yarder_cycle_time_tr127_minutes,
    estimate_cable_yarder_productivity_lee2018_downhill,
    estimate_cable_yarder_productivity_lee2018_uphill,
    estimate_cable_yarder_cycle_time_tr125_single_span,
    estimate_cable_yarder_cycle_time_tr125_multi_span,
    estimate_cable_yarder_productivity_tr125_multi_span,
    estimate_cable_yarder_productivity_tr125_single_span,
    estimate_cable_yarder_productivity_tr127,
    estimate_grapple_yarder_productivity_sr54,
    estimate_grapple_yarder_productivity_tr75_bunched,
    estimate_grapple_yarder_productivity_tr75_handfelled,
    estimate_grapple_yarder_productivity_tn157,
    estimate_grapple_yarder_productivity_adv1n35,
    estimate_grapple_yarder_productivity_adv1n40,
    estimate_grapple_yarder_productivity_tn147,
    estimate_grapple_yarder_productivity_tr122,
    estimate_grapple_yarder_productivity_adv5n28,
    get_tn157_case,
    get_adv1n35_metadata,
    get_adv1n40_metadata,
    get_adv6n7_metadata,
    get_tn147_case,
    get_tr122_treatment,
    get_adv5n28_block,
    list_tn157_case_ids,
    list_tn147_case_ids,
    list_tr122_treatment_ids,
    TN157Case,
    TN147Case,
    TR122Treatment,
    ADV5N28Block,
    ADV1N35Metadata,
    estimate_standing_skyline_productivity_aubuchon1979,
    estimate_standing_skyline_turn_time_aubuchon1979,
    estimate_standing_skyline_productivity_kramer1978,
    estimate_standing_skyline_turn_time_kramer1978,
    estimate_standing_skyline_productivity_kellogg1976,
    estimate_standing_skyline_turn_time_kellogg1976,
    estimate_running_skyline_cycle_time_mcneel2000_minutes,
    estimate_running_skyline_productivity_mcneel2000,
    estimate_residue_cycle_time_ledoux_minutes,
    estimate_residue_productivity_ledoux_m3_per_pmh,
    estimate_micro_master_productivity_m3_per_pmh,
    estimate_hi_skid_productivity_m3_per_pmh,
    get_tn173_system,
    ledoux_delay_component_minutes,
    running_skyline_variant_defaults,
    Fncy12ProductivityVariant,
    estimate_tmy45_productivity_fncy12,
    estimate_forwarder_productivity_bc,
    estimate_harvester_productivity_adv6n10,
    estimate_harvester_productivity_kellogg1994,
    estimate_productivity,
    estimate_productivity_distribution,
    estimate_shovel_logger_productivity_sessions2006,
    load_lahrsen_ranges,
    ProcessorProductivityResult,
    estimate_processor_productivity_berry2019,
    Labelle2016ProcessorProductivityResult,
    estimate_processor_productivity_labelle2016,
    Labelle2017PolynomialProcessorResult,
    Labelle2017PowerProcessorResult,
    Labelle2018ProcessorProductivityResult,
    estimate_processor_productivity_labelle2017,
    estimate_processor_productivity_labelle2018,
    VisserLogSortProductivityResult,
    Hypro775ProcessorProductivityResult,
    Spinelli2010ProcessorProductivityResult,
    Bertone2025ProcessorProductivityResult,
    Borz2023ProcessorProductivityResult,
    Nakagawa2010ProcessorProductivityResult,
    ADV5N6ProcessorProductivityResult,
    ADV7N3ProcessorProductivityResult,
    TN103ProcessorProductivityResult,
    TR106ProcessorProductivityResult,
    TN166ProcessorProductivityResult,
    TR87ProcessorProductivityResult,
    estimate_processor_productivity_adv5n6,
    estimate_processor_productivity_adv7n3,
    estimate_processor_productivity_tn103,
    estimate_processor_productivity_tr106,
    estimate_processor_productivity_tn166,
    estimate_processor_productivity_tr87,
    estimate_processor_productivity_visser2015,
    estimate_processor_productivity_hypro775,
    estimate_processor_productivity_spinelli2010,
    estimate_processor_productivity_bertone2025,
    estimate_processor_productivity_borz2023,
    estimate_processor_productivity_nakagawa2010,
    predict_berry2019_skid_effects,
    Labelle2019ProcessorProductivityResult,
    estimate_processor_productivity_labelle2019_dbh,
    Labelle2019VolumeProcessorProductivityResult,
    estimate_processor_productivity_labelle2019_volume,
    LoaderForwarderProductivityResult,
    estimate_loader_forwarder_productivity_tn261,
    estimate_loader_forwarder_productivity_adv5n1,
    LoaderAdv5N1ProductivityResult,
    LoaderBarko450ProductivityResult,
    ProcessorCarrierProfile,
    LoaderHotColdProductivityResult,
    estimate_loader_productivity_barko450,
    get_processor_carrier_profile,
    estimate_loader_hot_cold_productivity,
    ADV5N1_DEFAULT_PAYLOAD_M3,
    ADV5N1_DEFAULT_UTILISATION,
    ClambunkProductivityResult,
    estimate_clambunk_productivity_adv2n26,
    ADV2N26_DEFAULT_TRAVEL_EMPTY_M,
    ADV2N26_DEFAULT_STEMS_PER_CYCLE,
    ADV2N26_DEFAULT_STEM_VOLUME_M3,
    ADV2N26_DEFAULT_UTILISATION,
    BerryLogGradeStat,
    get_berry_log_grade_metadata,
    get_berry_log_grade_stats,
    get_labelle_huss_automatic_bucking_adjustment,
)
from fhops.reference import (
    ADV2N21StandSnapshot,
    TN98DiameterRecord,
    TN82Dataset,
    get_appendix5_profile,
    get_tr119_treatment,
    get_tr28_source_metadata,
    get_soil_profile,
    get_soil_profiles,
    adv2n21_cost_base_year,
    get_adv2n21_treatment,
    load_adv2n21_treatments,
    load_appendix5_stands,
    load_tr28_machines,
    load_soil_profiles,
    TR28CostEstimate,
    SoilProfile,
    estimate_tr28_road_cost,
    load_tn98_dataset,
    load_tn82_dataset,
    TR28Machine,
    load_unbc_hoe_chucking_data,
    load_unbc_processing_costs,
    load_unbc_construction_costs,
    load_adv6n25_dataset,
    load_fncy12_dataset,
)
from fhops.productivity.cable_logging import HI_SKID_DEFAULTS
from fhops.scenario.contract import Machine, RoadConstruction, SalvageProcessingMode, Scenario
from fhops.scenario.io import load_scenario
from fhops.scheduling.systems import (
    HarvestSystem,
    default_system_registry,
    system_productivity_overrides,
)
from fhops.telemetry import append_jsonl
from fhops.telemetry.machine_costs import build_machine_cost_snapshots
from fhops.validation.ranges import validate_block_ranges

def _get_tmy45_support_ratios() -> dict[str, float]:
    """Return Cat D8 / Timberjack utilisation ratios per yarder SMH."""

    dataset = load_fncy12_dataset()
    cat_ratio = dataset.support_cat_d8_ratio
    timber_ratio = dataset.support_timberjack_ratio
    if cat_ratio is None or timber_ratio is None:
        return {
            "cat_d8_smhr_per_yarder_smhr": 0.25,
            "timberjack_450_smhr_per_yarder_smhr": 0.14,
        }
    return {
        "cat_d8_smhr_per_yarder_smhr": float(cat_ratio),
        "timberjack_450_smhr_per_yarder_smhr": float(timber_ratio),
    }


_TN258_LATERAL_LIMIT_M = 30.0
_TN258_MAX_SKYLINE_TENSION_KN = 147.0
_TN98_SPECIES = ("cedar", "douglas_fir", "hemlock", "all_species")
_AUBUCHON_SLOPE_M_RANGE = (304.8, 914.4)
_AUBUCHON_LATERAL_M_RANGE = (15.24, 45.72)
_AUBUCHON_LOGS_RANGE = (3.5, 6.0)
_AUBUCHON_CREW_RANGE = (4.0, 5.0)
_AUBUCHON_RANGE_TEXT = (
    "Hensel et al. (1977) Wyssen trials: slope 305–914 m (1 000–3 000 ft); lateral 15–46 m "
    "(50–150 ft); logs/turn 3.5–6; crew size 4–5; slopes 45–75 %."
)
_KRAMER_CHORDSLOPE_RANGE = (-22.0, 3.0)
_KRAMER_RANGE_TEXT = (
    "Kramer (1978) standing skyline: chord slopes observed between −22% (downhill) and +3% "
    "(slight uphill); other predictors followed the Skagit/Koller multi-span trials."
)
_KELLOGG_LEAD_ANGLE_RANGE = (-90.0, 90.0)
_KELLOGG_CHOKERS_RANGE = (1.0, 2.0)
_KELLOGG_RANGE_TEXT = (
    "Kellogg (1976) tower yarder: lead angles ±90° (log vs. skyline) and 1–2 chokers per turn "
    "during the coastal Oregon trials."
)

console = Console()
dataset_app = typer.Typer(help="Inspect FHOPS datasets and bundled examples.")

_LOADER_METADATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "productivity" / "loader_models.json"
)


@lru_cache(maxsize=None)
def _load_loader_model_metadata() -> dict[str, Any]:
    try:
        return json.loads(_LOADER_METADATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:  # pragma: no cover - defensive
        return {}


def _loader_model_metadata(model: LoaderProductivityModel | None) -> dict[str, Any] | None:
    if model is None:
        return None
    data = _load_loader_model_metadata()
    return data.get(model.value)


def _append_loader_telemetry(
    *,
    log_path: Path,
    model: LoaderProductivityModel,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "command": "dataset estimate-productivity",
        "machine_role": "loader",
        "loader_model": model.value,
        "inputs": inputs,
        "outputs": outputs,
    }
    if metadata:
        payload["metadata"] = metadata
    append_jsonl(log_path, payload)


def _extract_preset_costs(meta: Mapping[str, Any] | None) -> dict[str, float] | None:
    if not meta:
        return None
    costs: dict[str, float] = {}
    base_year = meta.get("cost_base_year")
    cost_per_m3 = meta.get("cost_per_m3")
    if base_year and isinstance(cost_per_m3, (int, float)):
        costs["observed_cost_per_m3_cad_base"] = float(cost_per_m3)
        costs["observed_cost_per_m3_cad_2024"] = float(inflate_value(cost_per_m3, int(base_year)))
    cost_per_log = meta.get("cost_per_log")
    if base_year and isinstance(cost_per_log, (int, float)):
        costs["observed_cost_per_log_cad_base"] = float(cost_per_log)
        costs["observed_cost_per_log_cad_2024"] = float(inflate_value(cost_per_log, int(base_year)))
    projected = meta.get("projected_cost_per_m3")
    projected_target = meta.get("projected_cost_per_m3_target")
    if isinstance(projected, (int, float)):
        costs["projected_cost_per_m3_cad_base"] = float(projected)
        if isinstance(projected_target, (int, float)):
            costs["projected_cost_per_m3_cad_2024"] = float(projected_target)
    heli = meta.get("helicopter_cost_per_m3")
    heli_target = meta.get("helicopter_cost_per_m3_target")
    if isinstance(heli, (int, float)):
        costs["helicopter_cost_per_m3_cad_base"] = float(heli)
        if isinstance(heli_target, (int, float)):
            costs["helicopter_cost_per_m3_cad_2024"] = float(heli_target)
    return costs or None


def _append_grapple_yarder_telemetry(
    *,
    log_path: Path,
    model: GrappleYarderModel,
    inputs: Mapping[str, Any],
    productivity_m3_per_pmh: float,
    preset_meta: Mapping[str, Any] | None,
) -> None:
    payload: dict[str, Any] = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "command": "dataset estimate-productivity",
        "machine_role": "grapple_yarder",
        "grapple_model": model.value,
        "inputs": dict(inputs),
        "outputs": {
            "productivity_m3_per_pmh": productivity_m3_per_pmh,
            "costs": _extract_preset_costs(preset_meta),
        },
    }
    if preset_meta:
        preset_summary: dict[str, Any] = {}
        for key in ("label", "note", "cost_base_year"):
            if key in preset_meta:
                preset_summary[key] = preset_meta[key]
        if preset_summary:
            payload["preset"] = preset_summary
    append_jsonl(log_path, payload)


def _apply_loader_system_defaults(
    *,
    system: HarvestSystem | None,
    loader_model: LoaderProductivityModel,
    loader_model_supplied: bool,
    piece_size_m3: float | None,
    piece_size_supplied: bool,
    external_distance_m: float | None,
    distance_supplied: bool,
    payload_m3: float,
    payload_supplied: bool,
    slope_percent: float,
    slope_supplied: bool,
    bunched: bool,
    bunched_supplied: bool,
    delay_multiplier: float,
    delay_supplied: bool,
    travel_empty_m: float,
    travel_supplied: bool,
    stems_per_cycle: float,
    stems_supplied: bool,
    stem_volume_m3: float,
    stem_volume_supplied: bool,
    utilisation: float | None,
    utilisation_supplied: bool,
    in_cycle_delay_minutes: float | None,
    in_cycle_supplied: bool,
    slope_class: LoaderAdv5N1SlopeClass,
    slope_class_supplied: bool,
    barko_scenario: LoaderBarkoScenario,
    barko_scenario_supplied: bool,
    hot_cold_mode: LoaderHotColdMode,
    hot_cold_mode_supplied: bool,
) -> tuple[
    LoaderProductivityModel,
    float | None,
    float | None,
    float,
    float,
    bool,
    float,
    float,
    float,
    float,
    float | None,
    float | None,
    LoaderAdv5N1SlopeClass,
    LoaderBarkoScenario,
    LoaderHotColdMode,
    bool,
]:
    if system is None:
        return (
            loader_model,
            piece_size_m3,
            external_distance_m,
            payload_m3,
            slope_percent,
            bunched,
            delay_multiplier,
            travel_empty_m,
            stems_per_cycle,
            stem_volume_m3,
            utilisation,
            in_cycle_delay_minutes,
            slope_class,
            barko_scenario,
            hot_cold_mode,
            False,
        )
    overrides = system_productivity_overrides(system, ProductivityMachineRole.LOADER.value)
    if not overrides:
        return (
            loader_model,
            piece_size_m3,
            external_distance_m,
            payload_m3,
            slope_percent,
            bunched,
            delay_multiplier,
            travel_empty_m,
            stems_per_cycle,
            stem_volume_m3,
            utilisation,
            in_cycle_delay_minutes,
            slope_class,
            barko_scenario,
            hot_cold_mode,
            False,
        )
    used = False

    def maybe_float(
        key: str,
        current: float | None,
        supplied_flag: bool,
        *,
        allow_zero: bool = False,
        allow_negative: bool = False,
        max_value: float | None = None,
    ) -> tuple[float | None, bool]:
        if supplied_flag:
            return current, False
        value = overrides.get(key)
        if value is None:
            return current, False
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid loader override for '{key}': {value}") from exc
        if not allow_negative:
            if allow_zero:
                if coerced < 0:
                    raise ValueError(f"Loader override '{key}' must be ≥ 0 (got {coerced}).")
            else:
                if coerced <= 0:
                    raise ValueError(f"Loader override '{key}' must be > 0 (got {coerced}).")
        if max_value is not None and coerced > max_value:
            raise ValueError(f"Loader override '{key}' must be ≤ {max_value} (got {coerced}).")
        return coerced, True

    def maybe_bool(key: str, current: bool, supplied_flag: bool) -> tuple[bool, bool]:
        if supplied_flag:
            return current, False
        value = overrides.get(key)
        if value is None:
            return current, False
        if isinstance(value, bool):
            return value, True
        if isinstance(value, (int, float)):
            return bool(value), True
        if isinstance(value, str):
            normalized = value.strip().lower()
            truthy = {"true", "1", "yes", "y", "bunched", "mechanised", "mechanized", "machine"}
            falsy = {"false", "0", "no", "n", "hand", "scattered"}
            if normalized in truthy:
                return True, True
            if normalized in falsy:
                return False, True
        raise ValueError(f"Invalid loader override for '{key}': {value}")

    value = overrides.get("loader_model")
    if value is not None and not loader_model_supplied:
        try:
            loader_model = LoaderProductivityModel(str(value))
            used = True
        except ValueError as exc:  # pragma: no cover - validated via docs/tests
            raise ValueError(f"Unknown loader model override '{value}'.") from exc

    piece_size_m3, changed = maybe_float("loader_piece_size_m3", piece_size_m3, piece_size_supplied)
    used |= changed
    external_distance_m, changed = maybe_float(
        "loader_distance_m", external_distance_m, distance_supplied
    )
    used |= changed
    payload_m3, changed = maybe_float("loader_payload_m3", payload_m3, payload_supplied)
    used |= changed
    slope_percent, changed = maybe_float(
        "loader_slope_percent",
        slope_percent,
        slope_supplied,
        allow_zero=True,
        allow_negative=True,
    )
    used |= changed
    bunched, changed = maybe_bool("loader_bunched", bunched, bunched_supplied)
    used |= changed
    delay_multiplier, changed = maybe_float(
        "loader_delay_multiplier",
        delay_multiplier,
        delay_supplied,
        max_value=1.0,
    )
    used |= changed
    travel_empty_m, changed = maybe_float("loader_travel_empty_m", travel_empty_m, travel_supplied)
    used |= changed
    stems_per_cycle, changed = maybe_float(
        "loader_stems_per_cycle", stems_per_cycle, stems_supplied
    )
    used |= changed
    stem_volume_m3, changed = maybe_float(
        "loader_stem_volume_m3", stem_volume_m3, stem_volume_supplied
    )
    used |= changed
    utilisation, changed = maybe_float(
        "loader_utilisation",
        utilisation,
        utilisation_supplied,
        max_value=1.0,
    )
    used |= changed
    in_cycle_delay_minutes, changed = maybe_float(
        "loader_in_cycle_delay_minutes",
        in_cycle_delay_minutes,
        in_cycle_supplied,
        allow_zero=True,
    )
    used |= changed
    value = overrides.get("loader_slope_class")
    if value is not None and not slope_class_supplied:
        try:
            slope_class = LoaderAdv5N1SlopeClass(str(value))
            used = True
        except ValueError as exc:  # pragma: no cover - validated via docs/tests
            raise ValueError(f"Unknown loader slope-class override '{value}'.") from exc

    value = overrides.get("loader_barko_scenario")
    if value is not None and not barko_scenario_supplied:
        try:
            barko_scenario = LoaderBarkoScenario(str(value))
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown loader Barko scenario override '{value}'.") from exc

    value = overrides.get("loader_hot_cold_mode")
    if value is not None and not hot_cold_mode_supplied:
        try:
            hot_cold_mode = LoaderHotColdMode(str(value))
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown loader hot/cold mode override '{value}'.") from exc

    return (
        loader_model,
        piece_size_m3,
        external_distance_m,
        payload_m3,
        slope_percent,
        bunched,
        delay_multiplier,
        travel_empty_m,
        stems_per_cycle,
        stem_volume_m3,
        utilisation,
        in_cycle_delay_minutes,
        slope_class,
        barko_scenario,
        hot_cold_mode,
        used,
    )


def _derive_cost_role_override(
    machine_role: str | None, overrides: Mapping[str, float | str] | None
) -> str | None:
    if machine_role != "loader" or not overrides:
        return None
    model_value = overrides.get("loader_model")
    if model_value is None:
        return None
    if isinstance(model_value, str):
        key = model_value.lower()
    else:
        key = str(model_value).lower()
    return _LOADER_MODEL_COST_ROLES.get(key)


def _grapple_yarder_cost_role(model: GrappleYarderModel) -> str:
    return _GRAPPLE_YARDER_COST_ROLES.get(model, "grapple_yarder")


def _machine_rate_roles_help() -> str:
    roles = ", ".join(sorted(load_machine_rate_index().keys()))
    return f"Available roles: {roles}"


def _resolve_machine_rate(role: str) -> MachineRate:
    rate = get_machine_rate(role)
    if rate is None:
        available = ", ".join(sorted(load_machine_rate_index().keys()))
        raise typer.BadParameter(f"Unknown machine role '{role}'. Valid roles: {available}")
    return rate


@dataclass(frozen=True)
class DatasetRef:
    name: str
    path: Path


KNOWN_DATASETS: dict[str, DatasetRef] = {
    "minitoy": DatasetRef("minitoy", Path("examples/minitoy/scenario.yaml")),
    "small21": DatasetRef("small21", Path("examples/small21/scenario.yaml")),
    "med42": DatasetRef("med42", Path("examples/med42/scenario.yaml")),
    "large84": DatasetRef("large84", Path("examples/large84/scenario.yaml")),
    "synthetic-small": DatasetRef(
        "synthetic-small", Path("examples/synthetic/small/scenario.yaml")
    ),
    "synthetic-medium": DatasetRef(
        "synthetic-medium", Path("examples/synthetic/medium/scenario.yaml")
    ),
    "synthetic-large": DatasetRef(
        "synthetic-large", Path("examples/synthetic/large/scenario.yaml")
    ),
}


class ProductivityMachineRole(str, Enum):
    """Machine roles supported by the productivity command."""

    FELLER_BUNCHER = "feller_buncher"
    FORWARDER = "forwarder"
    CTL_HARVESTER = "ctl_harvester"
    GRAPPLE_SKIDDER = "grapple_skidder"
    GRAPPLE_YARDER = "grapple_yarder"
    ROADSIDE_PROCESSOR = "roadside_processor"
    LOADER = "loader"
    SHOVEL_LOGGER = "shovel_logger"
    HELICOPTER_LONGLINE = "helicopter_longline"


class ShovelSlopeClass(str, Enum):
    DOWNHILL = "downhill"
    LEVEL = "level"
    UPHILL = "uphill"


class ShovelBunching(str, Enum):
    FELLER_BUNCHED = "feller_bunched"
    HAND_SCATTERED = "hand_scattered"


class CTLHarvesterModel(str, Enum):
    """CTL harvester regressions."""

    ADV6N10 = "adv6n10"
    ADV5N30 = "adv5n30"
    TN292 = "tn292"
    KELLOGG1994 = "kellogg1994"


class CableSkiddingModel(str, Enum):
    """Ünver-Okan cable skidding regressions."""

    UNVER_SPSS = "unver-spss"
    UNVER_ROBUST = "unver-robust"


class GrappleYarderModel(str, Enum):
    """Supported grapple yarder regressions."""

    SR54 = "sr54"
    TR75_BUNCHED = "tr75-bunched"
    TR75_HANDFELLED = "tr75-handfelled"
    ADV1N35 = "adv1n35"
    ADV1N40 = "adv1n40"
    TN157 = "tn157"
    TN147 = "tn147"
    TR122_EXTENDED = "tr122-extended"
    TR122_SHELTERWOOD = "tr122-shelterwood"
    TR122_CLEARCUT = "tr122-clearcut"
    ADV5N28_CLEARCUT = "adv5n28-clearcut"
    ADV5N28_SHELTERWOOD = "adv5n28-shelterwood"


_TR122_MODEL_TO_TREATMENT: dict[GrappleYarderModel, str] = {
    GrappleYarderModel.TR122_EXTENDED: "extended_rotation",
    GrappleYarderModel.TR122_SHELTERWOOD: "uniform_shelterwood",
    GrappleYarderModel.TR122_CLEARCUT: "clearcut",
}

_ADV5N28_MODEL_TO_BLOCK: dict[GrappleYarderModel, str] = {
    GrappleYarderModel.ADV5N28_CLEARCUT: "block_1_clearcut_with_reserves",
    GrappleYarderModel.ADV5N28_SHELTERWOOD: "block_2_irregular_shelterwood",
}

_GRAPPLE_YARDER_COST_ROLES: dict[GrappleYarderModel, str] = {
    GrappleYarderModel.TN147: "grapple_yarder_madill009",
    GrappleYarderModel.TN157: "grapple_yarder_cypress7280",
    GrappleYarderModel.ADV5N28_CLEARCUT: "grapple_yarder_adv5n28",
    GrappleYarderModel.ADV5N28_SHELTERWOOD: "grapple_yarder_adv5n28",
}

def _tn157_case_choices() -> tuple[str, ...]:
    return list_tn157_case_ids()


def _tn157_case_help_text() -> str:
    numeric = ", ".join(cid for cid in _tn157_case_choices() if cid != "combined")
    return (
        "TN157 case identifier (combined, "
        f"{numeric}) when selecting --grapple-yarder-model tn157. "
        "Ignored for other models."
    )


def _normalize_tn157_case(case_id: str | None) -> str:
    candidate = (case_id or "combined").strip().lower()
    if candidate in {"", "combined", "avg", "average"}:
        return "combined"
    if candidate.startswith("case"):
        candidate = candidate[4:].strip()
    choices = set(_tn157_case_choices())
    if candidate not in choices:
        raise ValueError(
            f"TN157 case must be one of {', '.join(sorted(choices))}; received '{case_id}'."
        )
    return candidate


def _tn147_case_choices() -> tuple[str, ...]:
    return list_tn147_case_ids()


def _tn147_case_help_text() -> str:
    numeric = ", ".join(cid for cid in _tn147_case_choices() if cid != "combined")
    return (
        "TN147 case identifier (combined, "
        f"{numeric}) when selecting --grapple-yarder-model tn147. "
        "Ignored for other models."
    )


def _normalize_tn147_case(case_id: str | None) -> str:
    candidate = (case_id or "combined").strip().lower()
    if candidate in {"", "combined", "avg", "average"}:
        return "combined"
    if candidate.startswith("case"):
        candidate = candidate[4:].strip()
    choices = set(_tn147_case_choices())
    if candidate not in choices:
        raise ValueError(
            f"TN147 case must be one of {', '.join(sorted(choices))}; received '{case_id}'."
        )
    return candidate


def _tr28_machine_slugs() -> tuple[str, ...]:
    return tuple(sorted(machine.slug for machine in load_tr28_machines()))


def _resolve_tr28_machine(identifier: str) -> TR28Machine | None:
    candidate = identifier.strip().lower()
    slug_candidate = candidate.replace(" ", "_")
    for machine in load_tr28_machines():
        if candidate == machine.machine_name.lower() or slug_candidate == machine.slug:
            return machine
    return None


def _format_currency(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _tn98_species_choices() -> tuple[str, ...]:
    return _TN98_SPECIES


def _interpolate_tn98_value(
    records: Sequence[TN98DiameterRecord], dbh_cm: float, attr: str
) -> float | None:
    candidates = [record for record in records if getattr(record, attr) is not None]
    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda record: record.dbh_cm)
    if dbh_cm <= ordered[0].dbh_cm:
        return getattr(ordered[0], attr)
    if dbh_cm >= ordered[-1].dbh_cm:
        return getattr(ordered[-1], attr)
    lower = ordered[0]
    for upper in ordered[1:]:
        if dbh_cm <= upper.dbh_cm:
            lower_value = getattr(lower, attr)
            upper_value = getattr(upper, attr)
            if lower_value is None:
                return upper_value
            if upper_value is None:
                return lower_value
            span = upper.dbh_cm - lower.dbh_cm
            ratio = 0.0 if span == 0 else (dbh_cm - lower.dbh_cm) / span
            return lower_value + ratio * (upper_value - lower_value)
        lower = upper
    return getattr(ordered[-1], attr)


def _closest_tn98_record(
    records: Sequence[TN98DiameterRecord], dbh_cm: float
) -> TN98DiameterRecord | None:
    if not records:
        return None
    return min(records, key=lambda record: abs(record.dbh_cm - dbh_cm))


def _normalise_tn98_species_value(value: str) -> str:
    candidate = value.strip().lower().replace("-", "_")
    if candidate not in _TN98_SPECIES:
        raise ValueError(
            f"Unknown TN98 species '{value}'. Choose from {', '.join(_TN98_SPECIES)}."
        )
    return candidate


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Cannot interpret boolean value from '{value}'.")


def _manual_falling_overrides(system: HarvestSystem | None) -> dict[str, float | str] | None:
    if system is None:
        return None
    overrides = system_productivity_overrides(system, "hand_faller")
    if overrides:
        return overrides
    return system_productivity_overrides(system, "hand_or_mech_faller")


def _estimate_tn98_manual_falling(species: str, dbh_cm: float) -> dict[str, Any]:
    dataset = load_tn98_dataset()
    regression = dataset.regressions.get(species) or dataset.regressions.get("all_species")
    if regression is None:
        raise ValueError(f"TN98 regression missing for species '{species}'.")
    cut_minutes = max(
        0.0, regression.intercept_minutes + regression.slope_minutes_per_cm * dbh_cm
    )
    records = dataset.per_diameter_class.get(species) or dataset.per_diameter_class.get(
        "douglas_fir", ()
    )
    limb_minutes = _interpolate_tn98_value(records, dbh_cm, "limb_buck_minutes") or 0.0
    volume_m3 = _interpolate_tn98_value(records, dbh_cm, "volume_m3")
    cost_per_tree = _interpolate_tn98_value(records, dbh_cm, "cost_per_tree_cad")
    cost_per_m3 = _interpolate_tn98_value(records, dbh_cm, "cost_per_m3_cad")
    fixed_minutes = float(dataset.time_distribution.get("fixed_time_minutes_per_tree") or 0.0)
    nearest = _closest_tn98_record(records, dbh_cm)
    total_minutes = cut_minutes + limb_minutes + fixed_minutes
    currency = dataset.source.get("currency")
    base_year: int | None = None
    if isinstance(currency, str) and "_" in currency:
        suffix = currency.split("_")[-1]
        if suffix.isdigit():
            base_year = int(suffix)
    inflated_tree = (
        inflate_value(cost_per_tree, base_year) if (cost_per_tree is not None and base_year) else None
    )
    inflated_m3 = (
        inflate_value(cost_per_m3, base_year) if (cost_per_m3 is not None and base_year) else None
    )
    return {
        "species": species,
        "dbh_cm": dbh_cm,
        "cut_minutes": cut_minutes,
        "limb_minutes": limb_minutes,
        "fixed_minutes": fixed_minutes,
        "total_minutes": total_minutes,
        "volume_m3": volume_m3,
        "cost_per_tree_cad": cost_per_tree,
        "cost_per_m3_cad": cost_per_m3,
        "nearest_dbh_cm": nearest.dbh_cm if nearest else None,
        "nearest_tree_count": nearest.tree_count if nearest else None,
        "cost_base_year": base_year,
        "cost_per_tree_cad_2024": inflated_tree,
        "cost_per_m3_cad_2024": inflated_m3,
    }


class SkylineProductivityModel(str, Enum):
    """Supported skyline productivity regressions."""

    LEE_UPHILL = "lee-uphill"
    LEE_DOWNHILL = "lee-downhill"
    MCNEEL_RUNNING = "mcneel-running"
    TR125_SINGLE = "tr125-single-span"
    TR125_MULTI = "tr125-multi-span"
    TR127_BLOCK1 = "tr127-block1"
    TR127_BLOCK2 = "tr127-block2"
    TR127_BLOCK3 = "tr127-block3"
    TR127_BLOCK4 = "tr127-block4"
    TR127_BLOCK5 = "tr127-block5"
    TR127_BLOCK6 = "tr127-block6"
    AUBUCHON_STANDING = "aubuchon-standing"
    AUBUCHON_KRAMER = "aubuchon-kramer"
    AUBUCHON_KELLOGG = "aubuchon-kellogg"
    LEDOUX_SKAGIT_SHOTGUN = "ledoux-skagit-shotgun"
    LEDOUX_SKAGIT_HIGHLEAD = "ledoux-skagit-highlead"
    LEDOUX_WASHINGTON_208E = "ledoux-washington-208e"
    LEDOUX_TMY45 = "ledoux-tmy45"
    MICRO_MASTER = "micro-master"
    HI_SKID = "hi-skid"
    TN173_ECOLOGGER = "tn173-ecologger"
    TN173_GABRIEL = "tn173-gabriel"
    TN173_CHRISTIE = "tn173-christie"
    TN173_TELETRANSPORTEUR = "tn173-teletransporteur"
    TN173_TIMBERMASTER_1984 = "tn173-timbermaster-1984"
    TN173_TIMBERMASTER_1985 = "tn173-timbermaster-1985"
    FNCY12_TMY45 = "fncy12-tmy45"


_LEDOUX_MODEL_TO_PROFILE: dict[SkylineProductivityModel, str] = {
    SkylineProductivityModel.LEDOUX_SKAGIT_SHOTGUN: "skagit_shotgun",
    SkylineProductivityModel.LEDOUX_SKAGIT_HIGHLEAD: "skagit_highlead",
    SkylineProductivityModel.LEDOUX_WASHINGTON_208E: "washington_208e",
    SkylineProductivityModel.LEDOUX_TMY45: "tmy45",
}

_TN173_MODEL_TO_SYSTEM_ID: dict[SkylineProductivityModel, str] = {
    SkylineProductivityModel.TN173_ECOLOGGER: "tn173_ecologger",
    SkylineProductivityModel.TN173_GABRIEL: "tn173_gabriel",
    SkylineProductivityModel.TN173_CHRISTIE: "tn173_christie",
    SkylineProductivityModel.TN173_TELETRANSPORTEUR: "tn173_teletransporteur",
    SkylineProductivityModel.TN173_TIMBERMASTER_1984: "tn173_timbermaster_1984",
    SkylineProductivityModel.TN173_TIMBERMASTER_1985: "tn173_timbermaster_1985",
}

_SKYLINE_COST_ROLES: dict[SkylineProductivityModel, str] = {
    SkylineProductivityModel.TR125_SINGLE: "grapple_yarder_skyleadc40",
    SkylineProductivityModel.TR125_MULTI: "grapple_yarder_skyleadc40",
    SkylineProductivityModel.TR127_BLOCK1: "grapple_yarder_skyleadc40",
    SkylineProductivityModel.TR127_BLOCK2: "grapple_yarder_skyleadc40",
    SkylineProductivityModel.TR127_BLOCK3: "grapple_yarder_skyleadc40",
    SkylineProductivityModel.TR127_BLOCK4: "grapple_yarder_skyleadc40",
    SkylineProductivityModel.TR127_BLOCK5: "grapple_yarder_skyleadc40",
    SkylineProductivityModel.TR127_BLOCK6: "grapple_yarder_skyleadc40",
    SkylineProductivityModel.FNCY12_TMY45: "grapple_yarder_tmy45",
    SkylineProductivityModel.MCNEEL_RUNNING: "grapple_yarder_cypress7280",
    SkylineProductivityModel.TN173_ECOLOGGER: "skyline_ecologger_tn173",
    SkylineProductivityModel.TN173_GABRIEL: "skyline_gabriel_tn173",
    SkylineProductivityModel.TN173_CHRISTIE: "skyline_christie_tn173",
    SkylineProductivityModel.TN173_TELETRANSPORTEUR: "skyline_teletransporteur_tn173",
    SkylineProductivityModel.TN173_TIMBERMASTER_1984: "skyline_timbermaster_tn173",
    SkylineProductivityModel.TN173_TIMBERMASTER_1985: "skyline_timbermaster_tn173",
    SkylineProductivityModel.HI_SKID: "skyline_hi_skid",
    SkylineProductivityModel.LEDOUX_SKAGIT_SHOTGUN: "grapple_yarder_skagit_shotgun",
    SkylineProductivityModel.LEDOUX_SKAGIT_HIGHLEAD: "grapple_yarder_skagit_highlead",
    SkylineProductivityModel.LEDOUX_WASHINGTON_208E: "grapple_yarder_washington_208e",
    SkylineProductivityModel.LEDOUX_TMY45: "grapple_yarder_tmy45_residue",
}


def _skyline_cost_role(model: SkylineProductivityModel) -> str | None:
    return _SKYLINE_COST_ROLES.get(model)


class RoadsideProcessorModel(str, Enum):
    BERRY2019 = "berry2019"
    LABELLE2016 = "labelle2016"
    LABELLE2017 = "labelle2017"
    LABELLE2018 = "labelle2018"
    LABELLE2019_DBH = "labelle2019_dbh"
    LABELLE2019_VOLUME = "labelle2019_volume"
    ADV5N6 = "adv5n6"
    ADV7N3 = "adv7n3"
    VISSER2015 = "visser2015"
    TN103 = "tn103"
    TR106 = "tr106"
    TR87 = "tr87"
    TN166 = "tn166"
    HYPRO775 = "hypro775"
    SPINELLI2010 = "spinelli2010"
    BERTONE2025 = "bertone2025"
    BORZ2023 = "borz2023"
    NAKAGAWA2010 = "nakagawa2010"


_AUTOMATIC_BUCKING_SUPPORTED_MODELS = {
    RoadsideProcessorModel.BERRY2019,
    RoadsideProcessorModel.LABELLE2016,
    RoadsideProcessorModel.LABELLE2017,
    RoadsideProcessorModel.LABELLE2018,
    RoadsideProcessorModel.LABELLE2019_DBH,
    RoadsideProcessorModel.LABELLE2019_VOLUME,
}


class ADV5N6StemSource(str, Enum):
    LOADER_FORWARDED = "loader_forwarded"
    GRAPPLE_YARDED = "grapple_yarded"


class ADV5N6ProcessingMode(str, Enum):
    COLD = "cold"
    HOT = "hot"
    LOW_VOLUME = "low_volume"


class ADV7N3Machine(str, Enum):
    HYUNDAI_210 = "hyundai_210"
    JOHN_DEERE_892 = "john_deere_892"


class TN103Scenario(str, Enum):
    AREA_A = "area_a_feller_bunched"
    AREA_B = "area_b_handfelled"
    COMBINED_OBSERVED = "combined_observed"
    COMBINED_HIGH_UTIL = "combined_high_util"


class TR106Scenario(str, Enum):
    CASE1187_OCTNOV = "case1187_octnov"
    CASE1187_FEB = "case1187_feb"
    KP40_CAT225 = "kp40_caterpillar225"
    KP40_LINKBELT = "kp40_linkbelt_l2800"
    KP40_CAT_EL180 = "kp40_caterpillar_el180"


class TR87Scenario(str, Enum):
    DAY_SHIFT = "tj90_day_shift"
    NIGHT_SHIFT = "tj90_night_shift"
    COMBINED_OBSERVED = "tj90_combined_observed"
    BOTH_PROCESSORS = "tj90_both_processors_observed"
    BOTH_PROCESSORS_WAIT_ADJUSTED = "tj90_both_processors_wait_adjusted"


class TN166Scenario(str, Enum):
    GRAPPLE_YARDED = "grapple_yarded"
    RIGHT_OF_WAY = "right_of_way"
    MIXED_SHIFT = "mixed_shift"


class LabelleProcessorSpecies(str, Enum):
    SPRUCE = "spruce"
    BEECH = "beech"


class LabelleProcessorTreatment(str, Enum):
    CLEAR_CUT = "clear_cut"
    SELECTIVE_CUT = "selective_cut"


class Labelle2016TreeForm(str, Enum):
    ACCEPTABLE = "acceptable"
    UNACCEPTABLE = "unacceptable"


class Labelle2017Variant(str, Enum):
    POLY1 = "poly1"
    POLY2 = "poly2"
    POWER1 = "power1"
    POWER2 = "power2"


class Labelle2018Variant(str, Enum):
    RW_POLY1 = "rw_poly1"
    RW_POLY2 = "rw_poly2"
    CT_POLY1 = "ct_poly1"
    CT_POLY2 = "ct_poly2"


class ProcessorCarrier(str, Enum):
    PURPOSE_BUILT = "purpose_built"
    EXCAVATOR = "excavator"


class SpinelliOperation(str, Enum):
    HARVEST = "harvest"
    PROCESS = "process"


class SpinelliStandType(str, Enum):
    FOREST = "forest"
    PLANTATION = "plantation"
    COPPICE = "coppice"


class SpinelliCarrier(str, Enum):
    PURPOSE_BUILT = "purpose_built"
    EXCAVATOR = "excavator"
    SPIDER = "spider"
    TRACTOR = "tractor"


class SpinelliHead(str, Enum):
    ROLLER = "roller"
    STROKE = "stroke"


class SpinelliSpecies(str, Enum):
    CONIFER = "conifer"
    CHESTNUT_POPLAR = "chestnut_poplar"
    OTHER_HARDWOOD = "other_hardwood"


class LoaderProductivityModel(str, Enum):
    TN261 = "tn261"
    ADV2N26 = "adv2n26"
    ADV5N1 = "adv5n1"
    BARKO450 = "barko450"
    KIZHA2020 = "kizha2020"


class LoaderAdv5N1SlopeClass(str, Enum):
    ZERO_TO_TEN = "0_10"
    ELEVEN_TO_THIRTY = "11_30"


class LoaderBarkoScenario(str, Enum):
    GROUND_SKID_BLOCK = "ground_skid_block"
    CABLE_YARD_BLOCK = "cable_yard_block"


class LoaderHotColdMode(str, Enum):
    HOT = "hot"
    COLD = "cold"


class SkidderSpeedProfileOption(str, Enum):
    LEGACY = "legacy"
    GNSS_SKIDDER = "gnss_skidder"
    GNSS_FARM_TRACTOR = "gnss_farm_tractor"


_LOADER_MODEL_COST_ROLES = {
    LoaderProductivityModel.BARKO450.value: "loader_barko450",
}


_TR127_MODEL_TO_BLOCK = {
    SkylineProductivityModel.TR127_BLOCK1: 1,
    SkylineProductivityModel.TR127_BLOCK2: 2,
    SkylineProductivityModel.TR127_BLOCK3: 3,
    SkylineProductivityModel.TR127_BLOCK4: 4,
    SkylineProductivityModel.TR127_BLOCK5: 5,
    SkylineProductivityModel.TR127_BLOCK6: 6,
}


class RunningSkylineVariant(str, Enum):
    """Longline yarder variants from McNeel (2000)."""

    YARDER_A = "yarder_a"
    YARDER_B = "yarder_b"


class GrappleSkidderModel(str, Enum):
    """Supported grapple-skidder regressions."""

    HAN_LOP_AND_SCATTER = "lop_and_scatter"
    HAN_WHOLE_TREE = "whole_tree"
    ADV1N12_FULLTREE = "adv1n12-fulltree"
    ADV1N12_TWO_PHASE = "adv1n12-two-phase"
    ADV6N7 = "adv6n7"


_FORWARDER_GHAFFARIYAN_MODELS = {
    ForwarderBCModel.GHAFFARIYAN_SMALL,
    ForwarderBCModel.GHAFFARIYAN_LARGE,
}

_FORWARDER_ADV6N10_MODELS = {ForwarderBCModel.ADV6N10_SHORTWOOD}
_FORWARDER_ADV1N12_MODELS = {ForwarderBCModel.ADV1N12_SHORTWOOD}
_FORWARDER_ERIKSSON_MODELS = {
    ForwarderBCModel.ERIKSSON_FINAL_FELLING,
    ForwarderBCModel.ERIKSSON_THINNING,
}
_FORWARDER_BRUSHWOOD_MODELS = {ForwarderBCModel.LAITILA_VAATAINEN_BRUSHWOOD}


def _render_grapple_skidder_result(
    result: SkidderProductivityResult | Mapping[str, object]
) -> None:
    if isinstance(result, SkidderProductivityResult):
        params = result.parameters
        rows = [
            ("Model", result.method.value.replace("_", "-")),
            ("Pieces per Cycle", f"{float(params['pieces_per_cycle']):.2f}"),
            ("Piece Volume (m³)", f"{float(params['piece_volume_m3']):.3f}"),
            ("Empty Distance (m)", f"{float(params['empty_distance_m']):.1f}"),
            ("Loaded Distance (m)", f"{float(params['loaded_distance_m']):.1f}"),
            ("Cycle Time (s)", f"{result.cycle_time_seconds:.1f}"),
            ("Payload per Cycle (m³)", f"{result.payload_m3:.2f}"),
        ]
        if "trail_pattern" in params:
            rows.append(("Trail Pattern", str(params["trail_pattern"]).replace("_", " ")))
            rows.append(("Trail Multiplier", f"{float(params['trail_pattern_multiplier']):.2f}"))
        if "decking_condition" in params:
            rows.append(("Decking Condition", str(params["decking_condition"]).replace("_", " ")))
            rows.append(("Decking Multiplier", f"{float(params['decking_multiplier']):.2f}"))
        if "custom_multiplier" in params:
            rows.append(("Custom Multiplier", f"{float(params['custom_multiplier']):.3f}"))
        if "applied_multiplier" in params:
            rows.append(("Applied Multiplier", f"{float(params['applied_multiplier']):.3f}"))
        rows.append(("Predicted Productivity (m³/PMH0)", f"{result.predicted_m3_per_pmh:.2f}"))
        _render_kv_table("Grapple Skidder Productivity Estimate", rows)
        console.print(
            "[dim]Regression from Han et al. (2018) beetle-kill salvage study (delay-free cycle time).[/dim]"
        )
        return
    if isinstance(result, ADV6N7SkidderResult):
        metadata = result.metadata
        base_year = metadata.cost_base_year
        rows = [
            ("Model", GrappleSkidderModel.ADV6N7.value),
            ("Decking Mode", result.decking_mode.value.replace("_", " ")),
            ("Skidding Distance (m)", f"{result.skidding_distance_m:.1f}"),
            ("Payload per Cycle (m³)", f"{result.payload_m3:.2f}"),
            ("Utilisation (fraction)", f"{result.utilisation:.2f}"),
            ("Delay per Turn (min)", f"{result.delay_minutes:.2f}"),
            ("Cycle Time (min)", f"{result.cycle_time_minutes:.2f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
            (
                f"Skidding Cost ({base_year} CAD $/m³)",
                f"{result.skidder_cost_per_m3_cad_2004:.2f}",
            ),
            (
                f"Skidding Cost ({TARGET_YEAR} CAD $/m³)",
                f"{inflate_value(result.skidder_cost_per_m3_cad_2004, base_year):.2f}",
            ),
        ]
        if result.support_ratio is not None and result.combined_cost_per_m3_cad_2004 is not None:
            rows.append(("Loader Support Ratio", f"{result.support_ratio:.2f}"))
            rows.append(
                (
                    f"Combined Skid+Deck ({base_year} CAD $/m³)",
                    f"{result.combined_cost_per_m3_cad_2004:.2f}",
                )
            )
            rows.append(
                (
                    f"Combined Skid+Deck ({TARGET_YEAR} CAD $/m³)",
                    f"{inflate_value(result.combined_cost_per_m3_cad_2004, base_year):.2f}",
                )
            )
        loader_cost = metadata.loader_forwarding_cost_per_m3_at_85m_cad_2004
        if loader_cost:
            rows.append(
                (
                    f"Loader-Forwarding Baseline ({base_year} CAD $/m³)",
                    f"{loader_cost:.2f}",
                )
            )
            rows.append(
                (
                    f"Loader-Forwarding Baseline ({TARGET_YEAR} CAD $/m³)",
                    f"{inflate_value(loader_cost, base_year):.2f}",
                )
            )
        _render_kv_table("Grapple Skidder Productivity Estimate", rows)
        console.print(result.note)
        return

    model_label = str(result.get("model", "adv1n12")).replace("_", "-")
    distance = float(result.get("extraction_distance_m") or 0.0)
    rows = [
        ("Model", model_label),
        ("Extraction Distance (m)", f"{distance:.1f}"),
        ("Predicted Productivity (m³/PMH)", f"{float(result['productivity_m3_per_pmh']):.2f}"),
    ]
    _render_kv_table("Grapple Skidder Productivity Estimate", rows)
    note = result.get(
        "note",
        "[dim]FPInnovations Advantage 1N12 (commercial-thinning extraction distance optimization).[/dim]",
    )
    console.print(str(note))


def _render_shovel_logger_result(result: ShovelLoggerResult) -> None:
    params = result.parameters
    rows = [
        ("Passes", str(result.passes)),
        ("Swing Length (m)", f"{float(params['swing_length_m']):.2f}"),
        ("Strip Length (m)", f"{float(params['strip_length_m']):.1f}"),
        ("Volume per ha (m³)", f"{float(params['volume_per_ha_m3']):.1f}"),
        ("Cycle Time (min)", f"{result.cycle_minutes:.2f}"),
        ("Payload per Cycle (m³)", f"{result.payload_m3_per_cycle:.2f}"),
        ("Predicted Productivity (m³/PMH0)", f"{result.predicted_m3_per_pmh:.2f}"),
    ]
    _render_kv_table("Shovel Logger Productivity Estimate", rows)
    console.print(
        "[dim]Sessions & Boston (2006) serpentine shovel logging model with effective-time scaling.[/dim]"
    )


def _render_helicopter_result(result: HelicopterProductivityResult) -> None:
    rows = [
        ("Model", result.model.value.replace("_", "-")),
        ("Flight Distance (m)", f"{result.flight_distance_m:.1f}"),
        ("Cycle Time (min)", f"{result.cycle_minutes:.2f}"),
        ("Rated Payload (kg)", f"{result.spec.rated_payload_kg:.0f}"),
        ("Rated Payload (lb)", f"{result.spec.rated_payload_lb:.0f}"),
        ("Payload (kg)", f"{result.payload_kg:.0f}"),
        ("Payload (lb)", f"{result.payload_lb:.0f}"),
        ("Payload (m³)", f"{result.payload_m3:.2f}"),
        ("Load Factor", f"{result.load_factor:.2f}"),
        ("Turns per PMH0", f"{result.turns_per_pmh0:.2f}"),
        ("Productivity (m³/PMH0)", f"{result.productivity_m3_per_pmh0:.2f}"),
        ("Hook/Breakout (min)", f"{result.spec.hook_breakout_minutes:.2f}"),
        ("Unhook (min)", f"{result.spec.unhook_minutes:.2f}"),
        ("Additional Delay (min)", f"{result.additional_delay_minutes:.2f}"),
        ("Fly Empty Speed (km/h)", f"{result.spec.fly_empty_speed_mps * 3.6:.1f}"),
        ("Fly Loaded Speed (km/h)", f"{result.spec.fly_loaded_speed_mps * 3.6:.1f}"),
        ("Weight→Volume (kg/m³)", f"{result.weight_to_volume_kg_per_m3:.0f}"),
        ("Weight→Volume (lb/m³)", f"{result.weight_to_volume_lb_per_m3:.0f}"),
    ]
    _render_kv_table("Helicopter Longline Productivity Estimate", rows)
    console.print(
        "[dim]Defaults derived from FPInnovations helicopter logging studies (ADV3/4/5/6 series).[/dim]"
    )


def _render_processor_result(
    result: (
        ProcessorProductivityResult
        | VisserLogSortProductivityResult
        | Labelle2016ProcessorProductivityResult
        | Labelle2017PolynomialProcessorResult
        | Labelle2017PowerProcessorResult
        | Labelle2018ProcessorProductivityResult
        | Labelle2019ProcessorProductivityResult
        | Labelle2019VolumeProcessorProductivityResult
        | ADV5N6ProcessorProductivityResult
        | TN166ProcessorProductivityResult
        | Hypro775ProcessorProductivityResult
        | Spinelli2010ProcessorProductivityResult
        | Bertone2025ProcessorProductivityResult
        | Borz2023ProcessorProductivityResult
        | Nakagawa2010ProcessorProductivityResult
    ),
) -> None:
    if isinstance(result, ProcessorProductivityResult):
        rows = [
            ("Model", "berry2019"),
            ("Piece Size (m³)", f"{result.piece_size_m3:.3f}"),
            ("Tree Form Category", str(result.tree_form_category)),
            ("Base Productivity (m³/PMH)", f"{result.base_productivity_m3_per_pmh:.2f}"),
            ("Tree-form Multiplier", f"{result.tree_form_multiplier:.3f}"),
            ("Crew Multiplier", f"{result.crew_multiplier:.3f}"),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
        ]
        if result.carrier_profile:
            rows.append(("Carrier", result.carrier_profile.name))
            if result.carrier_profile.fuel_l_per_m3 is not None:
                rows.append(("Carrier Fuel (L/m³)", f"{result.carrier_profile.fuel_l_per_m3:.2f}"))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        note = "Regression from Berry (2019) Kinleith NZ time study; utilisation default accounts for <10 min delays."
        if result.carrier_profile:
            carrier_note = (
                f"Carrier profile '{result.carrier_profile.name}' captures utilisation/fuel differences "
                "reported by Magagnotti et al. (2017) and related studies."
            )
            note = f"{note} {carrier_note}"
        console.print(f"[dim]{note}[/dim]")
        return

    elif isinstance(result, VisserLogSortProductivityResult):
        rows = [
            ("Model", "visser2015"),
            ("Piece Size (m³)", f"{result.piece_size_m3:.3f}"),
            ("Log Sort Count", str(result.log_sort_count)),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
            ("Baseline (5 sorts, m³/PMH)", f"{result.baseline_productivity_m3_per_pmh:.2f}"),
            ("Δ vs. 5 sorts (%)", f"{result.relative_difference_percent:+.1f}"),
        ]
        if result.gross_value_per_2m3 is not None:
            rows.append(
                (
                    "Gross Value ($/2 m³)",
                    f"{result.gross_value_per_2m3:.2f} {result.value_currency or 'USD'} "
                    f"(piece size {result.value_reference_piece_size_m3 or 2.0:.1f} m³)",
                )
            )
        if result.value_per_pmh is not None:
            value_row = f"{result.value_per_pmh:.0f} {result.value_currency or 'USD'}/PMH"
            if result.value_base_year:
                value_row += f" (base {result.value_base_year})"
            rows.append(("Value per PMH", value_row))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        note_lines = [
            "Visser & Tolan (2015) NZ cable landing processors (Cat 330DL + Waratah HTH626) comparing 5/9/12/15 log sorts.",
            "CLI applies your utilisation multiplier to the published delay-free m³/PMH.",
        ]
        if result.notes:
            note_lines.append(" ".join(result.notes))
        console.print(f"[dim]{' '.join(note_lines)}[/dim]")
        return
    elif isinstance(result, Hypro775ProcessorProductivityResult):
        rows = [
            ("Model", "hypro775"),
            ("Description", result.description),
            ("Mean Cycle Time (s)", f"{result.mean_cycle_time_seconds:.1f}"),
            ("Logs per Tree", f"{result.mean_logs_per_tree:.1f}"),
            ("Gross Trees/h", f"{result.gross_trees_per_hour:.1f}"),
            ("Net Trees/h", f"{result.net_trees_per_hour:.1f}"),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
            ("Fuel (L/h)", f"{result.fuel_consumption_l_per_hour:.1f}"),
            ("Fuel (L/m³)", f"{result.fuel_consumption_l_per_m3:.2f}"),
            ("Utilisation (%)", f"{result.utilisation_percent:.1f}"),
        ]
        if result.noise_db is not None:
            rows.append(("Noise (dB[A])", f"{result.noise_db:.0f}"))
        if result.cardio_workload_percent_of_max is not None:
            rows.append(
                ("Cardio Workload (% max HR)", f"{result.cardio_workload_percent_of_max:.0f}")
            )
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        note_lines = [
            "HYPRO 775 tractor-mounted double-grip processor reference (Castro Pérez 2020; Zurita 2021).",
            "Use for small-diameter landing bucking where ergonomic limits (noise/heavy workload) and lower utilisation apply.",
        ]
        if result.notes:
            note_lines.extend(result.notes)
        console.print(f"[dim]{' '.join(note_lines)}[/dim]")
        return
    elif isinstance(result, Spinelli2010ProcessorProductivityResult):
        rows = [
            ("Model", "spinelli2010"),
            ("Operation", result.operation),
            ("Tree Volume (m³)", f"{result.tree_volume_m3:.3f}"),
            ("Machine Power (kW)", f"{result.machine_power_kw:.1f}"),
            ("Slope (%)", f"{result.slope_percent:.1f}"),
            ("Stand", result.stand_type),
            ("Carrier / Head", f"{result.carrier_type} / {result.head_type}"),
            ("Species Group", result.species_group),
        ]
        if result.removals_per_ha is not None:
            rows.append(("Removals (trees/ha)", f"{result.removals_per_ha:.1f}"))
        if result.residuals_per_ha is not None:
            rows.append(("Residuals (trees/ha)", f"{result.residuals_per_ha:.1f}"))
        rows.extend(
            [
                ("Delay-free Trees/PMH", f"{result.trees_per_pmh_delay_free:.1f}"),
                (
                    "Delay-free Productivity (m³/PMH₀)",
                    f"{result.delay_free_productivity_m3_per_pmh:.2f}",
                ),
                ("Accessory Ratio (%)", f"{result.accessory_ratio * 100:.1f}"),
                ("Delay Ratio (%)", f"{result.delay_ratio * 100:.1f}"),
                ("Utilisation (%)", f"{result.utilisation_percent:.1f}"),
                ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
            ]
        )
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        cycle_table = Table(title="Spinelli (2010) Cycle Breakdown", header_style="bold")
        cycle_table.add_column("Element")
        cycle_table.add_column("Minutes / Tree")
        for name, minutes in result.cycle_components_minutes:
            cycle_table.add_row(name, f"{minutes:.3f}")
        console.print(cycle_table)
        note_lines = [
            "Spinelli, Hartsough & Magagnotti (2010) Italian CTL study (Forest Products Journal 60(3):226–235).",
            "Accessory/delay ratios follow Spinelli & Visser (2008); outputs already include those penalties.",
        ]
        for note in result.notes:
            if note not in note_lines:
                note_lines.append(note)
        console.print(f"[dim]{' '.join(note_lines)}[/dim]")
        return
    elif isinstance(result, Bertone2025ProcessorProductivityResult):
        rows = [
            ("Model", "bertone2025"),
            ("DBH (cm)", f"{result.dbh_cm:.1f}"),
            ("Height (m)", f"{result.height_m:.1f}"),
            ("Logs per Tree", f"{result.logs_per_tree:.1f}"),
            ("Tree Volume (m³)", f"{result.tree_volume_m3:.2f}"),
            ("Delay-free Cycle (s)", f"{result.delay_free_cycle_seconds:.1f}"),
            (
                "Delay-free Productivity (m³/PMH₀)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/SMH)", f"{result.productivity_m3_per_smh:.2f}"),
            ("Utilisation (%)", f"{result.utilisation_percent:.1f}"),
            ("Fuel (L/SMH)", f"{result.fuel_l_per_smh:.1f}"),
            ("Fuel (L/m³)", f"{result.fuel_l_per_m3:.2f}"),
            ("Cost (/SMH)", f"{result.cost_per_smh:.2f} {result.cost_currency}"),
            ("Cost (/m³)", f"{result.cost_per_m3:.2f} {result.cost_currency}"),
        ]
        if result.cost_base_year is not None:
            rows.append(("Cost Base Year", str(result.cost_base_year)))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        note_lines = [
            "Bertone & Manzone (2025) excavator-based processor at a cable landing (Italian Alps, spruce).",
            "Default delay multiplier (≈57%) reflects yarder-supply waits; override --processor-delay-multiplier if your landing has different utilisation.",
        ]
        for note in result.notes:
            note_lines.append(note)
        console.print(f"[dim]{' '.join(note_lines)}[/dim]")
        return
    elif isinstance(result, Borz2023ProcessorProductivityResult):
        rows = [
            ("Model", "borz2023"),
            (
                "Tree Volume (m³)",
                f"{result.tree_volume_m3:.2f}" if result.tree_volume_m3 else "n/a",
            ),
            ("Efficiency (PMH/m³)", f"{result.efficiency_pmh_per_m3:.3f}"),
            ("Efficiency (SMH/m³)", f"{result.efficiency_smh_per_m3:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
            ("Productivity (m³/SMH)", f"{result.productivity_m3_per_smh:.2f}"),
            ("Recovery (%)", f"{result.recovery_percent:.1f}"),
            ("Fuel (L/h)", f"{result.fuel_l_per_h:.1f}"),
            ("Fuel (L/m³)", f"{result.fuel_l_per_m3:.2f}"),
            ("Cost (/m³)", f"{result.cost_per_m3:.2f} {result.cost_currency}"),
        ]
        if result.cost_base_year is not None:
            rows.append(("Cost Base Year", str(result.cost_base_year)))
        rows.append(("Utilisation (%)", f"{result.utilisation_percent:.1f}"))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        note_lines = [
            "Borz et al. (2023) single-grip harvester bucking cable-fed stems at a landing (Romania): averages only (21.4 m³/PMH, 0.78 L/m³, 10–11 EUR/m³).",
            "Use this preset when modelling full mechanization of landing bucking to replace manual chainsaw crews.",
        ]
        for note in result.notes:
            note_lines.append(note)
        console.print(f"[dim]{' '.join(note_lines)}[/dim]")
        return
    elif isinstance(result, Nakagawa2010ProcessorProductivityResult):
        rows = [("Model", "nakagawa2010"), ("Regression", result.model_used)]
        if result.dbh_cm is not None:
            rows.append(("DBH (cm)", f"{result.dbh_cm:.1f}"))
        if result.piece_volume_m3 is not None:
            rows.append(("Piece Volume (m³)", f"{result.piece_volume_m3:.3f}"))
        rows.extend(
            [
                (
                    "Delay-free Productivity (m³/PMH₀)",
                    f"{result.delay_free_productivity_m3_per_pmh:.2f}",
                ),
                ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
                ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
            ]
        )
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        note_lines = [
            "Nakagawa et al. (2010) excavator-based landing processor (Hokkaido thinning, Timberjack 746B + Komatsu PC138US).",
            "Delay multiplier lets you fold in site-specific waits (default assumes PMH₀ only).",
        ]
        if result.notes:
            note_lines.extend(result.notes)
        console.print(f"[dim]{' '.join(note_lines)}[/dim]")
        return

    elif isinstance(result, Labelle2016ProcessorProductivityResult):
        rows = [
            ("Model", "labelle2016_treeform"),
            ("Tree Form Class", result.tree_form),
            ("DBH (cm)", f"{result.dbh_cm:.1f}"),
            ("Coefficient a", f"{result.coefficient_a:.4f}"),
            ("Exponent b", f"{result.exponent_b:.4f}"),
            ("Sample Trees", str(result.sample_trees)),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
        ]
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]Labelle et al. (2016) sugar maple processor study (New Brunswick, acceptable vs. unacceptable tree forms). Outputs are PMH₀—apply utilisation via --processor-delay-multiplier.[/dim]"
        )
        return

    elif isinstance(result, Labelle2017PolynomialProcessorResult):
        rows = [
            ("Model", f"labelle2017_{result.variant}"),
            ("DBH (cm)", f"{result.dbh_cm:.1f}"),
            (
                "Polynomial",
                f"{result.intercept:+.2f} - {result.linear:.4f}·DBH "
                f"+ {result.quadratic_coeff:.4f}·DBH^{result.quadratic_exponent:.0f} "
                f"- {result.cubic_coeff:.4f}·DBH^{result.cubic_exponent:.0f}",
            ),
            ("Sample Trees", str(result.sample_trees)),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
        ]
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]Labelle et al. (2017) excavator-based CTL processors (power/polynomial DBH fits); outputs are PMH₀ from eastern Canadian hardwood blocks.[/dim]"
        )
        return

    elif isinstance(result, Labelle2017PowerProcessorResult):
        rows = [
            ("Model", f"labelle2017_{result.variant}"),
            ("DBH (cm)", f"{result.dbh_cm:.1f}"),
            ("Coefficient", f"{result.coefficient:.6f}"),
            ("Exponent", f"{result.exponent:.4f}"),
            ("Sample Trees", str(result.sample_trees)),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
        ]
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]Labelle et al. (2017) excavator-based CTL processors (power/polynomial DBH fits); outputs are PMH₀ from eastern Canadian hardwood blocks.[/dim]"
        )
        return

    elif isinstance(result, Labelle2018ProcessorProductivityResult):
        rows = [
            ("Model", f"labelle2018_{result.variant}"),
            ("DBH (cm)", f"{result.dbh_cm:.1f}"),
            (
                "Polynomial",
                f"-{result.intercept:.2f} + {result.linear:.2f}·DBH - {result.quadratic:.3f}·DBH²",
            ),
            ("Sample Trees", str(result.sample_trees)),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
        ]
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]Labelle et al. (2018) Bavarian hardwood processor study (rubber-tracked vs. crawler Ponsse rigs). Outputs are PMH₀; use --processor-delay-multiplier for utilisation assumptions.[/dim]"
        )
        return

    elif isinstance(result, Labelle2019ProcessorProductivityResult):
        rows = [
            ("Model", "labelle2019_dbh"),
            ("Species", result.species),
            ("Treatment", result.treatment.replace("_", " ")),
            ("DBH (cm)", f"{result.dbh_cm:.1f}"),
            (
                "Polynomial",
                f"{result.intercept:+.2f} + {result.linear:.4f}·DBH + {result.quadratic:.5f}·DBH²",
            ),
            ("Sample Trees", str(result.sample_trees)),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
        ]
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]Labelle et al. (2019) Bavarian hardwood case study (TimberPro 620-E + LogMax 7000C); values are PMH₀—apply utilisation via --processor-delay-multiplier.[/dim]"
        )
        return

    elif isinstance(result, Labelle2019VolumeProcessorProductivityResult):
        rows = [
            ("Model", "labelle2019_volume"),
            ("Species", result.species),
            ("Treatment", result.treatment.replace("_", " ")),
            ("Recovered Volume (m³)", f"{result.volume_m3:.3f}"),
            (
                "Polynomial",
                f"{result.intercept:+.2f} + {result.linear:.2f}·V - {result.quadratic:.3f}·V^{result.exponent:.0f}",
            ),
            ("Sample Trees", str(result.sample_trees)),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
        ]
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]Labelle et al. (2019) hardwood volume regression (PMH₀); use --processor-delay-multiplier to apply utilisation when exporting beyond Bavaria.[/dim]"
        )
        return

    elif isinstance(result, ADV5N6ProcessorProductivityResult):
        rows = [
            ("Model", "adv5n6"),
            ("Stem Source", result.stem_source.replace("_", " ")),
            ("Processing Mode", result.processing_mode.replace("_", " ")),
            ("Scenario", result.description or "See ADV5N6 case notes"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.1f}"),
            ("Productivity (m³/SMH)", f"{result.productivity_m3_per_smh:.1f}"),
            ("Cost ($/m³)", f"{result.cost_cad_per_m3:.2f}"),
        ]
        if result.mean_stem_volume_m3 is not None:
            rows.append(("Mean Stem Volume (m³)", f"{result.mean_stem_volume_m3:.2f}"))
        if result.stems_per_pmh is not None:
            rows.append(("Stems per PMH", f"{result.stems_per_pmh:.1f}"))
        if result.stems_per_smh is not None:
            rows.append(("Stems per SMH", f"{result.stems_per_smh:.1f}"))
        if result.utilisation_percent is not None:
            rows.append(("Utilisation (%)", f"{result.utilisation_percent:.0f}"))
        if result.availability_percent is not None:
            rows.append(("Availability (%)", f"{result.availability_percent:.0f}"))
        if result.shift_length_hours is not None:
            rows.append(("Shift Length (h)", f"{result.shift_length_hours:.1f}"))
        if result.machine_rate_cad_per_smh is not None:
            rows.append(("Machine Rate ($/SMH)", f"{result.machine_rate_cad_per_smh:.2f}"))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]FPInnovations Advantage Vol. 5 No. 6 (Madill 3800 + Waratah HTH624) landing processor study. Select stem source + processing mode to mirror loader-forwarded vs. grapple-yarded hot/cold decks.[/dim]"
        )
        if result.notes:
            console.print(f"[dim]{' '.join(result.notes)}[/dim]")
        if result.cost_base_year:
            console.print(
                f"[dim]Costs escalated from {result.cost_base_year} CAD to 2024 CAD using Statistics Canada CPI (Table 18-10-0005-01).[/dim]"
            )
        return
    elif isinstance(result, ADV7N3ProcessorProductivityResult):
        rows = [
            ("Model", "adv7n3"),
            ("Machine", result.machine_label),
            ("Shift Productivity (m³/PMH)", f"{result.shift_productivity_m3_per_pmh:.1f}"),
            ("Shift Productivity (m³/SMH)", f"{result.shift_productivity_m3_per_smh:.1f}"),
            ("Utilisation (%)", f"{result.utilisation_percent:.0f}"),
            ("Availability (%)", f"{result.availability_percent:.0f}"),
            ("Total Volume (m³)", f"{result.total_volume_m3:,.0f}"),
        ]
        if result.detailed_avg_stem_volume_m3 is not None:
            rows.append(("Avg Stem Volume (m³)", f"{result.detailed_avg_stem_volume_m3:.2f}"))
        if result.detailed_productivity_m3_per_pmh is not None:
            rows.append(
                ("Detailed Productivity (m³/PMH)", f"{result.detailed_productivity_m3_per_pmh:.1f}")
            )
        if result.detailed_stems_per_pmh is not None:
            rows.append(("Stems per PMH", f"{result.detailed_stems_per_pmh:.1f}"))
        if result.processor_cost_cad_per_m3_base_year is not None and result.cost_base_year:
            rows.append(
                (
                    f"Processor Cost ({result.cost_base_year} CAD $/m³)",
                    f"{result.processor_cost_cad_per_m3_base_year:.2f}",
                )
            )
        rows.append(
            (
                "Processor Cost (2024 CAD $/m³)",
                f"{result.processor_cost_cad_per_m3:.2f}",
            )
        )
        if result.loader_cost_cad_per_m3_base_year is not None and result.cost_base_year:
            rows.append(
                (
                    f"Loader Cost ({result.cost_base_year} CAD $/m³)",
                    f"{result.loader_cost_cad_per_m3_base_year:.2f}",
                )
            )
        if result.loader_cost_cad_per_m3 is not None:
            rows.append(
                (
                    "Loader Cost (2024 CAD $/m³)",
                    f"{result.loader_cost_cad_per_m3:.2f}",
                )
            )
        if result.system_cost_cad_per_m3_base_year is not None and result.cost_base_year:
            rows.append(
                (
                    f"Processor + Loader ({result.cost_base_year} CAD $/m³)",
                    f"{result.system_cost_cad_per_m3_base_year:.2f}",
                )
            )
        if result.system_cost_cad_per_m3 is not None:
            rows.append(
                (
                    "Processor + Loader (2024 CAD $/m³)",
                    f"{result.system_cost_cad_per_m3:.2f}",
                )
            )
        if result.processor_hourly_cost_cad_per_smh is not None:
            rows.append(
                (
                    "Processor Rate ($/SMH)",
                    f"{result.processor_hourly_cost_cad_per_smh:.2f}",
                )
            )
        if result.loader_hourly_cost_cad_per_smh is not None:
            rows.append(("Loader Rate ($/SMH)", f"{result.loader_hourly_cost_cad_per_smh:.2f}"))
        if result.loader_support_percent is not None:
            rows.append(("Loader Assist Time (%)", f"{result.loader_support_percent:.0f}"))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]FPInnovations Advantage Vol. 7 No. 3 (Hyundai 210LC vs. John Deere 892 summer processors feeding short-log skyline decks near Mackenzie, BC).[/dim]"
        )
        if result.loader_task_distribution_percent:
            summary = ", ".join(
                f"{label.replace('_', ' ')} {value:.0f}%"
                for label, value in result.loader_task_distribution_percent.items()
            )
            console.print(f"[dim]Loader task distribution: {summary}.[/dim]")
        if result.non_processing_time_minutes_per_cycle:
            summary = ", ".join(
                f"{label.replace('_', ' ')} = {value:.2f} min"
                for label, value in result.non_processing_time_minutes_per_cycle.items()
            )
            console.print(
                f"[dim]Non-processing time per cycle (loader/yarder combinations): {summary}.[/dim]"
            )
        if result.notes:
            console.print(f"[dim]{' '.join(result.notes)}[/dim]")
        if result.cost_base_year:
            console.print(
                f"[dim]Costs escalated from {result.cost_base_year} CAD to 2024 CAD using Statistics Canada CPI (Table 18-10-0005-01).[/dim]"
            )
        return

    elif isinstance(result, TN103ProcessorProductivityResult):
        rows = [
            ("Model", "tn103"),
            ("Scenario", result.scenario.replace("_", " ")),
            ("Stem Source", result.stem_source.replace("_", " ")),
        ]
        if result.mean_stem_volume_m3 is not None:
            rows.append(("Mean Stem Volume (m³)", f"{result.mean_stem_volume_m3:.2f}"))
        if result.trees_per_pmh is not None:
            rows.append(("Trees per PMH", f"{result.trees_per_pmh:.1f}"))
        if result.trees_per_smh is not None:
            rows.append(("Trees per SMH", f"{result.trees_per_smh:.1f}"))
        if result.productivity_m3_per_pmh is not None:
            rows.append(("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.1f}"))
        if result.productivity_m3_per_smh is not None:
            rows.append(("Productivity (m³/SMH)", f"{result.productivity_m3_per_smh:.1f}"))
        if result.volume_per_shift_m3 is not None:
            rows.append(("Volume per 8h Shift (m³)", f"{result.volume_per_shift_m3:.1f}"))
        if result.utilisation_percent is not None:
            rows.append(("Utilisation (%)", f"{result.utilisation_percent:.1f}"))
        if result.cost_cad_per_m3 is not None:
            rows.append(("Cost ($/m³)", f"{result.cost_cad_per_m3:.2f}"))
        if result.cost_cad_per_tree is not None:
            rows.append(("Cost ($/tree)", f"{result.cost_cad_per_tree:.2f}"))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]FERIC TN-103 (Caterpillar DL221 stroke processor) coastal old-growth study; select scenarios to mirror windrow prep (feller-bunched Area A vs. hand-felled Area B) or the combined/73% utilisation cases.[/dim]"
        )
        if result.notes:
            console.print(f"[dim]{' '.join(result.notes)}[/dim]")
        if result.cost_base_year:
            console.print(
                f"[dim]Costs escalated from {result.cost_base_year} CAD to 2024 CAD using Statistics Canada CPI (Table 18-10-0005-01).[/dim]"
            )
        return

    elif isinstance(result, TR106ProcessorProductivityResult):
        rows = [
            ("Model", "tr106"),
            ("Scenario", result.scenario.replace("_", " ")),
            ("Machine", result.machine or "—"),
            ("Stem Source", result.stem_source.replace("_", " ")),
        ]
        if result.mean_stem_volume_m3 is not None:
            rows.append(("Mean Stem Volume (m³)", f"{result.mean_stem_volume_m3:.3f}"))
        if result.stems_per_pmh is not None:
            rows.append(("Stems per PMH", f"{result.stems_per_pmh:.1f}"))
        if result.productivity_m3_per_pmh is not None:
            rows.append(("Gross Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.1f}"))
        if result.net_productivity_m3_per_pmh is not None:
            rows.append(("Net Productivity (m³/PMH)", f"{result.net_productivity_m3_per_pmh:.1f}"))
        if result.logs_per_stem is not None:
            rows.append(("Logs per Stem", f"{result.logs_per_stem:.2f}"))
        if result.cycle_minutes_per_stem is not None:
            rows.append(("Cycle Time (min/stem)", f"{result.cycle_minutes_per_stem:.2f}"))
        if result.utilisation_percent is not None:
            rows.append(("Utilisation (%)", f"{result.utilisation_percent:.1f}"))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]FERIC TR-106 stroke processor study (Case 1187B/Denis vs. Steyr KP40 carriers) in interior lodgepole pine shelterwoods. Use --processor-tr106-scenario to flip between the Case 1187 and KP40 carrier presets.[/dim]"
        )
        if result.notes:
            console.print(f"[dim]{' '.join(result.notes)}[/dim]")
        if result.cost_base_year:
            console.print(
                f"[dim]Costs escalated from {result.cost_base_year} CAD to 2024 CAD using Statistics Canada CPI (Table 18-10-0005-01).[/dim]"
            )
        return

    elif isinstance(result, TR87ProcessorProductivityResult):
        rows = [
            ("Model", "tr87"),
            ("Scenario", result.scenario.replace("_", " ")),
            ("Stem Source", result.stem_source.replace("_", " ")),
        ]
        if result.shift_type:
            rows.append(("Shift", result.shift_type.replace("_", " ")))
        if result.mean_stem_volume_m3 is not None:
            rows.append(("Mean Stem Volume (m³)", f"{result.mean_stem_volume_m3:.2f}"))
        if result.trees_per_pmh is not None:
            rows.append(("Trees per PMH", f"{result.trees_per_pmh:.1f}"))
        if result.productivity_m3_per_pmh is not None:
            rows.append(("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.1f}"))
        if result.productivity_m3_per_smh is not None:
            rows.append(("Productivity (m³/SMH)", f"{result.productivity_m3_per_smh:.1f}"))
        if result.volume_per_shift_m3 is not None:
            rows.append(("Volume per 8h Shift (m³)", f"{result.volume_per_shift_m3:.1f}"))
        if result.utilisation_percent is not None:
            rows.append(("Utilisation (%)", f"{result.utilisation_percent:.1f}"))
        if result.cost_cad_per_m3 is not None:
            rows.append(("Cost ($/m³)", f"{result.cost_cad_per_m3:.2f}"))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]FERIC TR-87 roadside logging case study (Timberjack TJ90 stroke processors). Use `--processor-tr87-scenario` to reflect day vs. night shift or the two-processor system averages with/without wait-for-wood delays.[/dim]"
        )
        if result.notes:
            console.print(f"[dim]{' '.join(result.notes)}[/dim]")
        if result.cost_base_year:
            console.print(
                f"[dim]Costs escalated from {result.cost_base_year} CAD to 2024 CAD using Statistics Canada CPI (Table 18-10-0005-01).[/dim]"
            )
        return

    elif isinstance(result, TN166ProcessorProductivityResult):
        rows = [
            ("Model", "tn166"),
            ("Scenario", result.scenario.replace("_", " ")),
            ("Stem Source", result.stem_source.replace("_", " ")),
            ("Processing Mode", result.processing_mode.replace("_", " ")),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.1f}"),
            ("Productivity (m³/SMH)", f"{result.productivity_m3_per_smh:.1f}"),
            ("Cost ($/m³)", f"{result.cost_cad_per_m3:.2f}"),
        ]
        if result.stems_per_pmh is not None:
            rows.append(("Stems per PMH", f"{result.stems_per_pmh:.1f}"))
        if result.stems_per_smh is not None:
            rows.append(("Stems per SMH", f"{result.stems_per_smh:.1f}"))
        if result.mean_stem_volume_m3 is not None:
            rows.append(("Mean Stem Volume (m³)", f"{result.mean_stem_volume_m3:.2f}"))
        if result.utilisation_percent is not None:
            rows.append(("Utilisation (%)", f"{result.utilisation_percent:.1f}"))
        if result.availability_percent is not None:
            rows.append(("Availability (%)", f"{result.availability_percent:.1f}"))
        if result.shift_length_hours is not None:
            rows.append(("Shift Length (h)", f"{result.shift_length_hours:.1f}"))
        if result.cost_cad_per_stem is not None:
            rows.append(("Cost ($/stem)", f"{result.cost_cad_per_stem:.2f}"))
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]FERIC TN-166 (Denis D3000 telescopic processor) shift/detailed timing study in interior BC; use this preset for stroke processors working grapple-yarded decks or ROW stems.[/dim]"
        )
        cycle = result.cycle_time_minutes or {}
        numeric_entries = [
            (name, value)
            for name, value in cycle.items()
            if name != "total" and isinstance(value, (int, float))
        ]
        if numeric_entries or isinstance(cycle.get("total"), (int, float)):
            prefix = "[dim]Cycle breakdown"
            total_value = cycle.get("total")
            if isinstance(total_value, (int, float)):
                prefix = f"[dim]Cycle breakdown (avg {total_value:.2f} min)"
            suffix = ""
            if numeric_entries:
                pieces = ", ".join(
                    f"{name} {float(value):.2f} min" for name, value in numeric_entries
                )
                suffix = f": {pieces}"
            console.print(f"{prefix}{suffix}[/dim]")
        if result.notes:
            console.print(f"[dim]{' '.join(result.notes)}[/dim]")
        if result.cost_base_year:
            console.print(
                f"[dim]Costs escalated from {result.cost_base_year} CAD to 2024 CAD using Statistics Canada CPI (Table 18-10-0005-01).[/dim]"
            )
        return

    raise TypeError(f"Unhandled processor result type: {type(result)!r}")


def _render_machine_cost_summary(role: str, *, label: str | None = None) -> None:
    try:
        rate = _resolve_machine_rate(role)
    except typer.BadParameter:
        console.print(f"[dim]No default machine rate available for role '{role}'.[/dim]")
        return
    composed = compose_default_rental_rate_for_role(role)
    if composed is None:
        console.print(f"[dim]Unable to build cost summary for role '{role}'.[/dim]")
        return
    rental_rate, breakdown = composed
    rows = [
        ("Machine Role", role),
        ("Default Rental Rate ($/SMH)", f"{rental_rate:.2f}"),
    ]
    if "ownership" in breakdown:
        rows.append(("Owning ($/SMH)", f"{breakdown['ownership']:.2f}"))
    if "operating" in breakdown:
        rows.append(("Operating ($/SMH)", f"{breakdown['operating']:.2f}"))
    if "repair_maintenance" in breakdown:
        rows.append(("Repair/Maint. ($/SMH)", f"{breakdown['repair_maintenance']:.2f}"))
    title = label or f"{role.replace('_', ' ').title()} Cost Reference"
    _render_kv_table(title, rows)
    if getattr(rate, "cost_base_year", TARGET_YEAR) != TARGET_YEAR:
        console.print(
            f"[dim]Default machine rate escalated from {rate.cost_base_year} CAD to {TARGET_YEAR} CAD using Statistics Canada CPI (Table 18-10-0005-01).[/dim]"
        )


def _maybe_render_costs(show_costs: bool, role: str) -> None:
    if show_costs:
        _render_machine_cost_summary(role)


def _render_loader_result(
    result: LoaderForwarderProductivityResult
    | ClambunkProductivityResult
    | LoaderAdv5N1ProductivityResult
    | LoaderBarko450ProductivityResult,
) -> None:
    if isinstance(result, LoaderAdv5N1ProductivityResult):
        rows = [
            ("Model", "adv5n1"),
            ("Slope Class (%)", "0–10" if result.slope_class == "0_10" else "11–30"),
            ("Forwarding Distance (m)", f"{result.forwarding_distance_m:.1f}"),
            ("Payload / Cycle (m³)", f"{result.payload_m3_per_cycle:.2f}"),
            ("Cycle Time (min)", f"{result.cycle_time_minutes:.2f}"),
            ("Utilisation (PMH/SMH)", f"{result.utilisation:.3f}"),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Productivity (m³/SMH)", f"{result.productivity_m3_per_smh:.2f}"),
        ]
        _render_kv_table("Loader-Forwarder Productivity Estimate", rows)
        metadata = _loader_model_metadata(LoaderProductivityModel.ADV5N1)
        note = (
            metadata.get("notes")[0]
            if metadata and metadata.get("notes")
            else "Regression digitised from FPInnovations ADV-5 No. 1 Figure 9 (payload 2.77 m³, utilisation 93%)."
        )
        console.print(f"[dim]{note}[/dim]")
        return
    if isinstance(result, ClambunkProductivityResult):
        rows = [
            ("Model", "adv2n26"),
            ("Travel Empty (m)", f"{result.travel_empty_distance_m:.1f}"),
            ("Stems / Cycle", f"{result.stems_per_cycle:.2f}"),
            ("Average Stem Volume (m³)", f"{result.average_stem_volume_m3:.3f}"),
            ("Payload / Cycle (m³)", f"{result.payload_m3_per_cycle:.2f}"),
            ("Delay-free Cycle (min)", f"{result.delay_free_cycle_minutes:.2f}"),
            ("In-cycle Delay (min)", f"{result.in_cycle_delay_minutes:.2f}"),
            ("Total Cycle (min)", f"{result.total_cycle_minutes:.2f}"),
            ("Utilisation (PMH/SMH)", f"{result.utilization:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
            ("Productivity (m³/SMH)", f"{result.productivity_m3_per_smh:.2f}"),
        ]
        _render_kv_table("Loader / Clambunk Productivity Estimate", rows)
        metadata = _loader_model_metadata(LoaderProductivityModel.ADV2N26) or {}
        console.print(
            "[dim]Regression from FPInnovations ADV-2 No. 26 (Trans-Gesco TG88 clambunk + JD 892D-LC loader-forwarder).[/dim]"
        )
        trail = metadata.get("trail_impact", {})
        classes = trail.get("classes", [])
        if classes:
            summary = ", ".join(
                f"{cls['class']}:{cls['average_width_m']:.1f} m avg width / {cls['exposed_mineral_soil_percent']}% exposed"
                for cls in classes
            )
            console.print(
                f"[yellow]Trail impact reminder[/yellow]: {trail.get('occupancy_percent', 0)}% of the sampled area "
                f"was occupied by unbladed trails ({summary}). Factor these into soil-disturbance constraints."
            )
        return

    if isinstance(result, LoaderBarko450ProductivityResult):
        rows = [
            ("Model", "barko450"),
            ("Scenario", result.scenario.replace("_", " ")),
            ("Avg Volume / Shift (m³)", f"{result.avg_volume_per_shift_m3:.0f}"),
        ]
        if result.avg_volume_per_load_m3 is not None:
            rows.append(("Avg Volume / Load (m³)", f"{result.avg_volume_per_load_m3:.1f}"))
        if result.total_truck_loads is not None:
            rows.append(("Total Loads", f"{result.total_truck_loads:.0f}"))
        if result.total_volume_m3 is not None:
            rows.append(("Total Volume (m³)", f"{result.total_volume_m3:.0f}"))
        if result.monitoring_days is not None:
            rows.append(("Monitoring Days", f"{result.monitoring_days:.0f}"))
        if result.utilisation_percent is not None:
            rows.append(("Utilisation (%)", f"{result.utilisation_percent:.1f}"))
        if result.availability_percent is not None:
            rows.append(("Availability (%)", f"{result.availability_percent:.1f}"))
        if result.wait_truck_move_sort_percent is not None:
            rows.append(("Wait/Move/Sort (%)", f"{result.wait_truck_move_sort_percent:.1f}"))
        if result.cost_per_shift_cad is not None:
            rows.append(("Cost ($/shift)", f"{result.cost_per_shift_cad:.2f}"))
        if result.cost_per_m3_cad is not None:
            rows.append(("Cost ($/m³)", f"{result.cost_per_m3_cad:.2f}"))
        if result.cost_per_piece_cad is not None:
            rows.append(("Cost ($/piece)", f"{result.cost_per_piece_cad:.2f}"))
        _render_kv_table("Loader Productivity Estimate", rows)
        console.print(
            "[dim]FERIC TN-46 Barko 450 loader trial (ground-skid vs. yarder-fed decks). Production capped by truck supply; utilisation losses (~17%) reflect truck waits/moves. Use this preset for live-heel loader ops when regressions are unavailable.[/dim]"
        )
        if result.notes:
            console.print(f"[dim]{' '.join(result.notes)}[/dim]")
        if result.cost_base_year:
            console.print(
                f"[dim]Costs escalated from {result.cost_base_year} CAD to 2024 CAD using Statistics Canada CPI (Table 18-10-0005-01).[/dim]"
            )
        return
    if isinstance(result, LoaderHotColdProductivityResult):
        rows = [
            ("Model", "kizha2020"),
            ("Mode", result.mode),
            ("Utilisation (%)", f"{result.utilisation_percent:.1f}"),
            (
                "Operational Delay (% of total time)",
                f"{result.operational_delay_percent_of_total_time:.1f}",
            ),
            ("Delay Cost ($/PMH)", f"{result.delay_cost_per_pmh:.2f} {result.currency or 'USD'}"),
            (
                "Machine Rate ($/PMH)",
                f"{result.machine_rate_per_pmh:.2f} {result.currency or 'USD'}",
            ),
            (
                "Effective Cost ($/PMH)",
                f"{result.effective_cost_per_pmh:.2f} {result.currency or 'USD'}",
            ),
        ]
        if result.observed_days is not None:
            rows.append(("Observed Days", str(result.observed_days)))
        if result.dominant_delay_breakdown_percent_of_delay:
            breakdown = ", ".join(
                f"{label}: {value:.0f}%"
                for label, value in result.dominant_delay_breakdown_percent_of_delay
            )
            rows.append(("Delay Breakdown", breakdown))
        _render_kv_table("Loader Productivity Estimate", rows)
        note_lines = [
            "Kizha et al. (2020) northern California biomass landing study (Thunderbird 840W loader).",
            "Hot = integrated sawlog+biomass loading (utilisation ~55%); Cold = decoupled biomass loading (utilisation ~7% with insufficient trucks).",
        ]
        if result.bottleneck:
            note_lines.append(f"Bottleneck: {result.bottleneck}")
        if result.notes:
            note_lines.extend(result.notes)
        if result.cost_base_year:
            note_lines.append(
                f"Costs referenced to {result.cost_base_year} {result.currency or 'USD'} (no CPI scaling applied)."
            )
        console.print(f"[dim]{' '.join(note_lines)}[/dim]")
        return

    rows = [
        ("Model", "tn261"),
        ("Piece Size (m³)", f"{result.piece_size_m3:.3f}"),
        ("Distance (m)", f"{result.external_distance_m:.1f}"),
        ("Slope (%)", f"{result.slope_percent:.1f}"),
        ("Bunched", "Yes" if result.bunched else "No"),
        ("Slope Multiplier", f"{result.slope_multiplier:.3f}"),
        ("Bunching Multiplier", f"{result.bunched_multiplier:.3f}"),
        ("Delay-free Productivity (m³/PMH)", f"{result.delay_free_productivity_m3_per_pmh:.2f}"),
        ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
        ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
    ]
    _render_kv_table("Loader-Forwarder Productivity Estimate", rows)
    console.print(
        "[dim]Regression calibrated from FERIC TN-261 (Vancouver Island loader-forwarding trials).[/dim]"
    )


def _render_grapple_yarder_result(
    *,
    model: GrappleYarderModel,
    turn_volume_m3: float | None,
    yarding_distance_m: float | None,
    productivity_m3_per_pmh: float,
    preset_meta: Mapping[str, object] | None = None,
    lateral_distance_m: float | None = None,
    stems_per_cycle: float | None = None,
    in_cycle_delay_minutes: float | None = None,
    note: str | None = None,
) -> None:
    rows = [("Model", model.value)]
    if turn_volume_m3 is not None:
        rows.append(("Turn Volume (m³)", f"{turn_volume_m3:.2f}"))
    if yarding_distance_m is not None:
        rows.append(("Yarding Distance (m)", f"{yarding_distance_m:.1f}"))
    if lateral_distance_m is not None:
        rows.append(("Lateral Distance (m)", f"{lateral_distance_m:.1f}"))
    if stems_per_cycle is not None:
        rows.append(("Stems per Turn", f"{stems_per_cycle:.2f}"))
    if in_cycle_delay_minutes is not None:
        rows.append(("In-cycle Delay (min)", f"{in_cycle_delay_minutes:.2f}"))
    rows.append(("Productivity (m³/PMH)", f"{productivity_m3_per_pmh:.2f}"))
    default_note = (
        "[dim]Regressions from MacDonald (1988) SR-54 and Peterson (1987) TR-75 "
        "(delay-free cycle times + minor delays).[/dim]"
    )
    if preset_meta is not None:
        label = preset_meta.get("label")
        if label:
            rows.insert(1, ("Preset", str(label)))
        logs_per_turn = preset_meta.get("logs_per_turn")
        if isinstance(logs_per_turn, (int, float)):
            rows.append(("Logs/Turn", f"{float(logs_per_turn):.2f}"))
        base_year = int(preset_meta.get("cost_base_year", TARGET_YEAR))
        cost_per_m3 = preset_meta.get("cost_per_m3")
        if isinstance(cost_per_m3, (int, float)):
            rows.append((f"Observed Cost ({base_year} CAD $/m³)", f"{float(cost_per_m3):.2f}"))
            rows.append(
                (
                    f"Cost ({TARGET_YEAR} CAD $/m³)",
                    f"{inflate_value(float(cost_per_m3), base_year):.2f}",
                )
            )
        cost_per_log = preset_meta.get("cost_per_log")
        if isinstance(cost_per_log, (int, float)):
            rows.append((f"Observed Cost ({base_year} CAD $/log)", f"{float(cost_per_log):.2f}"))
            rows.append(
                (
                    f"Cost ({TARGET_YEAR} CAD $/log)",
                    f"{inflate_value(float(cost_per_log), base_year):.2f}",
                )
            )
        extra_rows = preset_meta.get("extra_rows") or []
        for label, value in extra_rows:
            rows.append((label, value))
        default_note = preset_meta.get(
            "note",
            "[dim]Observed productivity/cost preset.[/dim]",
        )
    _render_kv_table("Grapple Yarder Productivity Estimate", rows)
    console.print(note or default_note)


def _parameter_supplied(ctx: typer.Context, name: str) -> bool:
    if ctx is None:
        return False
    try:
        source = ctx.get_parameter_source(name)
    except AttributeError:  # pragma: no cover - defensive
        return False
    return source is not None and source is not ParameterSource.DEFAULT


def _apply_skidder_system_defaults(
    *,
    system: HarvestSystem | None,
    model: GrappleSkidderModel,
    trail_pattern: TrailSpacingPattern | None,
    decking_condition: DeckingCondition | None,
    custom_multiplier: float | None,
    extraction_distance_m: float | None,
    adv6n7_decking_mode: ADV6N7DeckingMode,
    adv6n7_payload_m3: float | None,
    adv6n7_utilisation: float | None,
    adv6n7_delay_minutes: float | None,
    adv6n7_support_ratio: float | None,
    user_supplied: Mapping[str, bool],
) -> tuple[
    GrappleSkidderModel,
    TrailSpacingPattern | None,
    DeckingCondition | None,
    float | None,
    SkidderSpeedProfileOption,
    float | None,
    ADV6N7DeckingMode,
    float | None,
    float | None,
    float | None,
    float | None,
    bool,
]:
    speed_profile = SkidderSpeedProfileOption.LEGACY
    if system is None:
        return (
            model,
            trail_pattern,
            decking_condition,
            custom_multiplier,
            speed_profile,
            extraction_distance_m,
            adv6n7_decking_mode,
            adv6n7_payload_m3,
            adv6n7_utilisation,
            adv6n7_delay_minutes,
            adv6n7_support_ratio,
            False,
        )
    overrides = system_productivity_overrides(system, ProductivityMachineRole.GRAPPLE_SKIDDER.value)
    if not overrides:
        return (
            model,
            trail_pattern,
            decking_condition,
            custom_multiplier,
            speed_profile,
            extraction_distance_m,
            adv6n7_decking_mode,
            adv6n7_payload_m3,
            adv6n7_utilisation,
            adv6n7_delay_minutes,
            adv6n7_support_ratio,
            False,
        )
    used = False
    value = overrides.get("grapple_skidder_model")
    if value and not user_supplied.get("grapple_skidder_model", False):
        try:
            model = GrappleSkidderModel(value)
            used = True
        except ValueError as exc:  # pragma: no cover - validated by CI
            raise ValueError(f"Unknown grapple skidder model override: {value}") from exc
    value = overrides.get("skidder_trail_pattern")
    if trail_pattern is None and isinstance(value, str):
        try:
            trail_pattern = TrailSpacingPattern(value)
            used = True
        except ValueError as exc:  # pragma: no cover - validated by CI
            raise ValueError(f"Unknown trail pattern override: {value}") from exc
    value = overrides.get("skidder_decking_condition")
    if decking_condition is None and isinstance(value, str):
        try:
            decking_condition = DeckingCondition(value)
            used = True
        except ValueError as exc:  # pragma: no cover - validated by CI
            raise ValueError(f"Unknown decking condition override: {value}") from exc
    value = overrides.get("skidder_productivity_multiplier")
    if custom_multiplier is None and isinstance(value, (int, float)):
        custom_multiplier = float(value)
        used = True
    value = overrides.get("skidder_speed_profile")
    if value is not None:
        try:
            speed_profile = SkidderSpeedProfileOption(str(value))
            used = True
        except ValueError as exc:  # pragma: no cover - validated elsewhere
            raise ValueError(f"Unknown skidder speed profile override: {value}") from exc
    value = overrides.get("skidder_extraction_distance_m")
    if not user_supplied.get("skidder_extraction_distance", False) and isinstance(
        value, (int, float)
    ):
        extraction_distance_m = float(value)
        used = True
    if not user_supplied.get("skidder_adv6n7_decking_mode", False):
        override_mode = overrides.get("skidder_adv6n7_decking_mode")
        if override_mode is not None:
            try:
                adv6n7_decking_mode = ADV6N7DeckingMode(str(override_mode))
                used = True
            except ValueError as exc:  # pragma: no cover - validated via CI
                raise ValueError(f"Unknown ADV6N7 decking mode override: {override_mode}") from exc

    def maybe_float_override(
        key: str, current: float | None, supplied_flag: str
    ) -> tuple[float | None, bool]:
        if user_supplied.get(supplied_flag, False):
            return current, False
        override_value = overrides.get(key)
        if override_value is None:
            return current, False
        try:
            return float(override_value), True
        except (TypeError, ValueError) as exc:  # pragma: no cover
            raise ValueError(f"Invalid grapple skidder override for '{key}': {override_value}") from exc

    adv6n7_payload_m3, changed = maybe_float_override(
        "skidder_adv6n7_payload_m3", adv6n7_payload_m3, "skidder_adv6n7_payload_m3"
    )
    used |= changed
    adv6n7_utilisation, changed = maybe_float_override(
        "skidder_adv6n7_utilisation", adv6n7_utilisation, "skidder_adv6n7_utilisation"
    )
    used |= changed
    adv6n7_delay_minutes, changed = maybe_float_override(
        "skidder_adv6n7_delay_minutes", adv6n7_delay_minutes, "skidder_adv6n7_delay_minutes"
    )
    used |= changed
    adv6n7_support_ratio, changed = maybe_float_override(
        "skidder_adv6n7_support_ratio", adv6n7_support_ratio, "skidder_adv6n7_support_ratio"
    )
    used |= changed
    return (
        model,
        trail_pattern,
        decking_condition,
        custom_multiplier,
        speed_profile,
        extraction_distance_m,
        adv6n7_decking_mode,
        adv6n7_payload_m3,
        adv6n7_utilisation,
        adv6n7_delay_minutes,
        adv6n7_support_ratio,
        used,
    )


def _shovel_slope_multiplier(value: ShovelSlopeClass) -> float:
    return {
        ShovelSlopeClass.DOWNHILL: 1.1,
        ShovelSlopeClass.LEVEL: 1.0,
        ShovelSlopeClass.UPHILL: 0.9,
    }[value]


def _shovel_bunching_multiplier(value: ShovelBunching) -> float:
    return {
        ShovelBunching.FELLER_BUNCHED: 1.0,
        ShovelBunching.HAND_SCATTERED: 0.6,
    }[value]


def _apply_forwarder_system_defaults(
    *,
    system: HarvestSystem | None,
    model: ForwarderBCModel,
    extraction_distance_m: float | None,
    user_supplied: Mapping[str, bool],
) -> tuple[ForwarderBCModel, float | None, bool]:
    if system is None:
        return model, extraction_distance_m, False
    overrides = system_productivity_overrides(system, ProductivityMachineRole.FORWARDER.value)
    if not overrides:
        return model, extraction_distance_m, False
    used = False
    value = overrides.get("forwarder_model")
    if value and not user_supplied.get("forwarder_model", False):
        try:
            model = ForwarderBCModel(value)
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown forwarder model override: {value}") from exc
    value = overrides.get("forwarder_extraction_distance_m")
    if not user_supplied.get("extraction_distance", False) and isinstance(value, (int, float)):
        extraction_distance_m = float(value)
        used = True
    return model, extraction_distance_m, used


def _apply_processor_system_defaults(
    *,
    system: HarvestSystem | None,
    processor_model: RoadsideProcessorModel,
    processor_adv7n3_machine: ADV7N3Machine,
    user_supplied: Mapping[str, bool],
) -> tuple[RoadsideProcessorModel, ADV7N3Machine, bool]:
    if system is None:
        return processor_model, processor_adv7n3_machine, False
    overrides = system_productivity_overrides(
        system, ProductivityMachineRole.ROADSIDE_PROCESSOR.value
    )
    if not overrides:
        return processor_model, processor_adv7n3_machine, False
    used = False
    value = overrides.get("processor_model")
    if value and not user_supplied.get("processor_model", False):
        try:
            processor_model = RoadsideProcessorModel(value)
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown processor model override: {value}") from exc
    value = overrides.get("processor_adv7n3_machine")
    if value and not user_supplied.get("processor_adv7n3_machine", False):
        try:
            processor_adv7n3_machine = ADV7N3Machine(value)
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown ADV7N3 processor override: {value}") from exc
    return processor_model, processor_adv7n3_machine, used


def _apply_shovel_system_defaults(
    *,
    system: HarvestSystem | None,
    passes: int | None,
    swing_length_m: float | None,
    strip_length_m: float | None,
    volume_per_ha_m3: float | None,
    swing_time_roadside_s: float | None,
    payload_per_swing_roadside_m3: float | None,
    swing_time_initial_s: float | None,
    payload_per_swing_initial_m3: float | None,
    swing_time_rehandle_s: float | None,
    payload_per_swing_rehandle_m3: float | None,
    travel_speed_index_kph: float | None,
    travel_speed_return_kph: float | None,
    travel_speed_serpentine_kph: float | None,
    effective_minutes_per_hour: float | None,
    slope_class: ShovelSlopeClass,
    bunching: ShovelBunching,
    custom_multiplier: float | None,
) -> tuple[
    int | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    bool,
]:
    if system is None:
        return (
            passes,
            swing_length_m,
            strip_length_m,
            volume_per_ha_m3,
            swing_time_roadside_s,
            payload_per_swing_roadside_m3,
            swing_time_initial_s,
            payload_per_swing_initial_m3,
            swing_time_rehandle_s,
            payload_per_swing_rehandle_m3,
            travel_speed_index_kph,
            travel_speed_return_kph,
            travel_speed_serpentine_kph,
            effective_minutes_per_hour,
            slope_class,
            bunching,
            custom_multiplier,
            False,
        )
    overrides = system_productivity_overrides(system, ProductivityMachineRole.SHOVEL_LOGGER.value)
    if not overrides:
        return (
            passes,
            swing_length_m,
            strip_length_m,
            volume_per_ha_m3,
            swing_time_roadside_s,
            payload_per_swing_roadside_m3,
            swing_time_initial_s,
            payload_per_swing_initial_m3,
            swing_time_rehandle_s,
            payload_per_swing_rehandle_m3,
            travel_speed_index_kph,
            travel_speed_return_kph,
            travel_speed_serpentine_kph,
            effective_minutes_per_hour,
            slope_class,
            bunching,
            custom_multiplier,
            False,
        )

    def coerce_float(value: object | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):  # pragma: no cover
            raise ValueError(f"Invalid shovel override value: {value}")

    used = False
    if passes is None and overrides.get("shovel_passes") is not None:
        passes = int(float(overrides["shovel_passes"]))
        used = True
    if swing_length_m is None:
        swing_length_m = coerce_float(overrides.get("shovel_swing_length")) or swing_length_m
        used = used or overrides.get("shovel_swing_length") is not None
    if strip_length_m is None:
        strip_length_m = coerce_float(overrides.get("shovel_strip_length")) or strip_length_m
        used = used or overrides.get("shovel_strip_length") is not None
    if volume_per_ha_m3 is None:
        volume_per_ha_m3 = coerce_float(overrides.get("shovel_volume_per_ha")) or volume_per_ha_m3
        used = used or overrides.get("shovel_volume_per_ha") is not None
    if swing_time_roadside_s is None:
        swing_time_roadside_s = (
            coerce_float(overrides.get("shovel_swing_time_roadside")) or swing_time_roadside_s
        )
        used = used or overrides.get("shovel_swing_time_roadside") is not None
    if payload_per_swing_roadside_m3 is None:
        payload_per_swing_roadside_m3 = (
            coerce_float(overrides.get("shovel_payload_roadside")) or payload_per_swing_roadside_m3
        )
        used = used or overrides.get("shovel_payload_roadside") is not None
    if swing_time_initial_s is None:
        swing_time_initial_s = (
            coerce_float(overrides.get("shovel_swing_time_initial")) or swing_time_initial_s
        )
        used = used or overrides.get("shovel_swing_time_initial") is not None
    if payload_per_swing_initial_m3 is None:
        payload_per_swing_initial_m3 = (
            coerce_float(overrides.get("shovel_payload_initial")) or payload_per_swing_initial_m3
        )
        used = used or overrides.get("shovel_payload_initial") is not None
    if swing_time_rehandle_s is None:
        swing_time_rehandle_s = (
            coerce_float(overrides.get("shovel_swing_time_rehandle")) or swing_time_rehandle_s
        )
        used = used or overrides.get("shovel_swing_time_rehandle") is not None
    if payload_per_swing_rehandle_m3 is None:
        payload_per_swing_rehandle_m3 = (
            coerce_float(overrides.get("shovel_payload_rehandle")) or payload_per_swing_rehandle_m3
        )
        used = used or overrides.get("shovel_payload_rehandle") is not None
    if travel_speed_index_kph is None:
        travel_speed_index_kph = (
            coerce_float(overrides.get("shovel_speed_index")) or travel_speed_index_kph
        )
        used = used or overrides.get("shovel_speed_index") is not None
    if travel_speed_return_kph is None:
        travel_speed_return_kph = (
            coerce_float(overrides.get("shovel_speed_return")) or travel_speed_return_kph
        )
        used = used or overrides.get("shovel_speed_return") is not None
    if travel_speed_serpentine_kph is None:
        travel_speed_serpentine_kph = (
            coerce_float(overrides.get("shovel_speed_serpentine")) or travel_speed_serpentine_kph
        )
        used = used or overrides.get("shovel_speed_serpentine") is not None
    if effective_minutes_per_hour is None:
        effective_minutes_per_hour = (
            coerce_float(overrides.get("shovel_effective_minutes")) or effective_minutes_per_hour
        )
        used = used or overrides.get("shovel_effective_minutes") is not None
    slope_value = overrides.get("shovel_slope_class")
    if slope_value is not None:
        try:
            slope_class = ShovelSlopeClass(str(slope_value))
            used = True
        except ValueError as exc:  # pragma: no cover
            raise ValueError(f"Unknown shovel slope class override: {slope_value}") from exc
    bunch_value = overrides.get("shovel_bunching")
    if bunch_value is not None:
        try:
            bunching = ShovelBunching(str(bunch_value))
            used = True
        except ValueError as exc:  # pragma: no cover
            raise ValueError(f"Unknown shovel bunching override: {bunch_value}") from exc
    custom_value = overrides.get("shovel_productivity_multiplier")
    if custom_multiplier is None and custom_value is not None:
        custom_multiplier = float(custom_value)
        used = True

    return (
        passes,
        swing_length_m,
        strip_length_m,
        volume_per_ha_m3,
        swing_time_roadside_s,
        payload_per_swing_roadside_m3,
        swing_time_initial_s,
        payload_per_swing_initial_m3,
        swing_time_rehandle_s,
        payload_per_swing_rehandle_m3,
        travel_speed_index_kph,
        travel_speed_return_kph,
        travel_speed_serpentine_kph,
        effective_minutes_per_hour,
        slope_class,
        bunching,
        custom_multiplier,
        used,
    )


def _apply_skyline_system_defaults(
    *,
    system: HarvestSystem | None,
    model: SkylineProductivityModel,
    slope_distance_m: float,
    lateral_distance_m: float,
    lateral_distance_2_m: float | None,
    logs_per_turn: float,
    average_log_volume_m3: float,
    crew_size: float,
    horizontal_distance_m: float | None,
    vertical_distance_m: float | None,
    pieces_per_cycle: float | None,
    piece_volume_m3: float | None,
    running_variant: RunningSkylineVariant,
    carriage_height_m: float | None,
    chordslope_percent: float | None,
    payload_m3: float | None,
    num_logs: float | None,
    user_supplied: Mapping[str, bool],
) -> tuple[
    SkylineProductivityModel,
    float,
    float,
    float | None,
    float,
    float,
    float,
    float,
    float | None,
    float | None,
    float | None,
    float | None,
    RunningSkylineVariant,
    float | None,
    float | None,
    float | None,
    float | None,
    bool,
    str | None,
]:
    if system is None:
        return (
            model,
            slope_distance_m,
            lateral_distance_m,
            lateral_distance_2_m,
            logs_per_turn,
            average_log_volume_m3,
            crew_size,
            horizontal_distance_m,
            vertical_distance_m,
            pieces_per_cycle,
            piece_volume_m3,
            running_variant,
            carriage_height_m,
            chordslope_percent,
            payload_m3,
            num_logs,
            False,
            None,
        )
    overrides = system_productivity_overrides(system, "skyline_yarder")
    if not overrides:
        overrides = system_productivity_overrides(system, "grapple_yarder")
    if not overrides:
        return (
            model,
            slope_distance_m,
            lateral_distance_m,
            lateral_distance_2_m,
            logs_per_turn,
            average_log_volume_m3,
            crew_size,
            horizontal_distance_m,
            vertical_distance_m,
            pieces_per_cycle,
            piece_volume_m3,
            running_variant,
            carriage_height_m,
            chordslope_percent,
            payload_m3,
            num_logs,
            False,
            None,
        )
    used = False
    tr119_override: str | None = None

    def maybe_float(
        key: str, current: float | None, supplied_flag: str, allow_zero: bool = False
    ) -> tuple[float | None, bool]:
        value = overrides.get(key)
        if value is None or user_supplied.get(supplied_flag, False):
            return current, False
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - validated via plan
            raise ValueError(f"Invalid skyline override for '{key}': {value}") from exc
        if not allow_zero and coerced == 0:
            return current, False
        return coerced, True

    value = overrides.get("skyline_model")
    if value and not user_supplied.get("model", False):
        try:
            model = SkylineProductivityModel(value)
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown skyline model override '{value}'.") from exc

    logs_per_turn, changed = maybe_float(
        "skyline_logs_per_turn", logs_per_turn, "logs_per_turn", True
    )
    used |= changed
    average_log_volume_m3, changed = maybe_float(
        "skyline_average_log_volume_m3", average_log_volume_m3, "average_log_volume_m3", True
    )
    used |= changed
    crew_size, changed = maybe_float("skyline_crew_size", crew_size, "crew_size", True)
    used |= changed
    horizontal_distance_m, changed = maybe_float(
        "skyline_horizontal_distance_m", horizontal_distance_m, "horizontal_distance_m", True
    )
    used |= changed
    vertical_distance_m, changed = maybe_float(
        "skyline_vertical_distance_m", vertical_distance_m, "vertical_distance_m", True
    )
    used |= changed
    pieces_per_cycle, changed = maybe_float(
        "skyline_pieces_per_cycle", pieces_per_cycle, "pieces_per_cycle", True
    )
    used |= changed
    piece_volume_m3, changed = maybe_float(
        "skyline_piece_volume_m3", piece_volume_m3, "piece_volume_m3", True
    )
    used |= changed
    carriage_height_m, changed = maybe_float(
        "skyline_carriage_height_m", carriage_height_m, "carriage_height_m", True
    )
    used |= changed
    chordslope_percent, changed = maybe_float(
        "skyline_chordslope_percent", chordslope_percent, "chordslope_percent", True
    )
    used |= changed
    lateral_distance_m, changed = maybe_float(
        "skyline_lateral_distance_m", lateral_distance_m, "lateral_distance_m", True
    )
    used |= changed
    lateral_distance_2_m, changed = maybe_float(
        "skyline_lateral_distance2_m", lateral_distance_2_m, "lateral_distance_2_m", True
    )
    used |= changed
    payload_m3, changed = maybe_float(
        "skyline_payload_m3", payload_m3, "payload_m3", True
    )
    used |= changed
    num_logs, changed = maybe_float("skyline_num_logs", num_logs, "num_logs", True)
    used |= changed

    value = overrides.get("skyline_running_variant")
    if value and not user_supplied.get("running_yarder_variant", False):
        try:
            running_variant = RunningSkylineVariant(value)
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown running-skyline variant override '{value}'.") from exc

    if not user_supplied.get("tr119_treatment", False):
        override_treatment = overrides.get("tr119_treatment")
        if isinstance(override_treatment, str):
            tr119_override = override_treatment

    return (
        model,
        slope_distance_m,
        lateral_distance_m,
        lateral_distance_2_m,
        logs_per_turn,
        average_log_volume_m3,
        crew_size,
        horizontal_distance_m,
        vertical_distance_m,
        pieces_per_cycle,
        piece_volume_m3,
        running_variant,
        carriage_height_m,
        chordslope_percent,
        payload_m3,
        num_logs,
        used,
        tr119_override,
    )


def _apply_helicopter_system_defaults(
    *,
    system: HarvestSystem | None,
    model: HelicopterLonglineModel,
    flight_distance_m: float | None,
    payload_m3: float | None,
    load_factor: float | None,
    weight_to_volume_lb_per_m3: float | None,
    delay_minutes: float,
    user_supplied: Mapping[str, bool],
) -> tuple[
    HelicopterLonglineModel,
    float | None,
    float | None,
    float | None,
    float | None,
    float,
    bool,
]:
    if system is None:
        return (
            model,
            flight_distance_m,
            payload_m3,
            load_factor,
            weight_to_volume_lb_per_m3,
            delay_minutes,
            False,
        )
    overrides = system_productivity_overrides(
        system, ProductivityMachineRole.HELICOPTER_LONGLINE.value
    )
    if not overrides:
        return (
            model,
            flight_distance_m,
            payload_m3,
            load_factor,
            weight_to_volume_lb_per_m3,
            delay_minutes,
            False,
        )
    used = False

    value = overrides.get("helicopter_model")
    if value and not user_supplied.get("helicopter_model", False):
        try:
            model = HelicopterLonglineModel(value)
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown helicopter model override '{value}'.") from exc

    def maybe_float(
        key: str, current: float | None, supplied_flag: str, allow_zero: bool = False
    ) -> tuple[float | None, bool]:
        if user_supplied.get(supplied_flag, False):
            return current, False
        value = overrides.get(key)
        if value is None:
            return current, False
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover
            raise ValueError(f"Invalid helicopter override for '{key}': {value}") from exc
        if not allow_zero and coerced == 0:
            return current, False
        return coerced, True

    flight_distance_m, changed = maybe_float(
        "helicopter_flight_distance_m", flight_distance_m, "helicopter_flight_distance_m"
    )
    used |= changed
    payload_m3, changed = maybe_float(
        "helicopter_payload_m3", payload_m3, "helicopter_payload_m3", allow_zero=True
    )
    used |= changed
    load_factor, changed = maybe_float(
        "helicopter_load_factor", load_factor, "helicopter_load_factor", allow_zero=True
    )
    used |= changed
    weight_to_volume_lb_per_m3, changed = maybe_float(
        "helicopter_weight_to_volume",
        weight_to_volume_lb_per_m3,
        "helicopter_weight_to_volume",
        allow_zero=True,
    )
    used |= changed
    delay_value = overrides.get("helicopter_delay_minutes")
    if delay_value is not None and not user_supplied.get("helicopter_delay_minutes", False):
        delay_minutes = float(delay_value)
        used = True

    return (
        model,
        flight_distance_m,
        payload_m3,
        load_factor,
        weight_to_volume_lb_per_m3,
        delay_minutes,
        used,
    )


def _apply_grapple_yarder_system_defaults(
    *,
    system: HarvestSystem | None,
    model: GrappleYarderModel,
    turn_volume_m3: float | None,
    yarding_distance_m: float | None,
    lateral_distance_m: float | None,
    stems_per_cycle: float | None,
    in_cycle_delay_minutes: float | None,
    tn157_case: str,
    tn147_case: str,
    user_supplied: Mapping[str, bool],
) -> tuple[
    GrappleYarderModel,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    str,
    str,
    bool,
]:
    if system is None:
        return (
            model,
            turn_volume_m3,
            yarding_distance_m,
            lateral_distance_m,
            stems_per_cycle,
            in_cycle_delay_minutes,
            tn157_case,
            tn147_case,
            False,
        )
    overrides = system_productivity_overrides(system, ProductivityMachineRole.GRAPPLE_YARDER.value)
    if not overrides:
        return (
            model,
            turn_volume_m3,
            yarding_distance_m,
            lateral_distance_m,
            stems_per_cycle,
            in_cycle_delay_minutes,
            tn157_case,
            tn147_case,
            False,
        )
    used = False

    value = overrides.get("grapple_yarder_model")
    if value and not user_supplied.get("grapple_yarder_model", False):
        try:
            model = GrappleYarderModel(value)
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown grapple yarder model override '{value}'.") from exc

    def maybe_float(
        key: str, current: float | None, supplied_flag: str
    ) -> tuple[float | None, bool]:
        if user_supplied.get(supplied_flag, False):
            return current, False
        value = overrides.get(key)
        if value is None:
            return current, False
        try:
            return float(value), True
        except (TypeError, ValueError) as exc:  # pragma: no cover
            raise ValueError(f"Invalid grapple yarder override for '{key}': {value}") from exc

    turn_volume_m3, changed = maybe_float(
        "grapple_yarder_turn_volume_m3", turn_volume_m3, "grapple_turn_volume_m3"
    )
    used |= changed
    yarding_distance_m, changed = maybe_float(
        "grapple_yarder_yarding_distance_m", yarding_distance_m, "grapple_yarding_distance_m"
    )
    used |= changed
    lateral_distance_m, changed = maybe_float(
        "grapple_yarder_lateral_distance_m", lateral_distance_m, "grapple_lateral_distance_m"
    )
    used |= changed
    stems_per_cycle, changed = maybe_float(
        "grapple_yarder_stems_per_cycle", stems_per_cycle, "grapple_stems_per_cycle"
    )
    used |= changed
    in_cycle_delay_minutes, changed = maybe_float(
        "grapple_yarder_in_cycle_delay_minutes",
        in_cycle_delay_minutes,
        "grapple_in_cycle_delay_minutes",
    )
    used |= changed

    tn157_case_value = tn157_case
    if not user_supplied.get("tn157_case", False):
        override_case = overrides.get("grapple_yarder_tn157_case")
        if override_case is not None:
            try:
                tn157_case_value = _normalize_tn157_case(str(override_case))
                used = True
            except ValueError as exc:  # pragma: no cover - validated via unit tests
                raise ValueError(f"Unknown TN157 case override '{override_case}'.") from exc

    tn147_case_value = tn147_case
    if not user_supplied.get("tn147_case", False):
        override_case = overrides.get("grapple_yarder_tn147_case")
        if override_case is not None:
            try:
                tn147_case_value = _normalize_tn147_case(str(override_case))
                used = True
            except ValueError as exc:  # pragma: no cover - validated via unit tests
                raise ValueError(f"Unknown TN147 case override '{override_case}'.") from exc

    return (
        model,
        turn_volume_m3,
        yarding_distance_m,
        lateral_distance_m,
        stems_per_cycle,
        in_cycle_delay_minutes,
        tn157_case_value,
        tn147_case_value,
        used,
    )
    used |= changed
    crew_size, changed = maybe_float("skyline_crew_size", crew_size, "crew_size", True)
    used |= changed
    horizontal_distance_m, changed = maybe_float(
        "skyline_horizontal_distance_m", horizontal_distance_m, "horizontal_distance_m", True
    )
    used |= changed
    vertical_distance_m, changed = maybe_float(
        "skyline_vertical_distance_m", vertical_distance_m, "vertical_distance_m", True
    )
    used |= changed
    pieces_per_cycle, changed = maybe_float(
        "skyline_pieces_per_cycle", pieces_per_cycle, "pieces_per_cycle", True
    )
    used |= changed
    piece_volume_m3, changed = maybe_float(
        "skyline_piece_volume_m3", piece_volume_m3, "piece_volume_m3", True
    )
    used |= changed
    carriage_height_m, changed = maybe_float(
        "skyline_carriage_height_m", carriage_height_m, "carriage_height_m", True
    )
    used |= changed
    chordslope_percent, changed = maybe_float(
        "skyline_chordslope_percent", chordslope_percent, "chordslope_percent", True
    )
    used |= changed

    value = overrides.get("skyline_running_variant")
    if value and not user_supplied.get("running_yarder_variant", False):
        try:
            running_variant = RunningSkylineVariant(value)
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown running-skyline variant override '{value}'.") from exc

    return (
        model,
        logs_per_turn,
        average_log_volume_m3,
        crew_size,
        horizontal_distance_m,
        vertical_distance_m,
        pieces_per_cycle,
        piece_volume_m3,
        running_variant,
        carriage_height_m,
        chordslope_percent,
        used,
    )


def _forwarder_parameters(result: ForwarderBCResult) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("Model", result.model.value),
        ("Reference", result.reference or ""),
    ]
    params = result.parameters
    if result.model in _FORWARDER_GHAFFARIYAN_MODELS:
        extraction = params.get("extraction_distance_m")
        slope_class = params.get("slope_class")
        slope_factor = params.get("slope_factor")
        rows.extend(
            [
                ("Extraction Distance (m)", f"{float(extraction):.1f}"),
                ("Slope Class", str(slope_class)),
                ("Slope Factor", f"{float(slope_factor):.2f}"),
            ]
        )
    elif result.model in _FORWARDER_ADV1N12_MODELS:
        rows.extend(
            [
                ("Extraction Distance (m)", f"{float(params['extraction_distance_m']):.1f}"),
            ]
        )
    elif result.model in _FORWARDER_ADV6N10_MODELS:
        rows.extend(
            [
                ("Payload per Trip (m³)", f"{float(params['payload_m3']):.2f}"),
                ("Mean Log Length (m)", f"{float(params['mean_log_length_m']):.2f}"),
                ("Trail Length (m)", f"{float(params['trail_length_m']):.1f}"),
                (
                    "Travel Speed (m/min)",
                    f"{float(params['travel_speed_m_per_min']):.1f}",
                ),
                (
                    "Products per Trail",
                    f"{float(params['products_per_trail']):.2f}",
                ),
            ]
        )
    elif result.model in _FORWARDER_ERIKSSON_MODELS:
        rows.extend(
            [
                (
                    "Mean Extraction Distance (m)",
                    f"{float(params['mean_extraction_distance_m']):.1f}",
                ),
                ("Mean Stem Size (m³)", f"{float(params['mean_stem_size_m3']):.3f}"),
                ("Load Capacity (m³)", f"{float(params['load_capacity_m3']):.2f}"),
            ]
        )
    elif result.model in _FORWARDER_BRUSHWOOD_MODELS:
        rows.extend(
            [
                ("Harvested Trees (/ha)", f"{float(params['harvested_trees_per_ha']):.0f}"),
                (
                    "Average Tree Volume (dm³)",
                    f"{float(params['average_tree_volume_dm3']):.1f}",
                ),
                ("Forwarding Distance (m)", f"{float(params['forwarding_distance_m']):.1f}"),
                ("Harwarder Payload (m³)", f"{float(params['harwarder_payload_m3']):.2f}"),
                (
                    "Grapple Load (unloading, m³)",
                    f"{float(params['grapple_load_unloading_m3']):.2f}",
                ),
            ]
        )
    else:
        rows.extend(
            [
                ("Load Type", str(params.get("load_type", ""))),
                ("Volume per Load (m³)", f"{float(params['volume_per_load_m3']):.2f}"),
                ("Distance Out (m)", f"{float(params['distance_out_m']):.1f}"),
                ("Travel In Unit (m)", f"{float(params['travel_in_unit_m']):.1f}"),
                ("Distance In (m)", f"{float(params['distance_in_m']):.1f}"),
            ]
        )
    rows.append(("Predicted Productivity (m³/PMH0)", f"{result.predicted_m3_per_pmh:.2f}"))
    return rows


def _render_forwarder_result(result: ForwarderBCResult) -> None:
    rows = _forwarder_parameters(result)
    _render_kv_table("Forwarder Productivity Estimate", rows)
    console.print("[dim]Values expressed in PMH0 (productive machine hours without delays).[/dim]")
    if result.model in _FORWARDER_GHAFFARIYAN_MODELS:
        console.print(
            "[dim]Regression from Ghaffariyan et al. (2019) ALPACA thinning dataset.[/dim]"
        )
    elif result.model in _FORWARDER_ADV1N12_MODELS:
        console.print(
            "[dim]Regression from FPInnovations Advantage Vol. 1 No. 12 (Valmet 646 forwarder).[/dim]"
        )
    elif result.model in _FORWARDER_ADV6N10_MODELS:
        console.print(
            "[dim]Regression from Gingras & Favreau (2005) CTL sorting study (ADV6N10).[/dim]"
        )
    elif result.model in _FORWARDER_ERIKSSON_MODELS:
        console.print(
            "[dim]Regression from Eriksson & Lindroos (2014) Swedish follow-up study (700+ machines).[/dim]"
        )
    elif result.model in _FORWARDER_BRUSHWOOD_MODELS:
        console.print(
            "[dim]Regression from Laitila & Väätäinen (2020) Ponsse Buffalo Dual harwarder case study.[/dim]"
        )
    else:
        console.print(
            "[dim]Regression from Kellogg & Bettinger (1994) western Oregon CTL study.[/dim]"
        )


def _evaluate_forwarder_result(
    *,
    model: ForwarderBCModel,
    extraction_distance: float | None,
    slope_class: ALPACASlopeClass,
    slope_factor: float | None,
    volume_per_load: float | None,
    distance_out: float | None,
    travel_in_unit: float | None,
    distance_in: float | None,
    payload_per_trip: float | None,
    mean_log_length: float | None,
    travel_speed: float | None,
    trail_length: float | None,
    products_per_trail: float | None,
    mean_extraction_distance: float | None,
    mean_stem_size: float | None,
    load_capacity: float | None,
    harvested_trees_per_ha: float | None,
    avg_tree_volume_dm3: float | None,
    forwarding_distance: float | None,
    harwarder_payload: float | None,
    grapple_load_unloading: float | None,
) -> ForwarderBCResult:
    try:
        return estimate_forwarder_productivity_bc(
            model=model,
            extraction_distance_m=extraction_distance,
            slope_class=slope_class,
            slope_factor=slope_factor,
            volume_per_load_m3=volume_per_load,
            distance_out_m=distance_out,
            travel_in_unit_m=travel_in_unit,
            distance_in_m=distance_in,
            payload_m3=payload_per_trip,
            mean_log_length_m=mean_log_length,
            travel_speed_m_per_min=travel_speed,
            trail_length_m=trail_length,
            products_per_trail=products_per_trail,
            mean_extraction_distance_m=mean_extraction_distance,
            mean_stem_size_m3=mean_stem_size,
            load_capacity_m3=load_capacity,
            harvested_trees_per_ha=harvested_trees_per_ha,
            average_tree_volume_dm3=avg_tree_volume_dm3,
            forwarding_distance_m=forwarding_distance,
            harwarder_payload_m3=harwarder_payload,
            grapple_load_unloading_m3=grapple_load_unloading,
        )
    except ValueError as exc:  # pragma: no cover - Typer surfaces error text
        raise typer.BadParameter(str(exc)) from exc


def _evaluate_grapple_skidder_result(
    *,
    model: GrappleSkidderModel,
    pieces_per_cycle: float | None,
    piece_volume_m3: float | None,
    empty_distance_m: float | None,
    loaded_distance_m: float | None,
    trail_pattern: TrailSpacingPattern | None,
    decking_condition: DeckingCondition | None,
    custom_multiplier: float | None,
    speed_profile_option: SkidderSpeedProfileOption = SkidderSpeedProfileOption.LEGACY,
    extraction_distance_m: float | None,
    adv6n7_decking_mode: ADV6N7DeckingMode,
    adv6n7_payload_m3: float | None,
    adv6n7_utilisation: float | None,
    adv6n7_delay_minutes: float | None,
    adv6n7_support_ratio: float | None,
) -> SkidderProductivityResult | Mapping[str, object]:
    if model in {
        GrappleSkidderModel.ADV1N12_FULLTREE,
        GrappleSkidderModel.ADV1N12_TWO_PHASE,
    }:
        if extraction_distance_m is None:
            raise typer.BadParameter(
                "--skidder-extraction-distance is required for ADV1N12 skidder models."
            )
        if model is GrappleSkidderModel.ADV1N12_FULLTREE:
            value = estimate_cable_skidder_productivity_adv1n12_full_tree(extraction_distance_m)
            note = (
                "[dim]Integrated felling + skidding (semi-mechanized) from Advantage Vol. 1 No. 12. "
                "Productivity includes feller wait time effects.[/dim]"
            )
        else:
            value = estimate_cable_skidder_productivity_adv1n12_two_phase(extraction_distance_m)
            note = (
                "[dim]Two-phase thinning (dedicated extraction skidder) from Advantage Vol. 1 No. 12. "
                "Felling and extraction analyzed separately.[/dim]"
            )
        return {
            "model": model.value,
            "extraction_distance_m": extraction_distance_m,
            "productivity_m3_per_pmh": value,
            "note": note,
        }
    if model is GrappleSkidderModel.ADV6N7:
        if extraction_distance_m is None:
            raise typer.BadParameter("--skidder-extraction-distance is required for the ADV6N7 model.")
        try:
            return estimate_grapple_skidder_productivity_adv6n7(
                skidding_distance_m=extraction_distance_m,
                decking_mode=adv6n7_decking_mode,
                payload_m3=adv6n7_payload_m3,
                utilisation=adv6n7_utilisation,
                delay_minutes=adv6n7_delay_minutes,
                support_ratio=adv6n7_support_ratio,
            )
        except ValueError as exc:  # pragma: no cover - Typer surfaces message
            raise typer.BadParameter(str(exc)) from exc

    missing: list[str] = []
    if pieces_per_cycle is None:
        missing.append("--skidder-pieces-per-cycle")
    if piece_volume_m3 is None:
        missing.append("--skidder-piece-volume")
    if empty_distance_m is None:
        missing.append("--skidder-empty-distance")
    if loaded_distance_m is None:
        missing.append("--skidder-loaded-distance")
    if missing:
        raise typer.BadParameter(
            f"{', '.join(sorted(missing))} required when --machine-role {ProductivityMachineRole.GRAPPLE_SKIDDER.value}."
        )
    assert pieces_per_cycle is not None
    assert piece_volume_m3 is not None
    assert empty_distance_m is not None
    assert loaded_distance_m is not None

    profile_data: SkidderSpeedProfile | None = None
    if speed_profile_option is SkidderSpeedProfileOption.GNSS_SKIDDER:
        profile_data = get_skidder_speed_profile("SK")
    elif speed_profile_option is SkidderSpeedProfileOption.GNSS_FARM_TRACTOR:
        profile_data = get_skidder_speed_profile("FT")

    mapped_method = (
        Han2018SkidderMethod.LOP_AND_SCATTER
        if model is GrappleSkidderModel.HAN_LOP_AND_SCATTER
        else Han2018SkidderMethod.WHOLE_TREE
    )

    try:
        return estimate_grapple_skidder_productivity_han2018(
            method=mapped_method,
            pieces_per_cycle=pieces_per_cycle,
            piece_volume_m3=piece_volume_m3,
            empty_distance_m=empty_distance_m,
            loaded_distance_m=loaded_distance_m,
            trail_pattern=trail_pattern,
            decking_condition=decking_condition,
            custom_multiplier=custom_multiplier,
            speed_profile=profile_data,
        )
    except ValueError as exc:  # pragma: no cover
        raise typer.BadParameter(str(exc)) from exc


def _evaluate_grapple_yarder_result(
    *,
    model: GrappleYarderModel,
    turn_volume_m3: float | None,
    yarding_distance_m: float | None,
) -> float:
    missing: list[str] = []
    if turn_volume_m3 is None:
        missing.append("--grapple-turn-volume-m3")
    if yarding_distance_m is None:
        missing.append("--grapple-yard-distance-m")
    if missing:
        raise typer.BadParameter(
            f"{', '.join(sorted(missing))} required when --machine-role {ProductivityMachineRole.GRAPPLE_YARDER.value}."
        )
    assert turn_volume_m3 is not None
    assert yarding_distance_m is not None

    if model is GrappleYarderModel.SR54:
        return estimate_grapple_yarder_productivity_sr54(
            turn_volume_m3=turn_volume_m3, yarding_distance_m=yarding_distance_m
        )
    if model is GrappleYarderModel.TR75_BUNCHED:
        return estimate_grapple_yarder_productivity_tr75_bunched(
            turn_volume_m3=turn_volume_m3, yarding_distance_m=yarding_distance_m
        )
    if model is GrappleYarderModel.TR75_HANDFELLED:
        return estimate_grapple_yarder_productivity_tr75_handfelled(
            turn_volume_m3=turn_volume_m3, yarding_distance_m=yarding_distance_m
        )
    raise typer.BadParameter(f"Unsupported grapple yarder model: {model}")


def _evaluate_shovel_logger_result(
    *,
    passes: int | None,
    swing_length_m: float | None,
    strip_length_m: float | None,
    volume_per_ha_m3: float | None,
    swing_time_roadside_s: float | None,
    payload_per_swing_roadside_m3: float | None,
    swing_time_initial_s: float | None,
    payload_per_swing_initial_m3: float | None,
    swing_time_rehandle_s: float | None,
    payload_per_swing_rehandle_m3: float | None,
    travel_speed_index_kph: float | None,
    travel_speed_return_kph: float | None,
    travel_speed_serpentine_kph: float | None,
    effective_minutes_per_hour: float | None,
    slope_class: ShovelSlopeClass,
    bunching: ShovelBunching,
    custom_multiplier: float | None,
) -> ShovelLoggerResult:
    base = ShovelLoggerSessions2006Inputs().__dict__.copy()

    def _set_if(value: float | int | None, key: str) -> None:
        if value is not None:
            base[key] = value

    _set_if(passes, "passes")
    _set_if(swing_length_m, "swing_length_m")
    _set_if(strip_length_m, "strip_length_m")
    _set_if(volume_per_ha_m3, "volume_per_ha_m3")
    _set_if(swing_time_roadside_s, "swing_time_roadside_s")
    _set_if(payload_per_swing_roadside_m3, "payload_per_swing_roadside_m3")
    _set_if(swing_time_initial_s, "swing_time_initial_s")
    _set_if(payload_per_swing_initial_m3, "payload_per_swing_initial_m3")
    _set_if(swing_time_rehandle_s, "swing_time_rehandle_s")
    _set_if(payload_per_swing_rehandle_m3, "payload_per_swing_rehandle_m3")
    _set_if(travel_speed_index_kph, "travel_speed_index_kph")
    _set_if(travel_speed_return_kph, "travel_speed_return_kph")
    _set_if(travel_speed_serpentine_kph, "travel_speed_serpentine_kph")
    _set_if(effective_minutes_per_hour, "effective_minutes_per_hour")

    try:
        inputs = ShovelLoggerSessions2006Inputs(**base)
    except ValueError as exc:  # pragma: no cover
        raise typer.BadParameter(str(exc)) from exc
    try:
        return estimate_shovel_logger_productivity_sessions2006(
            inputs,
            slope_multiplier=_shovel_slope_multiplier(slope_class),
            bunching_multiplier=_shovel_bunching_multiplier(bunching),
            custom_multiplier=custom_multiplier or 1.0,
        )
    except ValueError as exc:  # pragma: no cover
        raise typer.BadParameter(str(exc)) from exc


def _render_ctl_harvester_result(
    model: CTLHarvesterModel, inputs: object, productivity: float
) -> None:
    rows: list[tuple[str, str]] = [("Model", model.value)]
    if model is CTLHarvesterModel.ADV6N10 and isinstance(inputs, ADV6N10HarvesterInputs):
        rows.extend(
            [
                ("Stem Volume (m³/stem)", f"{inputs.stem_volume_m3:.3f}"),
                ("Number of Products", f"{inputs.products_count:.2f}"),
                ("Stems per Cycle", f"{inputs.stems_per_cycle:.2f}"),
                ("Mean Log Length (m)", f"{inputs.mean_log_length_m:.2f}"),
            ]
        )
        source = "Gingras & Favreau (2005) ADV6N10 boreal CTL sorting study"
    elif model is CTLHarvesterModel.ADV5N30 and isinstance(inputs, dict):
        rows.extend(
            [
                ("Removal Fraction", f"{inputs['removal_fraction']:.2f}"),
                ("Brushed?", "yes" if inputs.get("brushed") else "no"),
            ]
        )
        source = "Meek (2004) ADV5N30 Alberta white spruce thinning study"
    elif model is CTLHarvesterModel.TN292 and isinstance(inputs, TN292HarvesterInputs):
        rows.extend(
            [
                ("Stem Volume (m³/stem)", f"{inputs.stem_volume_m3:.3f}"),
                ("Stand Density (/ha)", f"{inputs.stand_density_per_ha:.0f}"),
                ("Density Basis", inputs.density_basis),
            ]
        )
        source = "Bulley (1999) TN292 Alberta thinning study"
    elif model is CTLHarvesterModel.KELLOGG1994 and isinstance(inputs, dict):
        rows.extend(
            [
                ("DBH (cm)", f"{inputs['dbh_cm']:.1f}"),
            ]
        )
        source = "Kellogg & Bettinger (1994) western Oregon CTL thinning study"
    else:
        raise RuntimeError("Unhandled CTL harvester model payload.")
    rows.append(("Predicted Productivity (m³/PMH)", f"{productivity:.2f}"))
    _render_kv_table("CTL Harvester Productivity Estimate", rows)
    console.print(f"[dim]Regression from {source}.[/dim]")


def _evaluate_ctl_harvester_result(
    *,
    model: CTLHarvesterModel,
    stem_volume: float | None,
    products_count: float | None,
    stems_per_cycle: float | None,
    mean_log_length: float | None,
    removal_fraction: float | None,
    brushed: bool,
    density: float | None,
    density_basis: str,
    dbh_cm: float | None,
) -> tuple[object, float]:
    if model is CTLHarvesterModel.ADV6N10:
        missing = []
        if stem_volume is None:
            missing.append("--ctl-stem-volume")
        if products_count is None:
            missing.append("--ctl-products-count")
        if stems_per_cycle is None:
            missing.append("--ctl-stems-per-cycle")
        if mean_log_length is None:
            missing.append("--ctl-mean-log-length")
        if missing:
            raise typer.BadParameter(
                f"{', '.join(missing)} required when --machine-role {ProductivityMachineRole.CTL_HARVESTER.value} with ADV6N10 model."
            )
        inputs = ADV6N10HarvesterInputs(
            stem_volume_m3=stem_volume,
            products_count=products_count,
            stems_per_cycle=stems_per_cycle,
            mean_log_length_m=mean_log_length,
        )
        try:
            value = estimate_harvester_productivity_adv6n10(inputs)
        except FHOPSValueError as exc:  # pragma: no cover - Typer surfaces error
            raise typer.BadParameter(str(exc)) from exc
        return inputs, value
    if model is CTLHarvesterModel.ADV5N30:
        if removal_fraction is None:
            raise typer.BadParameter("--ctl-removal-fraction required for ADV5N30 model.")
        try:
            value = estimate_harvester_productivity_adv5n30(
                removal_fraction=removal_fraction,
                brushed=brushed,
            )
        except FHOPSValueError as exc:  # pragma: no cover
            raise typer.BadParameter(str(exc)) from exc
        return {"removal_fraction": removal_fraction, "brushed": brushed}, value
    if model is CTLHarvesterModel.TN292:
        missing = []
        if stem_volume is None:
            missing.append("--ctl-stem-volume")
        if density is None:
            missing.append("--ctl-density")
        if missing:
            raise typer.BadParameter(
                f"{', '.join(missing)} required when --machine-role {ProductivityMachineRole.CTL_HARVESTER.value} with TN292 model."
            )
        inputs = TN292HarvesterInputs(
            stem_volume_m3=stem_volume,
            stand_density_per_ha=density,
            density_basis=density_basis,
        )
        try:
            value = estimate_harvester_productivity_tn292(inputs)
        except FHOPSValueError as exc:  # pragma: no cover
            raise typer.BadParameter(str(exc)) from exc
        return inputs, value
    if model is CTLHarvesterModel.KELLOGG1994:
        if dbh_cm is None:
            raise typer.BadParameter("--ctl-dbh-cm is required for Kellogg (1994) model.")
        try:
            value = estimate_harvester_productivity_kellogg1994(dbh_cm=dbh_cm)
        except FHOPSValueError as exc:  # pragma: no cover
            raise typer.BadParameter(str(exc)) from exc
        return {"dbh_cm": dbh_cm}, value
    raise typer.BadParameter(f"Unsupported CTL harvester model: {model}")


def _candidate_roots() -> list[Path]:
    """Return candidate roots to resolve bundled dataset paths."""
    roots = [Path.cwd()]
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if parent not in roots:
            roots.append(parent)
    return roots


def _resolve_known_dataset(ref: DatasetRef) -> Path:
    rel_path = ref.path
    candidates: list[Path] = []
    if rel_path.is_absolute():
        candidates.append(rel_path)
    else:
        for root in _candidate_roots():
            candidates.append((root / rel_path).resolve())
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except FileNotFoundError:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    raise FileNotFoundError(f"Bundled dataset not found: {rel_path}")


def _resolve_scenario_from_path(path: Path) -> Path:
    expanded = path.expanduser().resolve()
    if not expanded.exists():
        raise FileNotFoundError(expanded)
    if expanded.is_file():
        return expanded
    scenario_file = expanded / "scenario.yaml"
    if scenario_file.exists():
        return scenario_file
    yaml_files = sorted(expanded.glob("*.yaml"))
    if len(yaml_files) == 1:
        return yaml_files[0]
    raise FileNotFoundError(
        f"No scenario YAML found under {expanded}. "
        "Place a scenario.yaml file or specify the path directly."
    )


def _resolve_dataset(identifier: str) -> tuple[str, Path]:
    key = identifier.strip()
    if not key:
        raise typer.BadParameter("Dataset identifier must be non-empty.")
    if key in KNOWN_DATASETS:
        ref = KNOWN_DATASETS[key]
        path = _resolve_known_dataset(ref)
        return ref.name, path

    candidate = Path(key)
    if candidate.exists():
        return candidate.name, _resolve_scenario_from_path(candidate)

    raise typer.BadParameter(
        f"Dataset '{identifier}' not recognised. Provide a bundled name "
        f"({', '.join(sorted(KNOWN_DATASETS))}) or a valid path to a scenario."
    )


def _prompt_choice(message: str, options: list[str]) -> str:
    if not options:
        raise typer.BadParameter("No options available to prompt.")
    for idx, option in enumerate(options, start=1):
        console.print(f"{idx}. {option}")
    while True:
        choice = typer.prompt(f"{message} [1-{len(options)}]")
        try:
            idx = int(choice)
        except ValueError:
            console.print("[red]Enter a numeric choice.[/red]")
            continue
        if 1 <= idx <= len(options):
            return options[idx - 1]
        console.print("[red]Choice out of range.[/red]")


def _ensure_dataset(identifier: str | None, interactive: bool) -> tuple[str, Scenario, Path]:
    dataset_id = identifier
    if dataset_id is None:
        if not interactive:
            raise typer.BadParameter("Dataset identifier is required when prompts are disabled.")
        dataset_id = typer.prompt(
            f"Dataset name or scenario path (bundled options: {', '.join(sorted(KNOWN_DATASETS))})"
        )
    name, path = _resolve_dataset(dataset_id)
    scenario = load_scenario(path)
    return name, scenario, path


def _scenario_systems(scenario: Scenario) -> dict[str, HarvestSystem]:
    return scenario.harvest_systems or dict(default_system_registry())


def _select_system(
    scenario: Scenario, system_id: str | None, interactive: bool
) -> tuple[str, HarvestSystem] | None:
    systems = _scenario_systems(scenario)
    if not systems:
        return None
    if system_id:
        system = systems.get(system_id)
        if system is None:
            raise typer.BadParameter(
                f"Unknown harvest system '{system_id}'. Options: {', '.join(sorted(systems))}"
            )
        return system.system_id, system
    if not interactive:
        raise typer.BadParameter("System selection required when prompts are disabled.")
    choice = _prompt_choice("Select a harvest system", sorted(systems))
    return choice, systems[choice]


def _select_machine(
    scenario: Scenario, machine_id: str | None, interactive: bool, system: HarvestSystem | None
):
    machines = {machine.id: machine for machine in scenario.machines}
    if machine_id:
        machine = machines.get(machine_id)
        if machine is None:
            raise typer.BadParameter(
                f"Machine '{machine_id}' not found. Options: {', '.join(sorted(machines))}"
            )
        return machine
    relevant_ids: list[str]
    if system:
        roles = {job.machine_role for job in system.jobs}
        relevant_ids = sorted(
            [machine.id for machine in scenario.machines if machine.role in roles]
        )
    else:
        relevant_ids = sorted(machines)
    if not relevant_ids:
        relevant_ids = sorted(machines)
    if not interactive:
        raise typer.BadParameter("Machine selection required when prompts are disabled.")
    choice = _prompt_choice("Select a machine", relevant_ids)
    return machines[choice]


def _select_block(scenario: Scenario, block_id: str | None, interactive: bool):
    blocks = {block.id: block for block in scenario.blocks}
    if block_id:
        block = blocks.get(block_id)
        if block is None:
            raise typer.BadParameter(
                f"Block '{block_id}' not found. Options: {', '.join(sorted(blocks))}"
            )
        return block
    if not interactive:
        raise typer.BadParameter("Block selection required when prompts are disabled.")
    choice = _prompt_choice("Select a block", sorted(blocks))
    return blocks[choice]


def _render_kv_table(title: str, rows: Iterable[tuple[str, str]]) -> None:
    table = Table(title=title, show_header=False, expand=True)
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)


def _render_berry_log_grade_table() -> None:
    stats = get_berry_log_grade_stats()
    if not stats:
        console.print("[dim]No Berry (2019) log-grade statistics are available.[/dim]")
        return
    table = Table(title="Berry (2019) Log-Grade Cycle Times", header_style="bold cyan", expand=True)
    table.add_column("Grade", style="bold")
    table.add_column("Mean (min)", justify="right")
    table.add_column("-2 (min)", justify="right")
    table.add_column("+2 (min)", justify="right")
    for stat in stats:
        table.add_row(
            stat.grade,
            f"{stat.mean_minutes:.2f}",
            f"{stat.lo_minutes:.2f}",
            f"{stat.hi_minutes:.2f}",
        )
    console.print(table)
    metadata = get_berry_log_grade_metadata()
    source = metadata.get("source")
    description = metadata.get("description")
    if description:
        console.print(f"[dim]{description}[/dim]")
    if source:
        console.print(f"[dim]Source: {source}[/dim]")
    for note in metadata.get("notes", ()):  # type: ignore[arg-type]
        console.print(f"[dim]{note}[/dim]")


def _render_unbc_hoe_chucking_table() -> None:
    scenarios = load_unbc_hoe_chucking_data()
    if not scenarios:
        console.print("[dim]No UNBC hoe-chucking data available.[/dim]")
        return
    table = Table(
        title="UNBC Hoe-Chucking Cost/Productivity", header_style="bold cyan", expand=True
    )
    table.add_column("Treatment", style="bold")
    table.add_column("Hours", justify="right")
    table.add_column("Volume (m³)", justify="right")
    table.add_column("Productivity (m³/SMH)", justify="right")
    table.add_column("Observed $/m³", justify="right")
    table.add_column("Weighted $/m³", justify="right")
    for scenario in scenarios:
        productivity = (
            f"{scenario.productivity_m3_per_smh:.2f}" if scenario.productivity_m3_per_smh else "—"
        )
        table.add_row(
            scenario.treatment.replace("_", " "),
            f"{scenario.time_hours:.1f}",
            f"{scenario.volume_m3:.1f}",
            productivity,
            f"{scenario.observed_cost_cad_per_m3:.2f}",
            f"{scenario.weighted_cost_cad_per_m3:.2f}"
            if scenario.weighted_cost_cad_per_m3
            else "—",
        )
    console.print(table)
    console.print(
        "[dim]Source: UNBC MSc thesis (Renzie 2006), Table 33 (Minnow block hoe-chucking shift summary)."
    )


def _render_unbc_processing_table() -> None:
    scenarios = load_unbc_processing_costs()
    if not scenarios:
        console.print("[dim]No UNBC processing cost data available.[/dim]")
        return
    table = Table(
        title="UNBC Manual Processing Cost (Table 20)", header_style="bold cyan", expand=True
    )
    table.add_column("System", style="bold")
    table.add_column("Treatment")
    table.add_column("Layout $/m³", justify="right")
    table.add_column("Felling $/m³", justify="right")
    table.add_column("Skid/Yard $/m³", justify="right")
    table.add_column("Processing $/m³", justify="right")
    table.add_column("Loading $/m³", justify="right")
    table.add_column("Total $/m³", justify="right")
    for scenario in scenarios:
        table.add_row(
            scenario.harvesting_system.replace("_", " "),
            scenario.treatment.replace("_", " "),
            f"{scenario.layout_planning_cost_cad_per_m3:.2f}",
            f"{scenario.felling_cost_cad_per_m3:.2f}",
            f"{scenario.skidding_yarding_cost_cad_per_m3:.2f}",
            f"{scenario.processing_cost_cad_per_m3:.2f}",
            f"{scenario.loading_cost_cad_per_m3:.2f}",
            f"{scenario.total_cost_cad_per_m3:.2f}",
        )
    console.print(table)
    console.print(
        "[dim]Source: UNBC MSc thesis (Renzie 2006), Table 20/21 (East Twin). Costs are per SMH."
    )


def _render_unbc_construction_table() -> None:
    scenarios = load_unbc_construction_costs()
    if not scenarios:
        return
    table = Table(
        title="UNBC Skid Trail + Landing Construction (Table 20)",
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("System", style="bold")
    table.add_column("Treatment")
    table.add_column("Hours", justify="right")
    table.add_column("Rate $/h", justify="right")
    table.add_column("Volume (m³)", justify="right")
    table.add_column("Cost $/m³", justify="right")
    for entry in scenarios:
        table.add_row(
            entry.harvesting_system.replace("_", " "),
            entry.treatment.replace("_", " "),
            f"{entry.time_hours:.2f}",
            f"{entry.hourly_rate_cad:.2f}",
            f"{entry.final_net_volume_m3:.1f}",
            f"{entry.cost_cad_per_m3:.2f}",
        )
    console.print(table)
    console.print(
        "[dim]Source: UNBC MSc thesis (Renzie 2006), Table 20 (skid trail & landing construction). Costs per SMH."
    )


def _print_salvage_processing_guidance(
    *,
    mode: SalvageProcessingMode,
    system_id: str,
) -> None:
    if mode is SalvageProcessingMode.PORTABLE_MILL:
        console.print(
            "[dim]Salvage system '%s' in portable-mill mode: rough cants stay near the satellite yard, keeping "
            "char-laden slabs onsite per ADV1N5. Remember to segregate chip furnish from dirty sorts before hauling." % system_id
        )
    elif mode is SalvageProcessingMode.IN_WOODS_CHIPPING:
        console.print(
            "[dim]Salvage system '%s' in in-woods chipping mode: separate pulp logs at the stump, feed the portable "
            "chip plant, screen fines, and truck chips directly so small charred stems never hit the mill deck." % system_id
        )
    else:
        console.print(
            "[dim]Salvage system '%s' using standard mill flow. Apply the ADV1N5 checklist (raise top diameters, "
            "buck out catfaces, double-ring debarkers, charcoal dust controls) before chips enter the regular furnish." % system_id
        )


@dataset_app.command("inspect-machine")
def inspect_machine(
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "-d",
        help="Dataset name (e.g., minitoy) or path to scenario/dataset folder.",
    ),
    system: str | None = typer.Option(
        None, "--system", "-s", help="Harvest system ID to focus on (prompts if omitted)."
    ),
    machine: str | None = typer.Option(
        None, "--machine", "-m", help="Machine ID to inspect (prompts if omitted)."
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Enable prompts when context is missing.",
    ),
    machine_role_override: str | None = typer.Option(
        None,
        "--machine-role",
        help=(
            "Inspect the default rental-rate entry for a machine role without loading a dataset. "
            + _machine_rate_roles_help()
        ),
    ),
    json_out: Path | None = typer.Option(
        None,
        "--json-out",
        help="Optional path to write machine metadata and rental breakdown as JSON.",
        writable=True,
        dir_okay=False,
    ),
    show_costs: bool = typer.Option(
        False,
        "--show-costs/--hide-costs",
        help="Display the default machine-rate breakdown (owning/operating/repair) inflated to 2024 CAD.",
    ),
):
    """Inspect machine parameters within a dataset/system context."""
    if dataset is None:
        if machine_role_override is None:
            if not interactive:
                raise typer.BadParameter(
                    "Provide --dataset/--machine or specify --machine-role to inspect the rate table."
                )
            raise typer.BadParameter("Dataset identifier is required when prompts are disabled.")
        _render_machine_cost_summary(machine_role_override)
        if json_out is not None:
            rate = _resolve_machine_rate(machine_role_override)
            composed = compose_default_rental_rate_for_role(machine_role_override)
            if composed is None:
                raise typer.BadParameter(
                    f"Unable to compose rental rate for role '{machine_role_override}'."
                )
            rental_rate, breakdown = composed
            payload = {
                "machine_role": machine_role_override,
                "machine_name": rate.machine_name,
                "rental_rate_smh": rental_rate,
                "breakdown": breakdown,
                "cost_base_year": rate.cost_base_year,
                "source": rate.source,
                "notes": rate.notes,
            }
            json_out.parent.mkdir(parents=True, exist_ok=True)
            json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return

    dataset_name, scenario, path = _ensure_dataset(dataset, interactive)
    system_selection = _select_system(scenario, system, interactive)
    selected_machine = _select_machine(
        scenario, machine, interactive, system_selection[1] if system_selection else None
    )
    cost_role_hint = machine_role_override
    cost_role_note: str | None = None
    if cost_role_hint:
        cost_role_note = f"[dim]Cost role manually overridden to '{cost_role_hint}' for rental-rate lookup.[/dim]"

    context_lines = [
        ("Dataset", dataset_name),
        ("Scenario Path", str(path)),
        ("Machine ID", selected_machine.id),
        ("Crew", selected_machine.crew or "—"),
        ("Daily Hours", f"{selected_machine.daily_hours}"),
        ("Operating Cost", f"{selected_machine.operating_cost}"),
        ("Role", selected_machine.role or "—"),
    ]
    machine_for_snapshot = selected_machine
    if cost_role_hint and hasattr(selected_machine, "model_copy"):
        try:
            machine_for_snapshot = selected_machine.model_copy(update={"role": cost_role_hint})
        except Exception:  # pragma: no cover - defensive fallback
            machine_for_snapshot = selected_machine
    default_snapshot = build_machine_cost_snapshots([machine_for_snapshot])[0]
    default_rate_rows: list[tuple[str, str]] = []
    default_rate_note: str | None = None
    if default_snapshot.rental_rate_smh is not None:
        default_rate_rows.append(
            ("Default Rental Rate ($/SMH)", f"{default_snapshot.rental_rate_smh:.2f}")
        )
        if default_snapshot.ownership is not None:
            default_rate_rows.append(
                ("Default Owning ($/SMH)", f"{default_snapshot.ownership:.2f}")
            )
        if default_snapshot.operating is not None:
            default_rate_rows.append(
                ("Default Operating ($/SMH)", f"{default_snapshot.operating:.2f}")
            )
        if default_snapshot.repair_maintenance is not None:
            default_rate_rows.append(
                ("Default Repair/Maint. ($/SMH)", f"{default_snapshot.repair_maintenance:.2f}")
            )
        if default_snapshot.usage_bucket_hours is not None:
            default_rate_rows.append(
                (
                    "Repair Usage Bucket",
                    f"{default_snapshot.usage_bucket_hours:,} h (multiplier {default_snapshot.usage_multiplier:.3f})",
                )
            )
            effective_role = machine_for_snapshot.role or selected_machine.role
            usage_hours = selected_machine.repair_usage_hours
            usage_text = (
                f"{usage_hours:,} h"
                if usage_hours is not None
                else f"{default_snapshot.usage_bucket_hours:,} h"
            )
            default_rate_note = (
                f"[dim]Default rate derived from role '{effective_role}' "
                f"with repair usage {usage_text} "
                f"(closest bucket {default_snapshot.usage_bucket_hours / 1000:.0f}×1000 h).[/dim]"
            )
        if (
            default_snapshot.cost_base_year is not None
            and default_snapshot.cost_base_year != TARGET_YEAR
        ):
            default_rate_rows.append(
                (
                    "Cost Base Year",
                    f"{default_snapshot.cost_base_year} CAD (inflated to {TARGET_YEAR})",
                )
            )
        elif selected_machine.repair_usage_hours is not None:
            default_rate_rows.append(
                (
                    "Repair Usage Bucket",
                    f"{selected_machine.repair_usage_hours:,} h (no FPInnovations bucket data)",
                )
            )
    if system_selection:
        system_id, system_model = system_selection
        job_matches: list[str] = []
        for job in system_model.jobs:
            if selected_machine.role and job.machine_role == selected_machine.role:
                job_matches.append(job.name)
                if cost_role_hint is None:
                    hint = _derive_cost_role_override(
                        selected_machine.role, job.productivity_overrides
                    )
                    if hint:
                        cost_role_hint = hint
                        cost_role_note = (
                            f"[dim]Harvest system '{system_id}' pins loader_model="
                            f"{job.productivity_overrides.get('loader_model')} so "
                            f"machine-rate role '{hint}' is used for cost summaries.[/dim]"
                        )
        context_lines.append(("Harvest System", system_id))
        context_lines.append(
            ("System Jobs Matched", ", ".join(job_matches) if job_matches else "—")
        )

    if cost_role_hint and cost_role_hint != selected_machine.role:
        context_lines.append(("Cost Role Override", cost_role_hint))
    _render_kv_table(f"Machine Inspection — {selected_machine.id}", context_lines)
    note_lines: list[str] = []
    if default_rate_note:
        note_lines.append(default_rate_note)
    if cost_role_note:
        note_lines.append(cost_role_note)

    if default_rate_rows:
        _render_kv_table("Default Rental Breakdown", default_rate_rows)
        for line in note_lines:
            console.print(line)
    if abs(selected_machine.daily_hours - 24.0) > 1e-6:
        console.print(
            "[red]Warning:[/red] machine daily_hours="
            f"{selected_machine.daily_hours} differs from the 24 h/day baseline."
        )
    console.print(
        "[yellow]* TODO: add derived statistics (utilisation, availability) once defined.[/yellow]"
    )
    if json_out is not None:
        payload = {
            "dataset": dataset_name,
            "scenario_path": str(path),
            "machine": {
                "id": selected_machine.id,
                "crew": selected_machine.crew,
                "daily_hours": selected_machine.daily_hours,
                "operating_cost": selected_machine.operating_cost,
                "role": selected_machine.role,
                "repair_usage_hours": selected_machine.repair_usage_hours,
            },
            "default_rental": default_snapshot.to_dict(),
        }
        if cost_role_hint and cost_role_hint != selected_machine.role:
            payload["machine"]["role_override"] = cost_role_hint
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataset_app.command("inspect-block")
def inspect_block(
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "-d",
        help="Dataset name (e.g., minitoy) or path to scenario/dataset folder.",
    ),
    block: str | None = typer.Option(
        None, "--block", "-b", help="Block ID to inspect (prompts if omitted)."
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Enable prompts when context is missing.",
    ),
):
    """Inspect a single block's declared parameters."""
    dataset_name, scenario, path = _ensure_dataset(dataset, interactive)
    selected_block = _select_block(scenario, block, interactive)
    rows = [
        ("Dataset", dataset_name),
        ("Scenario Path", str(path)),
        ("Block ID", selected_block.id),
        ("Landing ID", selected_block.landing_id),
        ("Work Required", f"{selected_block.work_required}"),
        ("Earliest Start", str(selected_block.earliest_start or 1)),
        (
            "Latest Finish",
            str(selected_block.latest_finish or scenario.num_days),
        ),
        ("Harvest System ID", selected_block.harvest_system_id or "—"),
    ]
    if selected_block.avg_stem_size_m3 is not None:
        rows.append(("Avg Stem Size (m³)", f"{selected_block.avg_stem_size_m3:.3f}"))
    if selected_block.volume_per_ha_m3 is not None:
        rows.append(("Volume per ha (m³)", f"{selected_block.volume_per_ha_m3:.1f}"))
    if selected_block.volume_per_ha_m3_sigma is not None:
        rows.append(("Volume per ha σ (m³)", f"{selected_block.volume_per_ha_m3_sigma:.1f}"))
    if selected_block.stem_density_per_ha is not None:
        rows.append(("Stem Density (/ha)", f"{selected_block.stem_density_per_ha:.1f}"))
    if selected_block.stem_density_per_ha_sigma is not None:
        rows.append(("Stem Density σ (/ha)", f"{selected_block.stem_density_per_ha_sigma:.1f}"))
    if selected_block.ground_slope_percent is not None:
        rows.append(("Ground Slope (%)", f"{selected_block.ground_slope_percent:.1f}"))
    _render_kv_table(f"Block Inspection — {selected_block.id}", rows)
    warnings = validate_block_ranges(
        block_id=selected_block.id,
        stem_size=selected_block.avg_stem_size_m3,
        volume_per_ha=selected_block.volume_per_ha_m3,
        stem_density=selected_block.stem_density_per_ha,
        ground_slope=selected_block.ground_slope_percent,
    )
    if warnings:
        console.print("[red]Stand metric warnings:[/red]")
        for msg in warnings:
            console.print(f"  - {msg}")
    console.print(
        "[yellow]* TODO: add derived statistics (windows, production rates) once defined.[/yellow]"
    )


@dataset_app.command("berry-log-grades")
def berry_log_grades_cmd() -> None:
    """Show the digitised Berry (2019) log-grade cycle-time emmeans."""

    _render_berry_log_grade_table()


@dataset_app.command("unbc-hoe-chucking")
def unbc_hoe_chucking_cmd() -> None:
    """Show the UNBC hoe-chucking and manual processing references."""

    _render_unbc_hoe_chucking_table()
    _render_unbc_processing_table()
    _render_unbc_construction_table()


@dataset_app.command("adv2n21-summary")
def adv2n21_summary_cmd(
    treatment: str | None = typer.Option(
        None,
        "--treatment",
        "-t",
        help="Treatment ID to inspect (e.g., partial_cut_2). Omit to list all ADV2N21 treatments.",
    ),
) -> None:
    """Summarize ADV2N21 Timberjack 1270/1010 partial-cut cost & stand context."""

    treatments = load_adv2n21_treatments()
    base_year = adv2n21_cost_base_year()
    if treatment:
        entry = get_adv2n21_treatment(treatment)
        rows = [
            ("Label", entry.label),
            ("Treatment ID", entry.id),
            ("Type", entry.treatment_type.replace("_", " ")),
            ("Objective", entry.objective),
            ("Area (ha)", f"{entry.area_ha:.2f}" if entry.area_ha is not None else "—"),
            (f"Cost ({base_year} CAD $/m³)", f"{entry.cost_per_m3_cad_1997:.2f}"),
            (
                "Increase vs. Clearcut 1 (%)",
                f"{entry.cost_increase_percent_vs_clearcut1:.0f}",
            ),
            ("Site Limitations", entry.site_limitations or "—"),
            ("CPPA Class", entry.cppt_classification or "—"),
        ]
        _render_kv_table(f"ADV2N21 Treatment — {entry.label}", rows)
        if entry.pre_harvest:
            _render_adv2n21_stand("Pre-harvest Stand Metrics", entry.pre_harvest)
        if entry.post_harvest:
            _render_adv2n21_stand("Post-harvest Stand Metrics", entry.post_harvest)
        console.print(
            "[dim]Costs follow FERIC 1997 ownership/operating assumptions (Advantage Vol. 2 No. 21).[/dim]"
        )
        return

    table = Table(title="ADV2N21 Treatment Cost Summary")
    table.add_column("Treatment ID", style="cyan", no_wrap=True)
    table.add_column("Type")
    table.add_column(f"Cost ({base_year} CAD $/m³)", justify="right")
    table.add_column("Δ vs. Clearcut 1 (%)", justify="right")
    table.add_column("Site Limitations", overflow="fold")
    for entry in treatments:
        table.add_row(
            entry.id,
            entry.treatment_type.replace("_", " "),
            f"{entry.cost_per_m3_cad_1997:.2f}",
            f"{entry.cost_increase_percent_vs_clearcut1:.0f}",
            entry.site_limitations,
        )
    console.print(table)
    console.print(
        "[dim]Use --treatment to drill into pre/post stand tables or cite scenario constraints.[/dim]"
    )


def _render_adv2n21_stand(title: str, snapshot: ADV2N21StandSnapshot) -> None:
    rows: list[tuple[str, str]] = []
    if snapshot.merchantable_basal_area_m2_per_ha is not None:
        rows.append(
            (
                "Merchantable Basal Area (m²/ha)",
                f"{snapshot.merchantable_basal_area_m2_per_ha:.1f}",
            )
        )
    if snapshot.live_trees_per_ha is not None:
        rows.append(("Live Trees (/ha)", f"{snapshot.live_trees_per_ha:.0f}"))
    if snapshot.dead_trees_per_ha is not None:
        rows.append(("Dead Trees (/ha)", f"{snapshot.dead_trees_per_ha:.0f}"))
    if snapshot.total_trees_per_ha is not None:
        rows.append(("Total Trees (/ha)", f"{snapshot.total_trees_per_ha:.0f}"))
    if snapshot.live_volume_m3_per_ha is not None:
        rows.append(("Live Volume (m³/ha)", f"{snapshot.live_volume_m3_per_ha:.1f}"))
    if snapshot.dead_volume_m3_per_ha is not None:
        rows.append(("Dead Volume (m³/ha)", f"{snapshot.dead_volume_m3_per_ha:.1f}"))
    if snapshot.total_volume_m3_per_ha is not None:
        rows.append(("Total Volume (m³/ha)", f"{snapshot.total_volume_m3_per_ha:.1f}"))
    if snapshot.avg_dbh_cm is not None:
        rows.append(("Average DBH (cm)", f"{snapshot.avg_dbh_cm:.1f}"))
    if snapshot.avg_height_m is not None:
        rows.append(("Average Height (m)", f"{snapshot.avg_height_m:.1f}"))
    if snapshot.avg_tree_volume_m3 is not None:
        rows.append(("Average Tree Volume (m³)", f"{snapshot.avg_tree_volume_m3:.2f}"))
    _render_kv_table(title, rows or [("Note", "Stand metrics not published for this treatment.")])


@dataset_app.command("estimate-productivity")
def estimate_productivity_cmd(
    ctx: typer.Context,
    machine_role: ProductivityMachineRole = typer.Option(
        ProductivityMachineRole.FELLER_BUNCHER,
        "--machine-role",
        case_sensitive=False,
        help=(
            "Machine role to evaluate "
            "(feller_buncher | forwarder | ctl_harvester | grapple_skidder | grapple_yarder | "
            "roadside_processor | loader | shovel_logger | helicopter_longline)."
        ),
    ),
    show_costs: bool = typer.Option(
        False,
        "--show-costs/--hide-costs",
        help="Display the default machine-rate breakdown (owning/operating/repair) inflated to 2024 CAD.",
    ),
    avg_stem_size: float | None = typer.Option(
        None,
        "--avg-stem-size",
        min=0.0,
        help="Average harvested stem size (m³/stem). Required for feller-buncher models.",
    ),
    volume_per_ha: float | None = typer.Option(
        None,
        "--volume-per-ha",
        min=0.0,
        help="Average harvested volume per hectare (m³/ha). Required for feller-buncher models.",
    ),
    stem_density: float | None = typer.Option(
        None,
        "--stem-density",
        min=0.0,
        help="Average stem density (trees/ha). Required for feller-buncher models.",
    ),
    ground_slope: float | None = typer.Option(
        None,
        "--ground-slope",
        min=0.0,
        help="Average ground slope (percent). Required for feller-buncher models.",
    ),
    model: LahrsenModel = typer.Option(
        LahrsenModel.DAILY,
        "--model",
        case_sensitive=False,
        help="Which Lahrsen (2025) coefficient set to use.",
    ),
    allow_out_of_range: bool = typer.Option(
        False,
        "--allow-out-of-range",
        help="Skip range validation (useful for exploratory synthetic data).",
    ),
    ctl_harvester_model: CTLHarvesterModel = typer.Option(
        CTLHarvesterModel.ADV6N10,
        "--ctl-harvester-model",
        case_sensitive=False,
        help="CTL harvester regression to evaluate when --machine-role ctl_harvester is used.",
    ),
    ctl_stem_volume: float | None = typer.Option(
        None,
        "--ctl-stem-volume",
        min=0.0,
        help="Mean stem volume (m³/stem). Required for CTL harvester models.",
    ),
    ctl_products_count: float | None = typer.Option(
        None,
        "--ctl-products-count",
        min=0.0,
        help="Number of products sorted per cycle. Required for CTL harvester models.",
    ),
    ctl_stems_per_cycle: float | None = typer.Option(
        None,
        "--ctl-stems-per-cycle",
        min=0.0,
        help="Average stems processed per cycle. Required for CTL harvester models.",
    ),
    ctl_mean_log_length: float | None = typer.Option(
        None,
        "--ctl-mean-log-length",
        min=0.0,
        help="Mean produced log length (m). Required for CTL harvester models.",
    ),
    ctl_removal_fraction: float | None = typer.Option(
        None,
        "--ctl-removal-fraction",
        min=0.0,
        max=1.0,
        help="Removal fraction (0-1) for ADV5N30 thinning model.",
    ),
    ctl_brushed: bool = typer.Option(
        False,
        "--ctl-brushed/--ctl-unbrushed",
        help="ADV5N30 brushing scenario (adds 21% productivity).",
    ),
    ctl_density: float | None = typer.Option(
        None,
        "--ctl-density",
        min=0.0,
        help="Stand density (trees/ha) for TN292 model.",
    ),
    ctl_dbh_cm: float | None = typer.Option(
        None,
        "--ctl-dbh-cm",
        min=0.0,
        help="Mean DBH (cm) for the Kellogg & Bettinger (1994) harvester model.",
    ),
    ctl_density_basis: str = typer.Option(
        "pre",
        "--ctl-density-basis",
        help="Density basis for TN292 model: pre or post (harvest).",
    ),
    forwarder_model: ForwarderBCModel = typer.Option(
        ForwarderBCModel.GHAFFARIYAN_SMALL,
        "--forwarder-model",
        case_sensitive=False,
        help="Forwarder regression to evaluate when --machine-role forwarder is used.",
    ),
    extraction_distance: float | None = typer.Option(
        None,
        "--extraction-distance",
        min=0.0,
        help="Mean forwarding distance (m). Required for Ghaffariyan and ADV1N12 forwarder models.",
    ),
    slope_class: ALPACASlopeClass = typer.Option(
        ALPACASlopeClass.FLAT,
        "--slope-class",
        case_sensitive=False,
        help="Slope bucket (<10, 10-20, >20 percent) for Ghaffariyan models.",
    ),
    slope_factor: float | None = typer.Option(
        None,
        "--slope-factor",
        min=0.0,
        help="Custom multiplier overriding --slope-class for Ghaffariyan models.",
    ),
    volume_per_load: float | None = typer.Option(
        None,
        "--volume-per-load",
        min=0.0,
        help="Per-load volume (m³). Required for Kellogg forwarder models.",
    ),
    distance_out: float | None = typer.Option(
        None,
        "--distance-out",
        min=0.0,
        help="Distance from landing to first loading point (m). Required for Kellogg models.",
    ),
    travel_in_unit: float | None = typer.Option(
        None,
        "--travel-in-unit",
        min=0.0,
        help="Distance while loading within the unit (m). Required for Kellogg models.",
    ),
    distance_in: float | None = typer.Option(
        None,
        "--distance-in",
        min=0.0,
        help="Return distance to the landing (m). Required for Kellogg models.",
    ),
    payload_per_trip: float | None = typer.Option(
        None,
        "--payload-per-trip",
        min=0.0,
        help="Payload per forwarder trip (m³). Required for ADV6N10 model.",
    ),
    mean_log_length: float | None = typer.Option(
        None,
        "--mean-log-length",
        min=0.0,
        help="Mean log length (m). Required for ADV6N10 model.",
    ),
    travel_speed: float | None = typer.Option(
        None,
        "--travel-speed",
        min=0.0,
        help="Forwarder travel speed (m/min). Required for ADV6N10 model.",
    ),
    trail_length: float | None = typer.Option(
        None,
        "--trail-length",
        min=0.0,
        help="Trail length from landing to loading point (m). Required for ADV6N10 model.",
    ),
    products_per_trail: float | None = typer.Option(
        None,
        "--products-per-trail",
        min=0.0,
        help="Number of products separated on the trail (ADV6N10).",
    ),
    mean_extraction_distance: float | None = typer.Option(
        None,
        "--mean-extraction-distance",
        min=0.0,
        help="Mean extraction distance (m) for Eriksson & Lindroos forwarder models.",
    ),
    mean_stem_size: float | None = typer.Option(
        None,
        "--mean-stem-size",
        min=0.0,
        help="Mean harvested stem size (m³) for Eriksson & Lindroos models.",
    ),
    load_capacity: float | None = typer.Option(
        None,
        "--load-capacity",
        min=0.0,
        help="Load capacity/payload (m³) for Eriksson & Lindroos models.",
    ),
    harvested_trees_per_ha: float | None = typer.Option(
        None,
        "--harvested-trees-per-ha",
        min=0.0,
        help="Harvested trees per hectare (required for Laitila & Väätäinen brushwood model).",
    ),
    avg_tree_volume_dm3: float | None = typer.Option(
        None,
        "--avg-tree-volume-dm3",
        min=0.0,
        help="Average harvested tree volume (dm³) for the brushwood harwarder.",
    ),
    forwarding_distance: float | None = typer.Option(
        None,
        "--forwarding-distance",
        min=0.0,
        help="Mean forwarding distance (m) for the brushwood harwarder.",
    ),
    harwarder_payload: float | None = typer.Option(
        None,
        "--harwarder-payload",
        min=0.0,
        help="Payload per harwarder trip (m³). Defaults to 7.1 m³ if omitted.",
    ),
    grapple_load_unloading: float | None = typer.Option(
        None,
        "--grapple-load-unloading",
        min=0.0,
        help="Grapple load during unloading (m³). Defaults to 0.29 m³ if omitted.",
    ),
    grapple_skidder_model: GrappleSkidderModel = typer.Option(
        GrappleSkidderModel.HAN_LOP_AND_SCATTER,
        "--grapple-skidder-model",
        case_sensitive=False,
        help=(
            "Grapple skidder regression (Han et al. 2018 | adv1n12-fulltree | "
            "adv1n12-two-phase | adv6n7)."
        ),
    ),
    skidder_pieces_per_cycle: float | None = typer.Option(
        None,
        "--skidder-pieces-per-cycle",
        min=0.0,
        help="Logs/trees moved per cycle (depends on selected grapple skidder model).",
    ),
    skidder_piece_volume: float | None = typer.Option(
        None,
        "--skidder-piece-volume",
        min=0.0,
        help="Average log/tree volume (m³) for grapple skidder payload calculations.",
    ),
    skidder_empty_distance: float | None = typer.Option(
        None,
        "--skidder-empty-distance",
        min=0.0,
        help="Empty travel distance per cycle (m) for grapple skidder models.",
    ),
    skidder_loaded_distance: float | None = typer.Option(
        None,
        "--skidder-loaded-distance",
        min=0.0,
        help="Loaded travel distance per cycle (m) for grapple skidder models.",
    ),
    skidder_extraction_distance: float | None = typer.Option(
        None,
        "--skidder-extraction-distance",
        min=0.0,
        help="Average extraction distance (m) for ADV1N12 and ADV6N7 skidder models.",
    ),
    skidder_adv6n7_decking_mode: ADV6N7DeckingMode = typer.Option(
        ADV6N7DeckingMode.SKIDDER_LOADER,
        "--skidder-adv6n7-decking-mode",
        case_sensitive=False,
        help="Decking variant for ADV6N7 (skidder | skidder_loader | loader | hot_processing).",
    ),
    skidder_adv6n7_payload_m3: float | None = typer.Option(
        None,
        "--skidder-adv6n7-payload-m3",
        min=0.0,
        help="Override payload per cycle (m³) for ADV6N7. Defaults to 7.69 m³ from the study.",
    ),
    skidder_adv6n7_delay_minutes: float | None = typer.Option(
        None,
        "--skidder-adv6n7-delay-minutes",
        min=0.0,
        help="In-cycle delay minutes per turn for ADV6N7 (default 0.12 min/turn).",
    ),
    skidder_adv6n7_utilisation: float | None = typer.Option(
        None,
        "--skidder-adv6n7-utilisation",
        min=0.0,
        help="Utilisation fraction (SMH basis) for ADV6N7 (default 0.85).",
    ),
    skidder_adv6n7_support_ratio: float | None = typer.Option(
        0.4,
        "--skidder-adv6n7-support-ratio",
        min=0.0,
        help=(
            "Loader support ratio for ADV6N7 combined costs (0 = skidder decks everything, "
            "1 = loader decks full-time). Defaults to 0.4 per the study."
        ),
    ),
    skidder_trail_pattern: TrailSpacingPattern | None = typer.Option(
        None,
        "--skidder-trail-pattern",
        case_sensitive=False,
        help="Trail spacing pattern (TN285) to apply productivity multipliers.",
    ),
    skidder_decking_condition: DeckingCondition | None = typer.Option(
        None,
        "--skidder-decking-condition",
        case_sensitive=False,
        help="Decking/landing preparation condition (ADV4N21 multipliers).",
    ),
    skidder_productivity_multiplier: float | None = typer.Option(
        None,
        "--skidder-productivity-multiplier",
        min=0.0,
        help="Optional custom multiplier applied to grapple skidder productivity (stacked with pattern/decking).",
    ),
    skidder_speed_profile: SkidderSpeedProfileOption = typer.Option(
        SkidderSpeedProfileOption.LEGACY,
        "--skidder-speed-profile",
        case_sensitive=False,
        help="Travel-speed profile for grapple skidders (legacy regression vs. GNSS cable skidder/farm tractor medians).",
    ),
    grapple_yarder_model: GrappleYarderModel = typer.Option(
        GrappleYarderModel.SR54,
        "--grapple-yarder-model",
        case_sensitive=False,
        help=(
            "Grapple yarder regression "
            "(sr54 | tr75-bunched | tr75-handfelled | tn157 | tn147 | tr122-extended | "
            "tr122-shelterwood | tr122-clearcut | adv5n28-clearcut | adv5n28-shelterwood)."
        ),
    ),
    grapple_turn_volume_m3: float | None = typer.Option(
        None,
        "--grapple-turn-volume-m3",
        min=0.0,
        help="Turn volume per cycle (m³) for grapple yarder helpers.",
    ),
    grapple_yarding_distance_m: float | None = typer.Option(
        None,
        "--grapple-yard-distance-m",
        min=0.0,
        help="Yarding distance along the corridor (m) for grapple yarder helpers.",
    ),
    grapple_lateral_distance_m: float | None = typer.Option(
        None,
        "--grapple-lateral-distance-m",
        min=0.0,
        help="Lateral yarding distance (m). Required for ADV1N35 when not using harvest-system defaults.",
    ),
    grapple_stems_per_cycle: float | None = typer.Option(
        None,
        "--grapple-stems-per-cycle",
        min=0.0,
        help="Stems per turn for grapple yarder models that require it (e.g., ADV1N35 Owren 400).",
    ),
    grapple_in_cycle_delay_minutes: float | None = typer.Option(
        None,
        "--grapple-in-cycle-delay-minutes",
        min=0.0,
        help="In-cycle delay minutes per turn (ADV1N35 default 0.69).",
    ),
    tn157_case: str = typer.Option(
        "combined",
        "--tn157-case",
        help=_tn157_case_help_text(),
        show_default=False,
    ),
    tn147_case: str = typer.Option(
        "combined",
        "--tn147-case",
        help=_tn147_case_help_text(),
        show_default=False,
    ),
    processor_model: RoadsideProcessorModel = typer.Option(
        RoadsideProcessorModel.BERRY2019,
        "--processor-model",
        case_sensitive=False,
        help=(
            "Roadside-processor regression to use "
            "(berry2019 | labelle2016/2017/2018 | labelle2019_dbh | labelle2019_volume | "
            "adv5n6 | adv7n3 | visser2015 | tn103 | tr106 | tr87 | tn166 | hypro775 | spinelli2010 | "
            "bertone2025 | borz2023 | nakagawa2010)."
        ),
    ),
    processor_piece_size_m3: float | None = typer.Option(
        None,
        "--processor-piece-size-m3",
        min=0.0,
        help="Average piece size (m³/stem) for roadside processor helpers.",
    ),
    processor_log_sorts: int | None = typer.Option(
        None,
        "--processor-log-sorts",
        help="Log-sort count for Visser & Tolan (2015) scenarios (choose 5, 9, 12, or 15).",
    ),
    processor_volume_m3: float | None = typer.Option(
        None,
        "--processor-volume-m3",
        min=0.0,
        help="Recovered tree volume (m³/stem) for Labelle (2019) hardwood volume models.",
    ),
    processor_dbh_cm: float | None = typer.Option(
        None,
        "--processor-dbh-cm",
        min=0.0,
        help="DBH (cm) for Labelle (2019) hardwood processor helper.",
    ),
    processor_tree_height_m: float | None = typer.Option(
        None,
        "--processor-tree-height-m",
        min=0.0,
        help="Tree height (m) for landing processor presets that require it (e.g., Bertone 2025).",
    ),
    processor_logs_per_tree: float | None = typer.Option(
        None,
        "--processor-logs-per-tree",
        min=0.0,
        help="Average number of logs per tree (Bertone 2025 helper).",
    ),
    processor_species: LabelleProcessorSpecies | None = typer.Option(
        None,
        "--processor-species",
        case_sensitive=False,
        help="Species selector for Labelle (2019) hardwood models (spruce | beech).",
    ),
    processor_treatment: LabelleProcessorTreatment | None = typer.Option(
        None,
        "--processor-treatment",
        case_sensitive=False,
        help="Silvicultural treatment for Labelle (2019) hardwood models (clear_cut | selective_cut).",
    ),
    processor_stem_source: ADV5N6StemSource = typer.Option(
        ADV5N6StemSource.LOADER_FORWARDED,
        "--processor-stem-source",
        case_sensitive=False,
        help="Stem source for ADV5N6 (loader_forwarded | grapple_yarded).",
    ),
    processor_adv5n6_processing_mode: ADV5N6ProcessingMode = typer.Option(
        ADV5N6ProcessingMode.COLD,
        "--processor-processing-mode",
        case_sensitive=False,
        help="Processing mode for ADV5N6 (cold | hot | low_volume).",
    ),
    processor_adv7n3_machine: ADV7N3Machine = typer.Option(
        ADV7N3Machine.HYUNDAI_210,
        "--processor-adv7n3-machine",
        case_sensitive=False,
        help="ADV7N3 processor selection (hyundai_210 | john_deere_892). Applies when --processor-model adv7n3.",
    ),
    processor_tn103_scenario: TN103Scenario = typer.Option(
        TN103Scenario.COMBINED_OBSERVED,
        "--processor-tn103-scenario",
        case_sensitive=False,
        help="TN-103 scenario (area_a_feller_bunched | area_b_handfelled | combined_observed | combined_high_util).",
    ),
    processor_tr106_scenario: TR106Scenario = typer.Option(
        TR106Scenario.CASE1187_FEB,
        "--processor-tr106-scenario",
        case_sensitive=False,
        help="TR-106 scenario (case1187_octnov | case1187_feb | kp40_caterpillar225 | kp40_linkbelt_l2800 | kp40_caterpillar_el180).",
    ),
    processor_tr87_scenario: TR87Scenario = typer.Option(
        TR87Scenario.BOTH_PROCESSORS,
        "--processor-tr87-scenario",
        case_sensitive=False,
        help="TR-87 scenario for TJ90 processors (tj90_day_shift | tj90_night_shift | tj90_combined_observed | tj90_both_processors_observed | tj90_both_processors_wait_adjusted).",
    ),
    processor_tn166_scenario: TN166Scenario = typer.Option(
        TN166Scenario.GRAPPLE_YARDED,
        "--processor-tn166-scenario",
        case_sensitive=False,
        help="TN-166 scenario (grapple_yarded | right_of_way | mixed_shift).",
    ),
    processor_machine_power_kw: float | None = typer.Option(
        None,
        "--processor-machine-power-kw",
        min=1.0,
        help="Carrier gross power (kW) for Spinelli (2010).",
    ),
    processor_slope_percent: float | None = typer.Option(
        None,
        "--processor-slope-percent",
        help="Average slope (%) for Spinelli (2010) helper.",
    ),
    processor_removals_per_ha: float | None = typer.Option(
        None,
        "--processor-removals-per-ha",
        min=0.0,
        help="Trees removed per hectare (required for Spinelli harvest mode).",
    ),
    processor_residuals_per_ha: float | None = typer.Option(
        None,
        "--processor-residuals-per-ha",
        min=0.0,
        help="Residual trees per hectare (Spinelli harvest mode).",
    ),
    processor_spinelli_operation: SpinelliOperation = typer.Option(
        SpinelliOperation.HARVEST,
        "--processor-spinelli-operation",
        case_sensitive=False,
        help="Spinelli (2010) mode (harvest | process).",
    ),
    processor_spinelli_stand_type: SpinelliStandType = typer.Option(
        SpinelliStandType.FOREST,
        "--processor-spinelli-stand-type",
        case_sensitive=False,
        help="Stand type for Spinelli (forest | plantation | coppice).",
    ),
    processor_spinelli_carrier: SpinelliCarrier = typer.Option(
        SpinelliCarrier.PURPOSE_BUILT,
        "--processor-spinelli-carrier",
        case_sensitive=False,
        help="Carrier for Spinelli (purpose_built | excavator | spider | tractor).",
    ),
    processor_spinelli_head: SpinelliHead = typer.Option(
        SpinelliHead.ROLLER,
        "--processor-spinelli-head",
        case_sensitive=False,
        help="Head type for Spinelli (roller | stroke).",
    ),
    processor_spinelli_species: SpinelliSpecies = typer.Option(
        SpinelliSpecies.CONIFER,
        "--processor-spinelli-species",
        case_sensitive=False,
        help="Species group for Spinelli (conifer | chestnut_poplar | other_hardwood).",
    ),
    processor_labelle2016_form: Labelle2016TreeForm = typer.Option(
        Labelle2016TreeForm.ACCEPTABLE,
        "--processor-labelle2016-form",
        case_sensitive=False,
        help="Tree-form class (Labelle 2016 sugar maple study).",
    ),
    processor_labelle2017_variant: Labelle2017Variant = typer.Option(
        Labelle2017Variant.POLY1,
        "--processor-labelle2017-variant",
        case_sensitive=False,
        help="Labelle (2017) variant (poly1, poly2, power1, power2).",
    ),
    processor_labelle2018_variant: Labelle2018Variant = typer.Option(
        Labelle2018Variant.RW_POLY1,
        "--processor-labelle2018-variant",
        case_sensitive=False,
        help="Labelle (2018) variant (rw_poly1/rw_poly2/ct_poly1/ct_poly2).",
    ),
    processor_tree_form: int = typer.Option(
        0,
        "--processor-tree-form",
        min=0,
        max=2,
        help="Tree form category (0=good, 1=poor, 2=bad) per Berry (2019).",
    ),
    processor_crew_multiplier: float = typer.Option(
        1.0,
        "--processor-crew-multiplier",
        min=0.1,
        help="Crew-specific multiplier (e.g., 1.16 for crew A, 0.75 for crew C) to reflect operator productivity.",
    ),
    processor_delay_multiplier: float = typer.Option(
        0.91,
        "--processor-delay-multiplier",
        min=0.01,
        max=1.0,
        help="Utilisation multiplier capturing delays (<10 min) relative to delay-free productivity (Berry 2019 default 0.91).",
    ),
    processor_carrier: ProcessorCarrier = typer.Option(
        ProcessorCarrier.PURPOSE_BUILT,
        "--processor-carrier",
        case_sensitive=False,
        help="Carrier profile for the Berry helper (purpose_built | excavator).",
    ),
    processor_skid_area_m2: float | None = typer.Option(
        None,
        "--processor-skid-area-m2",
        min=0.0,
        help="Approximate skid/landing area (m²). When using Berry (2019) this scales the utilisation multiplier using the published skid-size delay regression.",
    ),
    processor_show_grade_stats: bool = typer.Option(
        False,
        "--processor-show-grade-stats/--processor-hide-grade-stats",
        help="With Berry (2019) helper, print the digitised log-grade emmeans table (Appendix 13).",
    ),
    processor_automatic_bucking: bool = typer.Option(
        False,
        "--processor-automatic-bucking/--no-processor-automatic-bucking",
        help="Apply the Labelle & Huß (2018) automatic bucking multiplier (Berry/Labelle helpers only).",
    ),
    loader_model: LoaderProductivityModel = typer.Option(
        LoaderProductivityModel.TN261,
        "--loader-model",
        case_sensitive=False,
        help="Loader helper to use (tn261 | adv2n26 | adv5n1 | barko450 | kizha2020).",
    ),
    loader_piece_size_m3: float | None = typer.Option(
        None,
        "--loader-piece-size-m3",
        min=0.0,
        help="Average piece size (m³) for loader-forwarder helper (TN261).",
    ),
    loader_distance_m: float | None = typer.Option(
        None,
        "--loader-distance-m",
        min=0.0,
        help="External forwarding distance (m) from deck to farthest stem for loader helper.",
    ),
    loader_payload_m3: float = typer.Option(
        ADV5N1_DEFAULT_PAYLOAD_M3,
        "--loader-payload-m3",
        min=0.01,
        help="Payload per cycle (m³) for ADV5N1 regression (default 2.77 m³).",
    ),
    loader_slope_percent: float = typer.Option(
        0.0,
        "--loader-slope-percent",
        help="Approximate slope (%) along the forwarding direction (positive = uphill).",
    ),
    loader_bunched: bool = typer.Option(
        True,
        "--loader-bunched/--loader-hand-felled",
        help="Whether stems are mechanically bunched/aligned (default) or hand-felled/scattered.",
    ),
    loader_delay_multiplier: float = typer.Option(
        1.0,
        "--loader-delay-multiplier",
        min=0.01,
        max=1.0,
        help="Optional utilisation multiplier for loader-forwarder helper (default assumes delay-free timing).",
    ),
    loader_travel_empty_m: float = typer.Option(
        ADV2N26_DEFAULT_TRAVEL_EMPTY_M,
        "--loader-travel-empty-m",
        min=0.0,
        help="Travel empty distance (m) for ADV2N26 clambunk regression (default 236 m).",
    ),
    loader_stems_per_cycle: float = typer.Option(
        ADV2N26_DEFAULT_STEMS_PER_CYCLE,
        "--loader-stems-per-cycle",
        min=0.1,
        help="Stems per cycle for ADV2N26 clambunk regression (default 19.7).",
    ),
    loader_stem_volume_m3: float = typer.Option(
        ADV2N26_DEFAULT_STEM_VOLUME_M3,
        "--loader-stem-volume-m3",
        min=0.01,
        help="Average stem volume (m³) for ADV2N26 payload calculations (default 1.52).",
    ),
    loader_utilisation: float | None = typer.Option(
        None,
        "--loader-utilisation",
        min=0.01,
        max=1.0,
        help="Utilisation (PMH/SMH) for loader helpers (defaults per model if omitted).",
    ),
    loader_in_cycle_delay_minutes: float | None = typer.Option(
        None,
        "--loader-in-cycle-delay-minutes",
        min=0.0,
        help="Override in-cycle delay minutes for ADV2N26 (defaults to 5% of delay-free cycle).",
        show_default=False,
    ),
    loader_slope_class: LoaderAdv5N1SlopeClass = typer.Option(
        LoaderAdv5N1SlopeClass.ZERO_TO_TEN,
        "--loader-slope-class",
        case_sensitive=False,
        help="ADV5N1 slope class (0_10 vs 11_30).",
    ),
    loader_barko_scenario: LoaderBarkoScenario = typer.Option(
        LoaderBarkoScenario.GROUND_SKID_BLOCK,
        "--loader-barko-scenario",
        case_sensitive=False,
        help="Scenario for Barko 450 loader preset (ground_skid_block | cable_yard_block).",
    ),
    loader_hot_cold_mode: LoaderHotColdMode = typer.Option(
        LoaderHotColdMode.HOT,
        "--loader-hot-cold-mode",
        case_sensitive=False,
        help="Hot vs. cold mode for the Kizha et al. (2020) loader preset.",
    ),
    shovel_passes: int | None = typer.Option(
        None,
        "--shovel-passes",
        min=1,
        help="Number of shovel passes (serpentine swings) between roads (default 4).",
    ),
    shovel_swing_length: float | None = typer.Option(
        None,
        "--shovel-swing-length",
        min=0.0,
        help="Effective swing length (m) for the hoe-chucker (default 16.15).",
    ),
    shovel_strip_length: float | None = typer.Option(
        None,
        "--shovel-strip-length",
        min=0.0,
        help="Length along the road (m) yarded per period (default 100).",
    ),
    shovel_volume_per_ha: float | None = typer.Option(
        None,
        "--shovel-volume-per-ha",
        min=0.0,
        help="Volume per hectare (m³) handled by the shovel logger (default 375).",
    ),
    shovel_swing_time_roadside: float | None = typer.Option(
        None,
        "--shovel-swing-time-roadside",
        min=0.0,
        help="Seconds per swing when straightening piles at roadside (default 20).",
    ),
    shovel_payload_roadside: float | None = typer.Option(
        None,
        "--shovel-payload-roadside",
        min=0.0,
        help="Payload per swing (m³) when straightening piles at roadside (default 1).",
    ),
    shovel_swing_time_initial: float | None = typer.Option(
        None,
        "--shovel-swing-time-initial",
        min=0.0,
        help="Seconds per swing when handling logs for the first time away from the road (default 30).",
    ),
    shovel_payload_initial: float | None = typer.Option(
        None,
        "--shovel-payload-initial",
        min=0.0,
        help="Payload per swing (m³) for first handling away from the road (default 1).",
    ),
    shovel_swing_time_rehandle: float | None = typer.Option(
        None,
        "--shovel-swing-time-rehandle",
        min=0.0,
        help="Seconds per swing when rehandling logs already bunched (default 30).",
    ),
    shovel_payload_rehandle: float | None = typer.Option(
        None,
        "--shovel-payload-rehandle",
        min=0.0,
        help="Payload per swing (m³) for rehandled logs (default 2).",
    ),
    shovel_speed_index: float | None = typer.Option(
        None,
        "--shovel-speed-index",
        min=0.0,
        help="Travel speed (kph) while working parallel to the road indexing butts (default 0.7).",
    ),
    shovel_speed_return: float | None = typer.Option(
        None,
        "--shovel-speed-return",
        min=0.0,
        help="Travel speed (kph) while walking to the back of the unit (default 0.7).",
    ),
    shovel_speed_serpentine: float | None = typer.Option(
        None,
        "--shovel-speed-serpentine",
        min=0.0,
        help="Travel speed (kph) while following the serpentine pattern (default 0.7).",
    ),
    shovel_effective_minutes: float | None = typer.Option(
        None,
        "--shovel-effective-minutes",
        min=0.0,
        help="Effective productive minutes per hour for the shovel logger (default 50).",
    ),
    shovel_slope_class: ShovelSlopeClass = typer.Option(
        ShovelSlopeClass.LEVEL,
        "--shovel-slope-class",
        case_sensitive=False,
        help="Slope class for hoe-chucker travel (TN261): downhill | level | uphill.",
    ),
    shovel_bunching: ShovelBunching = typer.Option(
        ShovelBunching.FELLER_BUNCHED,
        "--shovel-bunching",
        case_sensitive=False,
        help="Whether stems are feller-bunched (aligned) or hand-felled/scattered.",
    ),
    shovel_productivity_multiplier: float | None = typer.Option(
        None,
        "--shovel-productivity-multiplier",
        min=0.0,
        help="Custom multiplier to stack on top of slope/bunching adjustments.",
    ),
    helicopter_model: HelicopterLonglineModel = typer.Option(
        HelicopterLonglineModel.S64E_AIRCRANE,
        "--helicopter-model",
        case_sensitive=False,
        help="Helicopter model for longline productivity (lama | kmax | bell214b | s64e_aircrane).",
    ),
    helicopter_flight_distance_m: float | None = typer.Option(
        None,
        "--helicopter-flight-distance-m",
        min=0.0,
        help="Slope flight distance per turn (m) for helicopter helpers.",
    ),
    helicopter_payload_m3: float | None = typer.Option(
        None,
        "--helicopter-payload-m3",
        min=0.0,
        help="Override payload per turn (m³). Defaults to model load factor × rated payload.",
    ),
    helicopter_load_factor: float | None = typer.Option(
        None,
        "--helicopter-load-factor",
        min=0.0,
        max=1.0,
        help="Override load factor (0-1) for helicopter helpers.",
    ),
    helicopter_weight_to_volume: float | None = typer.Option(
        None,
        "--helicopter-weight-to-volume",
        min=0.0,
        help="Custom weight-to-volume conversion (lb/m³). Defaults per helicopter model.",
    ),
    helicopter_delay_minutes: float = typer.Option(
        0.0,
        "--helicopter-delay-minutes",
        min=0.0,
        help="Additional minutes per cycle (e.g., hooktender waits, weather holds).",
    ),
    harvest_system_id: str | None = typer.Option(
        None,
        "--harvest-system-id",
        help="Harvest system ID to pull productivity defaults from (scenario systems override registry).",
    ),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        help="Dataset name or scenario path providing harvest system context.",
    ),
    block_id: str | None = typer.Option(
        None,
        "--block-id",
        help="Block ID (requires --dataset) to infer harvest system defaults automatically.",
    ),
    salvage_processing_mode: SalvageProcessingMode = typer.Option(
        SalvageProcessingMode.STANDARD_MILL,
        "--salvage-processing-mode",
        case_sensitive=False,
        help=(
            "ADV1N5 salvage processing mode (standard_mill | portable_mill | in_woods_chipping). "
            "When a salvage harvest system is selected, the CLI prints the corresponding portable mill or "
            "in-woods chipping reminder; ignored for non-salvage systems."
        ),
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append productivity inputs/output to a JSONL telemetry file.",
        dir_okay=False,
        writable=True,
        show_default=False,
    ),
):
    """Estimate productivity for Lahrsen (feller-buncher) or forwarder models."""

    scenario_context: Scenario | None = None
    dataset_name: str | None = None
    systems_catalog = dict(default_system_registry())
    if dataset is not None:
        dataset_name, scenario_context, _ = _ensure_dataset(dataset, interactive=False)
        systems_catalog = _scenario_systems(scenario_context)
    if block_id is not None and scenario_context is None:
        raise typer.BadParameter("--block-id requires --dataset to be specified.")
    derived_system_id: str | None = None
    if block_id and scenario_context is not None:
        block = next((blk for blk in scenario_context.blocks if blk.id == block_id), None)
        if block is None:
            raise typer.BadParameter(
                f"Block '{block_id}' not found in dataset {dataset_name or dataset}."
            )
        derived_system_id = block.harvest_system_id
        if derived_system_id is None:
            console.print(
                f"[yellow]Block {block_id} does not declare a harvest system; system defaults will not apply.[/yellow]"
            )
    selected_system_id = harvest_system_id or derived_system_id
    selected_system: HarvestSystem | None = None
    telemetry_salvage_mode: str | None = None
    if selected_system_id:
        selected_system = systems_catalog.get(selected_system_id)
        if selected_system is None:
            raise typer.BadParameter(
                f"Harvest system '{selected_system_id}' not found. Options: {', '.join(sorted(systems_catalog))}"
            )

    salvage_system_ids = {"ground_salvage_grapple", "cable_salvage_grapple"}
    if selected_system_id in salvage_system_ids:
        _print_salvage_processing_guidance(
            mode=salvage_processing_mode,
            system_id=selected_system_id,
        )
        telemetry_salvage_mode = salvage_processing_mode.value
    elif (
        salvage_processing_mode is not SalvageProcessingMode.STANDARD_MILL
        and selected_system_id not in salvage_system_ids
    ):
        console.print(
            "[yellow]--salvage-processing-mode ignored because '%s' is not a salvage harvest system.[/yellow]"
            % (selected_system_id or "(none)")
        )

    role = machine_role.value
    if role == ProductivityMachineRole.FORWARDER.value:
        forwarder_user_supplied = {
            "forwarder_model": _parameter_supplied(ctx, "forwarder_model"),
            "extraction_distance": _parameter_supplied(ctx, "extraction_distance"),
        }
        (
            forwarder_model,
            extraction_distance,
            forwarder_defaults_used,
        ) = _apply_forwarder_system_defaults(
            system=selected_system,
            model=forwarder_model,
            extraction_distance_m=extraction_distance,
            user_supplied=forwarder_user_supplied,
        )
        result = _evaluate_forwarder_result(
            model=forwarder_model,
            extraction_distance=extraction_distance,
            slope_class=slope_class,
            slope_factor=slope_factor,
            volume_per_load=volume_per_load,
            distance_out=distance_out,
            travel_in_unit=travel_in_unit,
            distance_in=distance_in,
            payload_per_trip=payload_per_trip,
            mean_log_length=mean_log_length,
            travel_speed=travel_speed,
            trail_length=trail_length,
            products_per_trail=products_per_trail,
            mean_extraction_distance=mean_extraction_distance,
            mean_stem_size=mean_stem_size,
            load_capacity=load_capacity,
            harvested_trees_per_ha=harvested_trees_per_ha,
            avg_tree_volume_dm3=avg_tree_volume_dm3,
            forwarding_distance=forwarding_distance,
            harwarder_payload=harwarder_payload,
            grapple_load_unloading=grapple_load_unloading,
        )
        _render_forwarder_result(result)
        if forwarder_defaults_used and selected_system is not None:
            console.print(
                f"[dim]Applied productivity defaults from harvest system '{selected_system.system_id}'.[/dim]"
            )
        _maybe_render_costs(show_costs, ProductivityMachineRole.FORWARDER.value)
        return
    if role == ProductivityMachineRole.CTL_HARVESTER.value:
        inputs, value = _evaluate_ctl_harvester_result(
            model=ctl_harvester_model,
            stem_volume=ctl_stem_volume,
            products_count=ctl_products_count,
            stems_per_cycle=ctl_stems_per_cycle,
            mean_log_length=ctl_mean_log_length,
            removal_fraction=ctl_removal_fraction,
            brushed=ctl_brushed,
            density=ctl_density,
            density_basis=ctl_density_basis,
            dbh_cm=ctl_dbh_cm,
        )
        _render_ctl_harvester_result(ctl_harvester_model, inputs, value)
        _maybe_render_costs(show_costs, ProductivityMachineRole.CTL_HARVESTER.value)
        return
    if role == ProductivityMachineRole.GRAPPLE_SKIDDER.value:
        skidder_user_supplied = {
            "grapple_skidder_model": _parameter_supplied(ctx, "grapple_skidder_model"),
            "skidder_extraction_distance": _parameter_supplied(
                ctx, "skidder_extraction_distance"
            ),
            "skidder_adv6n7_decking_mode": _parameter_supplied(
                ctx, "skidder_adv6n7_decking_mode"
            ),
            "skidder_adv6n7_payload_m3": _parameter_supplied(
                ctx, "skidder_adv6n7_payload_m3"
            ),
            "skidder_adv6n7_utilisation": _parameter_supplied(
                ctx, "skidder_adv6n7_utilisation"
            ),
            "skidder_adv6n7_delay_minutes": _parameter_supplied(
                ctx, "skidder_adv6n7_delay_minutes"
            ),
            "skidder_adv6n7_support_ratio": _parameter_supplied(
                ctx, "skidder_adv6n7_support_ratio"
            ),
        }
        try:
            (
                grapple_skidder_model,
                skidder_trail_pattern,
                skidder_decking_condition,
                skidder_productivity_multiplier,
                system_speed_profile,
                skidder_extraction_distance,
                skidder_adv6n7_decking_mode,
                skidder_adv6n7_payload_m3,
                skidder_adv6n7_utilisation,
                skidder_adv6n7_delay_minutes,
                skidder_adv6n7_support_ratio,
                system_defaults_used,
            ) = _apply_skidder_system_defaults(
                system=selected_system,
                model=grapple_skidder_model,
                trail_pattern=skidder_trail_pattern,
                decking_condition=skidder_decking_condition,
                custom_multiplier=skidder_productivity_multiplier,
                extraction_distance_m=skidder_extraction_distance,
                adv6n7_decking_mode=skidder_adv6n7_decking_mode,
                adv6n7_payload_m3=skidder_adv6n7_payload_m3,
                adv6n7_utilisation=skidder_adv6n7_utilisation,
                adv6n7_delay_minutes=skidder_adv6n7_delay_minutes,
                adv6n7_support_ratio=skidder_adv6n7_support_ratio,
                user_supplied=skidder_user_supplied,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        skidder_speed_profile_option = skidder_speed_profile
        if (
            skidder_speed_profile_option is SkidderSpeedProfileOption.LEGACY
            and system_speed_profile is not SkidderSpeedProfileOption.LEGACY
        ):
            skidder_speed_profile_option = system_speed_profile
        result = _evaluate_grapple_skidder_result(
            model=grapple_skidder_model,
            pieces_per_cycle=skidder_pieces_per_cycle,
            piece_volume_m3=skidder_piece_volume,
            empty_distance_m=skidder_empty_distance,
            loaded_distance_m=skidder_loaded_distance,
            trail_pattern=skidder_trail_pattern,
            decking_condition=skidder_decking_condition,
            custom_multiplier=skidder_productivity_multiplier,
            speed_profile_option=skidder_speed_profile_option,
            extraction_distance_m=skidder_extraction_distance,
            adv6n7_decking_mode=skidder_adv6n7_decking_mode,
            adv6n7_payload_m3=skidder_adv6n7_payload_m3,
            adv6n7_utilisation=skidder_adv6n7_utilisation,
            adv6n7_delay_minutes=skidder_adv6n7_delay_minutes,
            adv6n7_support_ratio=skidder_adv6n7_support_ratio,
        )
        _render_grapple_skidder_result(result)
        if system_defaults_used and selected_system is not None:
            console.print(
                f"[dim]Applied productivity defaults from harvest system '{selected_system.system_id}'.[/dim]"
            )
        _maybe_render_costs(show_costs, ProductivityMachineRole.GRAPPLE_SKIDDER.value)
        return
    if role == ProductivityMachineRole.GRAPPLE_YARDER.value:
        grapple_user_supplied = {
            "grapple_yarder_model": _parameter_supplied(ctx, "grapple_yarder_model"),
            "grapple_turn_volume_m3": _parameter_supplied(ctx, "grapple_turn_volume_m3"),
            "grapple_yarding_distance_m": _parameter_supplied(ctx, "grapple_yarding_distance_m"),
            "grapple_lateral_distance_m": _parameter_supplied(ctx, "grapple_lateral_distance_m"),
            "grapple_stems_per_cycle": _parameter_supplied(ctx, "grapple_stems_per_cycle"),
            "grapple_in_cycle_delay_minutes": _parameter_supplied(
                ctx, "grapple_in_cycle_delay_minutes"
            ),
            "tn157_case": _parameter_supplied(ctx, "tn157_case"),
            "tn147_case": _parameter_supplied(ctx, "tn147_case"),
        }
        try:
            tn157_case = _normalize_tn157_case(tn157_case)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        try:
            tn147_case = _normalize_tn147_case(tn147_case)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        (
            grapple_yarder_model,
            grapple_turn_volume_m3,
            grapple_yarding_distance_m,
            grapple_lateral_distance_m,
            grapple_stems_per_cycle,
            grapple_in_cycle_delay_minutes,
            grapple_tn157_case,
            grapple_tn147_case,
            grapple_defaults_used,
        ) = _apply_grapple_yarder_system_defaults(
            system=selected_system,
            model=grapple_yarder_model,
            turn_volume_m3=grapple_turn_volume_m3,
            yarding_distance_m=grapple_yarding_distance_m,
            lateral_distance_m=grapple_lateral_distance_m,
            stems_per_cycle=grapple_stems_per_cycle,
            in_cycle_delay_minutes=grapple_in_cycle_delay_minutes,
            tn157_case=tn157_case,
            tn147_case=tn147_case,
            user_supplied=grapple_user_supplied,
        )
        preset_meta: dict[str, Any] | None = None
        tn157_case_metadata: TN157Case | None = None
        tn147_case_metadata: TN147Case | None = None
        tr122_treatment_metadata: TR122Treatment | None = None
        adv5n28_block_metadata: ADV5N28Block | None = None
        preset_note: str | None = None
        if grapple_yarder_model is GrappleYarderModel.TN157:
            tn157_case_metadata = get_tn157_case(grapple_tn157_case)
            if grapple_turn_volume_m3 is None:
                grapple_turn_volume_m3 = tn157_case_metadata.average_turn_volume_m3
            if grapple_yarding_distance_m is None:
                grapple_yarding_distance_m = tn157_case_metadata.average_yarding_distance_m
            value = tn157_case_metadata.productivity_m3_per_pmh
            preset_meta = {
                "label": tn157_case_metadata.label,
                "logs_per_turn": tn157_case_metadata.logs_per_turn,
                "cost_per_m3": tn157_case_metadata.cost_per_m3_cad_1991,
                "cost_per_log": tn157_case_metadata.cost_per_log_cad_1991,
                "cost_base_year": 1991,
                "note": (
                    "[dim]Observed productivity/costs from FERIC TN-157 "
                    "(Cypress 7280B swing yarder + Hitachi UH14 backspar, 1987–1988 case studies).[/dim]"
                ),
            }
        elif grapple_yarder_model is GrappleYarderModel.TN147:
            tn147_case_metadata = get_tn147_case(grapple_tn147_case)
            if grapple_turn_volume_m3 is None:
                grapple_turn_volume_m3 = tn147_case_metadata.average_turn_volume_m3
            if grapple_yarding_distance_m is None:
                grapple_yarding_distance_m = tn147_case_metadata.average_yarding_distance_m
            value = tn147_case_metadata.productivity_m3_per_pmh
            preset_meta = {
                "label": tn147_case_metadata.label,
                "logs_per_turn": tn147_case_metadata.logs_per_turn,
                "cost_per_m3": tn147_case_metadata.cost_per_m3_cad_1989,
                "cost_per_log": tn147_case_metadata.cost_per_log_cad_1989,
                "cost_base_year": 1989,
                "note": (
                    "[dim]Observed productivity/costs from FERIC TN-147 "
                    "(Madill 009 highlead trials near Lake Cowichan, 1989).[/dim]"
                ),
            }
        elif grapple_yarder_model in _TR122_MODEL_TO_TREATMENT:
            treatment_id = _TR122_MODEL_TO_TREATMENT[grapple_yarder_model]
            tr122_treatment_metadata = get_tr122_treatment(treatment_id)
            if grapple_turn_volume_m3 is None:
                grapple_turn_volume_m3 = tr122_treatment_metadata.cycle_volume_m3
            if grapple_yarding_distance_m is None:
                grapple_yarding_distance_m = tr122_treatment_metadata.yarding_distance_m
            value = tr122_treatment_metadata.productivity_m3_per_pmh
            base_year = tr122_treatment_metadata.cost_base_year
            preset_meta = {
                "label": tr122_treatment_metadata.label,
                "logs_per_turn": tr122_treatment_metadata.avg_pieces_per_cycle,
                "cost_per_m3": tr122_treatment_metadata.cost_total_per_m3_cad_1996,
                "cost_per_log": None,
                "cost_base_year": base_year,
                "extra_rows": [
                    (
                        f"Yarder Cost ({base_year} CAD $/m³)",
                        f"{tr122_treatment_metadata.yarder_cost_per_m3_cad_1996:.2f}",
                    ),
                    (
                        f"Loader Cost ({base_year} CAD $/m³)",
                        f"{tr122_treatment_metadata.loader_cost_per_m3_cad_1996:.2f}",
                    ),
                    (
                        f"Yarding Labour ({base_year} CAD $/m³)",
                        f"{tr122_treatment_metadata.yarding_labour_per_m3_cad_1996:.2f}",
                    ),
                    (
                        f"Loading Labour ({base_year} CAD $/m³)",
                        f"{tr122_treatment_metadata.loading_labour_per_m3_cad_1996:.2f}",
                    ),
                ],
                "note": (
                    "[dim]Observed productivity/costs from FERIC TR-122 "
                    "(Roberts Creek SLH 78 running skyline treatments, 1996).[/dim]"
                ),
            }
        elif grapple_yarder_model in _ADV5N28_MODEL_TO_BLOCK:
            block_id = _ADV5N28_MODEL_TO_BLOCK[grapple_yarder_model]
            adv5n28_block_metadata = get_adv5n28_block(block_id)
            if grapple_turn_volume_m3 is None:
                grapple_turn_volume_m3 = adv5n28_block_metadata.average_turn_volume_m3
            if grapple_yarding_distance_m is None:
                grapple_yarding_distance_m = adv5n28_block_metadata.average_yarding_distance_m
            value = adv5n28_block_metadata.productivity_m3_per_pmh
            base_year = adv5n28_block_metadata.cost_base_year
            extra_rows: list[tuple[str, str]] = []
            projected = adv5n28_block_metadata.cost_total_estimated_per_m3_cad_2002
            if projected is not None:
                extra_rows.extend(
                    [
                        (
                            f"Projected Cost ({base_year} CAD $/m³)",
                            f"{projected:.2f}",
                        ),
                        (
                            f"Projected Cost ({TARGET_YEAR} CAD $/m³)",
                            f"{inflate_value(projected, base_year):.2f}",
                        ),
                    ]
                )
            heli_cost = adv5n28_block_metadata.cost_helicopter_reference_per_m3_cad_2002
            if heli_cost is not None:
                extra_rows.extend(
                    [
                        (
                            f"Helicopter Baseline ({base_year} CAD $/m³)",
                            f"{heli_cost:.2f}",
                        ),
                        (
                            f"Helicopter Baseline ({TARGET_YEAR} CAD $/m³)",
                            f"{inflate_value(heli_cost, base_year):.2f}",
                        ),
                    ]
                )
            preset_meta = {
                "label": adv5n28_block_metadata.label.title(),
                "logs_per_turn": adv5n28_block_metadata.logs_per_turn,
                "cost_per_m3": adv5n28_block_metadata.cost_total_actual_per_m3_cad_2002,
                "cost_per_log": None,
                "cost_base_year": base_year,
                "extra_rows": extra_rows,
                "projected_cost_per_m3": projected,
                "projected_cost_per_m3_target": (
                    inflate_value(projected, base_year) if projected is not None else None
                ),
                "helicopter_cost_per_m3": heli_cost,
                "helicopter_cost_per_m3_target": (
                    inflate_value(heli_cost, base_year) if heli_cost is not None else None
                ),
                "note": (
                    "[dim]Observed skyline conversion metrics from FPInnovations ADV5N28 "
                    "(Madill 071 + Acme 200 Pow'-R Block, 2002).[/dim]"
                ),
            }
        elif grapple_yarder_model is GrappleYarderModel.ADV1N35:
            if grapple_yarding_distance_m is None:
                raise typer.BadParameter(
                    "--grapple-yard-distance-m is required for the ADV1N35 model."
                )
            metadata = get_adv1n35_metadata()
            if grapple_turn_volume_m3 is None:
                grapple_turn_volume_m3 = metadata.default_turn_volume_m3
            if grapple_lateral_distance_m is None:
                grapple_lateral_distance_m = metadata.default_lateral_distance_m
            if grapple_stems_per_cycle is None:
                grapple_stems_per_cycle = metadata.default_stems_per_turn
            if grapple_in_cycle_delay_minutes is None:
                grapple_in_cycle_delay_minutes = metadata.default_in_cycle_delay_min
            value = estimate_grapple_yarder_productivity_adv1n35(
                turn_volume_m3=grapple_turn_volume_m3,
                yarding_distance_m=grapple_yarding_distance_m,
                lateral_distance_m=grapple_lateral_distance_m,
                stems_per_turn=grapple_stems_per_cycle,
                in_cycle_delay_minutes=grapple_in_cycle_delay_minutes,
            )
            preset_note = metadata.note
        elif grapple_yarder_model is GrappleYarderModel.ADV1N40:
            metadata = get_adv1n40_metadata()
            if grapple_turn_volume_m3 is None:
                grapple_turn_volume_m3 = metadata.default_turn_volume_m3
            if grapple_yarding_distance_m is None:
                grapple_yarding_distance_m = metadata.default_yarding_distance_m
            if grapple_in_cycle_delay_minutes is None:
                grapple_in_cycle_delay_minutes = metadata.default_delay_minutes
            value = estimate_grapple_yarder_productivity_adv1n40(
                turn_volume_m3=grapple_turn_volume_m3,
                yarding_distance_m=grapple_yarding_distance_m,
                in_cycle_delay_minutes=grapple_in_cycle_delay_minutes,
            )
            preset_note = metadata.note
            preset_meta = {
                "label": "ADV1N40 Madill 071 (downhill running/scab)",
                "cost_per_m3": 12.11,
                "cost_base_year": 2000,
                "extra_rows": [
                    ("Total Harvest Cost (2000 CAD $/m³)", f"{22.25:.2f}"),
                    ("Total Harvest Cost (2024 CAD $/m³)", f"{inflate_value(22.25, 2000):.2f}"),
                ],
            }
        else:
            value = _evaluate_grapple_yarder_result(
                model=grapple_yarder_model,
                turn_volume_m3=grapple_turn_volume_m3,
                yarding_distance_m=grapple_yarding_distance_m,
            )
        assert grapple_turn_volume_m3 is not None
        assert grapple_yarding_distance_m is not None
        telemetry_inputs: dict[str, Any] = {
            "turn_volume_m3": grapple_turn_volume_m3,
            "yarding_distance_m": grapple_yarding_distance_m,
            "lateral_distance_m": grapple_lateral_distance_m,
            "stems_per_turn": grapple_stems_per_cycle,
            "in_cycle_delay_minutes": grapple_in_cycle_delay_minutes,
            "tn157_case": grapple_tn157_case if grapple_yarder_model is GrappleYarderModel.TN157 else None,
            "tn147_case": grapple_tn147_case if grapple_yarder_model is GrappleYarderModel.TN147 else None,
            "harvest_system_id": selected_system.system_id if selected_system else None,
            "harvest_system_defaults_used": grapple_defaults_used,
            "salvage_processing_mode": telemetry_salvage_mode,
        }
        _render_grapple_yarder_result(
            model=grapple_yarder_model,
            turn_volume_m3=grapple_turn_volume_m3,
            yarding_distance_m=grapple_yarding_distance_m,
            productivity_m3_per_pmh=value,
            preset_meta=preset_meta,
            lateral_distance_m=grapple_lateral_distance_m,
            stems_per_cycle=grapple_stems_per_cycle,
            in_cycle_delay_minutes=grapple_in_cycle_delay_minutes,
            note=preset_note,
        )
        if telemetry_log:
            _append_grapple_yarder_telemetry(
                log_path=telemetry_log,
                model=grapple_yarder_model,
                inputs=telemetry_inputs,
                productivity_m3_per_pmh=value,
                preset_meta=preset_meta,
            )
        if grapple_defaults_used and selected_system is not None:
            console.print(
                f"[dim]Applied grapple-yarder defaults from harvest system '{selected_system.system_id}'.[/dim]"
            )
        _maybe_render_costs(
            show_costs,
            _grapple_yarder_cost_role(grapple_yarder_model),
        )
        return
    if role == ProductivityMachineRole.ROADSIDE_PROCESSOR.value:
        processor_user_supplied = {
            "processor_model": _parameter_supplied(ctx, "processor_model"),
            "processor_adv7n3_machine": _parameter_supplied(ctx, "processor_adv7n3_machine"),
        }
        (
            processor_model,
            processor_adv7n3_machine,
            processor_defaults_used,
        ) = _apply_processor_system_defaults(
            system=selected_system,
            processor_model=processor_model,
            processor_adv7n3_machine=processor_adv7n3_machine,
            user_supplied=processor_user_supplied,
        )
        processor_delay_supplied = _parameter_supplied(ctx, "processor_delay_multiplier")
        berry_skid_prediction: dict[str, Any] | None = None
        berry_skid_auto_adjusted = False
        automatic_bucking_info = None
        automatic_bucking_multiplier_value: float | None = None
        if processor_automatic_bucking:
            if processor_model not in _AUTOMATIC_BUCKING_SUPPORTED_MODELS:
                valid_models = ", ".join(
                    sorted(m.value for m in _AUTOMATIC_BUCKING_SUPPORTED_MODELS)
                )
                raise typer.BadParameter(
                    f"--processor-automatic-bucking is supported for these models only: {valid_models}."
                )
            automatic_bucking_info = get_labelle_huss_automatic_bucking_adjustment()
            automatic_bucking_multiplier_value = automatic_bucking_info.multiplier
        processor_carrier_profile: ProcessorCarrierProfile | None = None
        if processor_model is RoadsideProcessorModel.BERRY2019:
            processor_carrier_profile = get_processor_carrier_profile(processor_carrier.value)
            if (
                not processor_delay_supplied
                and processor_carrier_profile.default_delay_multiplier is not None
            ):
                processor_delay_multiplier = processor_carrier_profile.default_delay_multiplier
        elif processor_carrier is not ProcessorCarrier.PURPOSE_BUILT:
            raise typer.BadParameter(
                "--processor-carrier currently applies to --processor-model berry2019 only."
            )
        if (
            processor_log_sorts is not None
            and processor_model is not RoadsideProcessorModel.VISSER2015
        ):
            raise typer.BadParameter(
                "--processor-log-sorts applies to --processor-model visser2015."
            )
        if processor_model is RoadsideProcessorModel.BERRY2019:
            if processor_piece_size_m3 is None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 is required when --processor-model berry2019."
                )
            if processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-volume-m3 applies to the Labelle volume helper; omit it for berry2019."
                )
            if processor_skid_area_m2 is not None:
                try:
                    (
                        predicted_delay_seconds,
                        predicted_productivity_m3_per_hour,
                        baseline_delay_seconds,
                        skid_area_range,
                        delay_r2,
                        productivity_r2,
                    ) = predict_berry2019_skid_effects(processor_skid_area_m2)
                except ValueError as exc:
                    raise typer.BadParameter(str(exc)) from exc
                berry_skid_prediction = {
                    "skid_area_m2": processor_skid_area_m2,
                    "delay_seconds": predicted_delay_seconds,
                    "predicted_productivity_m3_per_hour": predicted_productivity_m3_per_hour,
                    "baseline_delay_seconds": baseline_delay_seconds,
                    "out_of_range": bool(
                        skid_area_range
                        and (
                            processor_skid_area_m2 < skid_area_range[0]
                            or processor_skid_area_m2 > skid_area_range[1]
                        )
                    ),
                    "delay_r2": delay_r2,
                    "productivity_r2": productivity_r2,
                }
                if not processor_delay_supplied and predicted_delay_seconds > 0:
                    scaled_multiplier = processor_delay_multiplier * (
                        baseline_delay_seconds / predicted_delay_seconds
                    )
                    processor_delay_multiplier = max(min(scaled_multiplier, 1.0), 0.01)
                    berry_skid_auto_adjusted = True

            result_processor = estimate_processor_productivity_berry2019(
                piece_size_m3=processor_piece_size_m3,
                tree_form_category=processor_tree_form,
                crew_multiplier=processor_crew_multiplier,
                delay_multiplier=processor_delay_multiplier,
                automatic_bucking_multiplier=automatic_bucking_multiplier_value,
                carrier_profile=processor_carrier_profile,
            )
        elif processor_model is RoadsideProcessorModel.LABELLE2016:
            if processor_piece_size_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 applies to the Berry (2019) helper only."
                )
            if processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-volume-m3 applies to the Labelle 2019 volume helper only."
                )
            if processor_dbh_cm is None:
                raise typer.BadParameter(
                    "--processor-dbh-cm is required for Labelle (2016) models."
                )
            result_processor = estimate_processor_productivity_labelle2016(
                tree_form=processor_labelle2016_form.value,
                dbh_cm=processor_dbh_cm,
                delay_multiplier=processor_delay_multiplier,
                automatic_bucking_multiplier=automatic_bucking_multiplier_value,
            )
        elif processor_model is RoadsideProcessorModel.LABELLE2017:
            if processor_piece_size_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 applies to the Berry (2019) helper only."
                )
            if processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-volume-m3 applies to the Labelle 2019 helper."
                )
            if processor_dbh_cm is None:
                raise typer.BadParameter(
                    "--processor-dbh-cm is required for Labelle (2017) models."
                )
            result_processor = estimate_processor_productivity_labelle2017(
                variant=processor_labelle2017_variant.value,
                dbh_cm=processor_dbh_cm,
                delay_multiplier=processor_delay_multiplier,
                automatic_bucking_multiplier=automatic_bucking_multiplier_value,
            )
        elif processor_model is RoadsideProcessorModel.LABELLE2018:
            if processor_piece_size_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 applies to the Berry (2019) helper only."
                )
            if processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-volume-m3 applies to the Labelle 2019 volume helper."
                )
            if processor_dbh_cm is None:
                raise typer.BadParameter(
                    "--processor-dbh-cm is required for Labelle (2018) models."
                )
            result_processor = estimate_processor_productivity_labelle2018(
                variant=processor_labelle2018_variant.value,
                dbh_cm=processor_dbh_cm,
                delay_multiplier=processor_delay_multiplier,
                automatic_bucking_multiplier=automatic_bucking_multiplier_value,
            )
        elif processor_model is RoadsideProcessorModel.LABELLE2019_DBH:
            if processor_piece_size_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 applies to the Berry (2019) helper only."
                )
            if processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-volume-m3 applies to the Labelle volume helper; use --processor-dbh-cm here."
                )
            if processor_dbh_cm is None:
                raise typer.BadParameter(
                    "--processor-dbh-cm is required for Labelle (2019) DBH models."
                )
            if processor_species is None:
                raise typer.BadParameter(
                    "--processor-species (spruce | beech) is required for Labelle (2019) models."
                )
            if processor_treatment is None:
                raise typer.BadParameter(
                    "--processor-treatment (clear_cut | selective_cut) is required for Labelle (2019) models."
                )
            result_processor = estimate_processor_productivity_labelle2019_dbh(
                species=processor_species.value,
                treatment=processor_treatment.value,
                dbh_cm=processor_dbh_cm,
                delay_multiplier=processor_delay_multiplier,
                automatic_bucking_multiplier=automatic_bucking_multiplier_value,
            )
        elif processor_model is RoadsideProcessorModel.ADV5N6:
            if processor_piece_size_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 applies to the Berry (2019) helper only."
                )
            if processor_dbh_cm is not None or processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-dbh-cm/--processor-volume-m3 apply to Labelle helpers; ADV5N6 is table-driven."
                )
            if processor_species is not None or processor_treatment is not None:
                raise typer.BadParameter(
                    "--processor-species/--processor-treatment do not apply to ADV5N6."
                )
            stem_source_value = processor_stem_source.value
            processing_mode_value = processor_adv5n6_processing_mode.value
            if (
                stem_source_value == ADV5N6StemSource.LOADER_FORWARDED.value
                and processing_mode_value != ADV5N6ProcessingMode.COLD.value
            ):
                raise typer.BadParameter(
                    "ADV5N6 only reports loader-forwarded data for cold processing decks; use --processor-processing-mode cold."
                )
            result_processor = estimate_processor_productivity_adv5n6(
                stem_source=stem_source_value,
                processing_mode=processing_mode_value,
            )
        elif processor_model is RoadsideProcessorModel.ADV7N3:
            result_processor = estimate_processor_productivity_adv7n3(
                machine=processor_adv7n3_machine.value
            )
        elif processor_model is RoadsideProcessorModel.VISSER2015:
            if processor_piece_size_m3 is None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 is required when --processor-model visser2015."
                )
            if processor_log_sorts is None:
                raise typer.BadParameter(
                    "--processor-log-sorts must be provided for the Visser & Tolan (2015) helper."
                )
            if processor_volume_m3 is not None or processor_dbh_cm is not None:
                raise typer.BadParameter(
                    "--processor-volume-m3/--processor-dbh-cm apply to the Labelle helpers; omit them for visser2015."
                )
            if processor_species is not None or processor_treatment is not None:
                raise typer.BadParameter(
                    "--processor-species/--processor-treatment do not apply to visser2015."
                )
            result_processor = estimate_processor_productivity_visser2015(
                piece_size_m3=processor_piece_size_m3,
                log_sort_count=processor_log_sorts,
                delay_multiplier=processor_delay_multiplier,
            )
        elif processor_model is RoadsideProcessorModel.HYPRO775:
            if (
                processor_piece_size_m3 is not None
                or processor_volume_m3 is not None
                or processor_dbh_cm is not None
            ):
                raise typer.BadParameter(
                    "--processor-piece-size/volume/dbh do not apply to hypro775 preset."
                )
            result_processor = estimate_processor_productivity_hypro775(
                delay_multiplier=processor_delay_multiplier,
            )
        elif processor_model is RoadsideProcessorModel.BERTONE2025:
            if processor_piece_size_m3 is None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 (tree volume) is required for --processor-model bertone2025."
                )
            if processor_dbh_cm is None:
                raise typer.BadParameter("--processor-dbh-cm is required for bertone2025.")
            if processor_tree_height_m is None:
                raise typer.BadParameter("--processor-tree-height-m is required for bertone2025.")
            if processor_logs_per_tree is None:
                raise typer.BadParameter("--processor-logs-per-tree is required for bertone2025.")
            result_processor = estimate_processor_productivity_bertone2025(
                dbh_cm=processor_dbh_cm,
                height_m=processor_tree_height_m,
                logs_per_tree=processor_logs_per_tree,
                tree_volume_m3=processor_piece_size_m3,
                delay_multiplier=processor_delay_multiplier,
            )
        elif processor_model is RoadsideProcessorModel.SPINELLI2010:
            if processor_piece_size_m3 is None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 (tree volume) is required for --processor-model spinelli2010."
                )
            if processor_machine_power_kw is None:
                raise typer.BadParameter(
                    "--processor-machine-power-kw is required for --processor-model spinelli2010."
                )
            slope_value = processor_slope_percent or 0.0
            if processor_spinelli_operation is SpinelliOperation.HARVEST:
                if processor_removals_per_ha is None or processor_removals_per_ha <= 0:
                    raise typer.BadParameter(
                        "--processor-removals-per-ha must be provided (>0) for Spinelli harvest scenarios."
                    )
                if processor_residuals_per_ha is None or processor_residuals_per_ha < 0:
                    raise typer.BadParameter(
                        "--processor-residuals-per-ha must be provided (>=0) for Spinelli harvest scenarios."
                    )
            result_processor = estimate_processor_productivity_spinelli2010(
                operation=processor_spinelli_operation.value,
                tree_volume_m3=processor_piece_size_m3,
                slope_percent=slope_value,
                machine_power_kw=processor_machine_power_kw,
                carrier_type=processor_spinelli_carrier.value,
                head_type=processor_spinelli_head.value,
                species_group=processor_spinelli_species.value,
                stand_type=processor_spinelli_stand_type.value,
                removals_per_ha=processor_removals_per_ha,
                residuals_per_ha=processor_residuals_per_ha,
            )
        elif processor_model is RoadsideProcessorModel.BORZ2023:
            result_processor = estimate_processor_productivity_borz2023(
                tree_volume_m3=processor_piece_size_m3,
            )
        elif processor_model is RoadsideProcessorModel.NAKAGAWA2010:
            if processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-volume-m3 applies to the Labelle 2019 volume helper, not Nakagawa (2010)."
                )
            if processor_dbh_cm is None and processor_piece_size_m3 is None:
                raise typer.BadParameter(
                    "--processor-dbh-cm or --processor-piece-size-m3 must be provided for nakagawa2010."
                )
            result_processor = estimate_processor_productivity_nakagawa2010(
                dbh_cm=processor_dbh_cm,
                piece_volume_m3=processor_piece_size_m3,
                delay_multiplier=processor_delay_multiplier,
            )
        elif processor_model is RoadsideProcessorModel.TN103:
            if processor_piece_size_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 applies to the Berry (2019) helper only."
                )
            if processor_dbh_cm is not None or processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-dbh-cm/--processor-volume-m3 apply to Labelle helpers; TN-103 is table-driven."
                )
            if processor_species is not None or processor_treatment is not None:
                raise typer.BadParameter(
                    "--processor-species/--processor-treatment do not apply to TN-103."
                )
            result_processor = estimate_processor_productivity_tn103(
                scenario=processor_tn103_scenario.value,
            )
        elif processor_model is RoadsideProcessorModel.TR106:
            if processor_piece_size_m3 is not None or processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3/--processor-volume-m3 apply to Berry/Labelle helpers; TR-106 is table-driven."
                )
            if processor_dbh_cm is not None:
                raise typer.BadParameter(
                    "--processor-dbh-cm applies to the Labelle helpers, not TR-106."
                )
            if processor_species is not None or processor_treatment is not None:
                raise typer.BadParameter(
                    "--processor-species/--processor-treatment do not apply to TR-106."
                )
            result_processor = estimate_processor_productivity_tr106(
                scenario=processor_tr106_scenario.value,
            )
        elif processor_model is RoadsideProcessorModel.TR87:
            if processor_piece_size_m3 is not None or processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3/--processor-volume-m3 apply to Berry/Labelle helpers; TR-87 is table-driven."
                )
            if processor_dbh_cm is not None:
                raise typer.BadParameter(
                    "--processor-dbh-cm applies to the Labelle helpers, not TR-87."
                )
            if processor_species is not None or processor_treatment is not None:
                raise typer.BadParameter(
                    "--processor-species/--processor-treatment do not apply to TR-87."
                )
            result_processor = estimate_processor_productivity_tr87(
                scenario=processor_tr87_scenario.value,
            )
        elif processor_model is RoadsideProcessorModel.TN166:
            if processor_piece_size_m3 is not None or processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3/--processor-volume-m3 apply to other helpers; TN-166 is table-driven."
                )
            if processor_dbh_cm is not None:
                raise typer.BadParameter(
                    "--processor-dbh-cm applies to the Labelle helpers, not TN-166."
                )
            if processor_species is not None or processor_treatment is not None:
                raise typer.BadParameter(
                    "--processor-species/--processor-treatment do not apply to TN-166."
                )
            result_processor = estimate_processor_productivity_tn166(
                scenario=processor_tn166_scenario.value,
            )
        else:
            if processor_piece_size_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3 applies to the Berry (2019) helper only."
                )
            if processor_dbh_cm is not None:
                raise typer.BadParameter(
                    "--processor-dbh-cm applies to the Labelle DBH helper; use --processor-volume-m3 instead."
                )
            if processor_volume_m3 is None:
                raise typer.BadParameter(
                    "--processor-volume-m3 is required when --processor-model labelle2019_volume."
                )
            if processor_species is None:
                raise typer.BadParameter(
                    "--processor-species (spruce | beech) is required for Labelle (2019) models."
                )
            if processor_treatment is None:
                raise typer.BadParameter(
                    "--processor-treatment (clear_cut | selective_cut) is required for Labelle (2019) models."
                )
            result_processor = estimate_processor_productivity_labelle2019_volume(
                species=processor_species.value,
                treatment=processor_treatment.value,
                volume_m3=processor_volume_m3,
                delay_multiplier=processor_delay_multiplier,
                automatic_bucking_multiplier=automatic_bucking_multiplier_value,
            )
        _render_processor_result(result_processor)
        if processor_show_grade_stats:
            if processor_model is RoadsideProcessorModel.BERRY2019:
                _render_berry_log_grade_table()
            else:
                console.print(
                    "[dim]--processor-show-grade-stats applies to the Berry (2019) helper only.[/dim]"
                )
        if automatic_bucking_info is not None:
            pct_gain = (automatic_bucking_info.multiplier - 1.0) * 100.0
            console.print(
                "[dim]Applied Labelle & Huß (2018, Silva Fennica 52(3):9947) automatic bucking multiplier "
                f"(+{pct_gain:.1f}% delay-free productivity ≈ {automatic_bucking_info.delta_m3_per_pmh:.1f} m³/PMH₀ uplift).[/dim]"
            )
            if automatic_bucking_info.revenue_delta_per_m3 is not None:
                currency = automatic_bucking_info.currency or "EUR"
                base_year = (
                    str(automatic_bucking_info.base_year)
                    if automatic_bucking_info.base_year is not None
                    else "2018"
                )
                console.print(
                    "[dim]Reference revenue delta: "
                    f"+{automatic_bucking_info.revenue_delta_per_m3:.1f} {currency}/m³ ({base_year}).[/dim]"
                )
        _maybe_render_costs(show_costs, ProductivityMachineRole.ROADSIDE_PROCESSOR.value)
        if processor_defaults_used and selected_system is not None:
            console.print(
                f"[dim]Applied productivity defaults from harvest system '{selected_system.system_id}'.[/dim]"
            )
        if berry_skid_prediction is not None:
            delay_line = (
                f"[dim]Berry skid-size model predicts {berry_skid_prediction['delay_seconds']:.1f} s/stem "
                f"at {berry_skid_prediction['skid_area_m2']:.0f} m²."
            )
            if berry_skid_prediction["out_of_range"]:
                delay_line += " (Outside the published ~2.5–3.7k m² study range.)"
            if berry_skid_auto_adjusted:
                delay_line += (
                    f" Delay multiplier auto-adjusted to {processor_delay_multiplier:.3f}."
                )
            elif processor_delay_supplied:
                delay_line += " Delay multiplier left unchanged because --processor-delay-multiplier was supplied."
            console.print(delay_line + "[/dim]")
            predicted_prod = berry_skid_prediction["predicted_productivity_m3_per_hour"]
            if predicted_prod is not None:
                r2_text = berry_skid_prediction["productivity_r2"]
                r2_fragment = (
                    f"~R² {r2_text:.2f}" if isinstance(r2_text, (float, int)) else "weak fit"
                )
                console.print(
                    f"[dim]Skid-size productivity regression ({r2_fragment}) suggests ≈{predicted_prod:.1f} m³/PMH for this landing size (informational only).[/dim]"
                )
        return
    if role == ProductivityMachineRole.LOADER.value:
        loader_user_supplied = {
            "loader_model": _parameter_supplied(ctx, "loader_model"),
            "loader_piece_size_m3": _parameter_supplied(ctx, "loader_piece_size_m3"),
            "loader_distance_m": _parameter_supplied(ctx, "loader_distance_m"),
            "loader_payload_m3": _parameter_supplied(ctx, "loader_payload_m3"),
            "loader_slope_percent": _parameter_supplied(ctx, "loader_slope_percent"),
            "loader_bunched": _parameter_supplied(ctx, "loader_bunched"),
            "loader_delay_multiplier": _parameter_supplied(ctx, "loader_delay_multiplier"),
            "loader_travel_empty_m": _parameter_supplied(ctx, "loader_travel_empty_m"),
            "loader_stems_per_cycle": _parameter_supplied(ctx, "loader_stems_per_cycle"),
            "loader_stem_volume_m3": _parameter_supplied(ctx, "loader_stem_volume_m3"),
            "loader_utilisation": _parameter_supplied(ctx, "loader_utilisation"),
            "loader_in_cycle_delay_minutes": _parameter_supplied(
                ctx, "loader_in_cycle_delay_minutes"
            ),
            "loader_slope_class": _parameter_supplied(ctx, "loader_slope_class"),
            "loader_barko_scenario": _parameter_supplied(ctx, "loader_barko_scenario"),
            "loader_hot_cold_mode": _parameter_supplied(ctx, "loader_hot_cold_mode"),
        }
        (
            loader_model,
            loader_piece_size_m3,
            loader_distance_m,
            loader_payload_m3,
            loader_slope_percent,
            loader_bunched,
            loader_delay_multiplier,
            loader_travel_empty_m,
            loader_stems_per_cycle,
            loader_stem_volume_m3,
            loader_utilisation,
            loader_in_cycle_delay_minutes,
            loader_slope_class,
            loader_barko_scenario,
            loader_hot_cold_mode,
            loader_defaults_used,
        ) = _apply_loader_system_defaults(
            system=selected_system,
            loader_model=loader_model,
            loader_model_supplied=loader_user_supplied["loader_model"],
            piece_size_m3=loader_piece_size_m3,
            piece_size_supplied=loader_user_supplied["loader_piece_size_m3"],
            external_distance_m=loader_distance_m,
            distance_supplied=loader_user_supplied["loader_distance_m"],
            payload_m3=loader_payload_m3,
            payload_supplied=loader_user_supplied["loader_payload_m3"],
            slope_percent=loader_slope_percent,
            slope_supplied=loader_user_supplied["loader_slope_percent"],
            bunched=loader_bunched,
            bunched_supplied=loader_user_supplied["loader_bunched"],
            delay_multiplier=loader_delay_multiplier,
            delay_supplied=loader_user_supplied["loader_delay_multiplier"],
            travel_empty_m=loader_travel_empty_m,
            travel_supplied=loader_user_supplied["loader_travel_empty_m"],
            stems_per_cycle=loader_stems_per_cycle,
            stems_supplied=loader_user_supplied["loader_stems_per_cycle"],
            stem_volume_m3=loader_stem_volume_m3,
            stem_volume_supplied=loader_user_supplied["loader_stem_volume_m3"],
            utilisation=loader_utilisation,
            utilisation_supplied=loader_user_supplied["loader_utilisation"],
            in_cycle_delay_minutes=loader_in_cycle_delay_minutes,
            in_cycle_supplied=loader_user_supplied["loader_in_cycle_delay_minutes"],
            slope_class=loader_slope_class,
            slope_class_supplied=loader_user_supplied["loader_slope_class"],
            barko_scenario=loader_barko_scenario,
            barko_scenario_supplied=loader_user_supplied["loader_barko_scenario"],
            hot_cold_mode=loader_hot_cold_mode,
            hot_cold_mode_supplied=loader_user_supplied["loader_hot_cold_mode"],
        )
        loader_metadata = _loader_model_metadata(loader_model)
        loader_cost_role = ProductivityMachineRole.LOADER.value
        if loader_model is LoaderProductivityModel.TN261:
            if loader_piece_size_m3 is None:
                raise typer.BadParameter(
                    "--loader-piece-size-m3 is required when --loader-model tn261."
                )
            if loader_distance_m is None:
                raise typer.BadParameter(
                    "--loader-distance-m is required when --loader-model tn261."
                )
            loader_result = estimate_loader_forwarder_productivity_tn261(
                piece_size_m3=loader_piece_size_m3,
                external_distance_m=loader_distance_m,
                slope_percent=loader_slope_percent,
                bunched=loader_bunched,
                delay_multiplier=loader_delay_multiplier,
            )
            telemetry_inputs = {
                "piece_size_m3": loader_piece_size_m3,
                "distance_m": loader_distance_m,
                "slope_percent": loader_slope_percent,
                "bunched": loader_bunched,
                "delay_multiplier": loader_delay_multiplier,
            }
            telemetry_outputs = {
                "delay_free_m3_per_pmh": loader_result.delay_free_productivity_m3_per_pmh,
                "productivity_m3_per_pmh": loader_result.productivity_m3_per_pmh,
            }
        elif loader_model is LoaderProductivityModel.ADV2N26:
            utilisation_value = (
                loader_utilisation
                if loader_utilisation is not None
                else ADV2N26_DEFAULT_UTILISATION
            )
            loader_result = estimate_clambunk_productivity_adv2n26(
                travel_empty_distance_m=loader_travel_empty_m,
                stems_per_cycle=loader_stems_per_cycle,
                average_stem_volume_m3=loader_stem_volume_m3,
                utilization=utilisation_value,
                in_cycle_delay_minutes=loader_in_cycle_delay_minutes,
            )
            telemetry_inputs = {
                "travel_empty_m": loader_travel_empty_m,
                "stems_per_cycle": loader_stems_per_cycle,
                "average_stem_volume_m3": loader_stem_volume_m3,
                "utilisation": utilisation_value,
                "in_cycle_delay_minutes": loader_in_cycle_delay_minutes,
            }
            telemetry_outputs = {
                "delay_free_cycle_minutes": loader_result.delay_free_cycle_minutes,
                "total_cycle_minutes": loader_result.total_cycle_minutes,
                "productivity_m3_per_smh": loader_result.productivity_m3_per_smh,
            }
        elif loader_model is LoaderProductivityModel.ADV5N1:
            if loader_distance_m is None:
                raise typer.BadParameter(
                    "--loader-distance-m is required when --loader-model adv5n1."
                )
            utilisation_value = (
                loader_utilisation if loader_utilisation is not None else ADV5N1_DEFAULT_UTILISATION
            )
            loader_result = estimate_loader_forwarder_productivity_adv5n1(
                forwarding_distance_m=loader_distance_m,
                slope_class=loader_slope_class.value,
                payload_m3_per_cycle=loader_payload_m3,
                utilisation=utilisation_value,
            )
            telemetry_inputs = {
                "forwarding_distance_m": loader_distance_m,
                "slope_class": loader_slope_class.value,
                "payload_m3_per_cycle": loader_payload_m3,
                "utilisation": utilisation_value,
            }
            telemetry_outputs = {
                "cycle_time_minutes": loader_result.cycle_time_minutes,
                "productivity_m3_per_smh": loader_result.productivity_m3_per_smh,
            }
        elif loader_model is LoaderProductivityModel.BARKO450:
            result = estimate_loader_productivity_barko450(
                scenario=loader_barko_scenario.value,
                utilisation_override=(
                    loader_utilisation if loader_user_supplied["loader_utilisation"] else None
                ),
            )
            telemetry_inputs = {
                "scenario": loader_barko_scenario.value,
            }
            telemetry_outputs = {
                "avg_volume_per_shift_m3": result.avg_volume_per_shift_m3,
                "utilisation_percent": result.utilisation_percent,
                "availability_percent": result.availability_percent,
            }
            loader_result = result
            loader_cost_role = "loader_barko450"
        elif loader_model is LoaderProductivityModel.KIZHA2020:
            loader_result = estimate_loader_hot_cold_productivity(mode=loader_hot_cold_mode.value)
            telemetry_inputs = {
                "mode": loader_hot_cold_mode.value,
            }
            telemetry_outputs = {
                "utilisation_percent": loader_result.utilisation_percent,
                "operational_delay_percent": loader_result.operational_delay_percent_of_total_time,
            }
        else:  # pragma: no cover - defensive, all enums handled
            raise RuntimeError(f"Unhandled loader model {loader_model}")
        _render_loader_result(loader_result)
        if (
            loader_model is LoaderProductivityModel.BARKO450
            and loader_user_supplied["loader_utilisation"]
            and loader_utilisation is not None
        ):
            console.print(
                f"[dim]Adjusted Barko utilisation to {loader_utilisation * 100:.1f}% (scaled shift volume/cost per m³ accordingly).[/dim]"
            )
        if telemetry_log:
            _append_loader_telemetry(
                log_path=telemetry_log,
                model=loader_model,
                inputs=telemetry_inputs,
                outputs=telemetry_outputs,
                metadata=loader_metadata,
            )
        if loader_defaults_used and selected_system is not None:
            console.print(
                f"[dim]Applied loader defaults from harvest system '{selected_system.system_id}'.[/dim]"
            )
        _maybe_render_costs(show_costs, loader_cost_role)
        return
    if role == ProductivityMachineRole.SHOVEL_LOGGER.value:
        (
            shovel_passes,
            shovel_swing_length,
            shovel_strip_length,
            shovel_volume_per_ha,
            shovel_swing_time_roadside,
            shovel_payload_roadside,
            shovel_swing_time_initial,
            shovel_payload_initial,
            shovel_swing_time_rehandle,
            shovel_payload_rehandle,
            shovel_speed_index,
            shovel_speed_return,
            shovel_speed_serpentine,
            shovel_effective_minutes,
            shovel_slope_class,
            shovel_bunching_class,
            shovel_productivity_multiplier,
            shovel_defaults_used,
        ) = _apply_shovel_system_defaults(
            system=selected_system,
            passes=shovel_passes,
            swing_length_m=shovel_swing_length,
            strip_length_m=shovel_strip_length,
            volume_per_ha_m3=shovel_volume_per_ha,
            swing_time_roadside_s=shovel_swing_time_roadside,
            payload_per_swing_roadside_m3=shovel_payload_roadside,
            swing_time_initial_s=shovel_swing_time_initial,
            payload_per_swing_initial_m3=shovel_payload_initial,
            swing_time_rehandle_s=shovel_swing_time_rehandle,
            payload_per_swing_rehandle_m3=shovel_payload_rehandle,
            travel_speed_index_kph=shovel_speed_index,
            travel_speed_return_kph=shovel_speed_return,
            travel_speed_serpentine_kph=shovel_speed_serpentine,
            effective_minutes_per_hour=shovel_effective_minutes,
            slope_class=shovel_slope_class,
            bunching=shovel_bunching,
            custom_multiplier=shovel_productivity_multiplier,
        )
        result = _evaluate_shovel_logger_result(
            passes=shovel_passes,
            swing_length_m=shovel_swing_length,
            strip_length_m=shovel_strip_length,
            volume_per_ha_m3=shovel_volume_per_ha,
            swing_time_roadside_s=shovel_swing_time_roadside,
            payload_per_swing_roadside_m3=shovel_payload_roadside,
            swing_time_initial_s=shovel_swing_time_initial,
            payload_per_swing_initial_m3=shovel_payload_initial,
            swing_time_rehandle_s=shovel_swing_time_rehandle,
            payload_per_swing_rehandle_m3=shovel_payload_rehandle,
            travel_speed_index_kph=shovel_speed_index,
            travel_speed_return_kph=shovel_speed_return,
            travel_speed_serpentine_kph=shovel_speed_serpentine,
            effective_minutes_per_hour=shovel_effective_minutes,
            slope_class=shovel_slope_class,
            bunching=shovel_bunching_class,
            custom_multiplier=shovel_productivity_multiplier,
        )
        _render_shovel_logger_result(result)
        if shovel_defaults_used and selected_system is not None:
            console.print(
                f"[dim]Applied shovel-logger defaults from harvest system '{selected_system.system_id}'.[/dim]"
            )
        _maybe_render_costs(show_costs, ProductivityMachineRole.SHOVEL_LOGGER.value)
        return
    if role == ProductivityMachineRole.HELICOPTER_LONGLINE.value:
        heli_user_supplied = {
            "helicopter_model": _parameter_supplied(ctx, "helicopter_model"),
            "helicopter_flight_distance_m": _parameter_supplied(
                ctx, "helicopter_flight_distance_m"
            ),
            "helicopter_payload_m3": _parameter_supplied(ctx, "helicopter_payload_m3"),
            "helicopter_load_factor": _parameter_supplied(ctx, "helicopter_load_factor"),
            "helicopter_weight_to_volume": _parameter_supplied(ctx, "helicopter_weight_to_volume"),
            "helicopter_delay_minutes": _parameter_supplied(ctx, "helicopter_delay_minutes"),
        }
        (
            helicopter_model,
            helicopter_flight_distance_m,
            helicopter_payload_m3,
            helicopter_load_factor,
            helicopter_weight_to_volume,
            helicopter_delay_minutes,
            helicopter_defaults_used,
        ) = _apply_helicopter_system_defaults(
            system=selected_system,
            model=helicopter_model,
            flight_distance_m=helicopter_flight_distance_m,
            payload_m3=helicopter_payload_m3,
            load_factor=helicopter_load_factor,
            weight_to_volume_lb_per_m3=helicopter_weight_to_volume,
            delay_minutes=helicopter_delay_minutes,
            user_supplied=heli_user_supplied,
        )
        if helicopter_flight_distance_m is None:
            raise typer.BadParameter(
                "--helicopter-flight-distance-m is required for helicopter_longline role."
            )
        result = estimate_helicopter_longline_productivity(
            model=helicopter_model,
            flight_distance_m=helicopter_flight_distance_m,
            payload_m3=helicopter_payload_m3,
            load_factor=helicopter_load_factor,
            weight_to_volume_lb_per_m3=helicopter_weight_to_volume,
            additional_delay_minutes=helicopter_delay_minutes,
        )
        _render_helicopter_result(result)
        if helicopter_defaults_used and selected_system is not None:
            console.print(
                f"[dim]Applied helicopter defaults from harvest system '{selected_system.system_id}'.[/dim]"
            )
        _maybe_render_costs(show_costs, ProductivityMachineRole.HELICOPTER_LONGLINE.value)
        return

    else:
        rows = [
            ("Model", "labelle2019_volume"),
            ("Species", result.species),
            ("Treatment", result.treatment.replace("_", " ")),
            ("Recovered Volume (m³)", f"{result.volume_m3:.3f}"),
            (
                "Polynomial",
                f"{result.intercept:+.2f} + {result.linear:.2f}·V - {result.quadratic:.3f}·V^{result.exponent:.0f}",
            ),
            ("Sample Trees", str(result.sample_trees)),
            (
                "Delay-free Productivity (m³/PMH)",
                f"{result.delay_free_productivity_m3_per_pmh:.2f}",
            ),
            ("Delay Multiplier", f"{result.delay_multiplier:.3f}"),
            ("Productivity (m³/PMH)", f"{result.productivity_m3_per_pmh:.2f}"),
        ]
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]Labelle et al. (2019) hardwood volume regression (PMH₀); use --processor-delay-multiplier to apply utilisation when exporting beyond Bavaria.[/dim]"
        )

    missing: list[str] = []
    if avg_stem_size is None:
        missing.append("--avg-stem-size")
    if volume_per_ha is None:
        missing.append("--volume-per-ha")
    if stem_density is None:
        missing.append("--stem-density")
    if ground_slope is None:
        missing.append("--ground-slope")
    if missing:
        raise typer.BadParameter(
            f"{', '.join(missing)} required when --machine-role {ProductivityMachineRole.FELLER_BUNCHER.value}."
        )
    assert avg_stem_size is not None
    assert volume_per_ha is not None
    assert stem_density is not None
    assert ground_slope is not None

    try:
        result = estimate_productivity(
            avg_stem_size=avg_stem_size,
            volume_per_ha=volume_per_ha,
            stem_density=stem_density,
            ground_slope=ground_slope,
            model=model,
            validate_ranges=not allow_out_of_range,
        )
    except FHOPSValueError as exc:  # pragma: no cover - Typer surfaces error.
        raise typer.BadParameter(str(exc)) from exc

    rows = [
        ("Model", result.model.value),
        ("Average Stem Size (m³/stem)", f"{result.avg_stem_size:.3f}"),
        ("Volume per Hectare (m³/ha)", f"{result.volume_per_ha:.1f}"),
        ("Stem Density (trees/ha)", f"{result.stem_density:.1f}"),
        ("Ground Slope (%)", f"{result.ground_slope:.1f}"),
        ("Predicted Productivity (m³/PMH15)", f"{result.predicted_m3_per_pmh:.2f}"),
    ]
    _render_kv_table(
        "Lahrsen (2025) Feller-Buncher Productivity Estimate",
        rows,
    )
    if result.out_of_range:
        console.print("[red]Warning: inputs outside observed BC ranges:[/red]")
        for msg in result.out_of_range:
            console.print(f"  - {msg}")
    range_table = Table(title="Observed Ranges (Lahrsen 2025)")
    range_table.add_column("Variable", style="bold")
    range_table.add_column("Min")
    range_table.add_column("Max")
    for label, key in [
        ("Avg stem size (m³)", "avg_stem_size"),
        ("Volume per ha (m³)", "volume_per_ha"),
        ("Stem density (/ha)", "stem_density"),
        ("Ground slope (%)", "ground_slope"),
    ]:
        bounds = result.ranges[key]
        min_val = bounds.get("min")
        max_val = bounds.get("max")
        range_table.add_row(
            label,
            f"{min_val:.3f}" if min_val is not None else "—",
            f"{max_val:.3f}" if max_val is not None else "—",
        )
    console.print(range_table)
    console.print(
        "[dim]Coefficients sourced from Lahrsen, 2025 (UBC PhD) — whole-tree feller-buncher dataset.[/dim]"
    )
    _maybe_render_costs(show_costs, ProductivityMachineRole.FELLER_BUNCHER.value)
    return


@dataset_app.command("estimate-productivity-rv")
def estimate_productivity_rv_cmd(
    avg_stem_size: float = typer.Option(..., help="Mean stem size (m³)", min=0.0),
    avg_stem_size_sigma: float = typer.Option(0.05, help="Std dev for stem size (m³)", min=0.0),
    volume_per_ha: float = typer.Option(..., help="Mean volume per ha (m³)", min=0.0),
    volume_per_ha_sigma: float = typer.Option(25.0, help="Std dev volume per ha (m³)", min=0.0),
    stem_density: float = typer.Option(..., help="Mean stem density (/ha)", min=0.0),
    stem_density_sigma: float = typer.Option(50.0, help="Std dev stem density (/ha)", min=0.0),
    ground_slope: float = typer.Option(..., help="Mean slope (%)", min=0.0),
    ground_slope_sigma: float = typer.Option(2.0, help="Std dev slope (%)", min=0.0),
    model: LahrsenModel = typer.Option(LahrsenModel.DAILY, case_sensitive=False),
    method: str = typer.Option("auto", help="RV evaluation method: auto|pacal|monte-carlo"),
    samples: int = typer.Option(5000, help="Monte Carlo samples"),
):
    """Estimate expected productivity when inputs are random variates."""

    try:
        result = estimate_productivity_distribution(
            avg_stem_size_mu=avg_stem_size,
            avg_stem_size_sigma=avg_stem_size_sigma,
            volume_per_ha_mu=volume_per_ha,
            volume_per_ha_sigma=volume_per_ha_sigma,
            stem_density_mu=stem_density,
            stem_density_sigma=stem_density_sigma,
            ground_slope_mu=ground_slope,
            ground_slope_sigma=ground_slope_sigma,
            model=model,
            method=method.lower(),
            samples=samples,
        )
    except FHOPSValueError as exc:  # pragma: no cover
        raise typer.BadParameter(str(exc)) from exc

    rows = [
        ("Model", result.model.value),
        ("Method", result.method),
        ("Expected Productivity (m³/PMH15)", f"{result.expected_m3_per_pmh:.2f}"),
        ("Std Dev", f"{result.std_m3_per_pmh:.2f}" if result.std_m3_per_pmh is not None else "—"),
        ("Samples", str(result.sample_count) if result.sample_count else "—"),
        ("PaCal Used", "yes" if result.pacal_used else "no"),
    ]
    _render_kv_table("Lahrsen Productivity (RV)", rows)


@dataset_app.command("estimate-forwarder-productivity")
def estimate_forwarder_productivity_cmd(
    model: ForwarderBCModel = typer.Option(
        ForwarderBCModel.GHAFFARIYAN_SMALL,
        "--model",
        case_sensitive=False,
        help="Forwarder regression to evaluate.",
    ),
    extraction_distance: float | None = typer.Option(
        None,
        "--extraction-distance",
        min=0.0,
        help="Mean forwarding distance (m). Required for Ghaffariyan and ADV1N12 models.",
    ),
    slope_class: ALPACASlopeClass = typer.Option(
        ALPACASlopeClass.FLAT,
        "--slope-class",
        case_sensitive=False,
        help="Slope bin (<10, 10-20, >20 percent) from Ghaffariyan et al. 2019.",
    ),
    slope_factor: float | None = typer.Option(
        None,
        "--slope-factor",
        min=0.0,
        help="Custom multiplier overriding --slope-class for Ghaffariyan models.",
    ),
    volume_per_load: float | None = typer.Option(
        None,
        "--volume-per-load",
        min=0.0,
        help="Per-load volume (m³). Required for Kellogg models.",
    ),
    distance_out: float | None = typer.Option(
        None,
        "--distance-out",
        min=0.0,
        help="Distance from landing to the first loading point (m). Required for Kellogg models.",
    ),
    travel_in_unit: float | None = typer.Option(
        None,
        "--travel-in-unit",
        min=0.0,
        help="Distance travelled while loading within the unit (m). Required for Kellogg models.",
    ),
    distance_in: float | None = typer.Option(
        None,
        "--distance-in",
        min=0.0,
        help="Distance from final loading point back to the landing (m). Required for Kellogg models.",
    ),
    payload_per_trip: float | None = typer.Option(
        None,
        "--payload-per-trip",
        min=0.0,
        help="Payload per forwarder trip (m³). Required for ADV6N10 model.",
    ),
    mean_log_length: float | None = typer.Option(
        None,
        "--mean-log-length",
        min=0.0,
        help="Mean log length (m). Required for ADV6N10 model.",
    ),
    travel_speed: float | None = typer.Option(
        None,
        "--travel-speed",
        min=0.0,
        help="Forwarder travel speed (m/min). Required for ADV6N10 model.",
    ),
    trail_length: float | None = typer.Option(
        None,
        "--trail-length",
        min=0.0,
        help="Trail length from landing to loading point (m). Required for ADV6N10 model.",
    ),
    products_per_trail: float | None = typer.Option(
        None,
        "--products-per-trail",
        min=0.0,
        help="Number of products separated on the trail (ADV6N10).",
    ),
    mean_extraction_distance: float | None = typer.Option(
        None,
        "--mean-extraction-distance",
        min=0.0,
        help="Mean extraction distance (m) for Eriksson & Lindroos forwarder models.",
    ),
    mean_stem_size: float | None = typer.Option(
        None,
        "--mean-stem-size",
        min=0.0,
        help="Mean harvested stem size (m³) for Eriksson & Lindroos models.",
    ),
    load_capacity: float | None = typer.Option(
        None,
        "--load-capacity",
        min=0.0,
        help="Load capacity/payload (m³) for Eriksson & Lindroos models.",
    ),
    harvested_trees_per_ha: float | None = typer.Option(
        None,
        "--harvested-trees-per-ha",
        min=0.0,
        help="Harvested trees per hectare (required for Laitila & Väätäinen brushwood model).",
    ),
    avg_tree_volume_dm3: float | None = typer.Option(
        None,
        "--avg-tree-volume-dm3",
        min=0.0,
        help="Average harvested tree volume (dm³) for the brushwood harwarder.",
    ),
    forwarding_distance: float | None = typer.Option(
        None,
        "--forwarding-distance",
        min=0.0,
        help="Mean forwarding distance (m) for the brushwood harwarder.",
    ),
    harwarder_payload: float | None = typer.Option(
        None,
        "--harwarder-payload",
        min=0.0,
        help="Payload per harwarder trip (m³). Defaults to 7.1 m³ if omitted.",
    ),
    grapple_load_unloading: float | None = typer.Option(
        None,
        "--grapple-load-unloading",
        min=0.0,
        help="Grapple load during unloading (m³). Defaults to 0.29 m³ if omitted.",
    ),
):
    """Estimate forwarder productivity (m³/PMH0) for thinning operations."""

    result = _evaluate_forwarder_result(
        model=model,
        extraction_distance=extraction_distance,
        slope_class=slope_class,
        slope_factor=slope_factor,
        volume_per_load=volume_per_load,
        distance_out=distance_out,
        travel_in_unit=travel_in_unit,
        distance_in=distance_in,
        payload_per_trip=payload_per_trip,
        mean_log_length=mean_log_length,
        travel_speed=travel_speed,
        trail_length=trail_length,
        products_per_trail=products_per_trail,
        mean_extraction_distance=mean_extraction_distance,
        mean_stem_size=mean_stem_size,
        load_capacity=load_capacity,
        harvested_trees_per_ha=harvested_trees_per_ha,
        avg_tree_volume_dm3=avg_tree_volume_dm3,
        forwarding_distance=forwarding_distance,
        harwarder_payload=harwarder_payload,
        grapple_load_unloading=grapple_load_unloading,
    )
    _render_forwarder_result(result)


@dataset_app.command("productivity-ranges")
def show_productivity_ranges():
    """Display Lahrsen (2025) observed parameter ranges."""

    data = load_lahrsen_ranges()
    for section in ("daily", "cutblock"):
        table = Table(title=f"Lahrsen 2025 {section.title()} Ranges")
        table.add_column("Variable", style="bold")
        table.add_column("Min")
        table.add_column("Max")
        table.add_column("Mean")
        table.add_column("Median")
        entries = [
            ("productivity_m3_per_pmh15", "Productivity (m³/PMH15)"),
            ("avg_stem_size_m3", "Avg stem size (m³)"),
            ("volume_per_ha_m3", "Volume per ha (m³)"),
            ("stem_density_per_ha", "Stem density (/ha)"),
            ("ground_slope_percent", "Ground slope (%)"),
            ("block_size_ha", "Block size (ha)"),
        ]
        for key, label in entries:
            if key not in data[section]:
                continue
            entry = data[section][key]
            table.add_row(
                label,
                f"{entry.get('min', float('nan')):.3f}" if "min" in entry else "—",
                f"{entry.get('max', float('nan')):.3f}" if "max" in entry else "—",
                f"{entry.get('mean', float('nan')):.3f}" if "mean" in entry else "—",
                f"{entry.get('median', float('nan')):.3f}" if "median" in entry else "—",
            )
        console.print(table)
    console.print("[dim]Data from Lahrsen (2025) – see thesis for study context.[/dim]")


__all__ = ["dataset_app"]


@dataset_app.command("estimate-cost")
def estimate_cost_cmd(
    rental_rate: float | None = typer.Option(None, help="Rental rate ($/SMH)", min=0.0),
    machine_role: str | None = typer.Option(
        None,
        "--machine-role",
        "-r",
        help="Load rental rate components from the FHOPS machine-rate table.",
    ),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "-d",
        help="Dataset name or scenario path to pull machine defaults (role, repair usage hours, $/SMH).",
    ),
    machine_id: str | None = typer.Option(
        None, "--machine", "-m", help="Machine ID within --dataset used to auto-fill inputs."
    ),
    include_repair: bool = typer.Option(
        True,
        "--include-repair/--exclude-repair",
        help="Include FPInnovations repair/maintenance allowance when deriving --machine-role rates.",
    ),
    owning_rate: float | None = typer.Option(
        None,
        "--owning-rate",
        min=0.0,
        help="Override owning component ($/SMH) when --machine-role is supplied.",
    ),
    operating_rate: float | None = typer.Option(
        None,
        "--operating-rate",
        min=0.0,
        help="Override operating component ($/SMH) when --machine-role is supplied.",
    ),
    repair_rate: float | None = typer.Option(
        None,
        "--repair-rate",
        min=0.0,
        help="Override repair/maintenance component ($/SMH). Requires --machine-role.",
    ),
    usage_hours: int | None = typer.Option(
        None,
        "--usage-hours",
        min=0,
        help="Approximate cumulative usage hours when applying FPInnovations repair multipliers (nearest 5k bucket).",
    ),
    utilisation: float = typer.Option(0.9, help="Utilisation coefficient (0-1)", min=0.0, max=1.0),
    productivity: float | None = typer.Option(None, help="Direct productivity (m³/PMH15)."),
    use_rv: bool = typer.Option(False, help="Treat stand inputs as random variates with stddevs."),
    avg_stem_size: float | None = typer.Option(None, help="Avg stem size (m³)"),
    avg_stem_size_sigma: float = typer.Option(0.05, help="Std dev stem size (m³)", min=0.0),
    volume_per_ha: float | None = typer.Option(None, help="Volume per ha (m³)"),
    volume_per_ha_sigma: float = typer.Option(25.0, help="Std dev volume/ha", min=0.0),
    stem_density: float | None = typer.Option(None, help="Stem density (/ha)"),
    stem_density_sigma: float = typer.Option(50.0, help="Std dev stem density", min=0.0),
    ground_slope: float | None = typer.Option(None, help="Ground slope (%)"),
    ground_slope_sigma: float = typer.Option(2.0, help="Std dev slope", min=0.0),
    model: LahrsenModel = typer.Option(LahrsenModel.DAILY, case_sensitive=False),
    samples: int = typer.Option(5000, help="Monte Carlo samples (RV mode)", min=1),
    road_machine: str | None = typer.Option(
        None,
        "--road-machine",
        help="Optional TR-28 road-building machine slug/name to append subgrade costs (see `fhops dataset tr28-subgrade`).",
    ),
    road_job_id: str | None = typer.Option(
        None,
        "--road-job-id",
        help="Scenario road_construction entry to use when --dataset is supplied.",
    ),
    road_length_m: float | None = typer.Option(
        None,
        "--road-length-m",
        min=1.0,
        help="Road/subgrade length (m) to pair with --road-machine when estimating additional costs.",
    ),
    road_include_mobilisation: bool | None = typer.Option(
        None,
        "--road-include-mobilisation/--road-exclude-mobilisation",
        help="Include the TR-28 movement cost in the add-on road estimate.",
    ),
    road_soil_profile: list[str] | None = typer.Option(
        None,
        "--road-soil-profile",
        help="Soil profile ID (e.g., fnrb3_d7h). Repeat flag to include multiple profiles.",
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append machine-cost inputs/output (including road add-ons) to a JSONL telemetry file.",
    ),
):
    """Estimate $/m³ given rental rate, utilisation, and (optionally) Lahrsen stand inputs."""

    overrides = [owning_rate, operating_rate, repair_rate]
    if machine_role is None:
        if any(value is not None for value in overrides):
            raise typer.BadParameter(
                "--owning-rate/--operating-rate/--repair-rate require --machine-role."
            )
    else:
        if rental_rate is not None:
            raise typer.BadParameter("Use either --rental-rate or --machine-role (not both).")

    dataset_name: str | None = None
    dataset_path: Path | None = None
    scenario: Scenario | None = None
    scenario_machine: Machine | None = None
    scenario_road_entries: list[RoadConstruction] = []
    selected_road_entry: RoadConstruction | None = None
    if dataset is not None or machine_id is not None:
        if dataset is None or machine_id is None:
            raise typer.BadParameter("--dataset and --machine must be provided together.")
        dataset_name, scenario, dataset_path = _ensure_dataset(dataset, interactive=False)
        scenario_machine = next((m for m in scenario.machines if m.id == machine_id), None)
        if scenario_machine is None:
            raise typer.BadParameter(
                f"Machine '{machine_id}' not found in dataset '{dataset_name}'. "
                f"Options: {', '.join(sorted(machine.id for machine in scenario.machines))}"
            )
        if machine_role is None:
            if scenario_machine.role is None:
                raise typer.BadParameter(
                    f"Machine '{machine_id}' has no role assigned; specify --machine-role explicitly."
                )
            machine_role = scenario_machine.role
        if usage_hours is None and scenario_machine.repair_usage_hours is not None:
            usage_hours = scenario_machine.repair_usage_hours
        if rental_rate is None and machine_role is None and scenario_machine.operating_cost > 0:
            rental_rate = float(scenario_machine.operating_cost)
        scenario_road_entries = list(scenario.road_construction or [])

    if road_job_id and scenario is None:
        raise typer.BadParameter("--road-job-id requires --dataset/--machine.")
    if road_job_id:
        selected_road_entry = next(
            (entry for entry in scenario_road_entries if entry.id == road_job_id),
            None,
        )
        if selected_road_entry is None:
            options = ", ".join(entry.id for entry in scenario_road_entries) or "none"
            raise typer.BadParameter(
                f"Unknown road_construction id '{road_job_id}'. Available: {options}"
            )
    elif (
        not road_machine
        and road_length_m is None
        and scenario_road_entries
        and scenario is not None
    ):
        if len(scenario_road_entries) == 1:
            selected_road_entry = scenario_road_entries[0]
        else:
            options = ", ".join(entry.id for entry in scenario_road_entries)
            raise typer.BadParameter(
                f"Scenario '{scenario.name}' has multiple road_construction entries "
                f"({options}). Select one via --road-job-id or provide --road-machine/--road-length-m."
            )

    if selected_road_entry:
        if not road_machine:
            road_machine = selected_road_entry.machine_slug
        if road_length_m is None:
            road_length_m = selected_road_entry.road_length_m
        if road_include_mobilisation is None:
            road_include_mobilisation = selected_road_entry.include_mobilisation

    machine_entry: MachineRate | None = None
    rental_breakdown: dict[str, float] | None = None
    repair_reference_hours: int | None = None
    repair_usage_bucket: tuple[int, float] | None = None
    road_cost_estimate: TR28CostEstimate | None = None
    road_soil_profiles: list[SoilProfile] = []
    resolved_road_include: bool | None = None

    if machine_role is not None:
        machine_entry = _resolve_machine_rate(machine_role)
        composed = compose_default_rental_rate_for_role(
            machine_role,
            include_repair_maintenance=include_repair,
            ownership_override=owning_rate,
            operating_override=operating_rate,
            repair_override=repair_rate,
            usage_hours=usage_hours if include_repair else None,
        )
        if composed is None:
            raise typer.BadParameter(f"No default rate available for role '{machine_role}'.")
        rental_rate, rental_breakdown = composed
        if include_repair and machine_entry.repair_maintenance_cost_per_smh is not None:
            repair_reference_hours = machine_entry.repair_maintenance_reference_hours
            if usage_hours is not None:
                repair_usage_bucket = select_usage_class_multiplier(machine_entry, usage_hours)

    if rental_rate is None:
        raise typer.BadParameter(
            "Provide either --rental-rate or --machine-role (or use --dataset/--machine)."
        )

    if road_machine is not None or road_length_m is not None:
        if not road_machine or road_length_m is None:
            raise typer.BadParameter("--road-machine and --road-length-m must be provided together.")
        resolved_machine = _resolve_tr28_machine(road_machine)
        if resolved_machine is None:
            raise typer.BadParameter(
                f"Unknown road machine '{road_machine}'. Choose from: {', '.join(_tr28_machine_slugs())}"
            )
        include_flag = (
            road_include_mobilisation
            if road_include_mobilisation is not None
            else selected_road_entry.include_mobilisation
            if selected_road_entry
            else True
        )
        resolved_road_include = include_flag
        try:
            road_cost_estimate = estimate_tr28_road_cost(
                resolved_machine,
                road_length_m=road_length_m,
                include_mobilisation=include_flag,
            )
        except ValueError as exc:  # pragma: no cover - Typer handles messaging
            raise typer.BadParameter(str(exc)) from exc
        profile_ids = list(road_soil_profile or [])
        if not profile_ids and selected_road_entry and selected_road_entry.soil_profile_ids:
            profile_ids = list(selected_road_entry.soil_profile_ids)
        if profile_ids:
            load_soil_profiles()  # populate cache for clearer error below
        for profile_id in profile_ids:
            try:
                road_soil_profiles.append(get_soil_profile(profile_id))
            except KeyError as exc:
                raise typer.BadParameter(str(exc)) from exc

    prod_info: dict[str, object]
    if productivity is None:
        required = [avg_stem_size, volume_per_ha, stem_density, ground_slope]
        if any(value is None for value in required):
            raise typer.BadParameter(
                "Provide either --productivity or all stand metrics (avg stem size, volume/ha, stem density, slope)."
            )
        assert avg_stem_size is not None
        assert volume_per_ha is not None
        assert stem_density is not None
        assert ground_slope is not None
        if use_rv:
            cost, prod_distribution = estimate_unit_cost_from_distribution(
                rental_rate_smh=rental_rate,
                utilisation=utilisation,
                avg_stem_size_mu=avg_stem_size,
                avg_stem_size_sigma=avg_stem_size_sigma,
                volume_per_ha_mu=volume_per_ha,
                volume_per_ha_sigma=volume_per_ha_sigma,
                stem_density_mu=stem_density,
                stem_density_sigma=stem_density_sigma,
                ground_slope_mu=ground_slope,
                ground_slope_sigma=ground_slope_sigma,
                model=model,
                samples=samples,
                rental_rate_breakdown=rental_breakdown,
            )
            productivity = prod_distribution.expected_m3_per_pmh
            prod_info = {
                "method": prod_distribution.method,
                "productivity_mean": prod_distribution.expected_m3_per_pmh,
                "productivity_std": prod_distribution.std_m3_per_pmh,
                "samples": prod_distribution.sample_count,
            }
        else:
            cost, prod_point = estimate_unit_cost_from_stand(
                rental_rate_smh=rental_rate,
                utilisation=utilisation,
                avg_stem_size=avg_stem_size,
                volume_per_ha=volume_per_ha,
                stem_density=stem_density,
                ground_slope=ground_slope,
                model=model,
                rental_rate_breakdown=rental_breakdown,
            )
            prod_info = {
                "method": "deterministic",
                "productivity_mean": prod_point.predicted_m3_per_pmh,
                "productivity_std": None,
                "samples": 0,
            }
    else:
        cost = MachineCostEstimate(
            rental_rate_smh=rental_rate,
            utilisation=utilisation,
            productivity_m3_per_pmh=productivity,
            cost_per_m3=rental_rate / (utilisation * productivity),
            method="direct",
            rental_rate_breakdown=rental_breakdown,
        )
        prod_info = {
            "method": "direct",
            "productivity_mean": productivity,
            "productivity_std": None,
            "samples": 0,
        }

    telemetry_inputs: dict[str, object | None] = {
        "dataset": dataset_name,
        "scenario_name": scenario.name if scenario else None,
        "machine_id": scenario_machine.id if scenario_machine else None,
        "machine_role": machine_role,
        "machine_role_source": "dataset" if dataset_name else "cli",
        "usage_hours": usage_hours,
        "include_repair": include_repair,
        "utilisation": utilisation,
        "productivity_mode": prod_info["method"],
        "productivity_direct": productivity if prod_info["method"] == "direct" else None,
        "avg_stem_size_m3": avg_stem_size,
        "volume_per_ha_m3": volume_per_ha,
        "stem_density_per_ha": stem_density,
        "ground_slope_percent": ground_slope,
        "use_random_variates": use_rv,
        "samples": samples if use_rv else 0,
        "road_job_id": selected_road_entry.id if selected_road_entry else None,
        "road_machine": road_machine,
        "road_length_m": road_length_m,
        "road_include_mobilisation": resolved_road_include,
        "road_soil_profile_ids": [profile.id for profile in road_soil_profiles] or None,
    }
    telemetry_outputs: dict[str, object | None] = {
        "cost_per_m3": cost.cost_per_m3,
        "rental_rate_smh": cost.rental_rate_smh,
        "utilisation": cost.utilisation,
        "productivity_m3_per_pmh": cost.productivity_m3_per_pmh,
        "rental_breakdown": rental_breakdown,
        "productivity_method": prod_info["method"],
        "productivity_std": prod_info["productivity_std"],
        "samples": prod_info["samples"],
    }
    if road_cost_estimate:
        telemetry_outputs["road"] = {
            "road_job_id": selected_road_entry.id if selected_road_entry else None,
            "machine_slug": road_cost_estimate.machine.slug,
            "machine_name": road_cost_estimate.machine.machine_name,
            "road_length_m": road_cost_estimate.road_length_m,
            "include_mobilisation": road_cost_estimate.mobilisation_included,
            "unit_cost_target_cad_per_m": road_cost_estimate.unit_cost_target_cad_per_m,
            "total_cost_target_cad": road_cost_estimate.total_with_mobilisation_target_cad,
            "base_year": road_cost_estimate.base_year,
            "target_year": road_cost_estimate.target_year,
            "soil_profiles": [
                {"id": profile.id, "source": profile.source} for profile in road_soil_profiles
            ]
            or None,
        }
    else:
        telemetry_outputs["road"] = None

    rows: list[tuple[str, str]] = []
    if dataset_name is not None:
        rows.append(("Dataset", dataset_name))
        if dataset_path is not None:
            rows.append(("Scenario Path", str(dataset_path)))
    if machine_entry is not None:
        rows.extend(
            [
                ("Machine Role", machine_entry.role),
                ("Machine", machine_entry.machine_name),
                ("Source", machine_entry.source),
            ]
        )
    if scenario_machine is not None:
        rows.append(("Scenario Machine", scenario_machine.id))
        rows.append(
            (
                "Repair Usage Hours (dataset)",
                f"{scenario_machine.repair_usage_hours:,}"
                if scenario_machine.repair_usage_hours is not None
                else "—",
            )
        )
    if rental_breakdown:
        rows.append(("Owning Cost ($/SMH)", f"{rental_breakdown['ownership']:.2f}"))
        rows.append(("Operating Cost ($/SMH)", f"{rental_breakdown['operating']:.2f}"))
        repair_value = rental_breakdown.get("repair_maintenance")
        if repair_value is not None:
            rows.append(("Repair/Maint. ($/SMH)", f"{repair_value:.2f}"))
            if repair_usage_bucket is not None:
                bucket_hours, multiplier = repair_usage_bucket
                rows.append(
                    (
                        "Repair Usage Bucket",
                        f"{bucket_hours:,} h (multiplier {multiplier:.3f})",
                    )
                )
    rows.extend(
        [
            ("Rental Rate ($/SMH)", f"{cost.rental_rate_smh:.2f}"),
            ("Utilisation", f"{cost.utilisation:.3f}"),
            ("Productivity (m³/PMH15)", f"{cost.productivity_m3_per_pmh:.2f}"),
            ("Cost ($/m³)", f"{cost.cost_per_m3:.2f}"),
            ("Productivity Method", str(prod_info["method"])),
        ]
    )
    if prod_info["productivity_std"] is not None:
        rows.append(("Productivity Std", f"{prod_info['productivity_std']:.2f}"))
    rows.append(("Samples", str(prod_info["samples"])))
    _render_kv_table("Machine Cost Estimate", rows)
    if machine_entry and include_repair:
        if repair_usage_bucket is not None and usage_hours is not None:
            bucket_hours, multiplier = repair_usage_bucket
            console.print(
                f"[dim]Repair/maintenance allowance derived from Advantage Vol. 4 No. 23 (closest usage class {bucket_hours / 1000:.0f}×1000 h, multiplier {multiplier:.3f} for requested {usage_hours:,} h).[/dim]"
            )
        elif repair_reference_hours:
            console.print(
                f"[dim]Repair/maintenance allowance derived from Advantage Vol. 4 No. 23 (usage class {repair_reference_hours / 1000:.0f}×1000 h).[/dim]"
            )
    if road_cost_estimate:
        console.print()
        _render_tr28_road_cost(road_cost_estimate, soil_profiles=road_soil_profiles)
        if road_soil_profiles:
            sources = ", ".join(sorted({profile.source for profile in road_soil_profiles}))
            console.print(
                f"[dim]Soil guidance sourced from {sources}. Profiles recorded for future automation.[/dim]"
            )
        else:
            console.print(
                "[yellow]Soil-protection reminder:[/yellow] FNRB3’s Cat D7H vs. D7G trial showed that wider undercarriages cut ground pressure "
                "by 20–30% while boosting stripping/ditching productivity; ADV4N7 cautions that more than ~20% compacted area on moist soils "
                "requires mitigation (slash mats, limited traffic)."
            )

    if telemetry_log:
        telemetry_payload: dict[str, object] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "command": "dataset estimate-cost",
            "inputs": telemetry_inputs,
            "outputs": telemetry_outputs,
        }
        if dataset_path is not None:
            telemetry_payload["scenario_path"] = str(dataset_path)
        append_jsonl(telemetry_log, telemetry_payload)


@dataset_app.command("appendix5-stands")
def list_appendix5_stands(
    author_filter: str | None = typer.Option(None, "--author", help="Filter by author substring."),
    limit: int = typer.Option(20, "--limit", min=1, max=200, help="Max rows to display."),
):
    """Show stand metadata extracted from Arnvik (2024) Appendix 5."""

    entries = load_appendix5_stands()
    filtered = [
        entry
        for entry in entries
        if not author_filter or author_filter.lower() in entry.author.lower()
    ]
    table = Table(title="Appendix 5 Stand Profiles")
    table.add_column("Author", style="bold")
    table.add_column("Species")
    table.add_column("Age (y)")
    table.add_column("Volume (m³)")
    table.add_column("DBH (cm)")
    table.add_column("Slope (%)")
    table.add_column("Ground Condition")
    table.add_column("Roughness")
    table.add_column("Operators")
    for entry in filtered[:limit]:
        slope = entry.average_slope_percent
        slope_text = f"{slope:.1f}" if slope is not None else entry.slope_text or "—"
        age_text = (
            f"{entry.stand_age_years:.1f}"
            if entry.stand_age_years is not None
            else entry.stand_age_text or "—"
        )
        volume_text = (
            f"{entry.stem_volume_m3:.3f}"
            if entry.stem_volume_m3 is not None
            else entry.stem_volume_text or "—"
        )
        dbh_text = f"{entry.dbh_cm:.1f}" if entry.dbh_cm is not None else entry.dbh_text or "—"
        operators_text = str(entry.num_operators) if entry.num_operators is not None else "—"
        table.add_row(
            entry.author,
            entry.tree_species or "—",
            age_text,
            volume_text,
            dbh_text,
            slope_text,
            entry.ground_condition or "—",
            entry.ground_roughness or "—",
            operators_text,
        )
    if not filtered:
        console.print("No matching profiles.")
        return
    console.print(table)


def _render_tn98_table(records: Sequence[TN98DiameterRecord]) -> None:
    table = Table(title="TN98 per-diameter observations")
    table.add_column("DBH (cm)", justify="right")
    table.add_column("Trees", justify="right")
    table.add_column("Cut (min)", justify="right")
    table.add_column("Limb/Buck (min)", justify="right")
    table.add_column("Volume (m³)", justify="right")
    table.add_column("Cost/tree ($)", justify="right")
    table.add_column("Cost/m³ ($)", justify="right")
    for record in records:
        table.add_row(
            f"{record.dbh_cm:.1f}",
            str(record.tree_count) if record.tree_count is not None else "—",
            f"{record.cut_minutes:.2f}" if record.cut_minutes is not None else "—",
            f"{record.limb_buck_minutes:.2f}" if record.limb_buck_minutes is not None else "—",
            f"{record.volume_m3:.2f}" if record.volume_m3 is not None else "—",
            f"{record.cost_per_tree_cad:.2f}" if record.cost_per_tree_cad is not None else "—",
            f"{record.cost_per_m3_cad:.2f}" if record.cost_per_m3_cad is not None else "—",
        )
    console.print(table)


@dataset_app.command("tn82-ft180")
def tn82_ft180_cmd(
    show_notes: bool = typer.Option(False, "--show-notes", help="Display the system-level notes.")
):
    """Summarize the TN82 FMC FT-180 vs. John Deere 550 productivity datasets."""

    dataset = load_tn82_dataset()
    site_lookup = {site["id"]: site for site in dataset.sites}
    for machine in dataset.machines:
        title = f"{machine.name} ({machine.machine_type})"
        table = Table(title=title, header_style="bold cyan", expand=True)
        table.add_column("Site", style="bold")
        table.add_column("Description")
        table.add_column("Prod. m³/PMH", justify="right")
        table.add_column("Trees/PMH", justify="right")
        table.add_column("Turns/PMH", justify="right")
        table.add_column("m³/8h shift", justify="right")
        table.add_column("Trees/shift", justify="right")
        table.add_column("Turns/shift", justify="right")
        table.add_column("Prod. hrs (%)", justify="right")
        table.add_column("Avail. (%)", justify="right")
        for area in machine.areas:
            site = site_lookup.get(area.site_id, {})
            desc = site.get("description", area.site_id.replace("_", " "))
            table.add_row(
                area.site_id.replace("_", " "),
                desc,
                f"{area.volume_m3_per_pmh:.2f}",
                f"{area.trees_per_pmh:.1f}",
                f"{area.turns_per_pmh:.1f}",
                f"{area.volume_m3_per_shift:.1f}",
                f"{area.trees_per_shift:.0f}",
                f"{area.turns_per_shift:.1f}",
                f"{area.productive_hours_percent:.1f}" if area.productive_hours_percent is not None else "—",
                f"{area.availability_percent:.1f}" if area.availability_percent is not None else "—",
            )
        console.print(table)
        if machine.notes:
            console.print(f"[dim]{machine.notes}[/dim]")
    if show_notes and dataset.system_notes:
        console.print("[bold]Study Notes[/bold]")
        for note in dataset.system_notes:
            console.print(f"- {note}")
    if dataset.source:
        console.print(
            f"[dim]Source: {dataset.source.get('title', 'TN-82')} (FERIC TN-82, Columbia Valley FMC FT-180 vs. JD 550 study).[/dim]"
        )


@dataset_app.command("adv6n25-helicopters")
def adv6n25_helicopters_cmd(
    show_alternatives: bool = typer.Option(
        False, "--show-alternatives", help="Display the alternative scenario cost table."
    )
) -> None:
    """Summarize ADV6N25 dual-helicopter productivity and costs."""

    dataset = load_adv6n25_dataset()
    site_desc = dataset.site.get("location", "Unknown site")
    console.print(f"[bold]Site:[/bold] {site_desc}, {dataset.site.get('cutblock_area_ha')} ha")
    table = Table(title="Helicopter yarding summary", header_style="bold cyan", expand=True)
    table.add_column("Helicopter", style="bold")
    table.add_column("Payload (lb)", justify="right")
    table.add_column("m³/shift", justify="right")
    table.add_column("m³/flight-hour", justify="right")
    table.add_column("Volume (m³)", justify="right")
    table.add_column("Cost $/m³", justify="right")
    table.add_column("Cost $/flight-hour", justify="right")
    table.add_column("Yarding shifts", justify="right")
    for heli in dataset.helicopters:
        display_name = heli.model.replace("_", " ").title()
        table.add_row(
            display_name,
            f"{heli.rated_payload_lb:.0f}" if heli.rated_payload_lb else "—",
            f"{heli.productivity_m3_per_shift:.0f}" if heli.productivity_m3_per_shift else "—",
            f"{heli.productivity_m3_per_flight_hour:.1f}"
            if heli.productivity_m3_per_flight_hour
            else "—",
            f"{heli.volume_logged_m3:.0f}" if heli.volume_logged_m3 else "—",
            f"{heli.cost_per_m3_cad:.2f}" if heli.cost_per_m3_cad else "—",
            f"{heli.hourly_cost_cad:.0f}" if heli.hourly_cost_cad else "—",
            f"{heli.yarding_shifts:.0f}" if heli.yarding_shifts else "—",
        )
    console.print(table)
    total_cost = dataset.total.get("cost_per_m3_cad")
    if total_cost is not None:
        console.print(f"[bold]Total cost:[/bold] {total_cost:.2f} $/m³")
    if show_alternatives and dataset.alternative_scenarios:
        alt_table = Table(
            title="Alternative scenarios (estimated)",
            header_style="bold",
            expand=True,
        )
        alt_table.add_column("Scenario")
        alt_table.add_column("Cost ($/m³)", justify="right")
        alt_table.add_column("Δ vs. actual ($/m³)", justify="right")
        for item in dataset.alternative_scenarios:
            alt_table.add_row(
                item.get("scenario", "alt"),
                f"{item.get('estimated_cost_per_m3_cad', 0.0):.2f}",
                f"{item.get('delta_vs_actual_cad', 0.0):+.2f}",
            )
        console.print(alt_table)
    if dataset.source:
        console.print(
            "[dim]Source: "
            f"{dataset.source.get('title', 'ADV6N25')} (Lama + K-1200 K-Max light-lift helicopter case study).[/dim]"
        )


@dataset_app.command("tn98-handfalling")
def tn98_handfalling_cmd(
    dbh_cm: float = typer.Option(
        32.5,
        "--dbh-cm",
        min=5.0,
        help="Diameter at breast height midpoint to evaluate (cm).",
    ),
    species: str = typer.Option(
        "all_species",
        "--species",
        case_sensitive=False,
        help=f"Species bucket ({', '.join(_tn98_species_choices())}).",
    ),
    show_table: bool = typer.Option(
        False, "--show-table", help="Display the underlying TN98 per-diameter rows."
    ),
):
    """Estimate handfalling cutting time & cost using TN-98 regressions."""

    dataset = load_tn98_dataset()
    species_key = species.lower()
    if species_key not in _tn98_species_choices():
        raise typer.BadParameter(
            f"Unsupported species '{species}'. Choose from {', '.join(_tn98_species_choices())}."
        )
    regression = dataset.regressions.get(species_key) or dataset.regressions.get(
        "all_species"
    )
    if regression is None:
        raise typer.BadParameter("TN98 regressions missing for the requested species.")

    predicted_cut = max(
        0.0, regression.intercept_minutes + regression.slope_minutes_per_cm * dbh_cm
    )
    records = dataset.per_diameter_class.get(species_key) or dataset.per_diameter_class.get(
        "all_species", ()
    )
    limb_minutes = _interpolate_tn98_value(records, dbh_cm, "limb_buck_minutes") or 0.0
    cost_per_tree = _interpolate_tn98_value(records, dbh_cm, "cost_per_tree_cad")
    cost_per_m3 = _interpolate_tn98_value(records, dbh_cm, "cost_per_m3_cad")
    volume_m3 = _interpolate_tn98_value(records, dbh_cm, "volume_m3")
    fixed_time = dataset.time_distribution.get("fixed_time_minutes_per_tree") or 0.0
    total_minutes = predicted_cut + limb_minutes + fixed_time
    nearest_record = _closest_tn98_record(records, dbh_cm)

    rows = [
        ("Species", species_key.replace("_", " ")),
        ("DBH midpoint (cm)", f"{dbh_cm:.1f}"),
        ("Cutting time (min)", f"{predicted_cut:.2f}"),
        ("Limb/buck time (min)", f"{limb_minutes:.2f}"),
        ("Fixed delay (min)", f"{fixed_time:.2f}"),
        ("Estimated total minutes", f"{total_minutes:.2f}"),
    ]
    if cost_per_tree is not None:
        rows.append(("Cost per tree (CAD)", f"{cost_per_tree:.2f}"))
    if cost_per_m3 is not None:
        rows.append(("Cost per m³ (CAD)", f"{cost_per_m3:.2f}"))
    if volume_m3 is not None:
        rows.append(("Interpolated volume (m³/tree)", f"{volume_m3:.2f}"))
    if nearest_record:
        rows.append(("Nearest observed DBH", f"{nearest_record.dbh_cm:.1f} cm"))
        if nearest_record.tree_count is not None:
            rows.append(("Observed trees in class", str(nearest_record.tree_count)))
    _render_kv_table("TN98 handfalling estimate", rows)
    console.print(
        "[dim]Source: FERIC TN-98 (Peterson 1987). Labour base CAD 1985 with +35% fringe; "
        "costs exclude travel/supervision.[/dim]"
    )
    if show_table:
        if records:
            _render_tn98_table(records)
        else:
            console.print(
                "[yellow]No per-diameter table is available for this species in TN-98.[/yellow]"
            )


_TR28_SORT_FIELDS: tuple[str, ...] = ("case", "unit_cost", "stations", "roughness")


@dataset_app.command("tr28-subgrade")
def list_tr28_subgrade_machines(
    role_filter: str | None = typer.Option(
        None, "--role", help="Filter by machine role substring (e.g., bulldozer)."
    ),
    sort_by: str = typer.Option(
        "case",
        "--sort-by",
        help="Sort output by case id, unit_cost, stations, or roughness indicator.",
    ),
    limit: int = typer.Option(10, "--limit", min=1, max=20, help="Maximum rows to display."),
):
    """Summarize FERIC TR-28 subgrade construction machines."""

    machines = load_tr28_machines()
    filtered = [
        machine
        for machine in machines
        if not role_filter or role_filter.lower() in machine.role.lower()
    ]
    if not filtered:
        console.print("No TR-28 machines matched the filters.")
        return

    sort_key = sort_by.lower()
    if sort_key not in _TR28_SORT_FIELDS:
        raise typer.BadParameter(
            f"Invalid sort field '{sort_by}'. Choose from {', '.join(_TR28_SORT_FIELDS)}."
        )

    def _sort_key(machine: TR28Machine):
        match sort_key:
            case "unit_cost":
                return machine.unit_cost_cad_per_meter or float("inf")
            case "stations":
                return -(machine.stations_per_shift or float("-inf"))
            case "roughness":
                return machine.roughness_m2_per_100m or float("inf")
            case _:
                return machine.case_id or 0

    sorted_rows = sorted(filtered, key=_sort_key)
    limited_rows = sorted_rows[:limit]
    table = Table(title="TR-28 Subgrade Machine Summary")
    table.add_column("Case", justify="right", style="bold")
    table.add_column("Machine")
    table.add_column("Role")
    table.add_column("Unit Cost ($/m)", justify="right")
    table.add_column("Station Cost ($)", justify="right")
    table.add_column("Stations/Shift", justify="right")
    table.add_column("m/Shift", justify="right")
    table.add_column("Hourly Rate ($/h)", justify="right")
    table.add_column("Move Cost ($)", justify="right")
    table.add_column("Roughness (m²/100 m)", justify="right")

    def _fmt(value: float | None, precision: int = 2) -> str:
        return f"{value:.{precision}f}" if value is not None else "—"

    for machine in limited_rows:
        table.add_row(
            str(machine.case_id or "—"),
            machine.machine_name,
            machine.role or "—",
            _fmt(machine.unit_cost_cad_per_meter),
            _fmt(machine.station_cost_cad),
            _fmt(machine.stations_per_shift),
            _fmt(machine.meters_per_shift),
            _fmt(machine.machine_hourly_rate_cad),
            _fmt(machine.movement_total_cost_cad),
            _fmt(machine.roughness_m2_per_100m),
        )
    console.print(table)
    source = get_tr28_source_metadata()
    title = source.get("title", "FERIC TR-28")
    year = source.get("publication_date", "1978")
    currency = source.get("currency", "CAD")
    console.print(
        f"[dim]Source: {title} ({year}, {source.get('publisher', 'FPInnovations/FERIC')}), "
        f"currency {currency}. Data file: data/reference/fpinnovations/tr28_subgrade_machines.json[/dim]"
    )


@dataset_app.command("estimate-road-cost")
def estimate_road_cost(
    machine: str = typer.Option(
        ...,
        "--machine",
        help="TR-28 machine slug or full name (e.g., caterpillar_235_hydraulic_backhoe).",
    ),
    road_length_m: float = typer.Option(
        ...,
        "--road-length-m",
        min=1.0,
        help="Road/subgrade length in metres to build with the selected machine.",
    ),
    include_mobilisation: bool = typer.Option(
        True,
        "--include-mobilisation/--exclude-mobilisation",
        help="Include the TR-28 movement cost (lowbed + machine relocation) in the total.",
    ),
):
    """Estimate CPI-adjusted road/subgrade cost using TR-28 reference machines."""

    resolved = _resolve_tr28_machine(machine)
    if not resolved:
        raise typer.BadParameter(
            f"Unknown machine '{machine}'. Choose from: {', '.join(_tr28_machine_slugs())}"
        )
    try:
        estimate = estimate_tr28_road_cost(
            resolved,
            road_length_m=road_length_m,
            include_mobilisation=include_mobilisation,
        )
    except ValueError as exc:  # pragma: no cover - Typer surfaces message
        raise typer.BadParameter(str(exc)) from exc
    _render_tr28_road_cost(estimate)


def _render_tr28_road_cost(
    estimate: TR28CostEstimate, soil_profiles: Sequence[SoilProfile] | None = None
) -> None:
    table = Table(title="TR-28 Road Cost Estimate", box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Machine", estimate.machine.machine_name)
    table.add_row("Role", estimate.machine.role or "—")
    table.add_row("Road length", f"{estimate.road_length_m:,.1f} m")
    table.add_row("Stations (30.48 m)", f"{estimate.stations:,.2f}")
    if estimate.shifts is not None:
        table.add_row("Estimated shifts", f"{estimate.shifts:,.2f}")
    else:
        table.add_row("Estimated shifts", "—")
    table.add_row(
        f"Unit cost ({estimate.base_year} CAD $/m)",
        f"{_format_currency(estimate.unit_cost_base_cad_per_m)} / m",
    )
    table.add_row(
        f"Unit cost ({estimate.target_year} CAD $/m)",
        f"{_format_currency(estimate.unit_cost_target_cad_per_m)} / m",
    )
    table.add_row(
        f"Total ({estimate.base_year} CAD)",
        _format_currency(estimate.total_cost_base_cad),
    )
    table.add_row(
        f"Total ({estimate.target_year} CAD)",
        _format_currency(estimate.total_cost_target_cad),
    )
    mob_label = (
        "Mobilisation cost" if estimate.mobilisation_included else "Mobilisation cost (excluded)"
    )
    table.add_row(
        f"{mob_label} ({estimate.base_year} CAD)",
        _format_currency(estimate.mobilisation_cost_base_cad),
    )
    table.add_row(
        f"{mob_label} ({estimate.target_year} CAD)",
        _format_currency(estimate.mobilisation_cost_target_cad),
    )
    table.add_row(
        f"Total incl. mobilisation ({estimate.base_year} CAD)",
        _format_currency(estimate.total_with_mobilisation_base_cad),
    )
    table.add_row(
        f"Total incl. mobilisation ({estimate.target_year} CAD)",
        _format_currency(estimate.total_with_mobilisation_target_cad),
    )
    console.print(table)
    mobilisation_note = (
        "Mobilisation cost included."
        if estimate.mobilisation_included
        else "Mobilisation cost excluded (movement reported separately in TR-28)."
    )
    console.print(
        f"[dim]Base currency: {estimate.base_year} CAD (FERIC TR-28). "
        f"Values inflated to {estimate.target_year} CAD using StatCan CPI. "
        f"{mobilisation_note} Stations assume 30.48 m (100 ft).[/dim]"
    )
    if soil_profiles:
        _render_soil_profiles_table(soil_profiles)


def _render_soil_profiles_table(profiles: Sequence[SoilProfile]) -> None:
    table = Table(title="Soil Protection Profiles", box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Profile", style="cyan")
    table.add_column("Source")
    table.add_column("Guidance")
    for profile in profiles:
        metrics: list[str] = []
        if profile.ground_pressure_multiplier is not None:
            metrics.append(f"Ground pressure ×{profile.ground_pressure_multiplier:.2f}")
        if profile.productivity_gain_percent is not None:
            metrics.append(f"Productivity +{profile.productivity_gain_percent:.0f}% vs. baseline")
        if profile.compaction_threshold_percent is not None:
            metrics.append(
                f"Compaction threshold ≤{profile.compaction_threshold_percent:.0f}% of area"
            )
        guidance_parts = metrics + list(profile.recommendations)
        guidance = guidance_parts[0] if guidance_parts else "—"
        if len(guidance_parts) > 1:
            guidance = "; ".join(guidance_parts)
        table.add_row(profile.title, profile.source, guidance)
    console.print(table)


@dataset_app.command("estimate-cable-skidding")
def estimate_cable_skidding_cmd(
    model: CableSkiddingModel = typer.Option(CableSkiddingModel.UNVER_SPSS, case_sensitive=False),
    log_volume_m3: float = typer.Option(..., min=0.01, help="Log volume per cycle (m³)."),
    slope_percent: float | None = typer.Option(
        None,
        "--slope-percent",
        min=0.1,
        help="Route slope percent (ignored when --profile is used).",
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="Appendix 5 author/stand name to supply slope defaults."
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append cable-skidding inputs/output to a JSONL telemetry file.",
        dir_okay=False,
        writable=True,
    ),
):
    """Estimate cable skidding productivity (m³/h) using Ünver-Okan (2020) regressions."""

    source_label = "Ünver-Okan 2020 (North-East Turkey spruce uphill skidding)."
    slope_value = slope_percent
    if profile:
        if model is CableSkiddingModel.UNVER_SPSS:
            value = estimate_cable_skidding_productivity_unver_spss_profile(
                profile=profile, log_volume_m3=log_volume_m3
            )
        else:
            value = estimate_cable_skidding_productivity_unver_robust_profile(
                profile=profile, log_volume_m3=log_volume_m3
            )
        slope_value = get_appendix5_profile(profile).average_slope_percent
        rows = [
            ("Model", model.value),
            ("Profile", profile),
            ("Log Volume (m³)", f"{log_volume_m3:.3f}"),
            ("Productivity (m³/h)", f"{value:.2f}"),
        ]
    else:
        if slope_percent is None:
            raise typer.BadParameter(
                "Provide --slope-percent or --profile to supply slope defaults."
            )
        source_label = (
            "Ünver-Okan 2020 (SPSS linear regression, North-East Turkey spruce uphill skidding)."
        )
        if model is CableSkiddingModel.UNVER_ROBUST:
            value = estimate_cable_skidding_productivity_unver_robust(log_volume_m3, slope_percent)
            source_label = (
                "Ünver-Okan 2020 (robust regression, North-East Turkey spruce uphill skidding)."
            )
        else:
            value = estimate_cable_skidding_productivity_unver_spss(log_volume_m3, slope_percent)
        rows = [
            ("Model", model.value),
            ("Log Volume (m³)", f"{log_volume_m3:.3f}"),
            ("Slope (%)", f"{slope_percent:.2f}"),
            ("Productivity (m³/h)", f"{value:.2f}"),
        ]
    console_warning = None
    if model in {CableSkiddingModel.UNVER_SPSS, CableSkiddingModel.UNVER_ROBUST}:
        console_warning = (
            "[yellow]Warning:[/yellow] Ünver-Okan regressions were calibrated outside BC "
            "(North-East Turkey spruce uphill skidding). Use with caution."
        )
    _render_kv_table("Cable Skidding Productivity", rows)
    if source_label:
        console.print(f"[dim]Source: {source_label}[/dim]")
    if console_warning:
        console.print(console_warning)
    if telemetry_log:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "command": "dataset estimate-cable-skidding",
            "model": model.value,
            "profile": profile,
            "slope_percent": slope_value,
            "log_volume_m3": log_volume_m3,
            "productivity_m3_per_h": value,
            "source": source_label,
            "non_bc_source": True,
        }
        append_jsonl(telemetry_log, payload)


@dataset_app.command("estimate-skyline-productivity")
def estimate_skyline_productivity_cmd(
    ctx: typer.Context,
    model: SkylineProductivityModel = typer.Option(
        SkylineProductivityModel.LEE_UPHILL, case_sensitive=False
    ),
    slope_distance_m: float = typer.Option(..., min=1.0, help="Slope yarding distance (m)."),
    lateral_distance_m: float = typer.Option(25.0, min=0.0, help="Lateral yarding distance (m)."),
    lateral_distance_2_m: float | None = typer.Option(
        None,
        "--lateral-distance-2-m",
        min=0.0,
        help="Optional second lateral distance input for TR127 blocks that require it.",
        show_default=False,
    ),
    payload_m3: float = typer.Option(None, help="Payload per turn (m³). Defaults per source."),
    large_end_diameter_cm: float = typer.Option(
        34.0, min=1.0, help="Required for Lee downhill (cm).", show_default=False
    ),
    num_logs: float | None = typer.Option(
        None,
        "--num-logs",
        min=0.0,
        help="Number of logs per turn (required for TR127 Blocks 5–6).",
    ),
    horizontal_distance_m: float | None = typer.Option(
        None,
        "--horizontal-distance-m",
        help="Horizontal span distance (m) for running skyline regressions (defaults to slope distance).",
        show_default=False,
    ),
    vertical_distance_m: float | None = typer.Option(
        None,
        "--vertical-distance-m",
        help="Vertical carriage deflection (m) for running skyline regressions.",
        show_default=False,
    ),
    pieces_per_cycle: float | None = typer.Option(
        None,
        "--pieces-per-cycle",
        min=0.1,
        help="Pieces per cycle for running skyline regressions (defaults per yarder variant).",
        show_default=False,
    ),
    piece_volume_m3: float | None = typer.Option(
        None,
        "--piece-volume-m3",
        min=0.01,
        help="Piece volume (m³) for running skyline regressions (defaults per yarder variant).",
        show_default=False,
    ),
    running_yarder_variant: RunningSkylineVariant = typer.Option(
        RunningSkylineVariant.YARDER_A,
        "--running-yarder-variant",
        case_sensitive=False,
        help="Running skyline yarder variant from McNeel (2000).",
    ),
    logs_per_turn: float = typer.Option(
        3.5,
        "--logs-per-turn",
        min=0.1,
        help="Logs per turn for standing skyline regressions (used by Aubuchon/Hensel model).",
    ),
    average_log_volume_m3: float = typer.Option(
        0.35,
        "--average-log-volume-m3",
        min=0.01,
        help="Average log volume (m³) used to convert logs/turn to payload for Aubuchon model.",
    ),
    merchantable_logs_per_turn: float | None = typer.Option(
        None,
        "--merchantable-logs-per-turn",
        min=0.0,
        help="Merchantable logs per turn (LeDoux 1984 residue regressions).",
        show_default=False,
    ),
    merchantable_volume_m3: float | None = typer.Option(
        None,
        "--merchantable-volume-m3",
        min=0.0,
        help="Merchantable volume per turn (m³) for LeDoux regressions.",
        show_default=False,
    ),
    residue_pieces_per_turn: float | None = typer.Option(
        None,
        "--residue-pieces-per-turn",
        min=0.0,
        help="Residue pieces per turn (LeDoux regressions).",
        show_default=False,
    ),
    residue_volume_m3: float | None = typer.Option(
        None,
        "--residue-volume-m3",
        min=0.0,
        help="Residue volume per turn (m³) for LeDoux regressions.",
        show_default=False,
    ),
    crew_size: float = typer.Option(
        4.0,
        "--crew-size",
        min=1.0,
        help="Crew size (people) for the Aubuchon standing skyline regression.",
    ),
    carriage_height_m: float | None = typer.Option(
        None,
        "--carriage-height-m",
        min=0.0,
        help="Carriage height above ground (m) for Kramer (1978) standing skyline regression.",
        show_default=False,
    ),
    chordslope_percent: float | None = typer.Option(
        None,
        "--chordslope-percent",
        help="Chord slope (%) measured from the landing (negative for uphill) for Kramer (1978).",
        show_default=False,
    ),
    lead_angle_degrees: float | None = typer.Option(
        None,
        "--lead-angle-deg",
        help="Lead angle (degrees) for the Kellogg (1976) standing skyline regression.",
        show_default=False,
    ),
    chokers: float | None = typer.Option(
        None,
        "--chokers",
        min=0.1,
        help="Number of chokers for the Kellogg (1976) standing skyline regression.",
        show_default=False,
    ),
    harvest_system_id: str | None = typer.Option(
        None,
        "--harvest-system-id",
        help="Harvest system ID to pull skyline defaults from (registry or dataset).",
    ),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        help="Dataset/scenario providing harvest system context for defaults.",
    ),
    block_id: str | None = typer.Option(
        None,
        "--block-id",
        help="Block ID (requires --dataset) to infer harvest system defaults automatically.",
    ),
    hi_skid_include_haul: bool = typer.Option(
        False,
        "--hi-skid-include-haul/--hi-skid-yard-only",
        help="For the hi-skid model, include the 30 min travel/unload cycle when reporting productivity.",
    ),
    tr119_treatment: str | None = typer.Option(
        None,
        "--tr119-treatment",
        help="Optional TR119 treatment (e.g., strip_cut, 70_retention, 65_retention) to scale output and show costs.",
    ),
    manual_falling: bool | None = typer.Option(
        None,
        "--manual-falling/--no-manual-falling",
        help="Include TN98 manual falling time/cost estimates ahead of skyline yarding (defaults to harvest system when present).",
    ),
    manual_falling_species: str | None = typer.Option(
        None,
        "--manual-falling-species",
        case_sensitive=False,
        help="TN98 species bucket (cedar, douglas_fir, hemlock, all_species). Defaults to harvest system or Douglas-fir.",
        show_default=False,
    ),
    manual_falling_dbh_cm: float | None = typer.Option(
        None,
        "--manual-falling-dbh-cm",
        min=5.0,
        help="DBH midpoint (cm) for the TN98 manual falling estimate. Defaults to harvest system or 32.5 cm.",
        show_default=False,
    ),
    fncy12_variant: Fncy12ProductivityVariant | None = typer.Option(
        None,
        "--fncy12-variant",
        case_sensitive=False,
        help="Only used with --model fncy12-tmy45. Select observed shift average: overall, steady_state, or steady_state_no_fire.",
        show_default=False,
    ),
    show_costs: bool = typer.Option(
        False,
        "--show-costs",
        help="Print the CPI-adjusted skyline machine-rate summary for the selected model.",
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append skyline inputs/output to a JSONL telemetry file.",
        dir_okay=False,
        writable=True,
    ),
):
    """Estimate skyline productivity (m³/PMH) using Lee et al. (2018), FPInnovations TR-125/TR-127, or McNeel (2000)."""

    if payload_m3 is not None and payload_m3 <= 0:
        raise typer.BadParameter("--payload-m3 must be > 0 when specified.")
    if hi_skid_include_haul and model is not SkylineProductivityModel.HI_SKID:
        raise typer.BadParameter("--hi-skid-include-haul is only valid when --model hi-skid.")
    if (manual_falling_species is not None or manual_falling_dbh_cm is not None) and manual_falling is False:
        raise typer.BadParameter(
            "Cannot specify manual falling overrides when --no-manual-falling is set."
        )
    if manual_falling_species is not None or manual_falling_dbh_cm is not None:
        manual_falling = True

    def _append_warning(existing: str | None, message: str) -> str:
        return f"{existing}\n{message}" if existing else message

    telemetry_calibration_flags: list[dict[str, Any]] = []
    calibration_notes: list[str] = []

    def _check_calibration_range(
        *,
        model_label: str,
        field: str,
        value: float | None,
        range_min: float,
        range_max: float,
        units: str = "",
    ) -> None:
        if value is None:
            return
        if value < range_min or value > range_max:
            units_suffix = units if units else ""
            warning = (
                f"[yellow]Calibration warning ({model_label}):[/yellow] {field} {value:.2f}{units_suffix} "
                f"lies outside the {range_min:.2f}–{range_max:.2f}{units_suffix} study range."
            )
            nonlocal console_warning
            console_warning = _append_warning(console_warning, warning)
            telemetry_calibration_flags.append(
                {
                    "model": model_label,
                    "field": field,
                    "value": value,
                    "range": [range_min, range_max],
                }
            )

    scenario_context: Scenario | None = None
    dataset_name: str | None = None
    systems_catalog = dict(default_system_registry())
    if dataset is not None:
        dataset_name, scenario_context, _ = _ensure_dataset(dataset, interactive=False)
        systems_catalog = _scenario_systems(scenario_context)
    if block_id is not None and scenario_context is None:
        raise typer.BadParameter("--block-id requires --dataset to be specified.")
    derived_system_id: str | None = None
    if block_id and scenario_context is not None:
        block = next((blk for blk in scenario_context.blocks if blk.id == block_id), None)
        if block is None:
            raise typer.BadParameter(
                f"Block '{block_id}' not found in dataset {dataset_name or dataset}."
            )
        derived_system_id = block.harvest_system_id
        if derived_system_id is None:
            console.print(
                f"[yellow]Block {block_id} does not declare a harvest system; skyline defaults will not apply.[/yellow]"
            )
    selected_system_id = harvest_system_id or derived_system_id
    selected_system: HarvestSystem | None = None
    if selected_system_id:
        selected_system = systems_catalog.get(selected_system_id)
        if selected_system is None:
            raise typer.BadParameter(
                f"Harvest system '{selected_system_id}' not found. Options: {', '.join(sorted(systems_catalog))}"
            )

    fncy12_variant_supplied = _parameter_supplied(ctx, "fncy12_variant")

    user_supplied = {
        "model": _parameter_supplied(ctx, "model"),
        "slope_distance_m": True,  # required option always supplied
        "logs_per_turn": _parameter_supplied(ctx, "logs_per_turn"),
        "average_log_volume_m3": _parameter_supplied(ctx, "average_log_volume_m3"),
        "crew_size": _parameter_supplied(ctx, "crew_size"),
        "lateral_distance_m": _parameter_supplied(ctx, "lateral_distance_m"),
        "lateral_distance_2_m": _parameter_supplied(ctx, "lateral_distance_2_m"),
        "horizontal_distance_m": _parameter_supplied(ctx, "horizontal_distance_m"),
        "vertical_distance_m": _parameter_supplied(ctx, "vertical_distance_m"),
        "pieces_per_cycle": _parameter_supplied(ctx, "pieces_per_cycle"),
        "piece_volume_m3": _parameter_supplied(ctx, "piece_volume_m3"),
        "running_yarder_variant": _parameter_supplied(ctx, "running_yarder_variant"),
        "carriage_height_m": _parameter_supplied(ctx, "carriage_height_m"),
        "chordslope_percent": _parameter_supplied(ctx, "chordslope_percent"),
        "payload_m3": _parameter_supplied(ctx, "payload_m3"),
        "num_logs": _parameter_supplied(ctx, "num_logs"),
        "merchantable_logs_per_turn": _parameter_supplied(ctx, "merchantable_logs_per_turn"),
        "merchantable_volume_m3": _parameter_supplied(ctx, "merchantable_volume_m3"),
        "residue_pieces_per_turn": _parameter_supplied(ctx, "residue_pieces_per_turn"),
        "residue_volume_m3": _parameter_supplied(ctx, "residue_volume_m3"),
        "manual_falling": manual_falling is not None,
        "manual_falling_species": _parameter_supplied(ctx, "manual_falling_species"),
        "manual_falling_dbh_cm": _parameter_supplied(ctx, "manual_falling_dbh_cm"),
        "tr119_treatment": tr119_treatment is not None,
    }

    (
        model,
        slope_distance_m,
        lateral_distance_m,
        lateral_distance_2_m,
        logs_per_turn,
        average_log_volume_m3,
        crew_size,
        horizontal_distance_m,
        vertical_distance_m,
        pieces_per_cycle,
        piece_volume_m3,
        running_yarder_variant,
        carriage_height_m,
        chordslope_percent,
        payload_m3,
        num_logs,
        skyline_defaults_used,
        tr119_override,
    ) = _apply_skyline_system_defaults(
        system=selected_system,
        model=model,
        slope_distance_m=slope_distance_m,
        lateral_distance_m=lateral_distance_m,
        lateral_distance_2_m=lateral_distance_2_m,
        logs_per_turn=logs_per_turn,
        average_log_volume_m3=average_log_volume_m3,
        crew_size=crew_size,
        horizontal_distance_m=horizontal_distance_m,
        vertical_distance_m=vertical_distance_m,
        pieces_per_cycle=pieces_per_cycle,
        piece_volume_m3=piece_volume_m3,
        running_variant=running_yarder_variant,
        carriage_height_m=carriage_height_m,
        chordslope_percent=chordslope_percent,
        payload_m3=payload_m3,
        num_logs=num_logs,
        user_supplied=user_supplied,
    )
    if fncy12_variant_supplied and model is not SkylineProductivityModel.FNCY12_TMY45:
        raise typer.BadParameter("--fncy12-variant is only valid when --model fncy12-tmy45.")
    if tr119_treatment is None and tr119_override is not None:
        tr119_treatment = tr119_override
    manual_overrides = _manual_falling_overrides(selected_system)
    manual_defaults_used = False
    manual_falling_enabled = manual_falling
    manual_species_value = manual_falling_species
    manual_dbh_value = manual_falling_dbh_cm
    if manual_overrides:
        try:
            override_enabled = _coerce_bool(manual_overrides.get("manual_falling_enabled"))
        except ValueError as exc:
            raise typer.BadParameter(str(exc))
        if manual_falling_enabled is None and override_enabled is not None:
            manual_falling_enabled = override_enabled
            manual_defaults_used = override_enabled or manual_defaults_used
        if manual_species_value is None and manual_overrides.get("manual_falling_species"):
            manual_species_value = str(manual_overrides["manual_falling_species"])
            manual_defaults_used = True
        if manual_dbh_value is None and manual_overrides.get("manual_falling_dbh_cm") is not None:
            try:
                manual_dbh_value = float(manual_overrides["manual_falling_dbh_cm"])
            except (TypeError, ValueError) as exc:  # pragma: no cover
                raise typer.BadParameter(
                    f"Invalid manual_falling_dbh_cm override: {manual_overrides.get('manual_falling_dbh_cm')}"
                ) from exc
            manual_defaults_used = True
    if manual_falling_enabled is None:
        manual_falling_enabled = False
    manual_species_normalized: str | None = None
    manual_falling_summary: dict[str, Any] | None = None
    if manual_falling_enabled:
        fallback_species = manual_species_value or "douglas_fir"
        try:
            manual_species_normalized = _normalise_tn98_species_value(fallback_species)
        except ValueError as exc:
            raise typer.BadParameter(str(exc))
        manual_dbh = manual_dbh_value if manual_dbh_value is not None else 32.5
        if manual_dbh <= 0:
            raise typer.BadParameter("--manual-falling-dbh-cm must be > 0.")
        try:
            manual_falling_summary = _estimate_tn98_manual_falling(
                manual_species_normalized, manual_dbh
            )
            manual_falling_summary["species_label"] = manual_species_normalized.replace("_", " ")
        except ValueError as exc:
            raise typer.BadParameter(str(exc))

    telemetry_payload_m3 = payload_m3
    source_label = None
    console_warning = None
    cycle_minutes = None
    telemetry_horizontal = horizontal_distance_m
    telemetry_vertical = vertical_distance_m
    telemetry_pieces = pieces_per_cycle
    telemetry_piece_volume = piece_volume_m3
    telemetry_running_variant = running_yarder_variant.value if running_yarder_variant else None
    telemetry_carriage_height = None
    telemetry_chordslope = None
    telemetry_lead_angle = None
    telemetry_chokers = None
    telemetry_merch_logs = None
    telemetry_merch_volume = None
    telemetry_residue_pieces = None
    telemetry_residue_volume = None
    telemetry_support_cat_d8_ratio = None
    telemetry_support_timberjack_ratio = None
    telemetry_fncy12_variant = None
    tn258_limit_exceeded = False
    non_bc_warning = False
    if model is SkylineProductivityModel.LEE_UPHILL:
        value = estimate_cable_yarder_productivity_lee2018_uphill(
            yarding_distance_m=slope_distance_m,
            payload_m3=payload_m3 or 0.57,
        )
        source_label = "Lee et al. 2018 (HAM300 uphill, South Korea)."
        console_warning = (
            "[yellow]Warning:[/yellow] Lee et al. (2018) regressions are non-BC small-scale skyline "
            "studies (South Korea). Validate before using for BC costing."
        )
        non_bc_warning = True
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Payload (m³)", f"{(payload_m3 or 0.57):.2f}"),
        ]
    elif model is SkylineProductivityModel.LEE_DOWNHILL:
        value = estimate_cable_yarder_productivity_lee2018_downhill(
            yarding_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            large_end_diameter_cm=large_end_diameter_cm,
            payload_m3=payload_m3 or 0.61,
        )
        source_label = "Lee et al. 2018 (HAM300 downhill, South Korea)."
        console_warning = (
            "[yellow]Warning:[/yellow] Lee et al. (2018) regressions are non-BC small-scale skyline "
            "studies (South Korea). Validate before using for BC costing."
        )
        non_bc_warning = True
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Large-end Diameter (cm)", f"{large_end_diameter_cm:.1f}"),
            ("Payload (m³)", f"{(payload_m3 or 0.61):.2f}"),
        ]
    elif model is SkylineProductivityModel.TR125_SINGLE:
        cycle_minutes = estimate_cable_yarder_cycle_time_tr125_single_span(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
        )
        value = estimate_cable_yarder_productivity_tr125_single_span(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            payload_m3=payload_m3 or 1.6,
        )
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Payload (m³)", f"{(payload_m3 or 1.6):.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
        ]
        source_label = "FPInnovations TR-125 single-span regression (coastal BC)."
        if lateral_distance_m > _TN258_LATERAL_LIMIT_M:
            tn258_limit_exceeded = True
            tension_warning = (
                f"[yellow]TN258 envelope:[/yellow] Thunderbird TMY45 trials recorded skyline tension spikes up "
                f"to {_TN258_MAX_SKYLINE_TENSION_KN:.0f} kN once lateral pulls exceeded "
                f"{_TN258_LATERAL_LIMIT_M:.0f} m. Trim lateral distance or add anchors/intermediate supports."
            )
            console_warning = _append_warning(console_warning, tension_warning)
    elif model is SkylineProductivityModel.TR125_MULTI:
        cycle_minutes = estimate_cable_yarder_cycle_time_tr125_multi_span(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
        )
        value = estimate_cable_yarder_productivity_tr125_multi_span(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            payload_m3=payload_m3 or 1.6,
        )
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Payload (m³)", f"{(payload_m3 or 1.6):.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
        ]
        source_label = (
            "FPInnovations TR-125 multi-span (intermediate support) regression (coastal BC)."
        )
        if lateral_distance_m > _TN258_LATERAL_LIMIT_M:
            tn258_limit_exceeded = True
            tension_warning = (
                f"[yellow]TN258 envelope:[/yellow] Thunderbird TMY45 trials recorded skyline tension spikes up "
                f"to {_TN258_MAX_SKYLINE_TENSION_KN:.0f} kN once lateral pulls exceeded "
                f"{_TN258_LATERAL_LIMIT_M:.0f} m. Trim lateral distance or add supports before trusting the output."
            )
            console_warning = _append_warning(console_warning, tension_warning)
        support_ratios = _get_tmy45_support_ratios()
        telemetry_support_cat_d8_ratio = support_ratios["cat_d8_smhr_per_yarder_smhr"]
        telemetry_support_timberjack_ratio = support_ratios[
            "timberjack_450_smhr_per_yarder_smhr"
        ]
        support_note = (
            "[yellow]Support reminder:[/yellow] FNCY12 crew data implies Cat D8 backspar standby "
            f"{telemetry_support_cat_d8_ratio:.2f} SMH/SMH and Timberjack 450 trail support "
            f"{telemetry_support_timberjack_ratio:.2f} SMH/SMH—override if your support plan differs."
        )
        console_warning = _append_warning(console_warning, support_note)
    elif model in _TR127_MODEL_TO_BLOCK:
        block_id = _TR127_MODEL_TO_BLOCK[model]
        if block_id in (5, 6) and num_logs is None:
            raise typer.BadParameter("--num-logs is required for TR127 Block 5/6 models.")
        cycle_minutes = estimate_cable_yarder_cycle_time_tr127_minutes(
            block=block_id,
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            num_logs=num_logs,
            lateral_distance2_m=lateral_distance_2_m,
        )
        value = estimate_cable_yarder_productivity_tr127(
            block=block_id,
            payload_m3=payload_m3 or 1.6,
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            num_logs=num_logs,
            lateral_distance2_m=lateral_distance_2_m,
        )
        rows = [
            ("Model", model.value),
            ("Block", str(block_id)),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Logs per Turn", f"{num_logs:.1f}" if num_logs is not None else "—"),
            ("Payload (m³)", f"{(payload_m3 or 1.6):.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
        ]
        source_label = f"FPInnovations TR-127 Block {block_id} regression (northwestern BC)."
    elif model is SkylineProductivityModel.FNCY12_TMY45:
        resolved_variant = fncy12_variant or Fncy12ProductivityVariant.STEADY_STATE
        fncy12_result = estimate_tmy45_productivity_fncy12(resolved_variant)
        value = fncy12_result.productivity_m3_per_pmh
        telemetry_payload_m3 = None
        telemetry_fncy12_variant = resolved_variant.value
        cycle_minutes = None
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Variant", resolved_variant.value.replace("_", " ")),
            ("Shift Hours", f"{fncy12_result.shift_hours:.1f}"),
            (
                "Shift Productivity (m³/shift)",
                f"{fncy12_result.shift_productivity_m3:.1f}",
            ),
        ]
        source_label = (
            "FERIC FNCY-12 / TN-258 Thunderbird TMY45 with Mini-Mak II intermediate supports."
        )
        support_ratios = _get_tmy45_support_ratios()
        telemetry_support_cat_d8_ratio = support_ratios["cat_d8_smhr_per_yarder_smhr"]
        telemetry_support_timberjack_ratio = support_ratios[
            "timberjack_450_smhr_per_yarder_smhr"
        ]
        support_note = (
            "[yellow]Support reminder:[/yellow] FNCY12 crew data implies Cat D8 backspar standby "
            f"{telemetry_support_cat_d8_ratio:.2f} SMH/SMH and Timberjack 450 trail support "
            f"{telemetry_support_timberjack_ratio:.2f} SMH/SMH—override if your support plan differs."
        )
        console_warning = _append_warning(console_warning, support_note)
        if lateral_distance_m > _TN258_LATERAL_LIMIT_M:
            tn258_limit_exceeded = True
            tension_warning = (
                f"[yellow]TN258 envelope:[/yellow] Thunderbird TMY45 trials recorded skyline tension spikes up "
                f"to {_TN258_MAX_SKYLINE_TENSION_KN:.0f} kN once lateral pulls exceeded "
                f"{_TN258_LATERAL_LIMIT_M:.0f} m. Trim lateral distance or add support trees before trusting the output."
            )
            console_warning = _append_warning(console_warning, tension_warning)
    elif model is SkylineProductivityModel.MCNEEL_RUNNING:
        horizontal_span = horizontal_distance_m or slope_distance_m
        if horizontal_span is None:
            raise typer.BadParameter(
                "--horizontal-distance-m is required (or supply --slope-distance-m)."
            )
        if vertical_distance_m is None:
            raise typer.BadParameter(
                "--vertical-distance-m is required for running skyline regressions."
            )
        default_pieces, default_piece_volume = running_skyline_variant_defaults(
            running_yarder_variant.value
        )
        resolved_pieces = pieces_per_cycle if pieces_per_cycle is not None else default_pieces
        resolved_piece_volume = (
            piece_volume_m3 if piece_volume_m3 is not None else default_piece_volume
        )
        cycle_minutes = estimate_running_skyline_cycle_time_mcneel2000_minutes(
            horizontal_distance_m=horizontal_span,
            lateral_distance_m=lateral_distance_m,
            vertical_distance_m=vertical_distance_m,
            pieces_per_cycle=resolved_pieces,
            yarder_variant=running_yarder_variant.value,
        )
        value = estimate_running_skyline_productivity_mcneel2000(
            horizontal_distance_m=horizontal_span,
            lateral_distance_m=lateral_distance_m,
            vertical_distance_m=vertical_distance_m,
            pieces_per_cycle=resolved_pieces,
            piece_volume_m3=resolved_piece_volume,
            yarder_variant=running_yarder_variant.value,
        )
        payload_value = resolved_pieces * resolved_piece_volume
        rows = [
            ("Model", model.value),
            ("Yarder Variant", running_yarder_variant.value),
            ("Horizontal Distance (m)", f"{horizontal_span:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Vertical Distance (m)", f"{vertical_distance_m:.1f}"),
            ("Pieces per Cycle", f"{resolved_pieces:.2f}"),
            ("Piece Volume (m³)", f"{resolved_piece_volume:.2f}"),
            ("Payload (m³)", f"{payload_value:.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
        ]
        source_label = "McNeel 2000 running skyline regression (Madill 046, coastal BC)."
        telemetry_horizontal = horizontal_span
        telemetry_vertical = vertical_distance_m
        telemetry_pieces = resolved_pieces
        telemetry_piece_volume = resolved_piece_volume
        telemetry_running_variant = running_yarder_variant.value
    elif model in _LEDOUX_MODEL_TO_PROFILE:
        profile = _LEDOUX_MODEL_TO_PROFILE[model]
        if merchantable_logs_per_turn is None:
            raise typer.BadParameter("--merchantable-logs-per-turn is required for LeDoux models.")
        if merchantable_volume_m3 is None:
            raise typer.BadParameter("--merchantable-volume-m3 is required for LeDoux models.")
        if residue_pieces_per_turn is None:
            raise typer.BadParameter("--residue-pieces-per-turn is required for LeDoux models.")
        if residue_volume_m3 is None:
            raise typer.BadParameter("--residue-volume-m3 is required for LeDoux models.")
        value, cycle_minutes = estimate_residue_productivity_ledoux_m3_per_pmh(
            profile=profile,
            slope_distance_m=slope_distance_m,
            merchantable_logs_per_turn=merchantable_logs_per_turn,
            merchantable_volume_m3=merchantable_volume_m3,
            residue_pieces_per_turn=residue_pieces_per_turn,
            residue_volume_m3=residue_volume_m3,
        )
        merch_delay_minutes, residue_delay_minutes = ledoux_delay_component_minutes(
            profile=profile,
            merchantable_logs_per_turn=merchantable_logs_per_turn,
            merchantable_volume_m3=merchantable_volume_m3,
            residue_pieces_per_turn=residue_pieces_per_turn,
            residue_volume_m3=residue_volume_m3,
        )
        total_payload = merchantable_volume_m3 + residue_volume_m3
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Merchantable Logs/Turn", f"{merchantable_logs_per_turn:.2f}"),
            ("Merchantable Volume (m³)", f"{merchantable_volume_m3:.3f}"),
            ("Residue Pieces/Turn", f"{residue_pieces_per_turn:.2f}"),
            ("Residue Volume (m³)", f"{residue_volume_m3:.3f}"),
            ("Total Payload (m³)", f"{total_payload:.3f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
            ("Merchantable Delay Component (min)", f"{merch_delay_minutes:.2f}"),
            ("Residue Delay Component (min)", f"{residue_delay_minutes:.2f}"),
        ]
        source_label = "LeDoux (1984) residue yarding regressions (Willamette/Mt. Hood experimental trials)."
        console_warning = (
            "[yellow]Warning:[/yellow] LeDoux regressions are based on US residue logging (1984 USD); validate before using for BC skyline costing."
        )
        non_bc_warning = True
        if residue_pieces_per_turn > 0 and residue_delay_minutes > merch_delay_minutes:
            residue_warning = (
                "[yellow]Residue-heavy turn:[/yellow] residue wood is consuming "
                f"{residue_delay_minutes:.2f} min/turn vs. {merch_delay_minutes:.2f} min from merchantable logs. "
                "Consider breaking slash out separately or bundling to maintain productivity."
            )
            console_warning = (
                f"{console_warning}\n{residue_warning}" if console_warning else residue_warning
            )
        telemetry_payload_m3 = total_payload
        telemetry_horizontal = slope_distance_m
        telemetry_merch_logs = merchantable_logs_per_turn
        telemetry_merch_volume = merchantable_volume_m3
        telemetry_residue_pieces = residue_pieces_per_turn
        telemetry_residue_volume = residue_volume_m3
    elif model is SkylineProductivityModel.MICRO_MASTER:
        (
            value,
            cycle_minutes,
            resolved_pieces,
            resolved_piece_volume,
            payload_value,
        ) = estimate_micro_master_productivity_m3_per_pmh(
            slope_distance_m=slope_distance_m,
            payload_m3=payload_m3,
            pieces_per_turn=pieces_per_cycle,
            piece_volume_m3=piece_volume_m3,
        )
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Pieces per Turn", f"{resolved_pieces:.2f}"),
            ("Piece Volume (m³)", f"{resolved_piece_volume:.3f}"),
            ("Payload (m³)", f"{payload_value:.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
        ]
        source_label = "FERIC TN-54 (1982) Model 9 Micro Master yarder (Vancouver Island clearcut)."
        telemetry_payload_m3 = payload_value
        telemetry_pieces = resolved_pieces
        telemetry_piece_volume = resolved_piece_volume
    elif model is SkylineProductivityModel.HI_SKID:
        include_minutes = (
            HI_SKID_DEFAULTS["travel_to_dump_minutes"] if hi_skid_include_haul else None
        )
        (
            yarding_productivity,
            overall_productivity,
            cycle_minutes,
            resolved_pieces,
            resolved_piece_volume,
            payload_value,
        ) = estimate_hi_skid_productivity_m3_per_pmh(
            slope_distance_m=slope_distance_m,
            include_travel_minutes=include_minutes,
            payload_per_cycle_m3=payload_m3,
            pieces_per_cycle=pieces_per_cycle,
            piece_volume_m3=piece_volume_m3,
        )
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Pieces per Cycle", f"{resolved_pieces:.2f}"),
            ("Piece Volume (m³)", f"{resolved_piece_volume:.3f}"),
            ("Payload per Cycle (m³)", f"{payload_value:.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
            ("Yarding Productivity (m³/PMH)", f"{yarding_productivity:.2f}"),
        ]
        if hi_skid_include_haul and overall_productivity is not None:
            rows.append(
                ("Overall Productivity incl. travel (m³/PMH)", f"{overall_productivity:.2f}")
            )
            value = overall_productivity
        else:
            value = yarding_productivity
        source_label = "FERIC FNG73 (1999) Hi-Skid short-yarding, self-loading truck."
        max_distance = HI_SKID_DEFAULTS.get("max_distance_m")
        if max_distance and slope_distance_m > max_distance:
            console_warning = (
                "[yellow]Warning:[/yellow] Hi-Skid trials only covered spans up to "
                f"{max_distance:.0f} m (80 m observed). Validate performance for longer corridors."
            )
        telemetry_payload_m3 = payload_value
        telemetry_pieces = resolved_pieces
        telemetry_piece_volume = resolved_piece_volume
        telemetry_horizontal = slope_distance_m
    elif model in _TN173_MODEL_TO_SYSTEM_ID:
        system_id = _TN173_MODEL_TO_SYSTEM_ID[model]
        system = get_tn173_system(system_id)
        resolved_pieces = pieces_per_cycle or system.pieces_per_turn
        if resolved_pieces is None or resolved_pieces <= 0:
            raise typer.BadParameter(
                "--pieces-per-cycle is required for TN173 presets when the dataset "
                "entry does not declare a default pieces/turn."
            )
        resolved_piece_volume = piece_volume_m3 or system.piece_volume_m3
        if resolved_piece_volume is None:
            if system.payload_m3 is not None and resolved_pieces > 0:
                resolved_piece_volume = system.payload_m3 / resolved_pieces
        if resolved_piece_volume is None or resolved_piece_volume <= 0:
            raise typer.BadParameter(
                "--piece-volume-m3 must be > 0 for TN173 presets when no dataset default exists."
            )
        if payload_m3 is not None and payload_m3 <= 0:
            raise typer.BadParameter("--payload-m3 must be > 0 for TN173 presets.")
        resolved_payload = (
            payload_m3
            if payload_m3 is not None
            else (system.payload_m3 if system.payload_m3 is not None else resolved_pieces * resolved_piece_volume)
        )
        cycle_minutes = system.cycle_minutes
        if cycle_minutes <= 0:
            raise typer.BadParameter(f"TN173 system '{system_id}' is missing a valid cycle time.")
        value = (resolved_payload * 60.0) / cycle_minutes
        rows = [
            ("Model", model.value),
            ("System", system.label),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Pieces per Turn", f"{resolved_pieces:.2f}"),
            ("Piece Volume (m³)", f"{resolved_piece_volume:.3f}"),
            ("Payload (m³)", f"{resolved_payload:.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
            ("Recorded Productivity (m³/PMH)", f"{system.productivity_m3_per_pmh:.2f}"),
        ]
        if system.crew_size:
            rows.insert(2, ("Crew Size", f"{system.crew_size:.1f}"))
        if system.average_yarding_distance_m:
            rows.append(
                ("Observed Avg Distance (m)", f"{system.average_yarding_distance_m:.1f}")
            )
        if system.yarding_distance_min_m is not None or system.yarding_distance_max_m is not None:
            min_label = (
                f"{system.yarding_distance_min_m:.0f}"
                if system.yarding_distance_min_m is not None
                else "–"
            )
            max_label = (
                f"{system.yarding_distance_max_m:.0f}"
                if system.yarding_distance_max_m is not None
                else "–"
            )
            rows.append(("Observed Distance Range (m)", f"{min_label}–{max_label}"))
        if system.average_slope_percent:
            rows.append(("Observed Avg Slope (%)", f"{system.average_slope_percent:.1f}"))
        if system.slope_percent_min is not None or system.slope_percent_max is not None:
            min_slope = (
                f"{system.slope_percent_min:.0f}"
                if system.slope_percent_min is not None
                else "–"
            )
            max_slope = (
                f"{system.slope_percent_max:.0f}"
                if system.slope_percent_max is not None
                else "–"
            )
            rows.append(("Observed Slope Range (%)", f"{min_slope}–{max_slope}"))
        source_label = f"FERIC TN-173 (1991) {system.label} case study."
        warning_parts = [
            "TN-173 trials are Eastern Canada small-span skyline systems; confirm applicability for BC modelling."
        ]
        if (
            system.yarding_distance_max_m is not None
            and slope_distance_m > system.yarding_distance_max_m
        ):
            warning_parts.append(
                f"Slope distance {slope_distance_m:.0f} m exceeds observed max "
                f"{system.yarding_distance_max_m:.0f} m."
            )
        if (
            system.yarding_distance_min_m is not None
            and slope_distance_m < system.yarding_distance_min_m
        ):
            warning_parts.append(
                f"Slope distance {slope_distance_m:.0f} m is below observed min "
                f"{system.yarding_distance_min_m:.0f} m."
            )
        console_warning = "[yellow]Warning:[/yellow] " + " ".join(warning_parts)
        non_bc_warning = True
        telemetry_payload_m3 = resolved_payload
        telemetry_pieces = resolved_pieces
        telemetry_piece_volume = resolved_piece_volume
        telemetry_horizontal = slope_distance_m
    elif model is SkylineProductivityModel.AUBUCHON_STANDING:
        cycle_minutes = estimate_standing_skyline_turn_time_aubuchon1979(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            logs_per_turn=logs_per_turn,
            crew_size=crew_size,
        )
        value = estimate_standing_skyline_productivity_aubuchon1979(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            logs_per_turn=logs_per_turn,
            average_log_volume_m3=average_log_volume_m3,
            crew_size=crew_size,
        )
        payload_value = logs_per_turn * average_log_volume_m3
        telemetry_payload_m3 = payload_value
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Logs per Turn", f"{logs_per_turn:.2f}"),
            ("Average Log Volume (m³)", f"{average_log_volume_m3:.3f}"),
            ("Crew Size", f"{crew_size:.1f}"),
            ("Payload (m³)", f"{payload_value:.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
        ]
        calibration_notes.append(_AUBUCHON_RANGE_TEXT)
        _check_calibration_range(
            model_label="aubuchon-standing",
            field="Slope distance",
            value=slope_distance_m,
            range_min=_AUBUCHON_SLOPE_M_RANGE[0],
            range_max=_AUBUCHON_SLOPE_M_RANGE[1],
            units=" m",
        )
        _check_calibration_range(
            model_label="aubuchon-standing",
            field="Lateral distance",
            value=lateral_distance_m,
            range_min=_AUBUCHON_LATERAL_M_RANGE[0],
            range_max=_AUBUCHON_LATERAL_M_RANGE[1],
            units=" m",
        )
        _check_calibration_range(
            model_label="aubuchon-standing",
            field="Logs per turn",
            value=logs_per_turn,
            range_min=_AUBUCHON_LOGS_RANGE[0],
            range_max=_AUBUCHON_LOGS_RANGE[1],
            units="",
        )
        _check_calibration_range(
            model_label="aubuchon-standing",
            field="Crew size",
            value=crew_size,
            range_min=_AUBUCHON_CREW_RANGE[0],
            range_max=_AUBUCHON_CREW_RANGE[1],
            units="",
        )
        source_label = "Hensel et al. 1979 (Wyssen standing skyline, compiled by Aubuchon 1982)."
        console_warning = (
            "[yellow]Warning:[/yellow] Regression derived from interior WA/ID trials using Wyssen standing skyline;"
            " validate before applying to other regions."
        )
        non_bc_warning = True
        telemetry_horizontal = slope_distance_m
        telemetry_pieces = logs_per_turn
        telemetry_piece_volume = average_log_volume_m3
    elif model is SkylineProductivityModel.AUBUCHON_KRAMER:
        if carriage_height_m is None:
            raise typer.BadParameter("--carriage-height-m is required for aubuchon-kramer.")
        if chordslope_percent is None:
            raise typer.BadParameter("--chordslope-percent is required for aubuchon-kramer.")
        cycle_minutes = estimate_standing_skyline_turn_time_kramer1978(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            logs_per_turn=logs_per_turn,
            carriage_height_m=carriage_height_m,
            chordslope_percent=chordslope_percent,
        )
        value = estimate_standing_skyline_productivity_kramer1978(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            logs_per_turn=logs_per_turn,
            average_log_volume_m3=average_log_volume_m3,
            carriage_height_m=carriage_height_m,
            chordslope_percent=chordslope_percent,
        )
        payload_value = logs_per_turn * average_log_volume_m3
        telemetry_payload_m3 = payload_value
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Logs per Turn", f"{logs_per_turn:.2f}"),
            ("Average Log Volume (m³)", f"{average_log_volume_m3:.3f}"),
            ("Carriage Height (m)", f"{carriage_height_m:.1f}"),
            ("Chord Slope (%)", f"{chordslope_percent:.2f}"),
            ("Payload (m³)", f"{payload_value:.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
        ]
        calibration_notes.append(_KRAMER_RANGE_TEXT)
        _check_calibration_range(
            model_label="aubuchon-kramer",
            field="Chord slope",
            value=chordslope_percent,
            range_min=_KRAMER_CHORDSLOPE_RANGE[0],
            range_max=_KRAMER_CHORDSLOPE_RANGE[1],
            units="%",
        )
        source_label = "Kramer 1978 standing skyline (Aubuchon 1982 Appendix A)."
        console_warning = (
            "[yellow]Warning:[/yellow] Kramer (1978) regressions are US Pacific Northwest trials; "
            "validate before using for BC costing."
        )
        non_bc_warning = True
        telemetry_horizontal = slope_distance_m
        telemetry_pieces = logs_per_turn
        telemetry_piece_volume = average_log_volume_m3
        telemetry_carriage_height = carriage_height_m
        telemetry_chordslope = chordslope_percent
    elif model is SkylineProductivityModel.AUBUCHON_KELLOGG:
        if lead_angle_degrees is None:
            raise typer.BadParameter("--lead-angle-deg is required for aubuchon-kellogg.")
        if chokers is None:
            raise typer.BadParameter("--chokers is required for aubuchon-kellogg.")
        cycle_minutes = estimate_standing_skyline_turn_time_kellogg1976(
            slope_distance_m=slope_distance_m,
            lead_angle_degrees=lead_angle_degrees,
            logs_per_turn=logs_per_turn,
            average_log_volume_m3=average_log_volume_m3,
            chokers=chokers,
        )
        value = estimate_standing_skyline_productivity_kellogg1976(
            slope_distance_m=slope_distance_m,
            lead_angle_degrees=lead_angle_degrees,
            logs_per_turn=logs_per_turn,
            average_log_volume_m3=average_log_volume_m3,
            chokers=chokers,
        )
        payload_value = logs_per_turn * average_log_volume_m3
        telemetry_payload_m3 = payload_value
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Logs per Turn", f"{logs_per_turn:.2f}"),
            ("Average Log Volume (m³)", f"{average_log_volume_m3:.3f}"),
            ("Lead Angle (°)", f"{lead_angle_degrees:.1f}"),
            ("Chokers", f"{chokers:.1f}"),
            ("Payload (m³)", f"{payload_value:.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
        ]
        calibration_notes.append(_KELLOGG_RANGE_TEXT)
        _check_calibration_range(
            model_label="aubuchon-kellogg",
            field="Lead angle",
            value=lead_angle_degrees,
            range_min=_KELLOGG_LEAD_ANGLE_RANGE[0],
            range_max=_KELLOGG_LEAD_ANGLE_RANGE[1],
            units="°",
        )
        _check_calibration_range(
            model_label="aubuchon-kellogg",
            field="Chokers",
            value=chokers,
            range_min=_KELLOGG_CHOKERS_RANGE[0],
            range_max=_KELLOGG_CHOKERS_RANGE[1],
            units="",
        )
        console_warning = (
            "[yellow]Warning:[/yellow] Kellogg (1976) regression is based on small tower yarders in Oregon; "
            "confirm applicability before BC deployment."
        )
        non_bc_warning = True
        source_label = "Kellogg 1976 standing skyline regression (Aubuchon 1982 Appendix A)."
        telemetry_horizontal = slope_distance_m
        telemetry_pieces = logs_per_turn
        telemetry_piece_volume = average_log_volume_m3
        telemetry_lead_angle = lead_angle_degrees
        telemetry_chokers = chokers
    else:
        raise typer.BadParameter(f"Unsupported skyline model: {model}")
    if manual_falling_summary:
        cut = manual_falling_summary["cut_minutes"]
        limb = manual_falling_summary["limb_minutes"]
        fixed = manual_falling_summary["fixed_minutes"]
        total = manual_falling_summary["total_minutes"]
        rows.append(
            (
                "Manual Falling Species",
                manual_falling_summary["species_label"].replace("_", " ").title(),
            )
        )
        rows.append(("Manual Falling DBH (cm)", f"{manual_falling_summary['dbh_cm']:.1f}"))
        rows.append(
            (
                "Manual Falling Time (min/tree)",
                f"{total:.2f} (cut {cut:.2f} + limb {limb:.2f} + fixed {fixed:.2f})",
            )
        )
        if manual_falling_summary.get("volume_m3") is not None:
            rows.append(
                (
                    "Manual Falling Volume (m³/tree)",
                    f"{manual_falling_summary['volume_m3']:.2f}",
                )
            )
        if manual_falling_summary.get("cost_per_tree_cad") is not None:
            rows.append(
                (
                    f"Manual Falling Cost ({manual_falling_summary.get('cost_base_year') or 'base'} CAD $/tree)",
                    f"{manual_falling_summary['cost_per_tree_cad']:.2f}",
                )
            )
            if manual_falling_summary.get("cost_per_tree_cad_2024") is not None:
                rows.append(
                    (
                        "Manual Falling Cost (2024 CAD $/tree)",
                        f"{manual_falling_summary['cost_per_tree_cad_2024']:.2f}",
                    )
                )
        if manual_falling_summary.get("cost_per_m3_cad") is not None:
            rows.append(
                (
                    f"Manual Falling Cost ({manual_falling_summary.get('cost_base_year') or 'base'} CAD $/m³)",
                    f"{manual_falling_summary['cost_per_m3_cad']:.2f}",
                )
            )
            if manual_falling_summary.get("cost_per_m3_cad_2024") is not None:
                rows.append(
                    (
                        "Manual Falling Cost (2024 CAD $/m³)",
                        f"{manual_falling_summary['cost_per_m3_cad_2024']:.2f}",
                    )
                )
    if tr119_treatment:
        try:
            treatment = get_tr119_treatment(tr119_treatment)
        except KeyError as exc:
            raise typer.BadParameter(str(exc))
        value *= treatment.volume_multiplier
        rows.append(("TR119 Treatment", treatment.treatment))
        rows.append(("TR119 Volume Multiplier", f"{treatment.volume_multiplier:.3f}"))
        if treatment.yarding_total_cost_per_m3 is not None:
            rows.append(("TR119 Yarding Cost ($/m³)", f"{treatment.yarding_total_cost_per_m3:.2f}"))
        tr119_cost_note = (
            f"TR119 {treatment.treatment} multiplier applied to skyline cost (volume × {treatment.volume_multiplier:.3f})."
        )
    else:
        tr119_cost_note = None
    rows.append(("Productivity (m³/PMH)", f"{value:.2f}"))
    _render_kv_table("Skyline Productivity", rows)
    if calibration_notes:
        for note in calibration_notes:
            console.print(f"[dim]{note}[/dim]")
    skyline_cost_role = _skyline_cost_role(model)
    if skyline_cost_role is not None:
        if show_costs:
            _render_machine_cost_summary(
                skyline_cost_role,
                label="Skyline Cost Reference",
            )
            if tr119_cost_note:
                console.print(f"[dim]{tr119_cost_note}[/dim]")
    elif show_costs:
        console.print("[dim]No default skyline machine rate is published for this preset.[/dim]")
    if source_label:
        console.print(f"[dim]Source: {source_label}[/dim]")
    if console_warning:
        console.print(console_warning)
    if skyline_defaults_used and selected_system is not None:
        console.print(
            f"[dim]Applied productivity defaults from harvest system '{selected_system.system_id}'.[/dim]"
        )
    if manual_falling_summary and manual_defaults_used and selected_system is not None:
        console.print(
            f"[dim]Applied manual falling defaults from harvest system '{selected_system.system_id}'.[/dim]"
        )
    if telemetry_log:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "command": "dataset estimate-skyline",
            "model": model.value,
            "slope_distance_m": slope_distance_m,
            "lateral_distance_m": lateral_distance_m,
            "num_logs": num_logs,
            "payload_m3": telemetry_payload_m3,
            "horizontal_distance_m": telemetry_horizontal,
            "vertical_distance_m": telemetry_vertical,
            "pieces_per_cycle": telemetry_pieces,
            "piece_volume_m3": telemetry_piece_volume,
            "running_yarder_variant": telemetry_running_variant,
            "carriage_height_m": telemetry_carriage_height,
            "chordslope_percent": telemetry_chordslope,
            "lead_angle_degrees": telemetry_lead_angle,
            "chokers": telemetry_chokers,
            "merchantable_logs_per_turn": telemetry_merch_logs,
            "merchantable_volume_m3": telemetry_merch_volume,
            "residue_pieces_per_turn": telemetry_residue_pieces,
            "residue_volume_m3": telemetry_residue_volume,
            "cycle_minutes": cycle_minutes,
            "productivity_m3_per_pmh": value,
            "tr119_treatment": tr119_treatment,
            "source": source_label,
            "non_bc_source": non_bc_warning,
            "hi_skid_include_haul": hi_skid_include_haul
            if model is SkylineProductivityModel.HI_SKID
            else None,
            "support_cat_d8_smhr_per_yarder_smhr": telemetry_support_cat_d8_ratio,
            "support_timberjack450_smhr_per_yarder_smhr": telemetry_support_timberjack_ratio,
            "tn258_lateral_limit_exceeded": tn258_limit_exceeded,
            "fncy12_variant": telemetry_fncy12_variant,
            "manual_falling": manual_falling_summary is not None,
            "manual_falling_species": manual_falling_summary.get("species")
            if manual_falling_summary
            else None,
            "manual_falling_dbh_cm": manual_falling_summary.get("dbh_cm")
            if manual_falling_summary
            else None,
            "manual_falling_total_minutes": manual_falling_summary.get("total_minutes")
            if manual_falling_summary
            else None,
            "manual_falling_cost_per_tree_cad": manual_falling_summary.get("cost_per_tree_cad")
            if manual_falling_summary
            else None,
            "manual_falling_cost_per_m3_cad": manual_falling_summary.get("cost_per_m3_cad")
            if manual_falling_summary
            else None,
            "manual_falling_cost_base_year": manual_falling_summary.get("cost_base_year")
            if manual_falling_summary
            else None,
            "manual_falling_cost_per_tree_cad_2024": manual_falling_summary.get("cost_per_tree_cad_2024")
            if manual_falling_summary
            else None,
            "manual_falling_cost_per_m3_cad_2024": manual_falling_summary.get("cost_per_m3_cad_2024")
            if manual_falling_summary
            else None,
            "calibration_warnings": telemetry_calibration_flags or None,
        }
        append_jsonl(telemetry_log, payload)
