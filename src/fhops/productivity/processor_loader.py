"""Roadside processor and loader productivity helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fhops.costing.inflation import inflate_value

_DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "productivity"
_BERRY_DATA_PATH = _DATA_ROOT / "processor_berry2019.json"
_ADV5N6_DATA_PATH = _DATA_ROOT / "processor_adv5n6.json"
_TN103_DATA_PATH = _DATA_ROOT / "processor_tn103.json"
_TR87_DATA_PATH = _DATA_ROOT / "processor_tr87.json"
_TN166_DATA_PATH = _DATA_ROOT / "processor_tn166.json"
_BARKO450_DATA_PATH = _DATA_ROOT / "loader_barko450.json"
@lru_cache(maxsize=1)
def _load_berry_dataset() -> dict[str, object]:
    try:
        return json.loads(_BERRY_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"Berry (2019) processor data missing: {_BERRY_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_adv5n6_dataset() -> dict[str, object]:
    try:
        return json.loads(_ADV5N6_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"ADV5N6 processor data missing: {_ADV5N6_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_tn166_dataset() -> dict[str, object]:
    try:
        return json.loads(_TN166_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"TN-166 processor data missing: {_TN166_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_barko450_dataset() -> dict[str, object]:
    try:
        return json.loads(_BARKO450_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"Barko 450 loader data missing: {_BARKO450_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_tn103_dataset() -> dict[str, object]:
    try:
        return json.loads(_TN103_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"TN-103 processor data missing: {_TN103_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_tr87_dataset() -> dict[str, object]:
    try:
        return json.loads(_TR87_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"TR-87 processor data missing: {_TR87_DATA_PATH}") from exc


def _load_tree_form_productivity_multipliers() -> dict[int, float]:
    data = _load_berry_dataset()
    tree_form = data.get("tree_form") or {}
    rel = tree_form.get("relative_processing_time")
    if not rel:
        raise KeyError("Berry (2019) dataset missing tree form multipliers.")
    multipliers: dict[int, float] = {}
    for category in (0, 1, 2):
        key = f"category_{category}_multiplier"
        time_multiplier = rel.get(key)
        if time_multiplier is None or time_multiplier <= 0:
            raise ValueError(f"Invalid tree form multiplier '{key}' in Berry dataset.")
        multipliers[category] = 1.0 / time_multiplier
    return multipliers


def _load_piece_size_regression() -> tuple[float, float]:
    data = _load_berry_dataset()
    regression = data.get("piece_size_regression")
    if not regression:
        raise KeyError("Berry (2019) dataset missing piece-size regression.")
    slope = regression.get("slope_m3_per_hour_per_m3")
    intercept = regression.get("intercept_m3_per_hour")
    if slope is None or intercept is None:
        raise KeyError("Berry (2019) regression missing slope/intercept fields.")
    return float(slope), float(intercept)


def _load_default_utilisation() -> float:
    utilisation = _load_berry_dataset().get("utilisation") or {}
    percent = utilisation.get("utilisation_percent", 91.0)
    return float(percent) / 100.0


def _load_skid_size_models() -> tuple[
    dict[str, float],
    dict[str, float] | None,
    float,
    tuple[float, float] | None,
]:
    data = _load_berry_dataset()
    skid = data.get("skid_size")
    if not skid:
        raise KeyError("Berry (2019) dataset missing skid-size section.")
    delay_model = skid.get("delay_per_stem_equation")
    if not delay_model:
        raise KeyError("Berry (2019) dataset missing skid delay model.")
    productivity_model = skid.get("productivity_equation")
    outlier = skid.get("outlier_test") or {}
    baseline_delay = float(outlier.get("mean_seconds", 10.9))
    area_range = skid.get("area_range_m2")
    area_tuple = None
    if isinstance(area_range, dict):
        area_tuple = (
            float(area_range.get("min", float("-inf"))),
            float(area_range.get("max", float("inf"))),
        )
    return delay_model, productivity_model, baseline_delay, area_tuple


def predict_berry2019_skid_effects(
    skid_area_m2: float,
) -> tuple[float, float | None, float, tuple[float, float] | None, float | None, float | None]:
    if skid_area_m2 <= 0:
        raise ValueError("Skid area must be > 0.")
    delay_model, productivity_model, baseline_delay, area_range = _load_skid_size_models()
    slope = float(delay_model.get("slope_seconds_per_m2", 0.0))
    intercept = float(delay_model.get("intercept_seconds", 0.0))
    delay_seconds = max(intercept + slope * skid_area_m2, 0.1)
    delay_r2 = delay_model.get("r2")

    predicted_productivity = None
    productivity_r2 = None
    if productivity_model:
        prod_slope = float(productivity_model.get("slope_m3_per_hour_per_m2", 0.0))
        prod_intercept = float(productivity_model.get("intercept_m3_per_hour", 0.0))
        predicted_productivity = prod_intercept + prod_slope * skid_area_m2
        productivity_r2 = productivity_model.get("r2")

    return (
        delay_seconds,
        predicted_productivity,
        baseline_delay,
        area_range,
        delay_r2,
        productivity_r2,
    )


@lru_cache(maxsize=1)
def _load_adv5n6_scenarios() -> dict[str, dict[str, object]]:
    payload = _load_adv5n6_dataset()
    cost_meta = payload.get("costing") or {}
    base_year = cost_meta.get("base_year")
    scenarios: dict[str, dict[str, object]] = {}
    for entry in payload.get("scenarios", []):
        scenario = dict(entry)
        scenario.setdefault("cost_base_year", base_year)
        scenarios[scenario["name"]] = scenario
    return scenarios


@lru_cache(maxsize=1)
def _load_tn103_scenarios() -> dict[str, dict[str, object]]:
    payload = _load_tn103_dataset()
    defaults = payload.get("defaults") or {}
    cost_meta = payload.get("costing") or {}
    base_year = cost_meta.get("base_year")
    scenarios: dict[str, dict[str, object]] = {}
    for entry in payload.get("scenarios", []):
        combined = {**defaults, **entry}
        combined.setdefault("cost_base_year", base_year)
        scenarios[entry["name"]] = combined
    return scenarios


@lru_cache(maxsize=1)
def _load_tn166_scenarios() -> dict[str, dict[str, object]]:
    payload = _load_tn166_dataset()
    defaults = payload.get("defaults") or {}
    cycle = payload.get("cycle_time_minutes")
    accuracy = payload.get("accuracy")
    cost_meta = payload.get("costing") or {}
    base_year = cost_meta.get("base_year")
    scenarios: dict[str, dict[str, object]] = {}
    for entry in payload.get("scenarios", []):
        combined = {**defaults, **entry}
        if cycle and "cycle_time_minutes" not in combined:
            combined["cycle_time_minutes"] = cycle
        if accuracy and "accuracy" not in combined:
            combined["accuracy"] = accuracy
        combined.setdefault("cost_base_year", base_year)
        scenarios[entry["name"]] = combined
    return scenarios


@lru_cache(maxsize=1)
def _load_barko450_scenarios() -> dict[str, dict[str, object]]:
    payload = _load_barko450_dataset()
    utilisation = payload.get("utilisation") or {}
    cost_meta = payload.get("costing") or {}
    base_year = cost_meta.get("base_year")
    scenarios: dict[str, dict[str, object]] = {}
    for entry in payload.get("scenarios", []):
        combined = {**utilisation, **entry}
        combined.setdefault("cost_base_year", base_year)
        scenarios[entry["name"]] = combined
    return scenarios


@lru_cache(maxsize=1)
def _load_tr87_scenarios() -> dict[str, dict[str, object]]:
    payload = _load_tr87_dataset()
    defaults = payload.get("defaults") or {}
    cost_meta = payload.get("costing") or {}
    base_year = cost_meta.get("base_year")
    scenarios: dict[str, dict[str, object]] = {}
    for entry in payload.get("scenarios", []):
        combined = {**defaults, **entry}
        combined.setdefault("cost_base_year", base_year)
        scenarios[entry["name"]] = combined
    return scenarios


_TREE_FORM_PRODUCTIVITY_MULTIPLIERS = _load_tree_form_productivity_multipliers()
_BERRY_BASE_SLOPE, _BERRY_BASE_INTERCEPT = _load_piece_size_regression()
_BERRY_DEFAULT_UTILISATION = _load_default_utilisation()


def _inflate_cost(value: float | None, base_year: int | None) -> float | None:
    if value is None:
        return None
    if base_year is None:
        return float(value)
    return inflate_value(float(value), base_year)


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


@dataclass(frozen=True)
class Labelle2016ProcessorProductivityResult:
    tree_form: Literal["acceptable", "unacceptable"]
    dbh_cm: float
    coefficient_a: float
    exponent_b: float
    sample_trees: int
    delay_multiplier: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float


_LABELLE2016_TREEFORM_MODELS: dict[str, tuple[float, float, int]] = {
    "acceptable": (1.0273, 0.8319, 54),
    "unacceptable": (0.7976, 0.8588, 55),
}


def estimate_processor_productivity_labelle2016(
    *,
    tree_form: Literal["acceptable", "unacceptable"],
    dbh_cm: float,
    delay_multiplier: float = 1.0,
) -> Labelle2016ProcessorProductivityResult:
    """Labelle et al. (2016) sugar maple processor regressions grouped by tree form."""

    if dbh_cm <= 0:
        raise ValueError("dbh_cm must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    key = tree_form.lower()
    if key not in _LABELLE2016_TREEFORM_MODELS:
        valid = ", ".join(sorted(_LABELLE2016_TREEFORM_MODELS))
        raise ValueError(f"Unknown tree form '{tree_form}'. Valid options: {valid}")

    coeff_a, exponent_b, sample_count = _LABELLE2016_TREEFORM_MODELS[key]
    delay_free = coeff_a * (dbh_cm**exponent_b)
    productivity = delay_free * delay_multiplier

    return Labelle2016ProcessorProductivityResult(
        tree_form=key,
        dbh_cm=dbh_cm,
        coefficient_a=coeff_a,
        exponent_b=exponent_b,
        sample_trees=sample_count,
        delay_multiplier=delay_multiplier,
        delay_free_productivity_m3_per_pmh=delay_free,
        productivity_m3_per_pmh=productivity,
    )


@dataclass(frozen=True)
class Labelle2017PolynomialProcessorResult:
    variant: str
    dbh_cm: float
    intercept: float
    linear: float
    quadratic_coeff: float
    quadratic_exponent: float
    cubic_coeff: float
    cubic_exponent: float
    sample_trees: int
    delay_multiplier: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float


@dataclass(frozen=True)
class Labelle2017PowerProcessorResult:
    variant: str
    dbh_cm: float
    coefficient: float
    exponent: float
    sample_trees: int
    delay_multiplier: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float


_LABELLE2017_POLY_MODELS: dict[str, tuple[float, float, float, float, float, int]] = {
    "poly1": (27.67, 5.1784, 0.3017, 0.0039, 0.0, 338),
    "poly2": (7.2145, 2.3227, 0.1802, 0.0023, 0.0, 365),
}
# tuple fields: intercept, linear_coeff (positive, subtract), quadratic_coeff, cubic_coeff, placeholder, sample count
# NB: quadratic exponent = 2, cubic exponent = 3 per appendix values.

_LABELLE2017_POWER_MODELS: dict[str, tuple[float, float, int]] = {
    "power1": (0.0071, 2.4652, 42),
    "power2": (0.005, 2.629, 55),
}


def estimate_processor_productivity_labelle2017(
    *,
    variant: Literal["poly1", "poly2", "power1", "power2"],
    dbh_cm: float,
    delay_multiplier: float = 1.0,
) -> Labelle2017PolynomialProcessorResult | Labelle2017PowerProcessorResult:
    """Labelle et al. (2017) hardwood processor regressions (power/polynomial DBH forms)."""

    if dbh_cm <= 0:
        raise ValueError("dbh_cm must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    variant_key = variant.lower()
    if variant_key in _LABELLE2017_POLY_MODELS:
        (
            intercept,
            linear_coeff,
            quadratic_coeff,
            cubic_coeff,
            _,
            sample_count,
        ) = _LABELLE2017_POLY_MODELS[variant_key]
        delay_free = (
            intercept
            - linear_coeff * dbh_cm
            + quadratic_coeff * (dbh_cm**2)
            - cubic_coeff * (dbh_cm**3)
        )
        delay_free = max(0.0, delay_free)
        productivity = delay_free * delay_multiplier
        return Labelle2017PolynomialProcessorResult(
            variant=variant_key,
            dbh_cm=dbh_cm,
            intercept=intercept,
            linear=linear_coeff,
            quadratic_coeff=quadratic_coeff,
            quadratic_exponent=2.0,
            cubic_coeff=cubic_coeff,
            cubic_exponent=3.0,
            sample_trees=sample_count,
            delay_multiplier=delay_multiplier,
            delay_free_productivity_m3_per_pmh=delay_free,
            productivity_m3_per_pmh=productivity,
        )

    if variant_key in _LABELLE2017_POWER_MODELS:
        coefficient, exponent, sample_count = _LABELLE2017_POWER_MODELS[variant_key]
        delay_free = coefficient * (dbh_cm**exponent)
        productivity = delay_free * delay_multiplier
        return Labelle2017PowerProcessorResult(
            variant=variant_key,
            dbh_cm=dbh_cm,
            coefficient=coefficient,
            exponent=exponent,
            sample_trees=sample_count,
            delay_multiplier=delay_multiplier,
            delay_free_productivity_m3_per_pmh=delay_free,
            productivity_m3_per_pmh=productivity,
        )

    valid = ", ".join(sorted({* _LABELLE2017_POLY_MODELS.keys(), *_LABELLE2017_POWER_MODELS.keys()}))
    raise ValueError(f"Unknown Labelle 2017 variant '{variant}'. Valid options: {valid}.")


@dataclass(frozen=True)
class Labelle2018ProcessorProductivityResult:
    variant: str
    dbh_cm: float
    intercept: float
    linear: float
    quadratic: float
    sample_trees: int
    delay_multiplier: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float


_LABELLE2018_MODELS: dict[str, tuple[float, float, float, int]] = {
    "rw_poly1": (15.15, 2.53, 0.02, 56),
    "rw_poly2": (42.42, 3.61, 0.04, 67),
    "ct_poly1": (61.26, 4.56, 0.047, 48),
    "ct_poly2": (42.72, 3.68, 0.04, 72),
}


def estimate_processor_productivity_labelle2018(
    *,
    variant: Literal["rw_poly1", "rw_poly2", "ct_poly1", "ct_poly2"],
    dbh_cm: float,
    delay_multiplier: float = 1.0,
) -> Labelle2018ProcessorProductivityResult:
    """Labelle et al. (2018) Bavarian hardwood processor regressions (DBH polynomial)."""

    if dbh_cm <= 0:
        raise ValueError("dbh_cm must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    coeffs = _LABELLE2018_MODELS.get(variant.lower())
    if coeffs is None:
        valid = ", ".join(sorted(_LABELLE2018_MODELS))
        raise ValueError(f"Unknown Labelle 2018 variant '{variant}'. Valid options: {valid}")

    intercept, linear, quadratic, sample_trees = coeffs
    delay_free = -intercept + linear * dbh_cm - quadratic * (dbh_cm**2)
    delay_free = max(0.0, delay_free)
    productivity = delay_free * delay_multiplier

    return Labelle2018ProcessorProductivityResult(
        variant=variant.lower(),
        dbh_cm=dbh_cm,
        intercept=intercept,
        linear=linear,
        quadratic=quadratic,
        sample_trees=sample_trees,
        delay_multiplier=delay_multiplier,
        delay_free_productivity_m3_per_pmh=delay_free,
        productivity_m3_per_pmh=productivity,
    )


@dataclass(frozen=True)
class Labelle2019VolumeProcessorProductivityResult:
    species: Literal["spruce", "beech"]
    treatment: Literal["clear_cut", "selective_cut"]
    volume_m3: float
    intercept: float
    linear: float
    quadratic: float
    exponent: float
    sample_trees: int
    delay_multiplier: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float


@dataclass(frozen=True)
class _Labelle2019VolumePolynomial:
    intercept: float
    linear: float
    quadratic: float
    exponent: float
    sample_trees: int


_LABELLE2019_VOLUME_MODELS: dict[tuple[str, str], _Labelle2019VolumePolynomial] = {
    ("spruce", "clear_cut"): _Labelle2019VolumePolynomial(
        intercept=2.938,
        linear=54.87,
        quadratic=16.56,
        exponent=2.0,
        sample_trees=15,
    ),
    ("beech", "clear_cut"): _Labelle2019VolumePolynomial(
        intercept=18.17,
        linear=31.92,
        quadratic=20.63,
        exponent=2.0,
        sample_trees=15,
    ),
    ("spruce", "selective_cut"): _Labelle2019VolumePolynomial(
        intercept=5.573,
        linear=20.18,
        quadratic=1.835,
        exponent=2.0,
        sample_trees=22,
    ),
    ("beech", "selective_cut"): _Labelle2019VolumePolynomial(
        intercept=4.743,
        linear=17.44,
        quadratic=2.445,
        exponent=2.0,
        sample_trees=30,
    ),
}


def estimate_processor_productivity_labelle2019_volume(
    *,
    species: Literal["spruce", "beech"],
    treatment: Literal["clear_cut", "selective_cut"],
    volume_m3: float,
    delay_multiplier: float = 1.0,
) -> Labelle2019VolumeProcessorProductivityResult:
    """Labelle et al. (2019) hardwood processor regressions keyed to recovered volume (m³/stem)."""

    if volume_m3 <= 0:
        raise ValueError("volume_m3 must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    key = (species.lower(), treatment.lower())
    if key not in _LABELLE2019_VOLUME_MODELS:
        valid = ", ".join(
            f"{spec}/{treatment}" for spec, treatment in sorted(_LABELLE2019_VOLUME_MODELS)
        )
        raise ValueError(f"Unknown species/treatment combination {key!r}. Valid pairs: {valid}")

    coeffs = _LABELLE2019_VOLUME_MODELS[key]
    delay_free = (
        coeffs.intercept
        + coeffs.linear * volume_m3
        - coeffs.quadratic * (volume_m3**coeffs.exponent)
    )
    delay_free = max(0.0, delay_free)
    productivity = delay_free * delay_multiplier

    return Labelle2019VolumeProcessorProductivityResult(
        species=key[0],
        treatment=key[1],
        volume_m3=volume_m3,
        intercept=coeffs.intercept,
        linear=coeffs.linear,
        quadratic=coeffs.quadratic,
        exponent=coeffs.exponent,
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

ADV2N26_DEFAULT_TRAVEL_EMPTY_M = 236.0
ADV2N26_DEFAULT_STEMS_PER_CYCLE = 19.7
ADV2N26_DEFAULT_STEM_VOLUME_M3 = 1.52
ADV2N26_DEFAULT_UTILISATION = 0.77
ADV2N26_IN_CYCLE_DELAY_RATIO = 0.05
ADV5N1_DEFAULT_PAYLOAD_M3 = 2.77
ADV5N1_DEFAULT_UTILISATION = 0.93
_ADV5N1_COEFFICIENTS = {
    "0_10": (1.00, 0.0432),
    "11_30": (1.10, 0.0504),
}


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


@dataclass(frozen=True)
class ClambunkProductivityResult:
    travel_empty_distance_m: float
    stems_per_cycle: float
    average_stem_volume_m3: float
    payload_m3_per_cycle: float
    utilization: float
    delay_free_cycle_minutes: float
    in_cycle_delay_minutes: float
    total_cycle_minutes: float
    productivity_m3_per_pmh: float
    productivity_m3_per_smh: float


@dataclass(frozen=True)
class LoaderBarko450ProductivityResult:
    scenario: str
    description: str
    avg_volume_per_shift_m3: float
    avg_volume_per_load_m3: float | None
    total_volume_m3: float | None
    total_truck_loads: float | None
    monitoring_days: float | None
    utilisation_percent: float | None
    availability_percent: float | None
    wait_truck_move_sort_percent: float | None
    cost_per_shift_cad: float | None
    cost_per_m3_cad: float | None
    cost_per_piece_cad: float | None
    notes: tuple[str, ...] | None
    cost_base_year: int | None


def estimate_clambunk_productivity_adv2n26(
    *,
    travel_empty_distance_m: float,
    stems_per_cycle: float,
    average_stem_volume_m3: float = ADV2N26_DEFAULT_STEM_VOLUME_M3,
    payload_m3_per_cycle: float | None = None,
    utilization: float = ADV2N26_DEFAULT_UTILISATION,
    in_cycle_delay_minutes: float | None = None,
) -> ClambunkProductivityResult:
    """ADV2N26 clambunk regression (Kosicki 2001, Equation 1 & 2, coastal BC)."""

    if travel_empty_distance_m <= 0:
        raise ValueError("travel_empty_distance_m must be > 0")
    if stems_per_cycle <= 0:
        raise ValueError("stems_per_cycle must be > 0")
    if average_stem_volume_m3 <= 0:
        raise ValueError("average_stem_volume_m3 must be > 0")
    if payload_m3_per_cycle is not None and payload_m3_per_cycle <= 0:
        raise ValueError("payload_m3_per_cycle must be > 0 when specified.")
    if not (0.0 < utilization <= 1.0):
        raise ValueError("utilization must lie in (0, 1].")

    payload = (
        payload_m3_per_cycle
        if payload_m3_per_cycle is not None
        else stems_per_cycle * average_stem_volume_m3
    )
    delay_free_cycle = 7.17 + 0.0682 * travel_empty_distance_m + 0.396 * stems_per_cycle
    dt = (
        in_cycle_delay_minutes
        if in_cycle_delay_minutes is not None
        else delay_free_cycle * ADV2N26_IN_CYCLE_DELAY_RATIO
    )
    total_cycle = delay_free_cycle + dt
    productivity_pmh = payload * (60.0 / total_cycle)
    productivity_smh = productivity_pmh * utilization
    return ClambunkProductivityResult(
        travel_empty_distance_m=travel_empty_distance_m,
        stems_per_cycle=stems_per_cycle,
        average_stem_volume_m3=average_stem_volume_m3,
        payload_m3_per_cycle=payload,
        utilization=utilization,
        delay_free_cycle_minutes=delay_free_cycle,
        in_cycle_delay_minutes=dt,
        total_cycle_minutes=total_cycle,
        productivity_m3_per_pmh=productivity_pmh,
        productivity_m3_per_smh=productivity_smh,
    )


@dataclass(frozen=True)
class LoaderAdv5N1ProductivityResult:
    forwarding_distance_m: float
    slope_class: str
    payload_m3_per_cycle: float
    utilisation: float
    intercept: float
    slope: float
    cycle_time_minutes: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_smh: float


@dataclass(frozen=True)
class ADV5N6ProcessorProductivityResult:
    stem_source: str
    processing_mode: str
    description: str
    productivity_m3_per_pmh: float
    productivity_m3_per_smh: float
    stems_per_pmh: float | None
    stems_per_smh: float | None
    mean_stem_volume_m3: float | None
    utilisation_percent: float | None
    availability_percent: float | None
    shift_length_hours: float | None
    cost_cad_per_m3: float
    machine_rate_cad_per_smh: float | None
    notes: tuple[str, ...] | None
    cost_base_year: int | None


@dataclass(frozen=True)
class TN103ProcessorProductivityResult:
    scenario: str
    description: str
    stem_source: str
    mean_stem_volume_m3: float | None
    trees_per_pmh: float | None
    trees_per_smh: float | None
    productivity_m3_per_pmh: float | None
    productivity_m3_per_smh: float | None
    utilisation_percent: float | None
    volume_per_shift_m3: float | None
    cost_cad_per_m3: float | None
    cost_cad_per_tree: float | None
    notes: tuple[str, ...] | None
    cost_base_year: int | None


@dataclass(frozen=True)
class TN166ProcessorProductivityResult:
    scenario: str
    description: str
    stem_source: str
    processing_mode: str
    mean_stem_volume_m3: float | None
    productivity_m3_per_pmh: float
    productivity_m3_per_smh: float
    stems_per_pmh: float | None
    stems_per_smh: float | None
    utilisation_percent: float | None
    availability_percent: float | None
    shift_length_hours: float | None
    cost_cad_per_m3: float
    cost_cad_per_stem: float | None
    cycle_time_minutes: dict[str, float | str] | None
    notes: tuple[str, ...] | None
    cost_base_year: int | None


@dataclass(frozen=True)
class TR87ProcessorProductivityResult:
    scenario: str
    description: str
    stem_source: str
    shift_type: str | None
    mean_stem_volume_m3: float | None
    trees_per_pmh: float | None
    productivity_m3_per_pmh: float | None
    productivity_m3_per_smh: float | None
    utilisation_percent: float | None
    volume_per_shift_m3: float | None
    cost_cad_per_m3: float | None
    notes: tuple[str, ...] | None
    cost_base_year: int | None


def estimate_loader_forwarder_productivity_adv5n1(
    *,
    forwarding_distance_m: float,
    slope_class: str = "0_10",
    payload_m3_per_cycle: float = ADV5N1_DEFAULT_PAYLOAD_M3,
    utilisation: float = ADV5N1_DEFAULT_UTILISATION,
) -> LoaderAdv5N1ProductivityResult:
    """ADV5N1 loader-forwarder regression (Figure 9, coefficients manually digitised by the project team)."""

    if forwarding_distance_m <= 0:
        raise ValueError("forwarding_distance_m must be > 0")
    if payload_m3_per_cycle <= 0:
        raise ValueError("payload_m3_per_cycle must be > 0")
    if not (0.0 < utilisation <= 1.0):
        raise ValueError("utilisation must lie in (0, 1].")

    normalized_class = slope_class.lower().replace("-", "_")
    if normalized_class not in _ADV5N1_COEFFICIENTS:
        valid = ", ".join(sorted(_ADV5N1_COEFFICIENTS))
        raise ValueError(f"Unknown ADV5N1 slope class '{slope_class}'. Valid options: {valid}")

    intercept, slope = _ADV5N1_COEFFICIENTS[normalized_class]
    cycle_minutes = intercept + slope * forwarding_distance_m
    delay_free = payload_m3_per_cycle * (60.0 / cycle_minutes)
    productivity_smh = delay_free * utilisation
    return LoaderAdv5N1ProductivityResult(
        forwarding_distance_m=forwarding_distance_m,
        slope_class=normalized_class,
        payload_m3_per_cycle=payload_m3_per_cycle,
        utilisation=utilisation,
        intercept=intercept,
        slope=slope,
        cycle_time_minutes=cycle_minutes,
        delay_free_productivity_m3_per_pmh=delay_free,
        productivity_m3_per_smh=productivity_smh,
    )


def estimate_processor_productivity_adv5n6(
    *,
    stem_source: Literal["loader_forwarded", "grapple_yarded"],
    processing_mode: Literal["cold", "hot", "low_volume"],
) -> ADV5N6ProcessorProductivityResult:
    scenarios = _load_adv5n6_scenarios()
    if stem_source == "loader_forwarded":
        if processing_mode != "cold":
            raise ValueError(
                "ADV5N6 only contains loader-forwarded data for cold processing decks."
            )
        scenario_key = "loader_forwarded_cold"
    else:
        if processing_mode == "cold":
            scenario_key = "grapple_yarded_cold"
        elif processing_mode == "hot":
            scenario_key = "grapple_yarded_hot"
        elif processing_mode == "low_volume":
            scenario_key = "grapple_yarded_low_volume"
        else:
            raise ValueError(f"Unknown processing_mode '{processing_mode}'.")

    payload = scenarios.get(scenario_key)
    if payload is None:
        raise ValueError(f"ADV5N6 scenario '{scenario_key}' unavailable.")

    def _maybe(name: str) -> float | None:
        value = payload.get(name)
        return None if value is None else float(value)

    notes = payload.get("notes")
    cost_base_year = payload.get("cost_base_year")
    cost_cad_per_m3 = _inflate_cost(float(payload["cost_cad_per_m3"]), cost_base_year)
    machine_rate = _inflate_cost(_maybe("machine_rate_cad_per_smh"), cost_base_year)
    return ADV5N6ProcessorProductivityResult(
        stem_source=payload.get("stem_source", stem_source),
        processing_mode=payload.get("processing_mode", processing_mode),
        description=payload.get("description", ""),
        productivity_m3_per_pmh=float(payload["productivity_m3_per_pmh"]),
        productivity_m3_per_smh=float(payload["productivity_m3_per_smh"]),
        stems_per_pmh=_maybe("stems_per_pmh"),
        stems_per_smh=_maybe("stems_per_smh"),
        mean_stem_volume_m3=_maybe("mean_stem_volume_m3"),
        utilisation_percent=_maybe("utilisation_percent"),
        availability_percent=_maybe("availability_percent"),
        shift_length_hours=_maybe("shift_length_hours"),
        cost_cad_per_m3=cost_cad_per_m3 if cost_cad_per_m3 is not None else float(payload["cost_cad_per_m3"]),
        machine_rate_cad_per_smh=machine_rate,
        notes=tuple(notes) if notes else None,
        cost_base_year=cost_base_year,
    )


def estimate_processor_productivity_tn103(
    *,
    scenario: Literal[
        "area_a_feller_bunched",
        "area_b_handfelled",
        "combined_observed",
        "combined_high_util",
    ],
) -> TN103ProcessorProductivityResult:
    scenarios = _load_tn103_scenarios()
    payload = scenarios.get(scenario)
    if payload is None:
        valid = ", ".join(sorted(scenarios))
        raise ValueError(f"Unknown TN-103 scenario '{scenario}'. Valid options: {valid}.")

    def _maybe(name: str) -> float | None:
        value = payload.get(name)
        return None if value is None else float(value)

    notes = payload.get("notes")
    cost_base_year = payload.get("cost_base_year")
    cost_cad_per_m3 = _inflate_cost(_maybe("cost_cad_per_m3"), cost_base_year)
    cost_cad_per_tree = _inflate_cost(_maybe("cost_cad_per_tree"), cost_base_year)

    return TN103ProcessorProductivityResult(
        scenario=payload.get("name", scenario),
        description=payload.get("description", ""),
        stem_source=payload.get("stem_source", "mixed"),
        mean_stem_volume_m3=_maybe("mean_stem_volume_m3"),
        trees_per_pmh=_maybe("trees_per_pmh"),
        trees_per_smh=_maybe("trees_per_smh"),
        productivity_m3_per_pmh=_maybe("productivity_m3_per_pmh"),
        productivity_m3_per_smh=_maybe("productivity_m3_per_smh"),
        utilisation_percent=_maybe("utilisation_percent"),
        volume_per_shift_m3=_maybe("volume_per_shift_m3"),
        cost_cad_per_m3=cost_cad_per_m3,
        cost_cad_per_tree=cost_cad_per_tree,
        notes=tuple(notes) if notes else None,
        cost_base_year=cost_base_year,
    )


def estimate_processor_productivity_tn166(
    *, scenario: Literal["grapple_yarded", "right_of_way", "mixed_shift"]
) -> TN166ProcessorProductivityResult:
    scenarios = _load_tn166_scenarios()
    payload = scenarios.get(scenario)
    if payload is None:
        valid = ", ".join(sorted(scenarios))
        raise ValueError(f"Unknown TN-166 scenario '{scenario}'. Valid options: {valid}.")

    def _maybe(name: str) -> float | None:
        value = payload.get(name)
        return None if value is None else float(value)

    notes = payload.get("notes")
    cycle_minutes = payload.get("cycle_time_minutes")
    cycle_dict: dict[str, float | str] | None = None
    if isinstance(cycle_minutes, dict):
        cycle_dict = {}
        for key, value in cycle_minutes.items():
            if isinstance(value, (int, float)):
                cycle_dict[key] = float(value)
            else:
                cycle_dict[key] = value
    cost_base_year = payload.get("cost_base_year")
    cost_m3 = _inflate_cost(float(payload["cost_cad_per_m3"]), cost_base_year)
    cost_stem = _inflate_cost(_maybe("cost_cad_per_stem"), cost_base_year)
    return TN166ProcessorProductivityResult(
        scenario=payload.get("name", scenario),
        description=payload.get("description", ""),
        stem_source=payload.get("stem_source", scenario),
        processing_mode=payload.get("processing_mode", ""),
        mean_stem_volume_m3=_maybe("mean_stem_volume_m3"),
        productivity_m3_per_pmh=float(payload["productivity_m3_per_pmh"]),
        productivity_m3_per_smh=float(payload["productivity_m3_per_smh"]),
        stems_per_pmh=_maybe("stems_per_pmh"),
        stems_per_smh=_maybe("stems_per_smh"),
        utilisation_percent=_maybe("utilisation_percent"),
        availability_percent=_maybe("availability_percent"),
        shift_length_hours=_maybe("shift_length_hours"),
        cost_cad_per_m3=cost_m3 if cost_m3 is not None else float(payload["cost_cad_per_m3"]),
        cost_cad_per_stem=cost_stem,
        cycle_time_minutes=cycle_dict,
        notes=tuple(notes) if notes else None,
        cost_base_year=cost_base_year,
    )


def estimate_processor_productivity_tr87(
    *,
    scenario: Literal[
        "tj90_day_shift",
        "tj90_night_shift",
        "tj90_combined_observed",
        "tj90_both_processors_observed",
        "tj90_both_processors_wait_adjusted",
    ],
) -> TR87ProcessorProductivityResult:
    scenarios = _load_tr87_scenarios()
    payload = scenarios.get(scenario)
    if payload is None:
        valid = ", ".join(sorted(scenarios))
        raise ValueError(f"Unknown TR-87 scenario '{scenario}'. Valid options: {valid}.")

    def _maybe(name: str) -> float | None:
        value = payload.get(name)
        return None if value is None else float(value)

    notes = payload.get("notes")
    cost_base_year = payload.get("cost_base_year")
    cost_cad_per_m3 = _inflate_cost(_maybe("cost_cad_per_m3"), cost_base_year)
    return TR87ProcessorProductivityResult(
        scenario=payload.get("name", scenario),
        description=payload.get("description", ""),
        stem_source=payload.get("stem_source", "grapple_yarded"),
        shift_type=payload.get("shift_type"),
        mean_stem_volume_m3=_maybe("mean_stem_volume_m3"),
        trees_per_pmh=_maybe("trees_per_pmh"),
        productivity_m3_per_pmh=_maybe("productivity_m3_per_pmh"),
        productivity_m3_per_smh=_maybe("productivity_m3_per_smh"),
        utilisation_percent=_maybe("utilisation_percent"),
        volume_per_shift_m3=_maybe("volume_per_shift_m3"),
        cost_cad_per_m3=cost_cad_per_m3,
        notes=tuple(notes) if notes else None,
        cost_base_year=cost_base_year,
    )


def estimate_loader_productivity_barko450(
    *,
    scenario: Literal["ground_skid_block", "cable_yard_block"],
    utilisation_override: float | None = None,
) -> LoaderBarko450ProductivityResult:
    scenarios = _load_barko450_scenarios()
    payload = scenarios.get(scenario)
    if payload is None:
        valid = ", ".join(sorted(scenarios))
        raise ValueError(f"Unknown Barko 450 scenario '{scenario}'. Valid options: {valid}.")
    if utilisation_override is not None and not (0.0 < utilisation_override <= 1.0):
        raise ValueError("utilisation_override must lie in (0, 1].")

    def _maybe_float(name: str) -> float | None:
        value = payload.get(name)
        return None if value is None else float(value)

    notes = payload.get("notes")
    cost_base_year = payload.get("cost_base_year")
    cost_per_shift = _inflate_cost(_maybe_float("cost_per_shift_cad"), cost_base_year)
    cost_per_m3 = _inflate_cost(_maybe_float("cost_per_m3_cad"), cost_base_year)
    cost_per_piece = _inflate_cost(_maybe_float("cost_per_piece_cad"), cost_base_year)
    avg_volume_per_shift = float(payload["avg_volume_per_shift_m3"])
    utilisation_percent = _maybe_float("utilisation_percent")
    scale = 1.0
    if utilisation_override is not None:
        if utilisation_percent is not None and utilisation_percent > 0:
            base_fraction = utilisation_percent / 100.0
            scale = utilisation_override / base_fraction if base_fraction > 0 else 1.0
        utilisation_percent = utilisation_override * 100.0
    if scale != 1.0:
        avg_volume_per_shift *= scale
        if cost_per_m3 is not None and scale != 0:
            cost_per_m3 /= scale
        if cost_per_piece is not None and scale != 0:
            cost_per_piece /= scale

    return LoaderBarko450ProductivityResult(
        scenario=payload.get("name", scenario),
        description=payload.get("description", ""),
        avg_volume_per_shift_m3=avg_volume_per_shift,
        avg_volume_per_load_m3=_maybe_float("avg_volume_per_load_m3"),
        total_volume_m3=_maybe_float("total_volume_m3"),
        total_truck_loads=_maybe_float("total_truck_loads"),
        monitoring_days=_maybe_float("monitoring_days"),
        utilisation_percent=utilisation_percent,
        availability_percent=_maybe_float("mechanical_availability_percent"),
        wait_truck_move_sort_percent=_maybe_float("wait_truck_move_sort_percent"),
        cost_per_shift_cad=cost_per_shift,
        cost_per_m3_cad=cost_per_m3,
        cost_per_piece_cad=cost_per_piece,
        notes=tuple(notes) if notes else None,
        cost_base_year=cost_base_year,
    )
