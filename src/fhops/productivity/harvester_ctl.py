"""CTL harvester productivity helpers."""

from __future__ import annotations

from dataclasses import dataclass

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


__all__ = [
    "ADV6N10HarvesterInputs",
    "estimate_harvester_productivity_adv6n10",
    "estimate_harvester_productivity_adv5n30",
]
