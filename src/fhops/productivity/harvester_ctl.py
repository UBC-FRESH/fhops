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


__all__ = ["ADV6N10HarvesterInputs", "estimate_harvester_productivity_adv6n10"]
