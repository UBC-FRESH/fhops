"""Roadside processor and loader productivity helpers."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fhops.costing.inflation import inflate_value

_DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "productivity"
_REFERENCE_ROOT = Path(__file__).resolve().parents[3] / "data" / "reference"
_BERRY_DATA_PATH = _DATA_ROOT / "processor_berry2019.json"
_BERRY_LOG_GRADES_PATH = _REFERENCE_ROOT / "berry2019_log_grade_emmeans.json"
_ADV5N6_DATA_PATH = _DATA_ROOT / "processor_adv5n6.json"
_ADV7N3_DATA_PATH = _DATA_ROOT / "processor_adv7n3.json"
_TN103_DATA_PATH = _DATA_ROOT / "processor_tn103.json"
_TR87_DATA_PATH = _DATA_ROOT / "processor_tr87.json"
_TR106_DATA_PATH = _DATA_ROOT / "processor_tr106.json"
_TN166_DATA_PATH = _DATA_ROOT / "processor_tn166.json"
_VISSER2015_DATA_PATH = _DATA_ROOT / "processor_visser2015.json"
_SPINELLI2010_DATA_PATH = _DATA_ROOT / "processor_spinelli2010.json"
_KIZHA2020_DATA_PATH = _DATA_ROOT / "loader_kizha2020.json"
_BARKO450_DATA_PATH = _DATA_ROOT / "loader_barko450.json"
_HYPRO775_DATA_PATH = _DATA_ROOT / "processor_hypro775.json"
_LABELLE_HUSS_DATA_PATH = _REFERENCE_ROOT / "processor_labelle_huss2018.json"
_BERTONE2025_DATA_PATH = _DATA_ROOT / "processor_bertone2025.json"
_BORZ2023_DATA_PATH = _DATA_ROOT / "processor_borz2023.json"
_NAKAGAWA2010_DATA_PATH = _DATA_ROOT / "processor_nakagawa2010.json"
_CARRIER_PROFILE_PATH = _REFERENCE_ROOT / "processor_carrier_profiles.json"


@lru_cache(maxsize=1)
def _load_berry_dataset() -> dict[str, object]:
    """Load the Berry (2019) skyline processor dataset from ``data/productivity``."""
    try:
        return json.loads(_BERRY_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"Berry (2019) processor data missing: {_BERRY_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_adv5n6_dataset() -> dict[str, object]:
    """Load the ADV5N6 (coastal BC) processor dataset."""
    try:
        return json.loads(_ADV5N6_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"ADV5N6 processor data missing: {_ADV5N6_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_adv7n3_dataset() -> dict[str, object]:
    """Load the ADV7N3 processor dataset (Hyundai 210 vs JD 892)."""
    try:
        return json.loads(_ADV7N3_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"ADV7N3 processor data missing: {_ADV7N3_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_tn166_dataset() -> dict[str, object]:
    """Load the TN-166 telescopic-boom processor dataset."""
    try:
        return json.loads(_TN166_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"TN-166 processor data missing: {_TN166_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_barko450_dataset() -> dict[str, object]:
    """Load the TN-46 Barko 450 loader dataset."""
    try:
        return json.loads(_BARKO450_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"Barko 450 loader data missing: {_BARKO450_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_kizha2020_dataset() -> dict[str, object]:
    """Load the Kizha et al. (2020) loader dataset (hot vs cold yarding)."""
    try:
        return json.loads(_KIZHA2020_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Kizha et al. (2020) loader data missing: {_KIZHA2020_DATA_PATH}"
        ) from exc


@lru_cache(maxsize=1)
def _load_hypro775_dataset() -> dict[str, object]:
    """Load the HYPRO 775 tractor-processor dataset."""
    try:
        return json.loads(_HYPRO775_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"HYPRO 775 processor data missing: {_HYPRO775_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_labelle_huss_dataset() -> dict[str, object]:
    """Load the Labelle & Huß (2018) automatic bucking uplift dataset."""
    try:
        return json.loads(_LABELLE_HUSS_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Labelle & Huß (2018) automatic bucking data missing: {_LABELLE_HUSS_DATA_PATH}"
        ) from exc


@lru_cache(maxsize=1)
def _load_tn103_dataset() -> dict[str, object]:
    """Load the TN-103 Caterpillar DL221 processor dataset."""
    try:
        return json.loads(_TN103_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"TN-103 processor data missing: {_TN103_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_tr87_dataset() -> dict[str, object]:
    """Load the TR-87 Timberjack TJ90 processor dataset."""
    try:
        return json.loads(_TR87_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"TR-87 processor data missing: {_TR87_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_tr106_dataset() -> dict[str, object]:
    """Load the TR-106 lodgepole pine processor dataset."""
    try:
        return json.loads(_TR106_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"TR-106 processor data missing: {_TR106_DATA_PATH}") from exc


@lru_cache(maxsize=1)
def _load_visser_dataset() -> dict[str, object]:
    """Load the Visser & Tolan (2015) processor dataset."""
    try:
        return json.loads(_VISSER2015_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Visser & Tolan (2015) processor data missing: {_VISSER2015_DATA_PATH}"
        ) from exc


@lru_cache(maxsize=1)
def _load_spinelli2010_dataset() -> dict[str, object]:
    """Load the Spinelli et al. (2010) processor dataset."""
    try:
        return json.loads(_SPINELLI2010_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Spinelli et al. (2010) processor data missing: {_SPINELLI2010_DATA_PATH}"
        ) from exc


@lru_cache(maxsize=1)
def _load_bertone2025_dataset() -> dict[str, object]:
    """Load the Bertone & Manzone (2025) excavator-processor dataset."""
    try:
        return json.loads(_BERTONE2025_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Bertone & Manzone (2025) processor data missing: {_BERTONE2025_DATA_PATH}"
        ) from exc


@lru_cache(maxsize=1)
def _load_borz2023_dataset() -> dict[str, object]:
    """Load the Borz et al. (2023) Romanian processor dataset."""
    try:
        return json.loads(_BORZ2023_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Borz et al. (2023) landing processor data missing: {_BORZ2023_DATA_PATH}"
        ) from exc


@lru_cache(maxsize=1)
def _load_nakagawa2010_dataset() -> dict[str, object]:
    """Load the Nakagawa et al. (2010) Japanese landing processor dataset."""
    try:
        return json.loads(_NAKAGAWA2010_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Nakagawa et al. (2010) processor data missing: {_NAKAGAWA2010_DATA_PATH}"
        ) from exc


@dataclass(frozen=True)
class AutomaticBuckingAdjustment:
    """
    Effect of Labelle & Huß (2018) automatic bucking on processor productivity/revenue.

    Attributes
    ----------
    multiplier:
        Productivity multiplier applied to delay-free m³/PMH₀.
    delta_m3_per_pmh:
        Absolute uplift (m³/PMH₀) relative to the manual baseline.
    revenue_delta_per_m3:
        Additional revenue per m³ (currency specified by ``currency``). ``None`` if not reported.
    currency:
        Currency code used in the study (e.g., EUR).
    base_year:
        CPI base year for the revenue delta.
    """

    multiplier: float
    delta_m3_per_pmh: float
    revenue_delta_per_m3: float | None
    currency: str | None
    base_year: int | None


@dataclass(frozen=True)
class BerryLogGradeStat:
    """
    Summary of Berry (2019) log grade emmeans (minutes per stem).

    Attributes
    ----------
    grade:
        Log grade label (A, B, etc.).
    mean_minutes:
        Mean processing time (minutes per stem).
    lo_minutes, hi_minutes:
        Lower/upper bounds (±2σ) for the time per stem.
    """

    grade: str
    mean_minutes: float
    lo_minutes: float
    hi_minutes: float


@dataclass(frozen=True)
class ProcessorCarrierProfile:
    """
    Metadata describing processor carriers (purpose-built vs excavator).

    Attributes
    ----------
    key:
        Identifier used by CLI helpers.
    name, description:
        Human-readable carrier name and description.
    productivity_ratio:
        Relative productivity multiplier vs the base profile.
    default_delay_multiplier:
        Optional utilisation multiplier applied to delay-free m³/PMH₀.
    fuel_l_per_m3:
        Litres per cubic metre consumed by the carrier (if available).
    yarder_delay_percent:
        Percent of yarder delay attributable to carrier waiting time.
    notes, references:
        Supplementary notes and citations.
    nakagawa:
        Optional Nakagawa (2010) regression coefficients for this carrier.
    """

    key: str
    name: str
    description: str
    productivity_ratio: float
    default_delay_multiplier: float | None
    fuel_l_per_m3: float | None
    yarder_delay_percent: float | None
    notes: tuple[str, ...]
    references: tuple[str, ...]
    nakagawa: dict[str, float] | None = None


@lru_cache(maxsize=1)
def get_labelle_huss_automatic_bucking_adjustment() -> AutomaticBuckingAdjustment:
    """Return the automatic bucking uplift (productivity + revenue) from Labelle & Huß (2018)."""
    data = _load_labelle_huss_dataset()
    productivity = (data.get("productivity") or {}).get("aggregate") or {}
    revenue = (data.get("revenue") or {}).get("aggregate") or {}
    metadata = data.get("metadata") or {}
    percent_gain = float(productivity.get("percent_gain", 0.0) or 0.0)
    multiplier = 1.0 + percent_gain
    delta_m3 = float(productivity.get("difference_m3_per_pmh", 0.0) or 0.0)
    revenue_delta = revenue.get("difference_eur_per_m3")
    revenue_delta_value = None if revenue_delta is None else float(revenue_delta)
    base_year = metadata.get("base_year")
    base_year_value = int(base_year) if isinstance(base_year, (int, float)) else base_year
    return AutomaticBuckingAdjustment(
        multiplier=multiplier,
        delta_m3_per_pmh=delta_m3,
        revenue_delta_per_m3=revenue_delta_value,
        currency=metadata.get("currency"),
        base_year=base_year_value,
    )


@lru_cache(maxsize=1)
def _load_berry_log_grade_payload() -> dict[str, object]:
    """Load Berry (2019) log grade emmeans for per-grade processing times."""
    try:
        return json.loads(_BERRY_LOG_GRADES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(
            f"Berry (2019) log grade emmeans data missing: {_BERRY_LOG_GRADES_PATH}"
        ) from exc


@lru_cache(maxsize=1)
def get_berry_log_grade_stats() -> tuple[BerryLogGradeStat, ...]:
    """Return Berry (2019) log grade statistics (mean/±2σ minutes per stem)."""
    payload = _load_berry_log_grade_payload()
    grades = []
    for entry in payload.get("grades", []):
        grade = entry.get("grade")
        if not grade:
            continue
        grades.append(
            BerryLogGradeStat(
                grade=str(grade),
                mean_minutes=float(entry.get("mean_minutes", 0.0) or 0.0),
                lo_minutes=float(entry.get("lo_minutes", 0.0) or 0.0),
                hi_minutes=float(entry.get("hi_minutes", 0.0) or 0.0),
            )
        )
    return tuple(grades)


@lru_cache(maxsize=1)
def get_berry_log_grade_metadata() -> dict[str, object]:
    """Return raw metadata payload for Berry (2019) log grade emmeans."""
    payload = _load_berry_log_grade_payload()
    return {
        "source": payload.get("source"),
        "description": payload.get("description"),
        "notes": tuple(payload.get("notes" or [])),
    }


@lru_cache(maxsize=1)
def _load_carrier_profiles_raw() -> dict[str, dict[str, object]]:
    """Load processor carrier profile metadata (purpose-built vs excavator)."""
    try:
        data = json.loads(_CARRIER_PROFILE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - configuration error
        raise FileNotFoundError(f"Carrier profile data missing: {_CARRIER_PROFILE_PATH}") from exc
    return data.get("carriers") or {}


def get_processor_carrier_profile(key: str) -> ProcessorCarrierProfile:
    """
    Return a processor carrier profile (purpose-built vs excavator) by key.

    Parameters
    ----------
    key:
        Carrier identifier as defined in ``processor_carrier_profiles.json``.

    Returns
    -------
    ProcessorCarrierProfile
        Dataclass with productivity ratios, utilisation defaults, and citation details.

    Raises
    ------
    ValueError
        If ``key`` is not present in the profile table.
    """
    profiles = _load_carrier_profiles_raw()
    payload = profiles.get(key)
    if payload is None:
        valid = ", ".join(sorted(profiles))
        raise ValueError(f"Unknown processor carrier '{key}'. Valid options: {valid}.")
    notes = payload.get("notes") or ()
    references = payload.get("references") or ()

    def _coerce_float(value: object | None) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return ProcessorCarrierProfile(
        key=key,
        name=str(payload.get("name", key)),
        description=str(payload.get("description", "")),
        productivity_ratio=float(payload.get("productivity_ratio", 1.0) or 1.0),
        default_delay_multiplier=_coerce_float(payload.get("default_delay_multiplier")),
        fuel_l_per_m3=_coerce_float(payload.get("fuel_l_per_m3")),
        yarder_delay_percent=_coerce_float(payload.get("yarder_delay_percent")),
        notes=tuple(str(n) for n in notes),
        references=tuple(
            str(ref.get("citation")) if isinstance(ref, dict) else str(ref) for ref in references
        ),
        nakagawa=payload.get("nakagawa_regression")
        if isinstance(payload.get("nakagawa_regression"), dict)
        else None,
    )


def _load_tree_form_productivity_multipliers() -> dict[int, float]:
    """Load Berry (2019) tree-form multipliers (category → productivity scalar)."""
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
    """Load the Berry (2019) piece-size regression coefficients (slope/intercept)."""
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
    """Return the Berry (2019) default utilisation fraction (0–1)."""
    utilisation = _load_berry_dataset().get("utilisation") or {}
    percent = utilisation.get("utilisation_percent", 91.0)
    return float(percent) / 100.0


def _load_skid_size_models() -> tuple[
    dict[str, float],
    dict[str, float] | None,
    float,
    tuple[float, float] | None,
]:
    """Load Berry (2019) skid area delay/productivity models."""
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
    """Predict skid-delay seconds and productivity deltas from Berry (2019) skid-yard trials."""
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
    """Load ADV5N6 scenario definitions keyed by scenario name."""
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
    """Load TN-103 line-processor scenario definitions."""
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
    """Load TN-166 telescopic-boom scenario definitions."""
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
    """Load Barko 450 loader scenario definitions."""
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
    """Load TR-87 processor scenario definitions."""
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


@lru_cache(maxsize=1)
def _load_tr106_scenarios() -> dict[str, dict[str, object]]:
    """Load TR-106 processor scenario definitions."""
    payload = _load_tr106_dataset()
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


@lru_cache(maxsize=1)
def _get_visser_tables() -> tuple[
    dict[int, tuple[tuple[float, float], ...]],
    float,
    float,
    dict[int, dict[str, float]],
    str | None,
    int | None,
    float | None,
    tuple[str, ...],
]:
    dataset = _load_visser_dataset()
    entries = dataset.get("piece_size_productivity") or []
    if not entries:
        raise KeyError("Visser & Tolan (2015) dataset missing piece-size table.")
    by_sort: dict[int, list[tuple[float, float]]] = {}
    pieces: list[float] = []
    for entry in entries:
        piece = float(entry.get("piece_size_m3", 0.0) or 0.0)
        pieces.append(piece)
        mapping = entry.get("productivity_m3_per_pmh_by_sort_count") or {}
        for sort_key, value in mapping.items():
            sort_count = int(sort_key)
            by_sort.setdefault(sort_count, []).append((piece, float(value)))
    if not by_sort:
        raise KeyError("Visser & Tolan (2015) dataset missing sort-count productivity entries.")
    by_sort_sorted: dict[int, tuple[tuple[float, float], ...]] = {}
    for sort_count, points in by_sort.items():
        points.sort()
        by_sort_sorted[sort_count] = tuple(points)
    min_piece = min(points[0][0] for points in by_sort_sorted.values())
    max_piece = max(points[-1][0] for points in by_sort_sorted.values())
    value_map: dict[int, dict[str, float]] = {}
    for summary in dataset.get("sort_count_summaries", []):
        log_sorts = summary.get("log_sorts")
        if log_sorts is None:
            continue
        log_sorts_int = int(log_sorts)
        value_map[log_sorts_int] = {
            "gross_value_per_2m3": summary.get("gross_value_usd_per_2m3"),
            "value_per_pmh": summary.get("value_usd_per_pmh"),
        }
    notes = tuple(dataset.get("source", {}).get("notes") or dataset.get("notes") or [])
    if not notes and dataset.get("source"):
        notes = tuple(dataset["source"].get("notes") or [])
    currency = dataset.get("currency")
    base_year = dataset.get("base_year")
    value_reference = dataset.get("value_summary_piece_size_m3")
    base_year_int = int(base_year) if isinstance(base_year, (int, float)) else None
    return (
        by_sort_sorted,
        float(min_piece),
        float(max_piece),
        value_map,
        currency,
        base_year_int,
        float(value_reference) if value_reference is not None else None,
        tuple(notes),
    )


def _interpolate_visser_productivity(
    points: tuple[tuple[float, float], ...],
    piece_size_m3: float,
) -> float:
    if not points:
        raise ValueError("Visser dataset missing required productivity points.")
    if piece_size_m3 < points[0][0] or piece_size_m3 > points[-1][0]:
        raise ValueError(
            f"piece_size_m3={piece_size_m3:.3f} outside supported range {points[0][0]:.2f}–{points[-1][0]:.2f} m³."
        )
    for idx, (piece, value) in enumerate(points):
        if abs(piece_size_m3 - piece) < 1e-6:
            return value
        if piece_size_m3 < piece and idx > 0:
            prev_piece, prev_value = points[idx - 1]
            span = piece - prev_piece
            if span <= 0:
                return value
            ratio = (piece_size_m3 - prev_piece) / span
            return prev_value + ratio * (value - prev_value)
    return points[-1][1]


def _inflate_cost(value: float | None, base_year: int | None) -> float | None:
    if value is None:
        return None
    if base_year is None:
        return float(value)
    return inflate_value(float(value), base_year)


@dataclass(frozen=True)
class ProcessorProductivityResult:
    """
    Normalized output for harvester/processor regression helpers.

    Attributes
    ----------
    base_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀) prior to multipliers.
    tree_form_multiplier, crew_multiplier, delay_multiplier:
        Multipliers applied to the base productivity.
    delay_free_productivity_m3_per_pmh:
        Post-multiplier delay-free productivity (before utilisation).
    productivity_m3_per_pmh:
        Final productivity after applying utilisation/delay multipliers.
    piece_size_m3:
        Piece size (m³) used for the regression.
    tree_form_category:
        Berry (2019) tree form category (0 good, 1 poor, 2 bad).
    carrier_profile:
        Optional :class:`ProcessorCarrierProfile` applied to the regression.
    """

    base_productivity_m3_per_pmh: float
    tree_form_multiplier: float
    crew_multiplier: float
    delay_multiplier: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float
    piece_size_m3: float
    tree_form_category: int
    carrier_profile: ProcessorCarrierProfile | None = None


def estimate_processor_productivity_berry2019(
    *,
    piece_size_m3: float,
    tree_form_category: int = 0,
    crew_multiplier: float = 1.0,
    delay_multiplier: float = _BERRY_DEFAULT_UTILISATION,
    automatic_bucking_multiplier: float | None = None,
    carrier_profile: ProcessorCarrierProfile | None = None,
) -> ProcessorProductivityResult:
    """Estimate processor productivity using Berry (2019) Kinleith NZ regressions.

    Parameters
    ----------
    piece_size_m3 : float
        Average piece volume per stem (m³). Used directly in the linear regression reported in the thesis.
    tree_form_category : int, default=0
        0 (good), 1 (poor), or 2 (bad) tree-form classes from Berry's emmeans table. Controls the tree
        form multiplier.
    crew_multiplier : float, default=1.0
        Adjustment for operator/crew effects (e.g., Crew A ≈ 1.16, Crew C ≈ 0.75). Must be > 0.
    delay_multiplier : float, default=_BERRY_DEFAULT_UTILISATION
        Utilisation ratio applied after computing delay-free productivity (0 < value ≤ 1). Defaults to
        0.91 per the study's short-delay observations.
    automatic_bucking_multiplier : float, optional
        Multiplier capturing log-optimiser benefits (Labelle & Huss 2007). Values ``> 0`` scale the
        delay-free output.
    carrier_profile : ProcessorCarrierProfile, optional
        Optional carrier metadata (purpose-built vs excavator) providing predefined productivity ratios
        and fuel/maintenance notes for CLI rendering.

    Returns
    -------
    ProcessorProductivityResult
        Dataclass summarising the base regression output, applied multipliers, and final m³/PMH (delay
        adjusted). ``carrier_profile`` is echoed for downstream CLI formatting.

    Notes
    -----
    Based on Berry's MASc thesis (2019) – Kinleith, NZ. Piece-size range is ≈0.2–1.2 m³ and the
    regression is PMH₀. Apply your own utilisation if you operate outside the observed 91 % value.
    """
    if piece_size_m3 <= 0:
        raise ValueError("piece_size_m3 must be > 0")
    if tree_form_category not in _TREE_FORM_PRODUCTIVITY_MULTIPLIERS:
        raise ValueError("tree_form_category must be 0, 1, or 2")
    if crew_multiplier <= 0:
        raise ValueError("crew_multiplier must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    auto_multiplier = 1.0
    if automatic_bucking_multiplier is not None:
        if automatic_bucking_multiplier <= 0:
            raise ValueError("automatic_bucking_multiplier must be > 0")
        auto_multiplier = automatic_bucking_multiplier

    base_productivity = _BERRY_BASE_SLOPE * piece_size_m3 + _BERRY_BASE_INTERCEPT
    tree_multiplier = _TREE_FORM_PRODUCTIVITY_MULTIPLIERS[tree_form_category]
    productivity_ratio = 1.0
    if carrier_profile and carrier_profile.productivity_ratio:
        productivity_ratio = max(carrier_profile.productivity_ratio, 0.0)
    delay_free = (
        base_productivity * tree_multiplier * crew_multiplier * auto_multiplier * productivity_ratio
    )
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
        carrier_profile=carrier_profile,
    )


@dataclass(frozen=True)
class VisserLogSortProductivityResult:
    """
    Result payload for the Visser & Tolan (2015) log-sort study.

    Attributes
    ----------
    piece_size_m3:
        Average piece volume (m³) used in the regression.
    log_sort_count:
        Number of simultaneous log sorts.
    delay_free_productivity_m3_per_pmh:
        Predicted m³/PMH₀ from the study.
    delay_multiplier:
        Utilisation multiplier applied to produce ``productivity_m3_per_pmh``.
    productivity_m3_per_pmh:
        Final productivity after utilisation adjustments.
    baseline_productivity_m3_per_pmh:
        Published baseline used for relative comparisons.
    relative_difference_percent:
        Percentage difference vs the baseline.
    gross_value_per_2m3, value_per_pmh:
        Economic outputs from the study (may be ``None`` when not provided).
    value_currency, value_base_year:
        Currency/base year for the economic metrics.
    value_reference_piece_size_m3:
        Reference piece size used when computing the economic deltas.
    notes:
        Additional study notes.
    """

    piece_size_m3: float
    log_sort_count: int
    delay_free_productivity_m3_per_pmh: float
    delay_multiplier: float
    productivity_m3_per_pmh: float
    baseline_productivity_m3_per_pmh: float
    relative_difference_percent: float
    gross_value_per_2m3: float | None
    value_per_pmh: float | None
    value_currency: str | None
    value_base_year: int | None
    value_reference_piece_size_m3: float | None
    notes: tuple[str, ...]


def estimate_processor_productivity_visser2015(
    *,
    piece_size_m3: float,
    log_sort_count: int,
    delay_multiplier: float = 1.0,
) -> VisserLogSortProductivityResult:
    """Apply the Visser & Tolan (2015) log-sort productivity curves.

    Parameters
    ----------
    piece_size_m3 : float
        Average log volume per piece (m³). Must lie within the 1–3 m³ calibration window.
    log_sort_count : int
        Number of simultaneous log sorts (5, 9, 12, or 15). Controls both productivity and value-per-PMH.
    delay_multiplier : float, default=1.0
        Utilisation factor (0 < value ≤ 1). ``1.0`` keeps the published delay-free PMH₀ outputs.

    Returns
    -------
    VisserLogSortProductivityResult
        Dataclass containing delay-free/observed productivity, relative change v. the 5-sort baseline,
        and the published gross-value metrics (2014 USD).

    Notes
    -----
    The function interpolates between the digitised curves shipped in ``data/productivity/visser2015``.
    Supplying an out-of-range ``piece_size_m3`` raises ``ValueError`` with the supported range.
    """
    if piece_size_m3 <= 0:
        raise ValueError("piece_size_m3 must be > 0")
    if delay_multiplier <= 0 or delay_multiplier > 1.0:
        raise ValueError("delay_multiplier must lie in (0, 1].")
    tables, min_piece, max_piece, value_map, currency, value_base_year, value_reference, notes = (
        _get_visser_tables()
    )
    if not (min_piece <= piece_size_m3 <= max_piece):
        raise ValueError(
            f"piece_size_m3 must lie within the Visser & Tolan (2015) study range "
            f"{min_piece:.2f}–{max_piece:.2f} m³."
        )
    if log_sort_count not in tables:
        valid = ", ".join(str(sort) for sort in sorted(tables))
        raise ValueError(f"log_sort_count={log_sort_count} is unsupported. Choose one of: {valid}.")
    baseline_points = tables.get(5)
    if not baseline_points:
        raise KeyError("Visser dataset missing baseline 5-sort curve.")
    delay_free_productivity = _interpolate_visser_productivity(
        tables[log_sort_count], piece_size_m3
    )
    baseline_productivity = _interpolate_visser_productivity(baseline_points, piece_size_m3)
    relative = (
        0.0
        if baseline_productivity == 0
        else (delay_free_productivity - baseline_productivity) / baseline_productivity * 100.0
    )
    value_summary = value_map.get(log_sort_count) or {}
    productivity = delay_free_productivity * delay_multiplier
    return VisserLogSortProductivityResult(
        piece_size_m3=piece_size_m3,
        log_sort_count=log_sort_count,
        delay_free_productivity_m3_per_pmh=delay_free_productivity,
        delay_multiplier=delay_multiplier,
        productivity_m3_per_pmh=productivity,
        baseline_productivity_m3_per_pmh=baseline_productivity,
        relative_difference_percent=relative,
        gross_value_per_2m3=(
            None
            if value_summary.get("gross_value_per_2m3") is None
            else float(value_summary["gross_value_per_2m3"])
        ),
        value_per_pmh=(
            None
            if value_summary.get("value_per_pmh") is None
            else float(value_summary["value_per_pmh"])
        ),
        value_currency=currency,
        value_base_year=value_base_year,
        value_reference_piece_size_m3=value_reference,
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class Labelle2019ProcessorProductivityResult:
    """
    Polynomial coefficients + outputs from Labelle et al. (2019) DBH-based regressions.

    Attributes
    ----------
    species, treatment:
        Species (spruce/beech) and silviculture treatment (clear_cut/selective_cut).
    dbh_cm:
        Diameter at breast height (cm).
    intercept, linear, quadratic:
        Polynomial coefficients describing delay-free productivity vs DBH.
    sample_trees:
        Sample size per species/treatment combination.
    delay_multiplier:
        Utilisation multiplier applied post regression.
    delay_free_productivity_m3_per_pmh:
        Delay-free m³/PMH₀ predicted by the polynomial (after optional auto bucking adjustments).
    productivity_m3_per_pmh:
        Final m³/PMH after applying ``delay_multiplier``.
    """

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
    """Helper structure for Labelle et al. (2019) DBH polynomials."""

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
    automatic_bucking_multiplier: float | None = None,
) -> Labelle2019ProcessorProductivityResult:
    """
    Labelle et al. (2019) DBH-based processor regressions (spruce/beech, clear/selective cuts).

    Parameters
    ----------
    species:
        ``"spruce"`` or ``"beech"``.
    treatment:
        ``"clear_cut"`` or ``"selective_cut"``.
    dbh_cm:
        Diameter at breast height (cm). Must be > 0.
    delay_multiplier:
        Utilisation multiplier (0,1], applied after delay-free productivity is calculated.
    automatic_bucking_multiplier:
        Optional multiplier (>0) representing automatic bucking productivity gains.

    Returns
    -------
    Labelle2019ProcessorProductivityResult
        Dataclass containing coefficients, delay-free productivity, and utilisation-adjusted output.
    """

    if dbh_cm <= 0:
        raise ValueError("dbh_cm must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")
    auto_multiplier = 1.0
    if automatic_bucking_multiplier is not None:
        if automatic_bucking_multiplier <= 0:
            raise ValueError("automatic_bucking_multiplier must be > 0")
        auto_multiplier = automatic_bucking_multiplier

    key = (species.lower(), treatment.lower())
    if key not in _LABELLE2019_DBH_MODELS:
        valid = ", ".join(
            f"{spec}/{treatment}" for spec, treatment in sorted(_LABELLE2019_DBH_MODELS)
        )
        raise ValueError(f"Unknown species/treatment combination {key!r}. Valid pairs: {valid}")

    coeffs = _LABELLE2019_DBH_MODELS[key]
    delay_free = coeffs.intercept + coeffs.linear * dbh_cm + coeffs.quadratic * (dbh_cm**2)
    delay_free = max(0.0, delay_free)
    delay_free *= auto_multiplier
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
    """
    Result payload for Labelle et al. (2016) sugar maple processor regressions.

    Attributes
    ----------
    tree_form:
        Tree-form class (`"acceptable"` or `"unacceptable"`).
    dbh_cm:
        Diameter at breast height (cm) used in the regression.
    coefficient_a, exponent_b:
        Power-law coefficients from the publication.
    sample_trees:
        Number of trees used to calibrate the regression.
    delay_multiplier:
        Utilisation multiplier applied to delay-free productivity.
    delay_free_productivity_m3_per_pmh:
        Predicted m³/PMH₀ prior to utilisation adjustments.
    productivity_m3_per_pmh:
        Final m³/PMH after applying ``delay_multiplier`` (and optional bucking multipliers).
    """

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
    automatic_bucking_multiplier: float | None = None,
) -> Labelle2016ProcessorProductivityResult:
    """
    Labelle et al. (2016) sugar maple processor regressions grouped by tree form.

    Parameters
    ----------
    tree_form:
        ``"acceptable"`` or ``"unacceptable"`` (see publication Table 3).
    dbh_cm:
        Diameter at breast height (cm). Must be > 0.
    delay_multiplier:
        Utilisation multiplier (0,1].
    automatic_bucking_multiplier:
        Optional multiplier (>0) for automatic bucking uplift.

    Returns
    -------
    Labelle2016ProcessorProductivityResult
        Dataclass carrying power-law coefficients and productivity outputs.
    """

    if dbh_cm <= 0:
        raise ValueError("dbh_cm must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    key = tree_form.lower()
    if key not in _LABELLE2016_TREEFORM_MODELS:
        valid = ", ".join(sorted(_LABELLE2016_TREEFORM_MODELS))
        raise ValueError(f"Unknown tree form '{tree_form}'. Valid options: {valid}")

    auto_multiplier = 1.0
    if automatic_bucking_multiplier is not None:
        if automatic_bucking_multiplier <= 0:
            raise ValueError("automatic_bucking_multiplier must be > 0")
        auto_multiplier = automatic_bucking_multiplier

    coeff_a, exponent_b, sample_count = _LABELLE2016_TREEFORM_MODELS[key]
    delay_free = coeff_a * (dbh_cm**exponent_b)
    delay_free *= auto_multiplier
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
    """
    Polynomial regression output for Labelle et al. (2017) excavator processors.

    Attributes
    ----------
    variant:
        Scenario label (e.g., ``"purpose_built"`` vs ``"excavator"``).
    dbh_cm:
        Diameter at breast height (cm).
    intercept, linear, quadratic:
        Polynomial coefficients for the delay-free productivity fit.
    sample_trees:
        Number of observations underpinning the regression.
    delay_multiplier:
        Utilisation multiplier applied after calculating delay-free productivity.
    delay_free_productivity_m3_per_pmh:
        m³/PMH₀ prior to utilisation adjustments.
    productivity_m3_per_pmh:
        Final m³/PMH after applying ``delay_multiplier`` (and optional auto bucking multipliers).
    """

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
    """
    Power-law regression output for Labelle et al. (2017) excavator processors.

    Attributes
    ----------
    variant:
        Scenario label for the regression.
    dbh_cm:
        Diameter at breast height (cm).
    coefficient, exponent:
        Power-law coefficients describing delay-free productivity.
    sample_trees:
        Number of trees measured in the study.
    delay_multiplier:
        Utilisation multiplier applied to the delay-free result.
    delay_free_productivity_m3_per_pmh:
        Predicted m³/PMH₀ before utilisation adjustments.
    productivity_m3_per_pmh:
        Final m³/PMH after applying ``delay_multiplier`` (and optional auto bucking multipliers).
    """

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
    automatic_bucking_multiplier: float | None = None,
) -> Labelle2017PolynomialProcessorResult | Labelle2017PowerProcessorResult:
    """
    Labelle et al. (2017) excavator-based CTL processor regressions (polynomial or power-law).

    Parameters
    ----------
    variant:
        One of the supported regression variants (see `_LABELLE2017_MODELS`).
    dbh_cm:
        Diameter at breast height (cm). Must be > 0.
    delay_multiplier:
        Utilisation multiplier (0,1].
    automatic_bucking_multiplier:
        Optional multiplier (>0) for automatic bucking uplift.

    Returns
    -------
    Labelle2017PolynomialProcessorResult | Labelle2017PowerProcessorResult
        Dataclass containing coefficients and productivity values for the requested variant.
    """

    if dbh_cm <= 0:
        raise ValueError("dbh_cm must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")
    auto_multiplier = 1.0
    if automatic_bucking_multiplier is not None:
        if automatic_bucking_multiplier <= 0:
            raise ValueError("automatic_bucking_multiplier must be > 0")
        auto_multiplier = automatic_bucking_multiplier

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
        delay_free *= auto_multiplier
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
        delay_free *= auto_multiplier
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

    valid = ", ".join(sorted({*_LABELLE2017_POLY_MODELS.keys(), *_LABELLE2017_POWER_MODELS.keys()}))
    raise ValueError(f"Unknown Labelle 2017 variant '{variant}'. Valid options: {valid}.")


@dataclass(frozen=True)
class Labelle2018ProcessorProductivityResult:
    """
    Regression output for Labelle et al. (2018) Bavarian beech/spruce processors.

    Attributes
    ----------
    variant:
        Scenario label (rubber tired vs tracked, spruce vs beech).
    dbh_cm:
        Diameter at breast height (cm).
    intercept, linear, quadratic:
        Polynomial coefficients for delay-free productivity.
    sample_trees:
        Number of observations for the variant.
    delay_multiplier:
        Utilisation multiplier (0,1].
    delay_free_productivity_m3_per_pmh:
        Predicted m³/PMH₀ without utilisation adjustments.
    productivity_m3_per_pmh:
        Final m³/PMH after applying utilisation and auto bucking multipliers.
    """

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
    automatic_bucking_multiplier: float | None = None,
) -> Labelle2018ProcessorProductivityResult:
    """
    Labelle et al. (2018) Bavarian beech/spruce processor regressions (DBH polynomials).

    Parameters
    ----------
    variant:
        Regression key describing species and undercarriage type.
    dbh_cm:
        Diameter at breast height (cm). Must be > 0.
    delay_multiplier:
        Utilisation multiplier (0,1].
    automatic_bucking_multiplier:
        Optional multiplier (>0) for automatic bucking uplift.

    Returns
    -------
    Labelle2018ProcessorProductivityResult
        Regression coefficients plus productivity outputs for the variant.
    """

    if dbh_cm <= 0:
        raise ValueError("dbh_cm must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")
    auto_multiplier = 1.0
    if automatic_bucking_multiplier is not None:
        if automatic_bucking_multiplier <= 0:
            raise ValueError("automatic_bucking_multiplier must be > 0")
        auto_multiplier = automatic_bucking_multiplier

    coeffs = _LABELLE2018_MODELS.get(variant.lower())
    if coeffs is None:
        valid = ", ".join(sorted(_LABELLE2018_MODELS))
        raise ValueError(f"Unknown Labelle 2018 variant '{variant}'. Valid options: {valid}")

    intercept, linear, quadratic, sample_trees = coeffs
    delay_free = -intercept + linear * dbh_cm - quadratic * (dbh_cm**2)
    delay_free = max(0.0, delay_free)
    delay_free *= auto_multiplier
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
    """
    Volume-keyed Labelle et al. (2019) regression outputs.

    Attributes
    ----------
    species, treatment:
        Species and silviculture treatment labels.
    volume_m3:
        Recovered volume per tree (m³).
    intercept, linear, quadratic:
        Polynomial coefficients keyed to volume (rather than DBH).
    sample_trees:
        Number of observations per combination.
    delay_multiplier:
        Utilisation multiplier applied after delay-free productivity is computed.
    delay_free_productivity_m3_per_pmh:
        Predicted m³/PMH₀ before utilisation adjustments.
    productivity_m3_per_pmh:
        Final m³/PMH after applying utilisation and optional auto bucking multipliers.
    """

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
    """Helper container for the volume-based Labelle (2019) polynomials."""

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
    automatic_bucking_multiplier: float | None = None,
) -> Labelle2019VolumeProcessorProductivityResult:
    """
    Labelle et al. (2019) volume-based processor regressions (spruce/beech treatments).

    Parameters
    ----------
    species:
        ``"spruce"`` or ``"beech"``.
    treatment:
        ``"clear_cut"`` or ``"selective_cut"``.
    volume_m3:
        Recovered volume per stem (m³). Must be > 0.
    delay_multiplier:
        Utilisation multiplier (0,1].
    automatic_bucking_multiplier:
        Optional multiplier (>0) for automatic bucking uplift.

    Returns
    -------
    Labelle2019VolumeProcessorProductivityResult
        Dataclass carrying coefficients and productivity outputs keyed to volume.
    """

    if volume_m3 <= 0:
        raise ValueError("volume_m3 must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")
    auto_multiplier = 1.0
    if automatic_bucking_multiplier is not None:
        if automatic_bucking_multiplier <= 0:
            raise ValueError("automatic_bucking_multiplier must be > 0")
        auto_multiplier = automatic_bucking_multiplier

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
    delay_free *= auto_multiplier
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
    """
    Result payload for loader-forwarder productivity estimates (ADV5N1/TN261).

    Attributes
    ----------
    piece_size_m3:
        Average piece volume (m³).
    external_distance_m:
        External forwarding distance (m).
    slope_percent:
        Average slope (%) for the forwarding corridor.
    delay_multiplier:
        Utilisation fraction applied to delay-free productivity.
    delay_free_productivity_m3_per_pmh:
        m³/PMH₀ predicted by the regression.
    productivity_m3_per_pmh:
        Final productive m³/PMH (utilisation applied).
    tonnes_per_cycle:
        Payload mass (tonnes) per cycle when available.
    cycles_per_hour:
        Cycle rate implied by the regression.
    """

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
    """
    Estimate loader-forwarder productivity using TN-261 regressions.

    Parameters
    ----------
    piece_size_m3:
        Average payload volume per cycle (m³). Must be > 0.
    external_distance_m:
        External distance travelled by the loader-forwarder (m). Must be > 0.
    slope_percent:
        Average slope (%) along the forwarding trail. Used to apply the slope multiplier.
    bunched:
        ``True`` when wood is mechanically bunched (higher payload factor), ``False`` for hand-felled.
    delay_multiplier:
        Utilisation multiplier (0,1] applied to delay-free productivity.

    Returns
    -------
    LoaderForwarderProductivityResult
        Dataclass containing delay-free and utilisation-adjusted productivity plus multiplier details.
    """
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
        * (piece_size_m3**_LOADER_PIECE_EXP)
        * (external_distance_m**_LOADER_DISTANCE_EXP)
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
    """
    ADV2N26 clambunk/hoe-forwarding productivity result.

    Attributes
    ----------
    travel_empty_distance_m:
        Empty travel distance per cycle (m).
    stems_per_cycle:
        Average stems moved in each cycle.
    average_stem_volume_m3:
        Cubic metres per stem.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀) from the regression.
    utilisation:
        Utilisation fraction applied to derive ``productivity_m3_per_pmh``.
    productivity_m3_per_pmh:
        Final productivity (m³/PMH).
    """

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
    """
    TN-46 Barko 450 loader productivity/cost result.

    Attributes
    ----------
    scenario:
        Scenario identifier from TN-46 dataset.
    description:
        Human-readable description of the block.
    avg_volume_per_shift_m3:
        Volume processed per 8 h shift.
    avg_stems_per_shift:
        Number of stems handled per shift.
    utilisation:
        Observed utilisation fraction.
    productivity_m3_per_pmh:
        Computed productivity (m³ per productive hour).
    cost_per_m3_cad:
        Loader cost per cubic metre (inflated to CAD 2024 when possible).
    labour_cost_per_m3_cad:
        Labour component per cubic metre.
    fuel_l_per_shift:
        Fuel consumption per shift.
    notes:
        Additional study notes.
    cost_base_year:
        Base year used for the cost figures.
    """

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


@dataclass(frozen=True)
class LoaderHotColdProductivityResult:
    """
    Loader hot vs cold yard productivity result (Kizha et al. 2020).

    Attributes
    ----------
    mode:
        ``"hot"`` or ``"cold"`` yarding mode.
    description:
        Scenario description.
    utilisation_percent:
        Utilisation percentage observed in the study.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    loader_hours:
        Loader hours recorded per shift.
    loader_cost_per_m3_cad:
        Loader cost per cubic metre.
    notes:
        Additional notes from the publication.
    cost_base_year:
        Base year for the cost figure.
    """

    mode: Literal["hot", "cold"]
    description: str
    utilisation_percent: float
    operational_delay_percent_of_total_time: float
    delay_cost_per_pmh: float
    machine_rate_per_pmh: float
    effective_cost_per_pmh: float
    currency: str | None
    cost_base_year: int | None
    dominant_delay_breakdown_percent_of_delay: tuple[tuple[str, float], ...]
    bottleneck: str | None
    notes: tuple[str, ...]
    observed_days: int | None


@dataclass(frozen=True)
class Hypro775ProcessorProductivityResult:
    """
    HYPRO 775 tractor-mounted processor regression result.

    Attributes
    ----------
    description:
        Scenario description (e.g., thinning vs final felling).
    mean_cycle_time_seconds:
        Observed mean cycle time.
    mean_logs_per_tree:
        Average logs processed per tree.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    utilisation_percent:
        Utilisation percentage applied to derive final productivity.
    productivity_m3_per_pmh:
        Final productivity (m³/PMH).
    cost_per_m3_cad:
        Cost per cubic metre (inflated to 2024 CAD when available).
    fuel_l_per_m3:
        Fuel consumption per cubic metre.
    notes:
        Study notes or caveats.
    cost_base_year:
        Base year for the cost figure.
    """

    description: str
    mean_cycle_time_seconds: float
    mean_logs_per_tree: float
    gross_trees_per_hour: float
    net_trees_per_hour: float
    delay_free_productivity_m3_per_pmh: float
    fuel_consumption_l_per_hour: float
    fuel_consumption_l_per_m3: float
    utilisation_percent: float
    noise_db: float | None
    cardio_workload_percent_of_max: float | None
    delay_multiplier: float
    productivity_m3_per_pmh: float
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Spinelli2010ProcessorProductivityResult:
    """
    Spinelli et al. (2010) CTL processor regression result.

    Attributes
    ----------
    operation:
        ``"harvest"`` or ``"process"`` operation type.
    tree_volume_m3:
        Tree volume (m³) used in the regression.
    slope_percent:
        Slope percentage for the study plot.
    machine_power_kw:
        Processor power (kW).
    delay_multiplier:
        Utilisation multiplier applied after the regression.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    notes:
        Additional notes from the publication.
    """

    operation: Literal["harvest", "process"]
    tree_volume_m3: float
    slope_percent: float
    machine_power_kw: float
    carrier_type: str
    head_type: str
    species_group: str
    stand_type: str
    removals_per_ha: float | None
    residuals_per_ha: float | None
    cycle_components_minutes: tuple[tuple[str, float], ...]
    delay_free_minutes_per_tree: float
    trees_per_pmh_delay_free: float
    delay_free_productivity_m3_per_pmh: float
    accessory_ratio: float
    delay_ratio: float
    delay_multiplier: float
    productivity_m3_per_pmh: float
    utilisation_percent: float
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Bertone2025ProcessorProductivityResult:
    """
    Bertone & Manzone (2025) excavator-processor regression result.

    Attributes
    ----------
    dbh_cm:
        Diameter at breast height (cm).
    height_m:
        Tree height (m).
    logs_per_tree:
        Average logs processed per tree.
    tree_volume_m3:
        Tree volume (m³).
    delay_multiplier:
        Utilisation multiplier applied post regression.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    notes:
        Additional notes or warnings from the study.
    """

    dbh_cm: float
    height_m: float
    logs_per_tree: float
    tree_volume_m3: float
    delay_free_cycle_seconds: float
    delay_free_productivity_m3_per_pmh: float
    delay_multiplier: float
    productivity_m3_per_smh: float
    utilisation_percent: float
    fuel_l_per_smh: float
    fuel_l_per_m3: float
    cost_per_smh: float
    cost_per_m3: float
    cost_currency: str
    cost_base_year: int | None
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Borz2023ProcessorProductivityResult:
    """
    Borz et al. (2023) processor regression result.

    Attributes
    ----------
    tree_volume_m3:
        Tree volume (m³) used in the regression (``None`` when unavailable).
    efficiency_pmh_per_m3, efficiency_smh_per_m3:
        Efficiency metrics reported in the study.
    productivity_m3_per_pmh, productivity_m3_per_smh:
        Productivity derived from the efficiency metrics.
    cost_eur_per_m3:
        Cost per cubic metre (EUR) at the study's base year.
    cost_currency, cost_base_year:
        Currency and base year for the cost figure.
    notes:
        Additional notes pulled from the dataset.
    """

    tree_volume_m3: float | None
    efficiency_pmh_per_m3: float
    efficiency_smh_per_m3: float
    productivity_m3_per_pmh: float
    productivity_m3_per_smh: float
    fuel_l_per_h: float
    fuel_l_per_m3: float
    cost_per_m3: float
    cost_currency: str
    cost_base_year: int | None
    recovery_percent: float
    utilisation_percent: float
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Nakagawa2010ProcessorProductivityResult:
    """
    Nakagawa et al. (2010) Hokkaido landing processor regression result.

    Attributes
    ----------
    dbh_cm:
        Diameter at breast height (cm) when the DBH model is used.
    piece_volume_m3:
        Piece volume (m³) when the piece-volume model is used.
    model_used:
        ``"dbh"`` or ``"piece_volume"`` depending on inputs.
    delay_multiplier:
        Utilisation multiplier applied to the delay-free productivity.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    utilisation_percent:
        Utilisation percentage reported in the study.
    notes:
        Additional notes from the dataset.
    """

    dbh_cm: float | None
    piece_volume_m3: float | None
    model_used: Literal["dbh", "piece_volume"]
    delay_free_productivity_m3_per_pmh: float
    delay_multiplier: float
    productivity_m3_per_pmh: float
    notes: tuple[str, ...]


@lru_cache(maxsize=1)
def _load_hypro775_scenario() -> dict[str, object]:
    payload = _load_hypro775_dataset()
    scenario = payload.get("scenario") or {}
    notes = tuple(str(n) for n in scenario.get("notes") or [])
    return {
        "description": scenario.get("description", "HYPRO 775 landing processor"),
        "mean_cycle_time_seconds": float(scenario.get("mean_cycle_time_seconds", 45.0) or 45.0),
        "mean_logs_per_tree": float(scenario.get("mean_logs_per_tree", 4.0) or 4.0),
        "gross_trees_per_hour": float(scenario.get("gross_trees_per_hour", 45.0) or 45.0),
        "net_trees_per_hour": float(scenario.get("net_trees_per_hour", 18.0) or 18.0),
        "delay_free_productivity_m3_per_pmh": float(
            scenario.get("delay_free_productivity_m3_per_pmh", 21.4) or 21.4
        ),
        "fuel_consumption_l_per_hour": float(
            scenario.get("fuel_consumption_l_per_hour", 21.0) or 21.0
        ),
        "fuel_consumption_l_per_m3": float(scenario.get("fuel_consumption_l_per_m3", 0.78) or 0.78),
        "utilisation_percent": float(scenario.get("utilisation_percent", 73.0) or 73.0),
        "noise_db": scenario.get("noise_db"),
        "cardio_workload_percent_of_max": scenario.get("cardio_workload_percent_of_max"),
        "notes": notes,
    }


def estimate_processor_productivity_hypro775(
    *, delay_multiplier: float | None = None
) -> Hypro775ProcessorProductivityResult:
    """
    HYPRO 775 tractor-processor regression (Castro Pérez 2020 / Zurita Vintimilla 2021).

    Parameters
    ----------
    delay_multiplier:
        Optional utilisation multiplier (0,1]. Defaults to the study utilisation when ``None``.

    Returns
    -------
    Hypro775ProcessorProductivityResult
        Dataclass with cycle times, utilisation, fuel, and productivity metrics.
    """
    data = _load_hypro775_scenario()
    base = data["delay_free_productivity_m3_per_pmh"]
    utilisation = data["utilisation_percent"] / 100.0
    multiplier = delay_multiplier if delay_multiplier is not None else utilisation
    if not (0.0 < multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1].")
    productivity = base * multiplier
    return Hypro775ProcessorProductivityResult(
        description=data["description"],
        mean_cycle_time_seconds=data["mean_cycle_time_seconds"],
        mean_logs_per_tree=data["mean_logs_per_tree"],
        gross_trees_per_hour=data["gross_trees_per_hour"],
        net_trees_per_hour=data["net_trees_per_hour"],
        delay_free_productivity_m3_per_pmh=base,
        fuel_consumption_l_per_hour=data["fuel_consumption_l_per_hour"],
        fuel_consumption_l_per_m3=data["fuel_consumption_l_per_m3"],
        utilisation_percent=data["utilisation_percent"],
        noise_db=(None if data["noise_db"] is None else float(data["noise_db"])),
        cardio_workload_percent_of_max=(
            None
            if data["cardio_workload_percent_of_max"] is None
            else float(data["cardio_workload_percent_of_max"])
        ),
        delay_multiplier=multiplier,
        productivity_m3_per_pmh=productivity,
        notes=data["notes"],
    )


def _spinelli_move_deck(tree_volume_m3: float) -> float:
    return 5.6 + 4.26 * tree_volume_m3


def _spinelli_move_stand(
    *,
    slope_percent: float,
    removals_per_ha: float,
    residuals_per_ha: float,
    machine_power_kw: float,
    is_spider: bool,
    is_tractor: bool,
) -> float:
    power_term = math.sqrt(machine_power_kw)
    numerator = 12_412 + 771 * slope_percent
    if is_spider:
        numerator += 46_706
    if is_tractor:
        numerator += 63_153
    return 7.5 + numerator / (removals_per_ha * power_term) + 0.204 * residuals_per_ha / power_term


def _spinelli_brush(is_forest: bool) -> float:
    return max(0.0, -1.8 + 9.2 * (1 if is_forest else 0))


def _spinelli_grab(
    *,
    tree_volume_m3: float,
    machine_power_kw: float,
    is_spider: bool,
) -> float:
    power_term = math.sqrt(machine_power_kw)
    value = 15.2 + 153.1 * tree_volume_m3 / power_term
    if is_spider:
        value += (13.9 + 274.9 * tree_volume_m3) / power_term
    return value


def _spinelli_fell(
    *,
    tree_volume_m3: float,
    machine_power_kw: float,
    slope_percent: float,
    carrier_type: str,
) -> float:
    power_term = math.sqrt(machine_power_kw)
    is_spider = carrier_type == "spider"
    is_excavator = carrier_type == "excavator"
    is_tractor = carrier_type == "tractor"
    value = 3.8 + 156.5 * tree_volume_m3 / power_term
    if not is_spider:
        value += 1.18 * slope_percent
    if is_excavator:
        value += 6.5
    if is_tractor:
        value += 24.8
    if is_spider:
        value += (25.5 + 188.5 * tree_volume_m3) / power_term
    return value


def _spinelli_process(
    *,
    tree_volume_m3: float,
    slope_percent: float,
    machine_power_kw: float,
    head_type: str,
    carrier_type: str,
    species_group: str,
) -> float:
    coeff = 1_115.0
    if head_type == "stroke":
        coeff += 446.0
    if carrier_type == "tractor":
        coeff += 2_244.0
    if species_group == "chestnut_poplar":
        coeff -= 362.0
    elif species_group == "other_hardwood":
        coeff += 1_118.0
    power_term = math.sqrt(machine_power_kw)
    return 22.7 + 1.433 * tree_volume_m3 * slope_percent + coeff * tree_volume_m3 / power_term


def estimate_processor_productivity_spinelli2010(
    *,
    operation: Literal["harvest", "process"],
    tree_volume_m3: float,
    slope_percent: float,
    machine_power_kw: float,
    carrier_type: str,
    head_type: str,
    species_group: str,
    stand_type: str,
    removals_per_ha: float | None = None,
    residuals_per_ha: float | None = None,
) -> Spinelli2010ProcessorProductivityResult:
    """
    Spinelli et al. (2010) Italian CTL processor regressions (harvest vs landing).

    Parameters
    ----------
    operation:
        ``"harvest"`` or ``"process"``. Harvest mode requires removal/residual densities.
    tree_volume_m3:
        Tree volume (m³). Must be > 0.
    slope_percent:
        Slope (%) affecting cycle components. Negative values are clamped to 0.
    machine_power_kw:
        Processor power (kW). Must be > 0.
    carrier_type:
        Carrier class (`"tractor"`, `"spider"`, etc.).
    head_type:
        Harvester head type (`"stroke"` vs others).
    species_group:
        Species class (as defined in the study).
    stand_type:
        ``"forest"`` or other labels controlling brushing time.
    removals_per_ha, residuals_per_ha:
        Required when ``operation="harvest"`` to compute move/brush cycle elements.

    Returns
    -------
    Spinelli2010ProcessorProductivityResult
        Dataclass with delay-free and utilisation-adjusted productivity plus cycle breakdowns.
    """
    if tree_volume_m3 <= 0:
        raise ValueError("tree_volume_m3 must be > 0.")
    if machine_power_kw <= 0:
        raise ValueError("machine_power_kw must be > 0.")
    slope_value = max(0.0, slope_percent)
    is_spider = carrier_type == "spider"
    is_tractor = carrier_type == "tractor"
    dataset = _load_spinelli2010_dataset()
    cycle_entries: list[tuple[str, float]] = []

    if operation == "harvest":
        if removals_per_ha is None or removals_per_ha <= 0:
            raise ValueError("--processor-removals-per-ha must be > 0 for harvest mode.")
        if residuals_per_ha is None or residuals_per_ha < 0:
            raise ValueError("--processor-residuals-per-ha must be >= 0 for harvest mode.")
        move = _spinelli_move_stand(
            slope_percent=slope_value,
            removals_per_ha=removals_per_ha,
            residuals_per_ha=residuals_per_ha,
            machine_power_kw=machine_power_kw,
            is_spider=is_spider,
            is_tractor=is_tractor,
        )
        brush = _spinelli_brush(is_forest=stand_type == "forest")
        fell = _spinelli_fell(
            tree_volume_m3=tree_volume_m3,
            machine_power_kw=machine_power_kw,
            slope_percent=slope_value,
            carrier_type=carrier_type,
        )
        process = _spinelli_process(
            tree_volume_m3=tree_volume_m3,
            slope_percent=slope_value,
            machine_power_kw=machine_power_kw,
            head_type=head_type,
            carrier_type=carrier_type,
            species_group=species_group,
        )
        cycle_entries.extend(
            [
                ("Move in stand (Eq.2)", move * 0.01),
                ("Brush (Eq.3)", brush * 0.01),
                ("Fell (Eq.5)", fell * 0.01),
                ("Process (Eq.6)", process * 0.01),
            ]
        )
        accessory_ratio = float(
            (dataset.get("coefficients") or {})
            .get("accessory_ratio", {})
            .get("harvest_forest", 0.147)
        )
        delay_ratio_map = (dataset.get("coefficients") or {}).get("delay_ratio", {})
        delay_ratio = float(
            delay_ratio_map.get(
                "harvest_plantation" if stand_type == "plantation" else "harvest_forest", 0.50
            )
        )
    else:
        move = _spinelli_move_deck(tree_volume_m3)
        grab = _spinelli_grab(
            tree_volume_m3=tree_volume_m3,
            machine_power_kw=machine_power_kw,
            is_spider=is_spider,
        )
        process = _spinelli_process(
            tree_volume_m3=tree_volume_m3,
            slope_percent=slope_value,
            machine_power_kw=machine_power_kw,
            head_type=head_type,
            carrier_type=carrier_type,
            species_group=species_group,
        )
        cycle_entries.extend(
            [
                ("Move @ deck (Eq.1)", move * 0.01),
                ("Grab (Eq.4)", grab * 0.01),
                ("Process (Eq.6)", process * 0.01),
            ]
        )
        coeffs = dataset.get("coefficients") or {}
        accessory_ratio = float((coeffs.get("accessory_ratio") or {}).get("process_deck", 0.296))
        delay_ratio = float((coeffs.get("delay_ratio") or {}).get("process_deck", 0.44))

    delay_free_minutes_per_tree = sum(value for _, value in cycle_entries)
    if delay_free_minutes_per_tree <= 0:
        raise ValueError("Computed delay-free minutes per tree must be > 0.")
    trees_per_pmh_delay_free = 60.0 / delay_free_minutes_per_tree
    delay_free_productivity = tree_volume_m3 * trees_per_pmh_delay_free
    minutes_with_accessory = delay_free_minutes_per_tree * (1.0 + accessory_ratio)
    minutes_with_delay = minutes_with_accessory * (1.0 + delay_ratio)
    delay_multiplier = delay_free_minutes_per_tree / minutes_with_delay
    productivity_with_delay = delay_free_productivity * delay_multiplier
    utilisation_percent = delay_multiplier * 100.0
    notes = [
        "Spinelli, Hartsough & Magagnotti (2010) CTL regression (Forest Products Journal 60(3):226–235).",
        "Accessory (14.7% harvest / 29.6% process) and delay ratios (Spinelli & Visser 2008) follow the published benchmarks.",
    ]
    for extra in (dataset.get("source") or {}).get("notes") or []:
        notes.append(str(extra))
    return Spinelli2010ProcessorProductivityResult(
        operation=operation,
        tree_volume_m3=tree_volume_m3,
        slope_percent=slope_value,
        machine_power_kw=machine_power_kw,
        carrier_type=carrier_type,
        head_type=head_type,
        species_group=species_group,
        stand_type=stand_type,
        removals_per_ha=removals_per_ha,
        residuals_per_ha=residuals_per_ha,
        cycle_components_minutes=tuple(cycle_entries),
        delay_free_minutes_per_tree=delay_free_minutes_per_tree,
        trees_per_pmh_delay_free=trees_per_pmh_delay_free,
        delay_free_productivity_m3_per_pmh=delay_free_productivity,
        accessory_ratio=accessory_ratio,
        delay_ratio=delay_ratio,
        delay_multiplier=delay_multiplier,
        productivity_m3_per_pmh=productivity_with_delay,
        utilisation_percent=utilisation_percent,
        notes=tuple(notes),
    )


def estimate_processor_productivity_bertone2025(
    *,
    dbh_cm: float,
    height_m: float,
    logs_per_tree: float,
    tree_volume_m3: float,
    delay_multiplier: float | None = None,
) -> Bertone2025ProcessorProductivityResult:
    """
    Bertone & Manzone (2025) excavator processor regression (Italian Alps cable landings).

    Parameters
    ----------
    dbh_cm:
        Diameter at breast height (cm). Must be > 0.
    height_m:
        Tree height (m). Must be > 0.
    logs_per_tree:
        Average logs processed per tree. Must be > 0.
    tree_volume_m3:
        Tree volume (m³). Must be > 0.
    delay_multiplier:
        Optional utilisation multiplier (0,1]; defaults to the published delay fraction.

    Returns
    -------
    Bertone2025ProcessorProductivityResult
        Dataclass with cycle time, productivity, utilisation, fuel, and cost metrics.
    """
    if dbh_cm <= 0 or height_m <= 0 or logs_per_tree <= 0 or tree_volume_m3 <= 0:
        raise ValueError("dbh_cm, height_m, logs_per_tree, and tree_volume_m3 must be > 0.")
    dataset = _load_bertone2025_dataset()
    defaults = dataset.get("defaults") or {}
    cycle_seconds = -8.1893 + 2.3810 * dbh_cm + 1.8789 * height_m + 5.6562 * logs_per_tree
    cycle_seconds = max(cycle_seconds, 10.0)
    delay_free_productivity = tree_volume_m3 * (3600.0 / cycle_seconds)
    base_multiplier = 1.0 - float(defaults.get("delay_fraction", 0.429))
    multiplier = delay_multiplier if delay_multiplier is not None else base_multiplier
    if not (0.0 < multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1].")
    productivity_smh = delay_free_productivity * multiplier
    utilisation_percent = multiplier * 100.0
    fuel_l_per_smh = float(defaults.get("fuel_l_per_smh", 16.5))
    fuel_l_per_m3 = float(defaults.get("fuel_l_per_m3", 1.1))
    cost_per_smh = float(defaults.get("cost_per_smh_eur", 103.46))
    cost_per_m3 = float(defaults.get("cost_per_m3_eur", 4.95))
    cost_currency = "EUR"
    cost_base_year = defaults.get("cost_base_year")
    notes = tuple(str(n) for n in (dataset.get("source") or {}).get("notes") or [])
    return Bertone2025ProcessorProductivityResult(
        dbh_cm=dbh_cm,
        height_m=height_m,
        logs_per_tree=logs_per_tree,
        tree_volume_m3=tree_volume_m3,
        delay_free_cycle_seconds=cycle_seconds,
        delay_free_productivity_m3_per_pmh=delay_free_productivity,
        delay_multiplier=multiplier,
        productivity_m3_per_smh=productivity_smh,
        utilisation_percent=utilisation_percent,
        fuel_l_per_smh=fuel_l_per_smh,
        fuel_l_per_m3=fuel_l_per_m3,
        cost_per_smh=cost_per_smh,
        cost_per_m3=cost_per_m3,
        cost_currency=cost_currency,
        cost_base_year=(None if cost_base_year is None else int(cost_base_year)),
        notes=notes,
    )


def estimate_processor_productivity_borz2023(
    *, tree_volume_m3: float | None = None
) -> Borz2023ProcessorProductivityResult:
    """
    Borz et al. (2023) Romanian landing processor productivity (harvester-as-processor).

    Parameters
    ----------
    tree_volume_m3:
        Optional average tree volume (m³) for reporting purposes (dataset values are fixed).

    Returns
    -------
    Borz2023ProcessorProductivityResult
        Dataclass containing efficiency, productivity, fuel, and cost metrics.
    """
    dataset = _load_borz2023_dataset()
    metrics = dataset.get("metrics") or {}
    cost_base_year = metrics.get("cost_base_year")
    notes = tuple(str(n) for n in (dataset.get("source") or {}).get("notes") or [])
    return Borz2023ProcessorProductivityResult(
        tree_volume_m3=tree_volume_m3,
        efficiency_pmh_per_m3=float(metrics.get("efficiency_pmh_per_m3", 0.047) or 0.047),
        efficiency_smh_per_m3=float(metrics.get("efficiency_smh_per_m3", 0.053) or 0.053),
        productivity_m3_per_pmh=float(metrics.get("productivity_m3_per_pmh", 21.41) or 21.41),
        productivity_m3_per_smh=float(metrics.get("productivity_m3_per_smh", 18.81) or 18.81),
        fuel_l_per_h=float(metrics.get("fuel_l_per_h", 21.0) or 21.0),
        fuel_l_per_m3=float(metrics.get("fuel_l_per_m3", 0.78) or 0.78),
        cost_per_m3=float(metrics.get("cost_per_m3_eur", 10.5) or 10.5),
        cost_currency="EUR",
        cost_base_year=(None if cost_base_year is None else int(cost_base_year)),
        recovery_percent=float(metrics.get("recovery_percent", 95.0) or 95.0),
        utilisation_percent=float(metrics.get("utilisation_percent", 79.0) or 79.0),
        notes=notes,
    )


def estimate_processor_productivity_nakagawa2010(
    *,
    dbh_cm: float | None = None,
    piece_volume_m3: float | None = None,
    delay_multiplier: float = 1.0,
) -> Nakagawa2010ProcessorProductivityResult:
    """
    Nakagawa et al. (2010) excavator-processor regression (Hokkaido thinning).

    Parameters
    ----------
    dbh_cm:
        Diameter at breast height (cm). Provide either ``dbh_cm`` or ``piece_volume_m3``.
    piece_volume_m3:
        Piece volume (m³). Provide either this or ``dbh_cm``.
    delay_multiplier:
        Utilisation multiplier (0,1] applied to the delay-free result.

    Returns
    -------
    Nakagawa2010ProcessorProductivityResult
        Dataclass describing which model was used, productivity outputs, and study notes.

    Raises
    ------
    ValueError
        If neither (or both invalid) inputs are provided, or multiplier outside (0,1].
    """
    if dbh_cm is None and piece_volume_m3 is None:
        raise ValueError("Provide either dbh_cm or piece_volume_m3 for the Nakagawa (2010) helper.")
    if dbh_cm is not None and dbh_cm <= 0:
        raise ValueError("dbh_cm must be > 0.")
    if piece_volume_m3 is not None and piece_volume_m3 <= 0:
        raise ValueError("piece_volume_m3 must be > 0.")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1].")
    dataset = _load_nakagawa2010_dataset()
    models = dataset.get("models") or {}
    notes = tuple(str(n) for n in (dataset.get("source") or {}).get("notes") or [])
    base_productivity: float | None = None
    model_used: Literal["dbh", "piece_volume"]
    if dbh_cm is not None:
        dbh_model = models.get("dbh") or {}
        coeff = float(dbh_model.get("coefficient", 0.363) or 0.363)
        exponent = float(dbh_model.get("exponent", 1.116) or 1.116)
        base_productivity = coeff * (dbh_cm**exponent)
        model_used = "dbh"
    else:
        piece_model = models.get("piece_volume") or {}
        coeff = float(piece_model.get("coefficient", 20.46) or 20.46)
        exponent = float(piece_model.get("exponent", 0.482) or 0.482)
        base_productivity = coeff * (piece_volume_m3**exponent)
        model_used = "piece_volume"
    productivity = base_productivity * delay_multiplier
    return Nakagawa2010ProcessorProductivityResult(
        dbh_cm=dbh_cm,
        piece_volume_m3=piece_volume_m3,
        model_used=model_used,
        delay_free_productivity_m3_per_pmh=base_productivity,
        delay_multiplier=delay_multiplier,
        productivity_m3_per_pmh=productivity,
        notes=notes,
    )


def estimate_clambunk_productivity_adv2n26(
    *,
    travel_empty_distance_m: float,
    stems_per_cycle: float,
    average_stem_volume_m3: float = ADV2N26_DEFAULT_STEM_VOLUME_M3,
    payload_m3_per_cycle: float | None = None,
    utilization: float = ADV2N26_DEFAULT_UTILISATION,
    in_cycle_delay_minutes: float | None = None,
) -> ClambunkProductivityResult:
    """
    Estimate clambunk/hoe-forwarder productivity using ADV2N26 regressions.

    Parameters
    ----------
    travel_empty_distance_m:
        Empty travel distance per cycle (m). Must be ≥ 0.
    stems_per_cycle:
        Stems transported per cycle. Must be > 0.
    average_stem_volume_m3:
        Average stem volume (m³). Defaults to ADV2N26 mean.
    payload_m3_per_cycle:
        Optional override for payload per cycle; when ``None`` it is derived from stems × volume.
    utilization:
        Utilisation fraction (0,1] applied to delay-free productivity.
    in_cycle_delay_minutes:
        Optional per-cycle delay minutes added to cycle time (defaults to dataset value).

    Returns
    -------
    ClambunkProductivityResult
        Dataclass with delay-free/utilisation-adjusted productivity and payload assumptions.
    """

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
    """
    ADV5N1 loader-forwarder regression result (distance/slope specific).

    Attributes
    ----------
    forwarding_distance_m:
        External forwarding distance (m).
    slope_class:
        Slope class key (e.g., ``"0_10"``).
    payload_m3_per_cycle:
        Payload per cycle (m³).
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity from the regression.
    delay_multiplier:
        Utilisation factor applied post regression.
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    pieces_per_cycle:
        Pieces per cycle implied by the regression.
    cycles_per_hour:
        Cycle rate.
    notes:
        Study notes from Advantage Vol. 5 No. 1.
    """

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
    """
    ADV5N6 processor regression summary (hot/cold processing scenarios).

    Attributes
    ----------
    stem_source:
        ``"loader_forwarded"`` or ``"grapple_yarded"`` source.
    processing_mode:
        ``"cold"``, ``"hot"``, or ``"low_volume"``.
    description:
        Scenario description.
    delay_free_productivity_m3_per_pmh:
        Delay-free m³/PMH₀ from the regression.
    utilisation_percent:
        Utilisation percentage assumed in the scenario.
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    cost_per_m3_cad:
        Cost per cubic metre (inflated when a base year is provided).
    loader_hours, processor_hours:
        Hour allocations in the scenario.
    notes:
        Additional notes from the publication.
    cost_base_year:
        Base year for the cost figures.
    """

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
class ADV7N3ProcessorProductivityResult:
    """
    ADV7N3 Canfor Mackenzie processor/loader regression summary.

    Attributes
    ----------
    machine_id:
        Machine identifier (Hyundai 210 or JD 892).
    machine_label:
        Human-readable label.
    description:
        Scenario description.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    utilisation_percent:
        Utilisation percentage used to derive the final value.
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    loader_hours, processor_hours:
        Hours allocated to each machine.
    cost_per_m3_cad:
        Cost per cubic metre (inflated to current CAD when possible).
    notes:
        Additional notes or caveats.
    cost_base_year:
        Base year for the cost metric.
    """

    machine_id: str
    machine_label: str
    description: str
    shift_productivity_m3_per_pmh: float
    shift_productivity_m3_per_smh: float
    utilisation_percent: float
    availability_percent: float
    total_volume_m3: float
    detailed_productivity_m3_per_pmh: float | None
    detailed_stems_per_pmh: float | None
    detailed_avg_stem_volume_m3: float | None
    processor_cost_cad_per_m3: float
    processor_cost_cad_per_m3_base_year: float | None
    loader_cost_cad_per_m3: float | None
    loader_cost_cad_per_m3_base_year: float | None
    system_cost_cad_per_m3: float | None
    system_cost_cad_per_m3_base_year: float | None
    processor_hourly_cost_cad_per_smh: float | None
    loader_hourly_cost_cad_per_smh: float | None
    cost_base_year: int | None
    loader_support_percent: float | None = None
    loader_task_distribution_percent: Mapping[str, float] | None = None
    loader_avg_travel_distance_m: float | None = None
    loader_travel_distance_block5_m: float | None = None
    non_processing_time_minutes_per_cycle: Mapping[str, float] | None = None
    cycle_distribution_percent: Mapping[str, float] | None = None
    notes: tuple[str, ...] | None = None


@dataclass(frozen=True)
class TN103ProcessorProductivityResult:
    """
    TN-103 Caterpillar DL221 processor scenario summary.

    Attributes
    ----------
    scenario:
        Scenario name (e.g., ``"feller_bunched"``).
    description:
        Scenario description.
    stem_source:
        Source of stems (hand felled vs bunched).
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    utilisation_percent:
        Utilisation percentage observed.
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    cost_per_m3_cad:
        Cost per cubic metre (inflated when base year provided).
    loader_hours, processor_hours:
        Time allocation per shift.
    notes:
        Scenario notes.
    cost_base_year:
        Base year for cost metrics.
    """

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
    """
    TN-166 telescopic-boom processor regression summary.

    Attributes
    ----------
    scenario:
        Scenario name.
    description:
        Description of the telescopic-boom workflow.
    stem_source:
        ``"grapple_yarded"``, ``"right_of_way"``, etc.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    utilisation_percent:
        Utilisation percentage.
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    cost_per_m3_cad:
        Cost per cubic metre (inflated to current CAD when possible).
    accuracy_percent:
        Model accuracy indicator from the bulletin.
    cost_base_year:
        Base year for the cost metric.
    notes:
        Additional notes.
    """

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
    """
    TR-87 processor scenario summary (day/night shifts, Timberjack TJ90).

    Attributes
    ----------
    scenario:
        Scenario name.
    description:
        Scenario description (day, night, wait-for-wood, etc.).
    stem_source:
        Stem source description.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    utilisation_percent:
        Utilisation percentage.
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    cost_per_m3_cad:
        Cost per cubic metre (inflated when possible).
    machine_allocation_hours:
        Mapping of machine → hours for the scenario.
    notes:
        Additional notes.
    cost_base_year:
        Base year for the cost metric.
    """

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


@dataclass(frozen=True)
class TR106ProcessorProductivityResult:
    """
    TR-106 lodgepole pine processor regression summary.

    Attributes
    ----------
    scenario:
        Scenario name, e.g., ``"kp40_case_1187"``.
    description:
        Scenario description.
    machine:
        Processor/machine description.
    delay_free_productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    utilisation_percent:
        Utilisation percentage used in the study.
    productivity_m3_per_pmh:
        Utilisation-adjusted productivity.
    cost_per_m3_cad:
        Cost per cubic metre (inflated when base year provided).
    loader_hours, processor_hours:
        Hours allocated per shift.
    notes:
        Additional notes.
    cost_base_year:
        Base year for the cost figure.
    """

    scenario: str
    description: str
    machine: str
    stem_source: str
    mean_stem_volume_m3: float | None
    stems_per_pmh: float | None
    productivity_m3_per_pmh: float | None
    net_productivity_m3_per_pmh: float | None
    logs_per_stem: float | None
    cycle_minutes_per_stem: float | None
    utilisation_percent: float | None
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
    """
    ADV5N6 processor regression (hot/cold/low-volume modes for coastal BC).

    Parameters
    ----------
    stem_source:
        ``"loader_forwarded"`` or ``"grapple_yarded"``. Loader-forwarded blocks only support
        ``processing_mode="cold"``.
    processing_mode:
        ``"cold"``, ``"hot"``, or ``"low_volume"`` (grapple-yarded only).

    Returns
    -------
    ADV5N6ProcessorProductivityResult
        Dataclass with productivity, utilisation, and inflated cost metrics for the scenario.
    """
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
        cost_cad_per_m3=cost_cad_per_m3
        if cost_cad_per_m3 is not None
        else float(payload["cost_cad_per_m3"]),
        machine_rate_cad_per_smh=machine_rate,
        notes=tuple(notes) if notes else None,
        cost_base_year=cost_base_year,
    )


def estimate_processor_productivity_adv7n3(
    *, machine: Literal["hyundai_210", "john_deere_892"]
) -> ADV7N3ProcessorProductivityResult:
    """
    ADV7N3 Canfor Mackenzie processor regression (Hyundai 210 vs JD 892).

    Parameters
    ----------
    machine:
        ``"hyundai_210"`` or ``"john_deere_892"``.

    Returns
    -------
    ADV7N3ProcessorProductivityResult
        Dataclass with productivity, utilisation, loader-support, and cost metrics for the machine.
    """
    dataset = _load_adv7n3_dataset()
    processors = {
        str(entry["id"]).lower(): entry
        for entry in dataset.get("processors", [])
        if entry.get("id")
    }
    normalized = machine.lower()
    payload = processors.get(normalized)
    if payload is None:
        valid = ", ".join(sorted(processors))
        raise ValueError(f"Unknown ADV7N3 machine '{machine}'. Valid options: {valid}.")

    loader_support = dataset.get("loader_support") or {}

    def _float(value: object | None) -> float | None:
        if value is None:
            return None
        return float(value)

    def _float_mapping(mapping: Mapping[str, object] | None) -> Mapping[str, float] | None:
        if not mapping:
            return None
        return {key: float(value) for key, value in mapping.items()}

    shift = payload.get("shift_summary") or {}
    detailed = payload.get("detailed_timing") or {}
    cycle_distribution = payload.get("cycle_distribution_percent") or {}
    costs = payload.get("costs") or {}
    base_year = costs.get("cost_base_year")

    processor_cost_base = _float(costs.get("processor_cost_per_m3_cad_2004"))
    loader_cost_base = _float(costs.get("loader_cost_per_m3_cad_2004"))
    system_cost_base = _float(costs.get("system_cost_per_m3_cad_2004"))

    processor_cost = _inflate_cost(processor_cost_base, base_year) or processor_cost_base or 0.0
    loader_cost = _inflate_cost(loader_cost_base, base_year) or loader_cost_base
    system_cost = _inflate_cost(system_cost_base, base_year) or system_cost_base

    loader_task_distribution = _float_mapping(loader_support.get("task_distribution_percent"))
    non_processing = _float_mapping(loader_support.get("non_processing_time_minutes_per_cycle"))

    notes = payload.get("notes")
    return ADV7N3ProcessorProductivityResult(
        machine_id=payload["id"],
        machine_label=payload.get("label", payload["id"]),
        description=payload.get("description", ""),
        shift_productivity_m3_per_pmh=float(shift.get("productivity_m3_per_pmh") or 0.0),
        shift_productivity_m3_per_smh=float(shift.get("productivity_m3_per_smh") or 0.0),
        utilisation_percent=float(shift.get("utilisation_percent") or 0.0),
        availability_percent=float(shift.get("availability_percent") or 0.0),
        total_volume_m3=float(shift.get("total_volume_m3") or 0.0),
        detailed_productivity_m3_per_pmh=_float(detailed.get("productivity_m3_per_pmh")),
        detailed_stems_per_pmh=_float(detailed.get("stems_per_pmh")),
        detailed_avg_stem_volume_m3=_float(detailed.get("average_stem_volume_m3")),
        processor_cost_cad_per_m3=processor_cost,
        processor_cost_cad_per_m3_base_year=processor_cost_base,
        loader_cost_cad_per_m3=loader_cost,
        loader_cost_cad_per_m3_base_year=loader_cost_base,
        system_cost_cad_per_m3=system_cost,
        system_cost_cad_per_m3_base_year=system_cost_base,
        processor_hourly_cost_cad_per_smh=_float(costs.get("processor_hourly_cost_cad_per_smh")),
        loader_hourly_cost_cad_per_smh=_float(costs.get("loader_hourly_cost_cad_per_smh")),
        cost_base_year=int(base_year) if base_year is not None else None,
        loader_support_percent=_float(loader_support.get("assist_time_percent")),
        loader_task_distribution_percent=loader_task_distribution,
        loader_avg_travel_distance_m=_float(loader_support.get("avg_travel_distance_m")),
        loader_travel_distance_block5_m=_float(loader_support.get("block5_travel_distance_m")),
        non_processing_time_minutes_per_cycle=non_processing,
        cycle_distribution_percent=_float_mapping(cycle_distribution),
        notes=tuple(notes) if notes else None,
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
    """
    TN-103 Caterpillar DL221 processor scenarios (feller-bunched vs hand-felled).

    Parameters
    ----------
    scenario:
        Scenario identifier as documented in TN-103 (area A/B, combined observed/high-util).

    Returns
    -------
    TN103ProcessorProductivityResult
        Dataclass containing utilisation, productivity, and cost metrics for the scenario.
    """
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
    """
    TN-166 telescopic-boom processor regression (mixed scenarios).

    Parameters
    ----------
    scenario:
        ``"grapple_yarded"``, ``"right_of_way"``, or ``"mixed_shift"``.

    Returns
    -------
    TN166ProcessorProductivityResult
        Dataclass with productivity, utilisation, and cost metrics.
    """
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
    """
    TR-87 processor regression (Timberjack TJ90 day/night + wait-for-wood).

    Parameters
    ----------
    scenario:
        Scenario identifier from TR-87 (day/night, combined, wait-adjusted).

    Returns
    -------
    TR87ProcessorProductivityResult
        Dataclass with productivity, utilisation, loader support, and cost metrics.
    """
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


def estimate_processor_productivity_tr106(
    *,
    scenario: Literal[
        "case1187_octnov",
        "case1187_feb",
        "kp40_caterpillar225",
        "kp40_linkbelt_l2800",
        "kp40_caterpillar_el180",
    ],
) -> TR106ProcessorProductivityResult:
    """
    TR-106 lodgepole pine processor regression (Case 1187 + Steyr KP40 variants).

    Parameters
    ----------
    scenario:
        Scenario identifier from the TR-106 dataset (Case vs KP40 combinations).

    Returns
    -------
    TR106ProcessorProductivityResult
        Dataclass with productivity, utilisation, and cost metrics for the scenario.
    """
    scenarios = _load_tr106_scenarios()
    payload = scenarios.get(scenario)
    if payload is None:
        valid = ", ".join(sorted(scenarios))
        raise ValueError(f"Unknown TR-106 scenario '{scenario}'. Valid options: {valid}.")

    def _maybe(name: str) -> float | None:
        value = payload.get(name)
        return None if value is None else float(value)

    notes = payload.get("notes")
    cost_base_year = payload.get("cost_base_year")
    return TR106ProcessorProductivityResult(
        scenario=payload.get("name", scenario),
        description=payload.get("description", ""),
        machine=payload.get("machine", ""),
        stem_source=payload.get("stem_source", "grapple_yarded"),
        mean_stem_volume_m3=_maybe("mean_stem_volume_m3"),
        stems_per_pmh=_maybe("stems_per_pmh"),
        productivity_m3_per_pmh=_maybe("productivity_m3_per_pmh"),
        net_productivity_m3_per_pmh=_maybe("net_productivity_m3_per_pmh"),
        logs_per_stem=_maybe("logs_per_stem"),
        cycle_minutes_per_stem=_maybe("cycle_minutes_per_stem"),
        utilisation_percent=_maybe("utilisation_percent"),
        notes=tuple(notes) if notes else None,
        cost_base_year=cost_base_year,
    )


def estimate_loader_productivity_barko450(
    *,
    scenario: Literal["ground_skid_block", "cable_yard_block"],
    utilisation_override: float | None = None,
) -> LoaderBarko450ProductivityResult:
    """
    Estimate Barko 450 heel-boom loader productivity/costs using TN-46 data.

    Parameters
    ----------
    scenario:
        ``"ground_skid_block"`` or ``"cable_yard_block"``.
    utilisation_override:
        Optional utilisation fraction (0,1] that replaces the study value. Costs and productivity
        are scaled accordingly.

    Returns
    -------
    LoaderBarko450ProductivityResult
        Dataclass with productivity, utilisation, and inflated cost metrics for the scenario.
    """
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


@lru_cache(maxsize=1)
def _load_kizha2020_scenarios() -> dict[str, dict[str, object]]:
    payload = _load_kizha2020_dataset()
    cost_meta = payload.get("costing") or {}
    machine_rate = float(cost_meta.get("machine_rate_per_pmh", 0.0) or 0.0)
    currency = cost_meta.get("currency")
    base_year = cost_meta.get("base_year")
    scenarios: dict[str, dict[str, object]] = {}
    for entry in payload.get("scenarios", []):
        mode = entry.get("mode")
        if not mode:
            continue
        combined = {**entry}
        combined.setdefault("machine_rate_per_pmh", machine_rate)
        combined.setdefault("currency", currency)
        combined.setdefault("cost_base_year", base_year)
        scenarios[str(mode).lower()] = combined
    return scenarios


def estimate_loader_hot_cold_productivity(
    *,
    mode: Literal["hot", "cold"],
) -> LoaderHotColdProductivityResult:
    """
    Estimate loader productivity for hot vs cold yards (Kizha et al. 2020).

    Parameters
    ----------
    mode:
        ``"hot"`` yard (swing/land immediately) or ``"cold"`` yard (deck and reload later).

    Returns
    -------
    LoaderHotColdProductivityResult
        Dataclass capturing utilisation, delay costs, and productivity metrics for the mode.
    """
    scenarios = _load_kizha2020_scenarios()
    payload = scenarios.get(mode.lower())
    if payload is None:
        valid = ", ".join(sorted(scenarios))
        raise ValueError(f"Unknown Kizha et al. (2020) mode '{mode}'. Valid options: {valid}.")

    def _maybe_float(key: str) -> float | None:
        value = payload.get(key)
        return None if value is None else float(value)

    breakdown_input = payload.get("dominant_delay_breakdown_percent_of_delay") or {}
    breakdown: list[tuple[str, float]] = []
    if isinstance(breakdown_input, dict):
        for k, v in breakdown_input.items():
            try:
                breakdown.append((str(k).replace("_", " "), float(v)))
            except (TypeError, ValueError):
                continue
    machine_rate = float(payload.get("machine_rate_per_pmh", 0.0) or 0.0)
    delay_cost = _maybe_float("delay_cost_usd_per_pmh") or 0.0
    effective = machine_rate + delay_cost

    notes = payload.get("notes") or ()
    return LoaderHotColdProductivityResult(
        mode=payload.get("mode", mode).lower(),  # type: ignore[arg-type]
        description=payload.get("description", ""),
        utilisation_percent=float(payload.get("utilisation_percent", 0.0) or 0.0),
        operational_delay_percent_of_total_time=float(
            payload.get("operational_delay_percent_of_total_time", 0.0) or 0.0
        ),
        delay_cost_per_pmh=delay_cost,
        machine_rate_per_pmh=machine_rate,
        effective_cost_per_pmh=effective,
        currency=payload.get("currency"),
        cost_base_year=payload.get("cost_base_year"),
        dominant_delay_breakdown_percent_of_delay=tuple(breakdown),
        bottleneck=payload.get("bottleneck"),
        notes=tuple(str(n) for n in notes),
        observed_days=(
            int(payload["observed_days"]) if payload.get("observed_days") is not None else None
        ),
    )
