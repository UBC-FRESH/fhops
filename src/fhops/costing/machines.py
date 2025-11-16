"""Machine costing helpers (rental-rate driven)."""

from __future__ import annotations

from dataclasses import dataclass

from fhops.core.errors import FHOPSValueError
from fhops.productivity import (
    LahrsenModel,
    ProductivityDistributionEstimate,
    ProductivityEstimate,
    estimate_productivity,
    estimate_productivity_distribution,
)


@dataclass(frozen=True)
class MachineCostEstimate:
    rental_rate_smh: float
    utilisation: float
    productivity_m3_per_pmh: float
    cost_per_m3: float
    method: str
    productivity_std: float | None = None
    rental_rate_breakdown: dict[str, float] | None = None


def _validate_inputs(rental_rate_smh: float, utilisation: float, productivity: float) -> None:
    if rental_rate_smh <= 0:
        raise FHOPSValueError("rental_rate_smh must be positive")
    if not (0 < utilisation <= 1.0):
        raise FHOPSValueError("utilisation must be in (0, 1]")
    if productivity <= 0:
        raise FHOPSValueError("productivity must be positive")


def compute_unit_cost(
    *,
    rental_rate_smh: float,
    utilisation: float,
    productivity_m3_per_pmh: float,
    method: str = "deterministic",
    productivity_std: float | None = None,
    rental_rate_breakdown: dict[str, float] | None = None,
) -> MachineCostEstimate:
    """Return unit cost ($/m³) given rental rate ($/SMH) and productivity."""

    _validate_inputs(rental_rate_smh, utilisation, productivity_m3_per_pmh)
    cost = rental_rate_smh / (utilisation * productivity_m3_per_pmh)
    return MachineCostEstimate(
        rental_rate_smh=rental_rate_smh,
        utilisation=utilisation,
        productivity_m3_per_pmh=productivity_m3_per_pmh,
        cost_per_m3=cost,
        method=method,
        productivity_std=productivity_std,
        rental_rate_breakdown=rental_rate_breakdown,
    )


def estimate_unit_cost_from_stand(
    *,
    rental_rate_smh: float,
    utilisation: float,
    avg_stem_size: float,
    volume_per_ha: float,
    stem_density: float,
    ground_slope: float,
    model: LahrsenModel = LahrsenModel.DAILY,
    rental_rate_breakdown: dict[str, float] | None = None,
) -> tuple[MachineCostEstimate, ProductivityEstimate]:
    productivity = estimate_productivity(
        avg_stem_size=avg_stem_size,
        volume_per_ha=volume_per_ha,
        stem_density=stem_density,
        ground_slope=ground_slope,
        model=model,
    )
    cost = compute_unit_cost(
        rental_rate_smh=rental_rate_smh,
        utilisation=utilisation,
        productivity_m3_per_pmh=productivity.predicted_m3_per_pmh,
        rental_rate_breakdown=rental_rate_breakdown,
    )
    return cost, productivity


def estimate_unit_cost_from_distribution(
    *,
    rental_rate_smh: float,
    utilisation: float,
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
    rental_rate_breakdown: dict[str, float] | None = None,
) -> tuple[MachineCostEstimate, ProductivityDistributionEstimate]:
    prod = estimate_productivity_distribution(
        avg_stem_size_mu=avg_stem_size_mu,
        avg_stem_size_sigma=avg_stem_size_sigma,
        volume_per_ha_mu=volume_per_ha_mu,
        volume_per_ha_sigma=volume_per_ha_sigma,
        stem_density_mu=stem_density_mu,
        stem_density_sigma=stem_density_sigma,
        ground_slope_mu=ground_slope_mu,
        ground_slope_sigma=ground_slope_sigma,
        model=model,
        method=method,
        samples=samples,
    )
    cost = compute_unit_cost(
        rental_rate_smh=rental_rate_smh,
        utilisation=utilisation,
        productivity_m3_per_pmh=prod.expected_m3_per_pmh,
        method=f"rv:{prod.method}",
        productivity_std=prod.std_m3_per_pmh,
        rental_rate_breakdown=rental_rate_breakdown,
    )
    return cost, prod


__all__ = [
    "MachineCostEstimate",
    "compute_unit_cost",
    "estimate_unit_cost_from_stand",
    "estimate_unit_cost_from_distribution",
]
