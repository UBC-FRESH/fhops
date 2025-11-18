"""CTL harvester productivity helpers."""

from __future__ import annotations

from dataclasses import dataclass

import math

from fhops.core.errors import FHOPSValueError


@dataclass(frozen=True)
class ADV6N10HarvesterInputs:
    """Inputs required by the ADV6N10 single-grip harvester regression."""

    stem_volume_m3: float
    products_count: float
    stems_per_cycle: float
    mean_log_length_m: float


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise FHOPSValueError(f"{name} must be > 0 (got {value}).")


def estimate_harvester_productivity_adv6n10(
    inputs: ADV6N10HarvesterInputs,
) -> float:
    """Estimate CTL harvester productivity (m³/PMH) using ADV6N10 regression."""

    _validate_positive("stem_volume_m3", inputs.stem_volume_m3)
    _validate_positive("products_count", inputs.products_count)
    _validate_positive("stems_per_cycle", inputs.stems_per_cycle)
    _validate_positive("mean_log_length_m", inputs.mean_log_length_m)

    productivity = (
        50.2
        * (inputs.stem_volume_m3 ** 0.68)
        * (inputs.products_count ** -0.09)
        * (inputs.stems_per_cycle ** 0.22)
        * (inputs.mean_log_length_m ** 0.34)
    )
    if productivity <= 0:
        raise FHOPSValueError("Derived ADV6N10 harvester productivity must be > 0.")
    return productivity


_ADV5N30_POINTS = (
    (0.30, 18.0),
    (0.50, 19.0),
    (0.70, 23.0),
)


def estimate_harvester_productivity_adv5n30(
    *, removal_fraction: float, brushed: bool = False
) -> float:
    """Estimate harvester productivity for ADV5N30 removal levels (m³/PMH)."""

    if removal_fraction <= 0 or removal_fraction > 1:
        raise FHOPSValueError(
            "removal_fraction must be within (0, 1]; expected 0.30–0.70 for ADV5N30 context."
        )
    (x0, y0), (x1, y1), (x2, y2) = _ADV5N30_POINTS
    if removal_fraction <= x0:
        base = y0 if removal_fraction == x0 else _lerp(y0, y1, (removal_fraction - x0) / (x1 - x0))
    elif removal_fraction >= x2:
        base = y2 if removal_fraction == x2 else _lerp(y1, y2, (removal_fraction - x1) / (x2 - x1))
    else:
        if removal_fraction <= x1:
            base = _lerp(y0, y1, (removal_fraction - x0) / (x1 - x0))
        else:
            base = _lerp(y1, y2, (removal_fraction - x1) / (x2 - x1))
    if base <= 0:
        raise FHOPSValueError("Derived ADV5N30 harvester productivity must be > 0.")
    if brushed:
        base *= 1.21  # 21% increase per ADV5N30 brushing trial.
    return base


def _lerp(y_a: float, y_b: float, t: float) -> float:
    return y_a + (y_b - y_a) * max(0.0, min(1.0, t))


@dataclass(frozen=True)
class TN292HarvesterInputs:
    """Inputs for the TN292 harvester regression (tree size + density)."""

    stem_volume_m3: float
    stand_density_per_ha: float
    density_basis: str = "pre"  # "pre" or "post"


def estimate_harvester_productivity_tn292(inputs: TN292HarvesterInputs) -> float:
    """Estimate harvester productivity (m³/PMH) based on TN292 regressions."""

    _validate_positive("stem_volume_m3", inputs.stem_volume_m3)
    _validate_positive("stand_density_per_ha", inputs.stand_density_per_ha)
    density_basis = inputs.density_basis.lower()
    if density_basis not in {"pre", "post"}:
        raise FHOPSValueError("density_basis must be 'pre' or 'post'.")

    # Stem volume component (linear regressions from Figure II-A).
    if inputs.stem_volume_m3 < 0.05 or inputs.stem_volume_m3 > 0.30:
        raise FHOPSValueError("stem_volume_m3 outside TN292 observed range (0.05–0.30).")
    if density_basis == "pre":
        vol_component = -5638.6 * inputs.stem_volume_m3 + 2949.6
        density_ln = math.log(inputs.stand_density_per_ha)
        density_component = -4.0842 * density_ln + 48.602
    else:
        vol_component = -4509.5 * inputs.stem_volume_m3 + 1864.6
        density_ln = math.log(inputs.stand_density_per_ha)
        density_component = -7.0706 * density_ln + 73.977
    productivity = min(vol_component, density_component)
    if productivity <= 0:
        raise FHOPSValueError("Derived TN292 harvester productivity must be > 0.")
    return productivity


def estimate_harvester_productivity_kellogg1994(*, dbh_cm: float) -> float:
    """Linear dbh → m³/PMH regression from Kellogg & Bettinger (1994)."""

    _validate_positive("dbh_cm", dbh_cm)
    if dbh_cm < 10.0 or dbh_cm > 50.0:
        raise FHOPSValueError("dbh_cm outside Kellogg & Bettinger study range (10–50 cm).")
    productivity = -17.48 + 2.11 * dbh_cm
    if productivity <= 0:
        raise FHOPSValueError("Derived Kellogg harvester productivity must be > 0.")
    return productivity


__all__ = [
    "ADV6N10HarvesterInputs",
    "TN292HarvesterInputs",
    "estimate_harvester_productivity_adv6n10",
    "estimate_harvester_productivity_adv5n30",
    "estimate_harvester_productivity_tn292",
    "estimate_harvester_productivity_kellogg1994",
]
