"""Roadside processor and loader productivity helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

_TREE_FORM_PRODUCTIVITY_MULTIPLIERS = {
    0: 1.0,
    1: 1.0 / 1.56,  # 56 % longer processing time → productivity ↓ by 1/1.56
    2: 1.0 / 1.84,  # 84 % longer processing time → productivity ↓ by 1/1.84
}

_BERRY_BASE_SLOPE = 34.7
_BERRY_BASE_INTERCEPT = 11.3
_BERRY_DEFAULT_UTILISATION = 0.91


@dataclass(frozen=True)
class ProcessorProductivityResult:
    base_productivity_m3_per_pmh: float
    tree_form_multiplier: float
    crew_multiplier: float
    delay_multiplier: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float
    piece_size_m3: float
    tree_form_category: int


def estimate_processor_productivity_berry2019(
    *,
    piece_size_m3: float,
    tree_form_category: int = 0,
    crew_multiplier: float = 1.0,
    delay_multiplier: float = _BERRY_DEFAULT_UTILISATION,
) -> ProcessorProductivityResult:
    if piece_size_m3 <= 0:
        raise ValueError("piece_size_m3 must be > 0")
    if tree_form_category not in _TREE_FORM_PRODUCTIVITY_MULTIPLIERS:
        raise ValueError("tree_form_category must be 0, 1, or 2")
    if crew_multiplier <= 0:
        raise ValueError("crew_multiplier must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    base_productivity = _BERRY_BASE_SLOPE * piece_size_m3 + _BERRY_BASE_INTERCEPT
    tree_multiplier = _TREE_FORM_PRODUCTIVITY_MULTIPLIERS[tree_form_category]
    delay_free = base_productivity * tree_multiplier * crew_multiplier
    productivity = delay_free * delay_multiplier

    return ProcessorProductivityResult(
        base_productivity_m3_per_pmh=base_productivity,
        tree_form_multiplier=tree_multiplier,
        crew_multiplier=crew_multiplier,
        delay_multiplier=delay_multiplier,
        delay_free_productivity_m3_per_pmh=delay_free,
        productivity_m3_per_pmh=productivity,
        piece_size_m3=piece_size_m3,
        tree_form_category=tree_form_category,
    )


@dataclass(frozen=True)
class Labelle2019ProcessorProductivityResult:
    species: Literal["spruce", "beech"]
    treatment: Literal["clear_cut", "selective_cut"]
    dbh_cm: float
    intercept: float
    linear: float
    quadratic: float
    sample_trees: int
    delay_multiplier: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float


@dataclass(frozen=True)
class _Labelle2019Polynomial:
    intercept: float
    linear: float
    quadratic: float
    sample_trees: int
    description: str


_LABELLE2019_DBH_MODELS: dict[tuple[str, str], _Labelle2019Polynomial] = {
    ("spruce", "clear_cut"): _Labelle2019Polynomial(
        intercept=-70.18,
        linear=5.301,
        quadratic=-0.06052,
        sample_trees=15,
        description="Labelle et al. (2019) — clear-cut spruce (Bavaria, Germany)",
    ),
    ("beech", "clear_cut"): _Labelle2019Polynomial(
        intercept=-7.87,
        linear=2.638,
        quadratic=-0.04544,
        sample_trees=15,
        description="Labelle et al. (2019) — clear-cut beech (Bavaria, Germany)",
    ),
    ("spruce", "selective_cut"): _Labelle2019Polynomial(
        intercept=-22.24,
        linear=1.482,
        quadratic=-0.00433,
        sample_trees=22,
        description="Labelle et al. (2019) — group-selection spruce (Bavaria, Germany)",
    ),
    ("beech", "selective_cut"): _Labelle2019Polynomial(
        intercept=1.12,
        linear=0.891,
        quadratic=-0.00783,
        sample_trees=30,
        description="Labelle et al. (2019) — group-selection beech (Bavaria, Germany)",
    ),
}


def estimate_processor_productivity_labelle2019_dbh(
    *,
    species: Literal["spruce", "beech"],
    treatment: Literal["clear_cut", "selective_cut"],
    dbh_cm: float,
    delay_multiplier: float = 1.0,
) -> Labelle2019ProcessorProductivityResult:
    """Labelle et al. (2019) Bavarian hardwood processor regressions (DBH polynomial).

    The underlying time-and-motion study covered a TimberPro 620-E with a LogMax 7000C
    harvesting head working in large-diameter, hardwood-dominated stands (clear-cut and
    selection-cut prescriptions). Output units are delay-free m³/PMH₀; the optional
    ``delay_multiplier`` lets analysts enforce utilisation assumptions when wiring the
    results into costing models.
    """

    if dbh_cm <= 0:
        raise ValueError("dbh_cm must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    key = (species.lower(), treatment.lower())
    if key not in _LABELLE2019_DBH_MODELS:
        valid = ", ".join(
            f"{spec}/{treatment}" for spec, treatment in sorted(_LABELLE2019_DBH_MODELS)
        )
        raise ValueError(f"Unknown species/treatment combination {key!r}. Valid pairs: {valid}")

    coeffs = _LABELLE2019_DBH_MODELS[key]
    delay_free = coeffs.intercept + coeffs.linear * dbh_cm + coeffs.quadratic * (dbh_cm**2)
    delay_free = max(0.0, delay_free)
    productivity = delay_free * delay_multiplier

    return Labelle2019ProcessorProductivityResult(
        species=key[0],
        treatment=key[1],
        dbh_cm=dbh_cm,
        intercept=coeffs.intercept,
        linear=coeffs.linear,
        quadratic=coeffs.quadratic,
        sample_trees=coeffs.sample_trees,
        delay_multiplier=delay_multiplier,
        delay_free_productivity_m3_per_pmh=delay_free,
        productivity_m3_per_pmh=productivity,
    )


_LOADER_INTERCEPT = 6.89172291
_LOADER_PIECE_EXP = 0.40841215
_LOADER_DISTANCE_EXP = -0.60174944
_LOADER_BUNCHED_MULTIPLIER = 1.0
_LOADER_HAND_MULTIPLIER = 0.90


@dataclass(frozen=True)
class LoaderForwarderProductivityResult:
    piece_size_m3: float
    external_distance_m: float
    slope_percent: float
    bunched: bool
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float
    slope_multiplier: float
    bunched_multiplier: float
    delay_multiplier: float


def _loader_slope_multiplier(slope_percent: float) -> float:
    factor = slope_percent / 100.0
    if factor >= 0:
        return max(0.6, 1.0 - 0.3 * factor)
    return min(1.15, 1.0 + 0.15 * abs(factor))


def estimate_loader_forwarder_productivity_tn261(
    *,
    piece_size_m3: float,
    external_distance_m: float,
    slope_percent: float = 0.0,
    bunched: bool = True,
    delay_multiplier: float = 1.0,
) -> LoaderForwarderProductivityResult:
    if piece_size_m3 <= 0:
        raise ValueError("piece_size_m3 must be > 0")
    if external_distance_m <= 0:
        raise ValueError("external_distance_m must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    slope_mult = _loader_slope_multiplier(slope_percent)
    base = math.exp(_LOADER_INTERCEPT)
    delay_free = (
        base
        * (piece_size_m3 ** _LOADER_PIECE_EXP)
        * (external_distance_m ** _LOADER_DISTANCE_EXP)
        * slope_mult
        * (_LOADER_BUNCHED_MULTIPLIER if bunched else _LOADER_HAND_MULTIPLIER)
    )
    productivity = delay_free * delay_multiplier
    return LoaderForwarderProductivityResult(
        piece_size_m3=piece_size_m3,
        external_distance_m=external_distance_m,
        slope_percent=slope_percent,
        bunched=bunched,
        delay_free_productivity_m3_per_pmh=delay_free,
        productivity_m3_per_pmh=productivity,
        slope_multiplier=slope_mult,
        bunched_multiplier=_LOADER_BUNCHED_MULTIPLIER if bunched else _LOADER_HAND_MULTIPLIER,
        delay_multiplier=delay_multiplier,
    )
