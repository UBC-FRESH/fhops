"""Dataset inspection CLI commands."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from functools import lru_cache
from typing import Any

from click.core import ParameterSource
import typer
from rich.console import Console
from rich.table import Table

from fhops.core import FHOPSValueError
from fhops.costing import (
    MachineCostEstimate,
    estimate_unit_cost_from_distribution,
    estimate_unit_cost_from_stand,
)
from fhops.costing.machine_rates import (
    MachineRate,
    compose_default_rental_rate_for_role,
    get_machine_rate,
    select_usage_class_multiplier,
)
from fhops.productivity import (
    ALPACASlopeClass,
    ForwarderBCModel,
    ForwarderBCResult,
    Han2018SkidderMethod,
    TrailSpacingPattern,
    DeckingCondition,
    LahrsenModel,
    ADV6N10HarvesterInputs,
    TN292HarvesterInputs,
    SkidderProductivityResult,
    ShovelLoggerSessions2006Inputs,
    ShovelLoggerResult,
    HelicopterLonglineModel,
    HelicopterProductivityResult,
    alpaca_slope_multiplier,
    estimate_grapple_skidder_productivity_han2018,
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
    estimate_standing_skyline_productivity_aubuchon1979,
    estimate_standing_skyline_turn_time_aubuchon1979,
    estimate_standing_skyline_productivity_kramer1978,
    estimate_standing_skyline_turn_time_kramer1978,
    estimate_standing_skyline_productivity_kellogg1976,
    estimate_standing_skyline_turn_time_kellogg1976,
    estimate_running_skyline_cycle_time_mcneel2000_minutes,
    estimate_running_skyline_productivity_mcneel2000,
    running_skyline_variant_defaults,
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
    ADV5N6ProcessorProductivityResult,
    TN166ProcessorProductivityResult,
    estimate_processor_productivity_adv5n6,
    estimate_processor_productivity_tn166,
    predict_berry2019_skid_effects,
    Labelle2019ProcessorProductivityResult,
    estimate_processor_productivity_labelle2019_dbh,
    Labelle2019VolumeProcessorProductivityResult,
    estimate_processor_productivity_labelle2019_volume,
    LoaderForwarderProductivityResult,
    estimate_loader_forwarder_productivity_tn261,
    estimate_loader_forwarder_productivity_adv5n1,
    LoaderAdv5N1ProductivityResult,
    ADV5N1_DEFAULT_PAYLOAD_M3,
    ADV5N1_DEFAULT_UTILISATION,
    ClambunkProductivityResult,
    estimate_clambunk_productivity_adv2n26,
    ADV2N26_DEFAULT_TRAVEL_EMPTY_M,
    ADV2N26_DEFAULT_STEMS_PER_CYCLE,
    ADV2N26_DEFAULT_STEM_VOLUME_M3,
    ADV2N26_DEFAULT_UTILISATION,
)
from fhops.reference import get_appendix5_profile, get_tr119_treatment, load_appendix5_stands
from fhops.scenario.contract import Machine, Scenario
from fhops.scenario.io import load_scenario
from fhops.scheduling.systems import (
    HarvestSystem,
    default_system_registry,
    system_productivity_overrides,
)
from fhops.telemetry import append_jsonl
from fhops.telemetry.machine_costs import build_machine_cost_snapshots
from fhops.validation.ranges import validate_block_ranges

console = Console()
dataset_app = typer.Typer(help="Inspect FHOPS datasets and bundled examples.")

_LOADER_METADATA_PATH = Path(__file__).resolve().parents[2] / "data" / "productivity" / "loader_models.json"


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
                    raise ValueError(
                        f"Loader override '{key}' must be ≥ 0 (got {coerced})."
                    )
            else:
                if coerced <= 0:
                    raise ValueError(
                        f"Loader override '{key}' must be > 0 (got {coerced})."
                    )
        if max_value is not None and coerced > max_value:
            raise ValueError(
                f"Loader override '{key}' must be ≤ {max_value} (got {coerced})."
            )
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

    piece_size_m3, changed = maybe_float(
        "loader_piece_size_m3", piece_size_m3, piece_size_supplied
    )
    used |= changed
    external_distance_m, changed = maybe_float(
        "loader_distance_m", external_distance_m, distance_supplied
    )
    used |= changed
    payload_m3, changed = maybe_float(
        "loader_payload_m3", payload_m3, payload_supplied
    )
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
    travel_empty_m, changed = maybe_float(
        "loader_travel_empty_m", travel_empty_m, travel_supplied
    )
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
        used,
    )


def _machine_rate_roles_help() -> str:
    from fhops.costing.machine_rates import load_machine_rate_index

    roles = ", ".join(sorted(load_machine_rate_index().keys()))
    return f"Available roles: {roles}"


def _resolve_machine_rate(role: str) -> MachineRate:
    rate = get_machine_rate(role)
    if rate is None:
        from fhops.costing.machine_rates import load_machine_rate_index

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


class SkylineProductivityModel(str, Enum):
    """Supported skyline productivity regressions."""

    LEE_UPHILL = "lee-uphill"
    LEE_DOWNHILL = "lee-downhill"
    TR125_SINGLE = "tr125-single-span"
    TR125_MULTI = "tr125-multi-span"
    TR127_BLOCK1 = "tr127-block1"
    TR127_BLOCK2 = "tr127-block2"
    TR127_BLOCK3 = "tr127-block3"
    TR127_BLOCK4 = "tr127-block4"
    TR127_BLOCK5 = "tr127-block5"
    TR127_BLOCK6 = "tr127-block6"


class RoadsideProcessorModel(str, Enum):
    BERRY2019 = "berry2019"
    LABELLE2016 = "labelle2016"
    LABELLE2017 = "labelle2017"
    LABELLE2018 = "labelle2018"
    LABELLE2019_DBH = "labelle2019_dbh"
    LABELLE2019_VOLUME = "labelle2019_volume"
    ADV5N6 = "adv5n6"
    TN166 = "tn166"


class ADV5N6StemSource(str, Enum):
    LOADER_FORWARDED = "loader_forwarded"
    GRAPPLE_YARDED = "grapple_yarded"


class ADV5N6ProcessingMode(str, Enum):
    COLD = "cold"
    HOT = "hot"
    LOW_VOLUME = "low_volume"


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


class LoaderProductivityModel(str, Enum):
    TN261 = "tn261"
    ADV2N26 = "adv2n26"
    ADV5N1 = "adv5n1"


class LoaderAdv5N1SlopeClass(str, Enum):
    ZERO_TO_TEN = "0_10"
    ELEVEN_TO_THIRTY = "11_30"


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


_FORWARDER_GHAFFARIYAN_MODELS = {
    ForwarderBCModel.GHAFFARIYAN_SMALL,
    ForwarderBCModel.GHAFFARIYAN_LARGE,
}

_FORWARDER_ADV6N10_MODELS = {ForwarderBCModel.ADV6N10_SHORTWOOD}
_FORWARDER_ERIKSSON_MODELS = {
    ForwarderBCModel.ERIKSSON_FINAL_FELLING,
    ForwarderBCModel.ERIKSSON_THINNING,
}
_FORWARDER_BRUSHWOOD_MODELS = {ForwarderBCModel.LAITILA_VAATAINEN_BRUSHWOOD}


def _render_grapple_skidder_result(result: SkidderProductivityResult) -> None:
    params = result.parameters
    rows = [
        ("Method", result.method.value.replace("_", "-")),
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
        | Labelle2016ProcessorProductivityResult
        | Labelle2017PolynomialProcessorResult
        | Labelle2017PowerProcessorResult
        | Labelle2018ProcessorProductivityResult
        | Labelle2019ProcessorProductivityResult
        | Labelle2019VolumeProcessorProductivityResult
        | ADV5N6ProcessorProductivityResult
        | TN166ProcessorProductivityResult
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
        _render_kv_table("Roadside Processor Productivity Estimate", rows)
        console.print(
            "[dim]Regression from Berry (2019) Kinleith NZ time study; utilisation default accounts for <10 min delays.[/dim]"
        )
        return

    elif isinstance(result, Labelle2016ProcessorProductivityResult):
        rows = [
            ("Model", "labelle2016_treeform"),
            ("Tree Form Class", result.tree_form),
            ("DBH (cm)", f"{result.dbh_cm:.1f}"),
            ("Coefficient a", f"{result.coefficient_a:.4f}"),
            ("Exponent b", f"{result.exponent_b:.4f}"),
            ("Sample Trees", str(result.sample_trees)),
            ("Delay-free Productivity (m³/PMH)", f"{result.delay_free_productivity_m3_per_pmh:.2f}"),
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
                pieces = ", ".join(f"{name} {float(value):.2f} min" for name, value in numeric_entries)
                suffix = f": {pieces}"
            console.print(f"{prefix}{suffix}[/dim]")
        if result.notes:
            console.print(f"[dim]{' '.join(result.notes)}[/dim]")
        return

    raise TypeError(f"Unhandled processor result type: {type(result)!r}")


def _render_loader_result(
    result: LoaderForwarderProductivityResult
    | ClambunkProductivityResult
    | LoaderAdv5N1ProductivityResult,
) -> None:
    if isinstance(result, LoaderAdv5N1ProductivityResult):
        rows = [
            ("Model", "adv5n1"),
            ("Slope Class (%)", "0–10" if result.slope_class == "0_10" else "11–30"),
            ("Forwarding Distance (m)", f"{result.forwarding_distance_m:.1f}"),
            ("Payload / Cycle (m³)", f"{result.payload_m3_per_cycle:.2f}"),
            ("Cycle Time (min)", f"{result.cycle_time_minutes:.2f}"),
            ("Utilisation (PMH/SMH)", f"{result.utilisation:.3f}"),
            ("Delay-free Productivity (m³/PMH)", f"{result.delay_free_productivity_m3_per_pmh:.2f}"),
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
    turn_volume_m3: float,
    yarding_distance_m: float,
    productivity_m3_per_pmh: float,
) -> None:
    rows = [
        ("Model", model.value),
        ("Turn Volume (m³)", f"{turn_volume_m3:.2f}"),
        ("Yarding Distance (m)", f"{yarding_distance_m:.1f}"),
        ("Productivity (m³/PMH)", f"{productivity_m3_per_pmh:.2f}"),
    ]
    _render_kv_table("Grapple Yarder Productivity Estimate", rows)
    console.print(
        "[dim]Regressions from MacDonald (1988) SR-54 and Peterson (1987) TR-75 (delay-free cycle times + minor delays).[/dim]"
    )


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
    trail_pattern: TrailSpacingPattern | None,
    decking_condition: DeckingCondition | None,
    custom_multiplier: float | None,
) -> tuple[TrailSpacingPattern | None, DeckingCondition | None, float | None, bool]:
    if system is None:
        return trail_pattern, decking_condition, custom_multiplier, False
    overrides = system_productivity_overrides(
        system, ProductivityMachineRole.GRAPPLE_SKIDDER.value
    )
    if not overrides:
        return trail_pattern, decking_condition, custom_multiplier, False
    used = False
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
    return trail_pattern, decking_condition, custom_multiplier, used


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
    overrides = system_productivity_overrides(
        system, ProductivityMachineRole.SHOVEL_LOGGER.value
    )
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
        swing_time_roadside_s = coerce_float(overrides.get("shovel_swing_time_roadside")) or swing_time_roadside_s
        used = used or overrides.get("shovel_swing_time_roadside") is not None
    if payload_per_swing_roadside_m3 is None:
        payload_per_swing_roadside_m3 = coerce_float(overrides.get("shovel_payload_roadside")) or payload_per_swing_roadside_m3
        used = used or overrides.get("shovel_payload_roadside") is not None
    if swing_time_initial_s is None:
        swing_time_initial_s = coerce_float(overrides.get("shovel_swing_time_initial")) or swing_time_initial_s
        used = used or overrides.get("shovel_swing_time_initial") is not None
    if payload_per_swing_initial_m3 is None:
        payload_per_swing_initial_m3 = coerce_float(overrides.get("shovel_payload_initial")) or payload_per_swing_initial_m3
        used = used or overrides.get("shovel_payload_initial") is not None
    if swing_time_rehandle_s is None:
        swing_time_rehandle_s = coerce_float(overrides.get("shovel_swing_time_rehandle")) or swing_time_rehandle_s
        used = used or overrides.get("shovel_swing_time_rehandle") is not None
    if payload_per_swing_rehandle_m3 is None:
        payload_per_swing_rehandle_m3 = coerce_float(overrides.get("shovel_payload_rehandle")) or payload_per_swing_rehandle_m3
        used = used or overrides.get("shovel_payload_rehandle") is not None
    if travel_speed_index_kph is None:
        travel_speed_index_kph = coerce_float(overrides.get("shovel_speed_index")) or travel_speed_index_kph
        used = used or overrides.get("shovel_speed_index") is not None
    if travel_speed_return_kph is None:
        travel_speed_return_kph = coerce_float(overrides.get("shovel_speed_return")) or travel_speed_return_kph
        used = used or overrides.get("shovel_speed_return") is not None
    if travel_speed_serpentine_kph is None:
        travel_speed_serpentine_kph = coerce_float(overrides.get("shovel_speed_serpentine")) or travel_speed_serpentine_kph
        used = used or overrides.get("shovel_speed_serpentine") is not None
    if effective_minutes_per_hour is None:
        effective_minutes_per_hour = coerce_float(overrides.get("shovel_effective_minutes")) or effective_minutes_per_hour
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
    user_supplied: Mapping[str, bool],
) -> tuple[
    SkylineProductivityModel,
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
    bool,
]:
    if system is None:
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
            False,
        )
    overrides = system_productivity_overrides(system, "skyline_yarder")
    if not overrides:
        overrides = system_productivity_overrides(system, "grapple_yarder")
    if not overrides:
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
            False,
        )
    used = False

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

    logs_per_turn, changed = maybe_float("skyline_logs_per_turn", logs_per_turn, "logs_per_turn", True)
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
    user_supplied: Mapping[str, bool],
) -> tuple[GrappleYarderModel, float | None, float | None, bool]:
    if system is None:
        return model, turn_volume_m3, yarding_distance_m, False
    overrides = system_productivity_overrides(system, ProductivityMachineRole.GRAPPLE_YARDER.value)
    if not overrides:
        return model, turn_volume_m3, yarding_distance_m, False
    used = False

    value = overrides.get("grapple_yarder_model")
    if value and not user_supplied.get("grapple_yarder_model", False):
        try:
            model = GrappleYarderModel(value)
            used = True
        except ValueError as exc:
            raise ValueError(f"Unknown grapple yarder model override '{value}'.") from exc

    def maybe_float(key: str, current: float | None, supplied_flag: str) -> tuple[float | None, bool]:
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

    return model, turn_volume_m3, yarding_distance_m, used
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
    model: Han2018SkidderMethod,
    pieces_per_cycle: float | None,
    piece_volume_m3: float | None,
    empty_distance_m: float | None,
    loaded_distance_m: float | None,
    trail_pattern: TrailSpacingPattern | None,
    decking_condition: DeckingCondition | None,
    custom_multiplier: float | None,
) -> SkidderProductivityResult:
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

    try:
        return estimate_grapple_skidder_productivity_han2018(
            method=model,
            pieces_per_cycle=pieces_per_cycle,
            piece_volume_m3=piece_volume_m3,
            empty_distance_m=empty_distance_m,
            loaded_distance_m=loaded_distance_m,
            trail_pattern=trail_pattern,
            decking_condition=decking_condition,
            custom_multiplier=custom_multiplier,
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
    json_out: Path | None = typer.Option(
        None,
        "--json-out",
        help="Optional path to write machine metadata and rental breakdown as JSON.",
        writable=True,
        dir_okay=False,
    ),
):
    """Inspect machine parameters within a dataset/system context."""
    dataset_name, scenario, path = _ensure_dataset(dataset, interactive)
    system_selection = _select_system(scenario, system, interactive)
    selected_machine = _select_machine(
        scenario, machine, interactive, system_selection[1] if system_selection else None
    )
    context_lines = [
        ("Dataset", dataset_name),
        ("Scenario Path", str(path)),
        ("Machine ID", selected_machine.id),
        ("Crew", selected_machine.crew or "—"),
        ("Daily Hours", f"{selected_machine.daily_hours}"),
        ("Operating Cost", f"{selected_machine.operating_cost}"),
        ("Role", selected_machine.role or "—"),
    ]
    default_snapshot = build_machine_cost_snapshots([selected_machine])[0]
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
            default_rate_note = (
                f"[dim]Default rate derived from role '{selected_machine.role}' "
                f"with repair usage {selected_machine.repair_usage_hours:,} h "
                f"(closest bucket {default_snapshot.usage_bucket_hours / 1000:.0f}×1000 h).[/dim]"
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
        job_matches = [
            job.name
            for job in system_model.jobs
            if selected_machine.role and job.machine_role == selected_machine.role
        ]
        context_lines.append(("Harvest System", system_id))
        context_lines.append(
            ("System Jobs Matched", ", ".join(job_matches) if job_matches else "—")
        )
    _render_kv_table(f"Machine Inspection — {selected_machine.id}", context_lines)
    if default_rate_rows:
        _render_kv_table("Default Rental Breakdown", default_rate_rows)
        if default_rate_note:
            console.print(default_rate_note)
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
        help="Mean forwarding distance (m). Required for Ghaffariyan forwarder models.",
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
    grapple_skidder_model: Han2018SkidderMethod = typer.Option(
        Han2018SkidderMethod.LOP_AND_SCATTER,
        "--grapple-skidder-model",
        case_sensitive=False,
        help="Grapple skidder regression (Han et al. 2018).",
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
    grapple_yarder_model: GrappleYarderModel = typer.Option(
        GrappleYarderModel.SR54,
        "--grapple-yarder-model",
        case_sensitive=False,
        help="Grapple yarder regression (sr54 | tr75-bunched | tr75-handfelled).",
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
    processor_model: RoadsideProcessorModel = typer.Option(
        RoadsideProcessorModel.BERRY2019,
        "--processor-model",
        case_sensitive=False,
        help=(
            "Roadside-processor regression to use "
            "(berry2019 | labelle2016/2017/2018 | labelle2019_dbh | labelle2019_volume | adv5n6 | tn166)."
        ),
    ),
    processor_piece_size_m3: float | None = typer.Option(
        None,
        "--processor-piece-size-m3",
        min=0.0,
        help="Average piece size (m³/stem) for roadside processor helpers.",
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
    processor_tn166_scenario: TN166Scenario = typer.Option(
        TN166Scenario.GRAPPLE_YARDED,
        "--processor-tn166-scenario",
        case_sensitive=False,
        help="TN-166 scenario (grapple_yarded | right_of_way | mixed_shift).",
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
    processor_skid_area_m2: float | None = typer.Option(
        None,
        "--processor-skid-area-m2",
        min=0.0,
        help="Approximate skid/landing area (m²). When using Berry (2019) this scales the utilisation multiplier using the published skid-size delay regression.",
    ),
    loader_model: LoaderProductivityModel = typer.Option(
        LoaderProductivityModel.TN261,
        "--loader-model",
        case_sensitive=False,
        help="Loader helper to use (`tn261` = Vancouver Island loader-forwarder, `adv2n26` = TG88 clambunk support).",
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
    if selected_system_id:
        selected_system = systems_catalog.get(selected_system_id)
        if selected_system is None:
            raise typer.BadParameter(
                f"Harvest system '{selected_system_id}' not found. Options: {', '.join(sorted(systems_catalog))}"
            )

    role = machine_role.value
    if role == ProductivityMachineRole.FORWARDER.value:
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
        return
    if role == ProductivityMachineRole.GRAPPLE_SKIDDER.value:
        try:
            (
                skidder_trail_pattern,
                skidder_decking_condition,
                skidder_productivity_multiplier,
                system_defaults_used,
            ) = _apply_skidder_system_defaults(
                system=selected_system,
                trail_pattern=skidder_trail_pattern,
                decking_condition=skidder_decking_condition,
                custom_multiplier=skidder_productivity_multiplier,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        result = _evaluate_grapple_skidder_result(
            model=grapple_skidder_model,
            pieces_per_cycle=skidder_pieces_per_cycle,
            piece_volume_m3=skidder_piece_volume,
            empty_distance_m=skidder_empty_distance,
            loaded_distance_m=skidder_loaded_distance,
            trail_pattern=skidder_trail_pattern,
            decking_condition=skidder_decking_condition,
            custom_multiplier=skidder_productivity_multiplier,
        )
        _render_grapple_skidder_result(result)
        if system_defaults_used and selected_system is not None:
            console.print(
                f"[dim]Applied productivity defaults from harvest system '{selected_system.system_id}'.[/dim]"
            )
        return
    if role == ProductivityMachineRole.GRAPPLE_YARDER.value:
        grapple_user_supplied = {
            "grapple_yarder_model": _parameter_supplied(ctx, "grapple_yarder_model"),
            "grapple_turn_volume_m3": _parameter_supplied(ctx, "grapple_turn_volume_m3"),
            "grapple_yarding_distance_m": _parameter_supplied(ctx, "grapple_yarding_distance_m"),
        }
        (
            grapple_yarder_model,
            grapple_turn_volume_m3,
            grapple_yarding_distance_m,
            grapple_defaults_used,
        ) = _apply_grapple_yarder_system_defaults(
            system=selected_system,
            model=grapple_yarder_model,
            turn_volume_m3=grapple_turn_volume_m3,
            yarding_distance_m=grapple_yarding_distance_m,
            user_supplied=grapple_user_supplied,
        )
        value = _evaluate_grapple_yarder_result(
            model=grapple_yarder_model,
            turn_volume_m3=grapple_turn_volume_m3,
            yarding_distance_m=grapple_yarding_distance_m,
        )
        assert grapple_turn_volume_m3 is not None
        assert grapple_yarding_distance_m is not None
        _render_grapple_yarder_result(
            model=grapple_yarder_model,
            turn_volume_m3=grapple_turn_volume_m3,
            yarding_distance_m=grapple_yarding_distance_m,
            productivity_m3_per_pmh=value,
        )
        if grapple_defaults_used and selected_system is not None:
            console.print(
                f"[dim]Applied grapple-yarder defaults from harvest system '{selected_system.system_id}'.[/dim]"
            )
        return
    if role == ProductivityMachineRole.ROADSIDE_PROCESSOR.value:
        processor_delay_supplied = _parameter_supplied(ctx, "processor_delay_multiplier")
        berry_skid_prediction: dict[str, Any] | None = None
        berry_skid_auto_adjusted = False
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
                raise typer.BadParameter("--processor-dbh-cm is required for Labelle (2016) models.")
            result_processor = estimate_processor_productivity_labelle2016(
                tree_form=processor_labelle2016_form.value,
                dbh_cm=processor_dbh_cm,
                delay_multiplier=processor_delay_multiplier,
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
                raise typer.BadParameter("--processor-dbh-cm is required for Labelle (2017) models.")
            result_processor = estimate_processor_productivity_labelle2017(
                variant=processor_labelle2017_variant.value,
                dbh_cm=processor_dbh_cm,
                delay_multiplier=processor_delay_multiplier,
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
                raise typer.BadParameter("--processor-dbh-cm is required for Labelle (2018) models.")
            result_processor = estimate_processor_productivity_labelle2018(
                variant=processor_labelle2018_variant.value,
                dbh_cm=processor_dbh_cm,
                delay_multiplier=processor_delay_multiplier,
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
                raise typer.BadParameter("--processor-dbh-cm is required for Labelle (2019) DBH models.")
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
                raise typer.BadParameter("--processor-species/--processor-treatment do not apply to ADV5N6.")
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
        elif processor_model is RoadsideProcessorModel.TN166:
            if processor_piece_size_m3 is not None or processor_volume_m3 is not None:
                raise typer.BadParameter(
                    "--processor-piece-size-m3/--processor-volume-m3 apply to other helpers; TN-166 is table-driven."
                )
            if processor_dbh_cm is not None:
                raise typer.BadParameter("--processor-dbh-cm applies to the Labelle helpers, not TN-166.")
            if processor_species is not None or processor_treatment is not None:
                raise typer.BadParameter("--processor-species/--processor-treatment do not apply to TN-166.")
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
            )
        _render_processor_result(result_processor)
        if berry_skid_prediction is not None:
            delay_line = (
                f"[dim]Berry skid-size model predicts {berry_skid_prediction['delay_seconds']:.1f} s/stem "
                f"at {berry_skid_prediction['skid_area_m2']:.0f} m²."
            )
            if berry_skid_prediction["out_of_range"]:
                delay_line += " (Outside the published ~2.5–3.7k m² study range.)"
            if berry_skid_auto_adjusted:
                delay_line += f" Delay multiplier auto-adjusted to {processor_delay_multiplier:.3f}."
            elif processor_delay_supplied:
                delay_line += " Delay multiplier left unchanged because --processor-delay-multiplier was supplied."
            console.print(delay_line + "[/dim]")
            predicted_prod = berry_skid_prediction["predicted_productivity_m3_per_hour"]
            if predicted_prod is not None:
                r2_text = berry_skid_prediction["productivity_r2"]
                r2_fragment = f"~R² {r2_text:.2f}" if isinstance(r2_text, (float, int)) else "weak fit"
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
        )
        loader_metadata = _loader_model_metadata(loader_model)
        if loader_model is LoaderProductivityModel.TN261:
            if loader_piece_size_m3 is None:
                raise typer.BadParameter("--loader-piece-size-m3 is required when --loader-model tn261.")
            if loader_distance_m is None:
                raise typer.BadParameter("--loader-distance-m is required when --loader-model tn261.")
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
        else:
            if loader_distance_m is None:
                raise typer.BadParameter("--loader-distance-m is required when --loader-model adv5n1.")
            utilisation_value = (
                loader_utilisation
                if loader_utilisation is not None
                else ADV5N1_DEFAULT_UTILISATION
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
        _render_loader_result(loader_result)
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
        ("Delay-free Productivity (m³/PMH)", f"{result.delay_free_productivity_m3_per_pmh:.2f}"),
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
        help="Mean forwarding distance (m). Required for Ghaffariyan models.",
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
    scenario_machine: Machine | None = None
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

    machine_entry: MachineRate | None = None
    rental_breakdown: dict[str, float] | None = None
    repair_reference_hours: int | None = None
    repair_usage_bucket: tuple[int, float] | None = None

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
        source_label = "Ünver-Okan 2020 (SPSS linear regression, North-East Turkey spruce uphill skidding)."
        if model is CableSkiddingModel.UNVER_ROBUST:
            value = estimate_cable_skidding_productivity_unver_robust(log_volume_m3, slope_percent)
            source_label = "Ünver-Okan 2020 (robust regression, North-East Turkey spruce uphill skidding)."
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
    tr119_treatment: str | None = typer.Option(
        None,
        "--tr119-treatment",
        help="Optional TR119 treatment (e.g., strip_cut, 70_retention, 65_retention) to scale output and show costs.",
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

    user_supplied = {
        "model": _parameter_supplied(ctx, "model"),
        "logs_per_turn": _parameter_supplied(ctx, "logs_per_turn"),
        "average_log_volume_m3": _parameter_supplied(ctx, "average_log_volume_m3"),
        "crew_size": _parameter_supplied(ctx, "crew_size"),
        "horizontal_distance_m": _parameter_supplied(ctx, "horizontal_distance_m"),
        "vertical_distance_m": _parameter_supplied(ctx, "vertical_distance_m"),
        "pieces_per_cycle": _parameter_supplied(ctx, "pieces_per_cycle"),
        "piece_volume_m3": _parameter_supplied(ctx, "piece_volume_m3"),
        "running_yarder_variant": _parameter_supplied(ctx, "running_yarder_variant"),
        "carriage_height_m": _parameter_supplied(ctx, "carriage_height_m"),
        "chordslope_percent": _parameter_supplied(ctx, "chordslope_percent"),
    }

    (
        model,
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
        skyline_defaults_used,
    ) = _apply_skyline_system_defaults(
        system=selected_system,
        model=model,
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
        user_supplied=user_supplied,
    )

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
        source_label = "FPInnovations TR-125 multi-span (intermediate support) regression (coastal BC)."
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
    elif model is SkylineProductivityModel.MCNEEL_RUNNING:
        horizontal_span = horizontal_distance_m or slope_distance_m
        if horizontal_span is None:
            raise typer.BadParameter("--horizontal-distance-m is required (or supply --slope-distance-m).")
        if vertical_distance_m is None:
            raise typer.BadParameter("--vertical-distance-m is required for running skyline regressions.")
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
        source_label = "Hensel et al. 1979 (Wyssen standing skyline, compiled by Aubuchon 1982)."
        console_warning = (
            "[yellow]Warning:[/yellow] Regression derived from interior WA/ID trials using Wyssen standing skyline;"
            " validate before applying to other regions."
        )
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
        source_label = "Kramer 1978 standing skyline (Aubuchon 1982 Appendix A)."
        console_warning = (
            "[yellow]Warning:[/yellow] Kramer (1978) regressions are US Pacific Northwest trials; "
            "validate before using for BC costing."
        )
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
        console_warning = (
            "[yellow]Warning:[/yellow] Kellogg (1976) regression is based on small tower yarders in Oregon; "
            "confirm applicability before BC deployment."
        )
        source_label = "Kellogg 1976 standing skyline regression (Aubuchon 1982 Appendix A)."
        telemetry_horizontal = slope_distance_m
        telemetry_pieces = logs_per_turn
        telemetry_piece_volume = average_log_volume_m3
        telemetry_lead_angle = lead_angle_degrees
        telemetry_chokers = chokers
    else:
        raise typer.BadParameter(f"Unsupported skyline model: {model}")
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
    rows.append(("Productivity (m³/PMH)", f"{value:.2f}"))
    _render_kv_table("Skyline Productivity", rows)
    if source_label:
        console.print(f"[dim]Source: {source_label}[/dim]")
    if console_warning:
        console.print(console_warning)
    if skyline_defaults_used and selected_system is not None:
        console.print(
            f"[dim]Applied productivity defaults from harvest system '{selected_system.system_id}'.[/dim]"
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
            "cycle_minutes": cycle_minutes,
            "productivity_m3_per_pmh": value,
            "tr119_treatment": tr119_treatment,
            "source": source_label,
            "non_bc_source": bool(console_warning),
        }
        append_jsonl(telemetry_log, payload)
