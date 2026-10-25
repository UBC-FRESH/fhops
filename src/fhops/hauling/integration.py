"""Bridges from FHOPS operational/tactical plans to the hauling contract.

The hauling layer needs supply (volume by block and log sort) and demand (volume by yard and log
sort). The operational and tactical models provide these in different shapes. This module turns
them into a validated hauling scenario and reports any assumption or residual explicitly; it never
silently invents a sort split or a missing arc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd

from fhops.hauling.contract import HaulingConfig, HaulingDemand, HaulingSupply, LogSort

if TYPE_CHECKING:
    from fhops.planning.tactical_operational import TacticalOperationalScenario
    from fhops.scenario.contract import Scenario

__all__ = [
    "HaulingIntegrationResult",
    "residual_report",
    "scenario_from_operational_plan",
    "scenario_from_tactical_plan",
]


@dataclass(slots=True)
class HaulingIntegrationResult:
    """A hauling scenario plus the assumptions and residuals behind it.

    Attributes
    ----------
    scenario:
        Scenario with the updated ``hauling`` section.
    warnings:
        Human-readable assumptions, skipped records, and unsupported mappings.
    residuals:
        One row per log sort with total supply, demand, and the residual.
    """

    scenario: Scenario
    warnings: list[str] = field(default_factory=list)
    residuals: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=["log_sort_id", "supply_m3", "demand_m3", "residual_m3"]
        )
    )


def scenario_from_operational_plan(
    scenario: Scenario,
    assignments: pd.DataFrame,
    *,
    sort_shares: dict[str, float] | None = None,
    production_column: str = "production",
) -> HaulingIntegrationResult:
    """Build hauling supply from an operational assignment table.

    Parameters
    ----------
    scenario:
        Base scenario with a ``hauling`` section.
    assignments:
        DataFrame with ``block_id`` and ``production`` columns. If ``production`` is absent,
        ``work_required`` is used for blocks that appear in the assignments.
    sort_shares:
        Optional ``log_sort_id -> fraction`` split. Fractions must be non-negative and sum to one.
        When omitted, each log sort receives an equal share of the block volume; this is recorded as
        a warning because the operational model does not carry product yields.
    production_column:
        Name of the production column. Defaults to ``production``.

    Returns
    -------
    HaulingIntegrationResult
        Updated scenario, warnings, and supply/demand residuals.

    Raises
    ------
    ValueError
        When the scenario has no hauling section, the assignment table lacks ``block_id``, or the
        sort split is invalid.
    """
    config = _require_config(scenario)
    if "block_id" not in assignments.columns:
        raise ValueError("assignments must contain a block_id column")
    log_sorts = config.log_sorts
    if not log_sorts:
        raise ValueError("hauling contract has no log sorts")
    shares = _normalise_shares(log_sorts, sort_shares)

    warnings: list[str] = []
    if sort_shares is None:
        warnings.append(
            "Operational assignments carry no product/sort split; equal shares were applied to "
            "the hauling log sorts. Supply a sort_shares mapping for a real split."
        )

    block_volume: dict[str, float] = {}
    for _, row in assignments.iterrows():
        block_id = str(row["block_id"])
        if production_column in assignments.columns:
            volume = float(row[production_column])
        else:
            block = next((block for block in scenario.blocks if block.id == block_id), None)
            if block is None:
                warnings.append(f"Ignored assignment for unknown block_id={block_id}")
                continue
            volume = block.work_required
        if volume <= 0:
            continue
        block_volume[block_id] = block_volume.get(block_id, 0.0) + volume

    supply: list[HaulingSupply] = []
    for block_id, volume in sorted(block_volume.items()):
        if not any(block.id == block_id for block in scenario.blocks):
            warnings.append(f"Ignored assignment for unknown block_id={block_id}")
            continue
        for sort in log_sorts:
            share = shares[sort.id]
            if share <= 0:
                continue
            sorted_m3 = volume * share if sort.sorted else 0.0
            unsorted_m3 = volume * share if not sort.sorted else 0.0
            supply.append(
                HaulingSupply(
                    block_id=block_id,
                    log_sort_id=sort.id,
                    sorted_m3=sorted_m3,
                    unsorted_m3=unsorted_m3,
                )
            )

    updated = _apply_supply(scenario, config, supply)
    return HaulingIntegrationResult(
        scenario=updated,
        warnings=warnings,
        residuals=residual_report(updated),
    )


def scenario_from_tactical_plan(
    scenario: Scenario,
    tactical: TacticalOperationalScenario,
    *,
    period_id: str,
    production: pd.DataFrame | None = None,
) -> HaulingIntegrationResult:
    """Build hauling supply and demand from a tactical-operational period.

    Parameters
    ----------
    scenario:
        Base scenario with a ``hauling`` section.
    tactical:
        Tactical-operational scenario.
    period_id:
        Period to translate.
    production:
        Optional tactical production table with ``block_id``, ``product_id``, ``period_id``, and
        ``volume_m3``. When omitted, supply is left unchanged and a warning is recorded; the model
        does not guess harvest volume from potential yields.

    Returns
    -------
    HaulingIntegrationResult
        Updated scenario, warnings, and residuals.

    Raises
    ------
    ValueError
        When the scenario has no hauling section, no sort yard links the tactical facilities, or
        the period is not known.
    """
    config = _require_config(scenario)
    periods = {period.period_id for period in tactical.periods}
    if period_id not in periods:
        raise ValueError(f"Unknown tactical period_id={period_id}; known: {sorted(periods)}")

    warnings: list[str] = []
    supply: list[HaulingSupply] = []
    if production is None:
        warnings.append(
            "No tactical production table supplied; hauling supply is unchanged. Pass the "
            "`production` DataFrame from the tactical solve."
        )
    else:
        required = {"block_id", "product_id", "period_id", "volume_m3"}
        missing = required - set(production.columns)
        if missing:
            raise ValueError(f"tactical production is missing columns: {sorted(missing)}")
        supply = _supply_from_tactical_production(config, production, period_id, warnings)

    demand = _demand_from_tactical(config, tactical, period_id, warnings)
    updated = _apply_supply_and_demand(scenario, config, supply or None, demand or None)
    return HaulingIntegrationResult(
        scenario=updated,
        warnings=warnings,
        residuals=residual_report(updated),
    )


def residual_report(scenario: Scenario) -> pd.DataFrame:
    """Return total supply, total demand, and the residual per log sort.

    Parameters
    ----------
    scenario:
        Scenario with a hauling section.

    Returns
    -------
    pandas.DataFrame
        Columns ``log_sort_id``, ``supply_m3``, ``demand_m3``, and ``residual_m3``. A positive
        residual means demand exceeds supply.
    """
    config = _require_config(scenario)
    supply = {sort.id: 0.0 for sort in config.log_sorts}
    for supply_row in config.supply:
        supply[supply_row.log_sort_id] = (
            supply.get(supply_row.log_sort_id, 0.0) + supply_row.sorted_m3 + supply_row.unsorted_m3
        )
    demand = {sort.id: 0.0 for sort in config.log_sorts}
    for demand_row in config.demand:
        demand[demand_row.log_sort_id] = (
            demand.get(demand_row.log_sort_id, 0.0) + demand_row.volume_m3
        )
    rows = [
        {
            "log_sort_id": sort_id,
            "supply_m3": supply.get(sort_id, 0.0),
            "demand_m3": demand.get(sort_id, 0.0),
            "residual_m3": demand.get(sort_id, 0.0) - supply.get(sort_id, 0.0),
        }
        for sort_id in sorted(set(supply) | set(demand))
    ]
    return pd.DataFrame(rows, columns=["log_sort_id", "supply_m3", "demand_m3", "residual_m3"])


def _require_config(scenario: Scenario) -> HaulingConfig:
    """Return the scenario's hauling config or raise."""
    if scenario.hauling is None:
        raise ValueError("Scenario has no hauling section")
    return scenario.hauling


def _normalise_shares(
    log_sorts: list[LogSort],
    sort_shares: dict[str, float] | None,
) -> dict[str, float]:
    """Validate and normalise per-sort shares."""
    if sort_shares is None:
        share = 1.0 / len(log_sorts)
        return {sort.id: share for sort in log_sorts}
    unknown = set(sort_shares) - {sort.id for sort in log_sorts}
    if unknown:
        raise ValueError(f"Unknown log_sort_id in sort_shares: {sorted(unknown)}")
    if any(value < 0 for value in sort_shares.values()):
        raise ValueError("sort_shares values must be non-negative")
    total = sum(sort_shares.values())
    if total <= 0:
        raise ValueError("sort_shares must sum to a positive value")
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"sort_shares must sum to 1.0 (got {total})")
    return {sort.id: sort_shares.get(sort.id, 0.0) for sort in log_sorts}


def _supply_from_tactical_production(
    config: HaulingConfig,
    production: pd.DataFrame,
    period_id: str,
    warnings: list[str],
) -> list[HaulingSupply]:
    """Translate tactical production rows into hauling supply."""
    product_to_sort: dict[str, LogSort] = {}
    for sort_record in config.log_sorts:
        if sort_record.product_id is not None:
            product_to_sort[sort_record.product_id] = sort_record
        product_to_sort.setdefault(sort_record.id, sort_record)
    volumes: dict[tuple[str, str], float] = {}
    for _, row in production.iterrows():
        if str(row["period_id"]) != period_id:
            continue
        product_id = str(row["product_id"])
        sort_candidate = product_to_sort.get(product_id)
        if sort_candidate is None:
            warnings.append(
                f"Tactical product_id={product_id} has no hauling log-sort link; skipped"
            )
            continue
        key = (str(row["block_id"]), sort_candidate.id)
        volumes[key] = volumes.get(key, 0.0) + float(row["volume_m3"])

    supply: list[HaulingSupply] = []
    for (block_id, sort_id), volume in sorted(volumes.items()):
        sort = next(sort for sort in config.log_sorts if sort.id == sort_id)
        if volume <= 0:
            continue
        supply.append(
            HaulingSupply(
                block_id=block_id,
                log_sort_id=sort_id,
                sorted_m3=volume if sort.sorted else 0.0,
                unsorted_m3=0.0 if sort.sorted else volume,
            )
        )
    return supply


def _demand_from_tactical(
    config: HaulingConfig,
    tactical: TacticalOperationalScenario,
    period_id: str,
    warnings: list[str],
) -> list[HaulingDemand]:
    """Translate tactical facility demand into daily hauling demand."""
    facility_to_yard = {
        yard.facility_id: yard.id for yard in config.sort_yards if yard.facility_id is not None
    }
    product_to_sort: dict[str, LogSort] = {}
    for sort_record in config.log_sorts:
        if sort_record.product_id is not None:
            product_to_sort[sort_record.product_id] = sort_record
        product_to_sort.setdefault(sort_record.id, sort_record)

    demand: list[HaulingDemand] = []
    horizon = config.planning_horizon_days
    for row in tactical.facility_demand:
        if row.period_id != period_id:
            continue
        yard_id = facility_to_yard.get(row.facility_id)
        if yard_id is None:
            warnings.append(
                f"Tactical facility_id={row.facility_id} has no sort-yard link; demand skipped"
            )
            continue
        sort_candidate = product_to_sort.get(row.product_id)
        if sort_candidate is None:
            warnings.append(
                f"Tactical product_id={row.product_id} has no hauling log-sort link; demand skipped"
            )
            continue
        total = row.target_m3 if row.target_m3 is not None else row.minimum_m3
        if total <= 0:
            continue
        daily = total / horizon
        for day in range(1, horizon + 1):
            demand.append(
                HaulingDemand(
                    yard_id=yard_id,
                    log_sort_id=sort_candidate.id,
                    day=day,
                    volume_m3=daily,
                )
            )
    if demand:
        warnings.append(
            "Tactical period demand was spread evenly across the hauling horizon; provide a "
            "daily demand table when the real pattern is known."
        )
    return demand


def _apply_supply(
    scenario: Scenario,
    config: HaulingConfig,
    supply: list[HaulingSupply],
) -> Scenario:
    """Return a scenario with replaced supply."""
    updated = _validated_config(config, supply=supply)
    return scenario.model_copy(update={"hauling": updated})


def _apply_supply_and_demand(
    scenario: Scenario,
    config: HaulingConfig,
    supply: list[HaulingSupply] | None,
    demand: list[HaulingDemand] | None,
) -> Scenario:
    """Return a scenario with optional supply and demand replacement."""
    updated = _validated_config(
        config,
        supply=supply if supply is not None else config.supply,
        demand=demand if demand is not None else config.demand,
    )
    return scenario.model_copy(update={"hauling": updated})


def _validated_config(
    config: HaulingConfig,
    *,
    supply: list[HaulingSupply],
    demand: list[HaulingDemand] | None = None,
) -> HaulingConfig:
    """Re-validate a hauling config after a supply/demand edit."""
    payload: dict[str, Any] = config.model_dump(mode="python")
    payload["supply"] = [row.model_dump(mode="python") for row in supply]
    if demand is not None:
        payload["demand"] = [row.model_dump(mode="python") for row in demand]
    return HaulingConfig.model_validate(payload)
