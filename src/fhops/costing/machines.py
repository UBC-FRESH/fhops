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
    """
    Cost summary tying machine rental-rate inputs to productivity predictions.

    Attributes
    ----------
    rental_rate_smh:
        Rental rate in $/SMH after all owning/operating components are included.
    utilisation:
        Scheduled-to-productive fraction applied when converting to $/m³.
    productivity_m3_per_pmh:
        Delay-free productivity used in the conversion.
    cost_per_m3:
        Resulting unit cost ($/m³).
    method:
        Label capturing how productivity was derived (deterministic vs stochastic).
    productivity_std:
        Optional standard deviation from Monte Carlo sampling (m³/PMH0).
    rental_rate_breakdown:
        Component breakdown dictionary fed to CLI / reporting layers.
    """

    rental_rate_smh: float
    utilisation: float
    productivity_m3_per_pmh: float
    cost_per_m3: float
    method: str
    productivity_std: float | None = None
    rental_rate_breakdown: dict[str, float] | None = None


def _validate_inputs(rental_rate_smh: float, utilisation: float, productivity: float) -> None:
    """
    Guard against non-physical inputs before computing unit costs.

    Parameters
    ----------
    rental_rate_smh:
        Machine cost in $/SMH (must be > 0).
    utilisation:
        Fraction in (0, 1].
    productivity:
        Productivity value (m³/PMH0) expected to be positive.
    """

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
    """
    Return a deterministic unit cost ($/m³) given the rental rate and productivity.

    Parameters
    ----------
    rental_rate_smh:
        Machine cost per scheduled machine hour (SMH) inclusive of owning/operating components.
    utilisation:
        Realised utilisation fraction (0, 1], usually derived from shift modelling.
    productivity_m3_per_pmh:
        Delay-free productivity used to convert $/SMH into $/m³.
    method:
        Label describing the upstream productivity approach (e.g., ``deterministic`` or ``rv:auto``).
    productivity_std:
        Optional standard deviation for probabilistic estimates.
    rental_rate_breakdown:
        Component breakdown returned by ``compose_rental_rate`` for reporting.

    Returns
    -------
    MachineCostEstimate
        Structured cost summary ready for CLI/GUI display.
    """

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
    """
    Estimate unit cost by running Lahrsen productivity models on stand averages.

    Parameters
    ----------
    rental_rate_smh:
        Machine rate ($/SMH) from ``compose_rental_rate`` or another cost source.
    utilisation:
        Realised utilisation fraction (0, 1].
    avg_stem_size:
        Mean stem volume per tree (m³/stem).
    volume_per_ha:
        Merchantable volume per hectare (m³/ha).
    stem_density:
        Stems per hectare used to derive cycles per PMH.
    ground_slope:
        Average ground slope (%) affecting cycle times.
    model:
        Lahrsen variant (``DAILY``, ``DETAILED``, etc.).
    rental_rate_breakdown:
        Optional breakdown to propagate into the returned ``MachineCostEstimate``.

    Returns
    -------
    (MachineCostEstimate, ProductivityEstimate)
        Tuple containing the unit-cost summary plus the raw productivity output for reuse.
    """

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
    """
    Estimate unit costs when stand variables are represented by normal distributions.

    Parameters
    ----------
    rental_rate_smh, utilisation:
        Same definitions as ``estimate_unit_cost_from_stand``.
    avg_stem_size_mu, avg_stem_size_sigma:
        Mean and standard deviation for stem volume (m³/stem).
    volume_per_ha_mu, volume_per_ha_sigma:
        Mean and standard deviation for volume per hectare (m³/ha).
    stem_density_mu, stem_density_sigma:
        Mean and standard deviation for stems per hectare.
    ground_slope_mu, ground_slope_sigma:
        Mean and standard deviation for slope (%).
    model:
        Lahrsen variant.
    method:
        Distribution sampling strategy label (``auto`` by default).
    samples:
        Number of Monte-Carlo samples (defaults to 5,000 to balance latency vs accuracy).
    rental_rate_breakdown:
        Optional breakdown dictionary propagated into the resulting ``MachineCostEstimate``.

    Returns
    -------
    (MachineCostEstimate, ProductivityDistributionEstimate)
        Unit-cost summary derived from the expected productivity and the accompanying distribution
        statistics for downstream analytics.
    """

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
