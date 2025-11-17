"""BC-focused forwarder productivity helpers built on existing regressions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from fhops.productivity.ghaffariyan2019 import (
    ALPACASlopeClass,
    alpaca_slope_multiplier,
    estimate_forwarder_productivity_large_forwarder_thinning,
    estimate_forwarder_productivity_small_forwarder_thinning,
)
from fhops.productivity.kellogg_bettinger1994 import (
    LoadType as KelloggLoadType,
    estimate_forwarder_productivity_kellogg_bettinger,
)


class ForwarderBCModel(str, Enum):
    """Forwarder regressions that FHOPS exposes for BC planning."""

    GHAFFARIYAN_SMALL = "ghaffariyan-small"
    GHAFFARIYAN_LARGE = "ghaffariyan-large"
    KELLOGG_SAWLOG = "kellogg-sawlog"
    KELLOGG_PULPWOOD = "kellogg-pulpwood"
    KELLOGG_MIXED = "kellogg-mixed"
    ADV6N10_SHORTWOOD = "adv6n10-shortwood"


_MODEL_TO_LOAD: dict[ForwarderBCModel, KelloggLoadType] = {
    ForwarderBCModel.KELLOGG_SAWLOG: KelloggLoadType.SAWLOG,
    ForwarderBCModel.KELLOGG_PULPWOOD: KelloggLoadType.PULPWOOD,
    ForwarderBCModel.KELLOGG_MIXED: KelloggLoadType.MIXED,
}

_ADV6N10_MODELS = {ForwarderBCModel.ADV6N10_SHORTWOOD}


@dataclass(frozen=True)
class ForwarderBCResult:
    """Result payload for BC forwarder helpers."""

    model: ForwarderBCModel
    predicted_m3_per_pmh: float
    pmh_basis: str = "PMH0"
    reference: str = ""
    parameters: Mapping[str, float | str] = field(default_factory=dict)


def estimate_forwarder_productivity_bc(
    *,
    model: ForwarderBCModel,
    extraction_distance_m: float | None = None,
    slope_class: ALPACASlopeClass = ALPACASlopeClass.FLAT,
    slope_factor: float | None = None,
    volume_per_load_m3: float | None = None,
    distance_out_m: float | None = None,
    travel_in_unit_m: float | None = None,
    distance_in_m: float | None = None,
    payload_m3: float | None = None,
    mean_log_length_m: float | None = None,
    travel_speed_m_per_min: float | None = None,
    trail_length_m: float | None = None,
    products_per_trail: float | None = None,
) -> ForwarderBCResult:
    """Evaluate one of the BC forwarder regressions with validation."""

    if model in (ForwarderBCModel.GHAFFARIYAN_SMALL, ForwarderBCModel.GHAFFARIYAN_LARGE):
        if extraction_distance_m is None:
            raise ValueError("extraction_distance_m is required for Ghaffariyan models")
        multiplier = slope_factor if slope_factor is not None else alpaca_slope_multiplier(slope_class)
        if multiplier <= 0:
            raise ValueError("slope_factor must be > 0")
        if model is ForwarderBCModel.GHAFFARIYAN_SMALL:
            value = estimate_forwarder_productivity_small_forwarder_thinning(
                extraction_distance_m=extraction_distance_m,
                slope_factor=multiplier,
            )
            reference = "Ghaffariyan et al. 2019 (14 t forwarder)"
        else:
            value = estimate_forwarder_productivity_large_forwarder_thinning(
                extraction_distance_m=extraction_distance_m,
                slope_factor=multiplier,
            )
            reference = "Ghaffariyan et al. 2019 (20 t forwarder)"
        params: dict[str, float | str] = {
            "extraction_distance_m": extraction_distance_m,
            "slope_class": slope_class.value,
            "slope_factor": multiplier,
        }
        return ForwarderBCResult(
            model=model,
            predicted_m3_per_pmh=value,
            reference=reference,
            parameters=params,
        )

    if model in _ADV6N10_MODELS:
        required_adv = {
            "payload_m3": payload_m3,
            "mean_log_length_m": mean_log_length_m,
            "travel_speed_m_per_min": travel_speed_m_per_min,
            "trail_length_m": trail_length_m,
            "products_per_trail": products_per_trail,
        }
        missing_adv = [name for name, value in required_adv.items() if value is None]
        if missing_adv:
            raise ValueError(
                "Missing parameters for ADV6N10 model: "
                + ", ".join(sorted(missing_adv))
            )
        assert payload_m3 is not None
        assert mean_log_length_m is not None
        assert travel_speed_m_per_min is not None
        assert trail_length_m is not None
        assert products_per_trail is not None

        value = _estimate_forwarder_productivity_adv6n10(
            payload_m3=payload_m3,
            mean_log_length_m=mean_log_length_m,
            travel_speed_m_per_min=travel_speed_m_per_min,
            trail_length_m=trail_length_m,
            products_per_trail=products_per_trail,
        )
        params = {
            "payload_m3": payload_m3,
            "mean_log_length_m": mean_log_length_m,
            "travel_speed_m_per_min": travel_speed_m_per_min,
            "trail_length_m": trail_length_m,
            "products_per_trail": products_per_trail,
        }
        return ForwarderBCResult(
            model=model,
            predicted_m3_per_pmh=value,
            reference="Gingras & Favreau 2005 (ADV6N10)",
            parameters=params,
        )

    required = {
        "volume_per_load_m3": volume_per_load_m3,
        "distance_out_m": distance_out_m,
        "travel_in_unit_m": travel_in_unit_m,
        "distance_in_m": distance_in_m,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ValueError(
            f"Missing parameters for Kellogg regressions: {', '.join(sorted(missing))}"
        )
    assert volume_per_load_m3 is not None
    assert distance_out_m is not None
    assert travel_in_unit_m is not None
    assert distance_in_m is not None

    load_type = _MODEL_TO_LOAD[model]
    value = estimate_forwarder_productivity_kellogg_bettinger(
        load_type=load_type,
        volume_per_load_m3=volume_per_load_m3,
        distance_out_m=distance_out_m,
        travel_in_unit_m=travel_in_unit_m,
        distance_in_m=distance_in_m,
    )
    params = {
        "load_type": load_type.value,
        "volume_per_load_m3": volume_per_load_m3,
        "distance_out_m": distance_out_m,
        "travel_in_unit_m": travel_in_unit_m,
        "distance_in_m": distance_in_m,
    }
    return ForwarderBCResult(
        model=model,
        predicted_m3_per_pmh=value,
        reference="Kellogg & Bettinger 1994 (FMG 910)",
        parameters=params,
    )


def _estimate_forwarder_productivity_adv6n10(
    *,
    payload_m3: float,
    mean_log_length_m: float,
    travel_speed_m_per_min: float,
    trail_length_m: float,
    products_per_trail: float,
) -> float:
    if payload_m3 <= 0:
        raise ValueError("payload_m3 must be > 0")
    if mean_log_length_m <= 0:
        raise ValueError("mean_log_length_m must be > 0")
    if travel_speed_m_per_min <= 0:
        raise ValueError("travel_speed_m_per_min must be > 0")
    if trail_length_m <= 0:
        raise ValueError("trail_length_m must be > 0")
    if products_per_trail <= 0:
        raise ValueError("products_per_trail must be > 0")

    def _loading_time() -> float:
        denom = (-0.1163 * mean_log_length_m**2) + (1.162 * mean_log_length_m) - 1.683
        if denom <= 0:
            raise ValueError("Loading denominator must be > 0; check mean_log_length_m")
        return payload_m3 / denom

    def _unloading_time() -> float:
        denom = (-0.1243 * mean_log_length_m**2) + (1.3484 * mean_log_length_m) - 1.8446
        if denom <= 0:
            raise ValueError("Unloading denominator must be > 0; check mean_log_length_m")
        return payload_m3 / denom

    def _travel_time() -> float:
        return (
            1.11
            * (travel_speed_m_per_min ** -0.935)
            * (products_per_trail**0.19)
            * (trail_length_m**1.016)
        )

    loading = _loading_time()
    unloading = _unloading_time()
    travel = _travel_time()
    total_minutes = loading + unloading + travel
    if total_minutes <= 0:
        raise ValueError("Total cycle minutes must be > 0")

    productivity = 60.0 * payload_m3 / total_minutes
    if productivity <= 0:
        raise ValueError("derived productivity must be > 0")
    return productivity


__all__ = [
    "ForwarderBCModel",
    "ForwarderBCResult",
    "estimate_forwarder_productivity_bc",
]
