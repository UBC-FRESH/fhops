"""Helpers for Lahrsen (2025) BC feller-buncher productivity models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

import numpy as np

from fhops.core.errors import FHOPSValueError
from fhops.productivity.ranges import load_lahrsen_ranges

try:  # pragma: no cover - optional dependency
    import pacal  # type: ignore
except Exception:  # pragma: no cover - fallback path
    pacal = None


class LahrsenModel(str, Enum):
    """Available coefficient sets from Lahrsen (2025)."""

    DAILY = "daily"
    CUTBLOCK = "cutblock"
    CUTBLOCK_HETEROSCEDASTIC = "cutblock_hetero"


@dataclass(frozen=True)
class ProductivityEstimate:
    """Result of a Lahrsen (2025) productivity prediction."""

    model: LahrsenModel
    avg_stem_size: float
    volume_per_ha: float
    stem_density: float
    ground_slope: float
    predicted_m3_per_pmh: float
    ranges: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    out_of_range: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductivityDistributionEstimate:
    """Expected productivity when inputs are random variates."""

    model: LahrsenModel
    method: str
    expected_m3_per_pmh: float
    std_m3_per_pmh: float | None
    sample_count: int
    pacal_used: bool


@dataclass(frozen=True)
class _Coefficients:
    stem_size: float
    volume_per_ha: float
    stem_density: float
    ground_slope: float
    intercept: float = 0.0


_COEFFICIENTS: Mapping[LahrsenModel, _Coefficients] = {
    LahrsenModel.DAILY: _Coefficients(
        stem_size=67.99345,
        volume_per_ha=0.05943,
        stem_density=0.01236,
        ground_slope=-0.46146,
    ),
    LahrsenModel.CUTBLOCK: _Coefficients(
        stem_size=61.02,
        volume_per_ha=0.052,
        stem_density=0.014,
        ground_slope=-0.24,
    ),
    LahrsenModel.CUTBLOCK_HETEROSCEDASTIC: _Coefficients(
        stem_size=57.08,
        volume_per_ha=0.031,
        stem_density=0.003,
        ground_slope=-0.36,
        intercept=0.013,  # captures block-size effect when set to zero.
    ),
}

_RANGE_DATA = load_lahrsen_ranges()
_MODEL_TO_SECTION = {
    LahrsenModel.DAILY: "daily",
    LahrsenModel.CUTBLOCK: "cutblock",
    LahrsenModel.CUTBLOCK_HETEROSCEDASTIC: "cutblock",
}
_FIELD_KEYS = {
    "avg_stem_size": "avg_stem_size_m3",
    "volume_per_ha": "volume_per_ha_m3",
    "stem_density": "stem_density_per_ha",
    "ground_slope": "ground_slope_percent",
}


def _range_bounds(model: LahrsenModel, key: str) -> Mapping[str, float]:
    section = _MODEL_TO_SECTION[model]
    field_key = _FIELD_KEYS[key]
    return _RANGE_DATA[section][field_key]


def _check_range(
    *,
    value: float,
    name: str,
    bounds: Mapping[str, float],
    strict: bool,
    violations: list[str],
) -> None:
    lo = bounds.get("min")
    hi = bounds.get("max")
    if value <= 0:
        raise FHOPSValueError(f"{name} must be positive (got {value}).")
    if lo is None or hi is None:
        return
    if lo <= value <= hi:
        return
    msg = f"{name}={value} outside Lahrsen (2025) observed range [{lo}, {hi}]"
    if strict:
        raise FHOPSValueError(msg)
    violations.append(msg)


def estimate_productivity(
    *,
    avg_stem_size: float,
    volume_per_ha: float,
    stem_density: float,
    ground_slope: float,
    model: LahrsenModel = LahrsenModel.DAILY,
    validate_ranges: bool = True,
) -> ProductivityEstimate:
    """Estimate productivity (m³/PMH15) using Lahrsen (2025) coefficients.

    Parameters
    ----------
    avg_stem_size:
        Mean harvested stem size (m³/stem).
    volume_per_ha:
        Mean harvested volume per hectare (m³/ha).
    stem_density:
        Mean harvested stem density (trees/ha).
    ground_slope:
        Average ground slope (%).
    model:
        Which Lahrsen coefficient set to use (daily machine-level by default).
    validate_ranges:
        Whether to enforce observed BC ranges (recommended when working with
        real operations rather than synthetic experiments).
    """

    if validate_ranges:
        strict = True
    else:
        strict = False
    bounds_cache = {
        "avg_stem_size": _range_bounds(model, "avg_stem_size"),
        "volume_per_ha": _range_bounds(model, "volume_per_ha"),
        "stem_density": _range_bounds(model, "stem_density"),
        "ground_slope": _range_bounds(model, "ground_slope"),
    }
    violations: list[str] = []
    _check_range(
        value=avg_stem_size,
        name="avg_stem_size",
        bounds=bounds_cache["avg_stem_size"],
        strict=strict,
        violations=violations,
    )
    _check_range(
        value=volume_per_ha,
        name="volume_per_ha",
        bounds=bounds_cache["volume_per_ha"],
        strict=strict,
        violations=violations,
    )
    _check_range(
        value=stem_density,
        name="stem_density",
        bounds=bounds_cache["stem_density"],
        strict=strict,
        violations=violations,
    )
    _check_range(
        value=ground_slope,
        name="ground_slope",
        bounds=bounds_cache["ground_slope"],
        strict=strict,
        violations=violations,
    )

    coeffs = _COEFFICIENTS[model]
    predicted = (
        coeffs.intercept
        + coeffs.stem_size * avg_stem_size
        + coeffs.volume_per_ha * volume_per_ha
        + coeffs.stem_density * stem_density
        + coeffs.ground_slope * ground_slope
    )

    return ProductivityEstimate(
        model=model,
        avg_stem_size=avg_stem_size,
        volume_per_ha=volume_per_ha,
        stem_density=stem_density,
        ground_slope=ground_slope,
        predicted_m3_per_pmh=predicted,
        ranges=bounds_cache,
        out_of_range=tuple(violations),
    )


def _pacal_available() -> bool:
    return pacal is not None


def _build_pacal_var(mu: float, sigma: float, bounds: Mapping[str, float]):  # pragma: no cover - requires pacal
    assert pacal is not None
    dist = pacal.NormalDistr(mu, sigma)
    lower = bounds.get("min")
    upper = bounds.get("max")
    if lower is not None:
        dist = dist | pacal.Gt(lower)
    if upper is not None:
        dist = dist | pacal.Lt(upper)
    return dist


def _sample_truncated_normal(
    mu: float,
    sigma: float,
    bounds: Mapping[str, float],
    size: int,
) -> np.ndarray:
    if sigma <= 0 or size <= 0:
        return np.full(max(size, 1), mu)
    lower = bounds.get("min")
    upper = bounds.get("max")
    samples = np.random.normal(mu, sigma, size)
    if lower is not None:
        mask = samples < lower
        while mask.any():
            samples[mask] = np.random.normal(mu, sigma, mask.sum())
            mask = samples < lower
    if upper is not None:
        mask = samples > upper
        while mask.any():
            samples[mask] = np.random.normal(mu, sigma, mask.sum())
            mask = samples > upper
    return samples


def estimate_productivity_distribution(
    *,
    avg_stem_size_mu: float,
    avg_stem_size_sigma: float,
    volume_per_ha_mu: float,
    volume_per_ha_sigma: float,
    stem_density_mu: float,
    stem_density_sigma: float,
    ground_slope_mu: float,
    ground_slope_sigma: float,
    model: LahrsenModel = LahrsenModel.DAILY,
    method: str = "auto",
    samples: int = 5000,
) -> ProductivityDistributionEstimate:
    """Estimate expected productivity when inputs are random variates."""

    coeffs = _COEFFICIENTS[model]
    bounds = {
        "avg_stem_size": _range_bounds(model, "avg_stem_size"),
        "volume_per_ha": _range_bounds(model, "volume_per_ha"),
        "stem_density": _range_bounds(model, "stem_density"),
        "ground_slope": _range_bounds(model, "ground_slope"),
    }

    use_pacal = method == "pacal" or (method == "auto" and _pacal_available())
    if use_pacal:
        if not _pacal_available():  # pragma: no cover - depends on pacal
            raise FHOPSValueError("PaCal not available; install 'pacal' or set method='monte-carlo'.")
        stem = _build_pacal_var(avg_stem_size_mu, avg_stem_size_sigma, bounds["avg_stem_size"])
        volume = _build_pacal_var(volume_per_ha_mu, volume_per_ha_sigma, bounds["volume_per_ha"])
        density = _build_pacal_var(stem_density_mu, stem_density_sigma, bounds["stem_density"])
        slope = _build_pacal_var(ground_slope_mu, ground_slope_sigma, bounds["ground_slope"])
        expr = (
            coeffs.intercept
            + coeffs.stem_size * stem
            + coeffs.volume_per_ha * volume
            + coeffs.stem_density * density
            + coeffs.ground_slope * slope
        )
        expected = float(expr.mean())
        std = float(expr.std()) if hasattr(expr, "std") else None
        return ProductivityDistributionEstimate(
            model=model,
            method="pacal",
            expected_m3_per_pmh=expected,
            std_m3_per_pmh=std,
            sample_count=0,
            pacal_used=True,
        )

    samples = max(samples, 1)
    stem_s = _sample_truncated_normal(avg_stem_size_mu, avg_stem_size_sigma, bounds["avg_stem_size"], samples)
    volume_s = _sample_truncated_normal(volume_per_ha_mu, volume_per_ha_sigma, bounds["volume_per_ha"], samples)
    density_s = _sample_truncated_normal(stem_density_mu, stem_density_sigma, bounds["stem_density"], samples)
    slope_s = _sample_truncated_normal(ground_slope_mu, ground_slope_sigma, bounds["ground_slope"], samples)
    preds = (
        coeffs.intercept
        + coeffs.stem_size * stem_s
        + coeffs.volume_per_ha * volume_s
        + coeffs.stem_density * density_s
        + coeffs.ground_slope * slope_s
    )
    expected = float(np.mean(preds))
    std = float(np.std(preds, ddof=1)) if samples > 1 else 0.0
    return ProductivityDistributionEstimate(
        model=model,
        method="monte-carlo",
        expected_m3_per_pmh=expected,
        std_m3_per_pmh=std,
        sample_count=samples,
        pacal_used=False,
    )
