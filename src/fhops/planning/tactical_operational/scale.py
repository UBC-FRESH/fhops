"""Synthetic scale fixtures and benchmark helpers for tactical–operational planning."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fhops.model.milp.tactical_operational import (
    build_tactical_operational_bundle,
    solve_tactical_operational_milp,
)
from fhops.planning.tactical_operational.models import (
    Economics,
    ExternalSupply,
    Facility,
    FacilityDemand,
    FleetCapacity,
    HarvestSystemOption,
    InitialInventory,
    PlanningPeriod,
    PlanningUnit,
    Product,
    TacticalOperationalScenario,
    TransportArc,
)
from fhops.planning.tactical_operational.time import four_week_periods


@dataclass(frozen=True)
class TacticalScaleConfig:
    """Configuration for a deterministic tactical–operational scale scenario."""

    num_blocks: int = 100
    years: int = 1
    periods_per_year: int = 4
    num_products: int = 2
    num_facilities: int = 2
    num_systems: int = 2
    seed: int = 44
    demand_fraction: float = 0.25


def generate_tactical_scale_scenario(
    config: TacticalScaleConfig,
) -> TacticalOperationalScenario:
    """Generate a deterministic TOPM-shaped scale scenario.

    The generator is intentionally simple and synthetic: it creates a rectangular block × system ×
    period eligibility grid with product yields, fleet capacity, facility demand, transport arcs,
    and optional outside supply. It is meant for model-size/runtime envelopes, not ecological
    realism.
    """
    if config.num_blocks < 1:
        raise ValueError("num_blocks must be >= 1")
    if not 0 <= config.demand_fraction <= 1:
        raise ValueError("demand_fraction must be between 0 and 1")
    rng = random.Random(config.seed)

    periods: list[PlanningPeriod] = []
    sequence = 1
    for year in range(2027, 2027 + config.years):
        for period in four_week_periods(year, periods=config.periods_per_year):
            periods.append(period.model_copy(update={"sequence": sequence}))
            sequence += 1

    products = [
        Product(product_id=f"product_{index}", species_group=f"sg{index}", grade=f"g{index}")
        for index in range(config.num_products)
    ]
    facilities = [
        Facility(
            facility_id=f"facility_{index}",
            facility_type="mill",
            accepted_products=[f"product_{index % config.num_products}"],
        )
        for index in range(config.num_facilities)
    ]
    systems = [f"system_{index}" for index in range(config.num_systems)]

    planning_units: list[PlanningUnit] = []
    options: list[HarvestSystemOption] = []
    fleet_capacity: list[FleetCapacity] = []
    transport_arcs: list[TransportArc] = []
    for index in range(config.num_blocks):
        block_id = f"B{index + 1:05d}"
        area = rng.uniform(8.0, 40.0)
        yields = {
            product.product_id: rng.uniform(60.0, 140.0) / config.num_products
            for product in products
        }
        planning_units.append(
            PlanningUnit(
                block_id=block_id,
                gross_area_ha=area,
                operable_area_ha=area,
                forest_class="synthetic",
                initial_state="available",
                product_yields_m3_per_ha=yields,
            )
        )
        for system_id in systems:
            for period in periods:
                option_id = f"{block_id}__{system_id}__{period.period_id}"
                options.append(
                    HarvestSystemOption(
                        option_id=option_id,
                        block_id=block_id,
                        system_id=system_id,
                        period_id=period.period_id,
                        min_area_ha=min(2.0, area),
                        max_area_ha=area,
                        variable_cost_per_m3=rng.uniform(15.0, 28.0),
                        fixed_cost=rng.uniform(50.0, 250.0),
                        productivity_m3_per_period=sum(yields.values()) * area,
                    )
                )
        for facility in facilities:
            product_id = facility.accepted_products[0]
            for period in periods:
                transport_arcs.append(
                    TransportArc(
                        arc_id=f"{block_id}__{facility.facility_id}__{product_id}__{period.period_id}",
                        origin_id=block_id,
                        destination_id=facility.facility_id,
                        product_id=product_id,
                        mode="truck",
                        period_id=period.period_id,
                        cost_per_m3=rng.uniform(4.0, 12.0),
                        capacity_m3=None,
                    )
                )

    total_period_capacity = sum(
        sum(unit.product_yields_m3_per_ha.values()) * unit.operable_area_ha
        for unit in planning_units
    )
    per_period_demand = total_period_capacity * config.demand_fraction / max(1, len(periods))
    facility_demand: list[FacilityDemand] = []
    initial_inventory: list[InitialInventory] = []
    for facility in facilities:
        product_id = facility.accepted_products[0]
        initial_inventory.append(
            InitialInventory(
                facility_id=facility.facility_id, product_id=product_id, opening_m3=0.0
            )
        )
        for period in periods:
            facility_demand.append(
                FacilityDemand(
                    facility_id=facility.facility_id,
                    product_id=product_id,
                    period_id=period.period_id,
                    minimum_m3=0.0,
                    target_m3=per_period_demand / max(1, config.num_facilities),
                    maximum_m3=None,
                    value_per_m3=50.0,
                )
            )

    for system_id in systems:
        for period in periods:
            fleet_capacity.append(
                FleetCapacity(
                    system_id=system_id,
                    period_id=period.period_id,
                    capacity_m3=total_period_capacity,
                    capacity_hours=None,
                )
            )

    return TacticalOperationalScenario(
        name=(
            f"topm-scale-b{config.num_blocks}-y{config.years}-p{config.periods_per_year}"
            f"-s{config.num_systems}"
        ),
        planning_level="tactical_operational",
        schema_version="0.1.0",
        economics=Economics(
            currency="CAD",
            base_year=2027,
            discount_rate_per_year=0.04,
            objective_profile="min_discounted_delivered_cost",
        ),
        periods=periods,
        products=products,
        planning_units=planning_units,
        harvest_system_options=options,
        fleet_capacity=fleet_capacity,
        facilities=facilities,
        facility_demand=facility_demand,
        initial_inventory=initial_inventory,
        transport_arcs=transport_arcs,
        external_supply=[
            ExternalSupply(
                source_id="open_market",
                destination_id=facility.facility_id,
                product_id=facility.accepted_products[0],
                period_id=periods[0].period_id,
                minimum_m3=0.0,
                maximum_m3=per_period_demand,
                delivered_cost_per_m3=80.0,
            )
            for facility in facilities
        ],
    )


def run_tactical_scale_benchmark(
    configs: list[TacticalScaleConfig],
    *,
    solver: str = "highs",
    time_limit: int | None = None,
    gap: float | None = None,
) -> pd.DataFrame:
    """Solve generated tactical scenarios and return scale/timing/model-size telemetry."""
    rows: list[dict[str, Any]] = []
    for config in configs:
        scenario = generate_tactical_scale_scenario(config)
        bundle = build_tactical_operational_bundle(scenario)
        result = solve_tactical_operational_milp(
            bundle,
            solver=solver,
            time_limit=time_limit,
            gap=gap,
        )
        stats = result.get("model_statistics") or {}
        dimensions = result.get("model_dimensions") or {}
        rows.append(
            {
                **asdict(config),
                "scenario": scenario.name,
                "objective": result.get("objective"),
                "solver_status": result.get("solver_status"),
                "termination_condition": result.get("termination_condition"),
                "runtime_s": result.get("runtime_s"),
                "build_time_s": result.get("build_time_s"),
                "solve_time_s": result.get("solve_time_s"),
                **{f"dim_{key}": value for key, value in dimensions.items()},
                **{f"model_{key}": value for key, value in stats.items()},
            }
        )
    return pd.DataFrame(rows)


def write_tactical_scale_benchmark(
    frame: pd.DataFrame,
    out_dir: str | Path,
) -> dict[str, Path]:
    """Write benchmark summary CSV/JSON/Markdown files."""
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "tactical_scale_benchmark.csv"
    json_path = output / "tactical_scale_benchmark.json"
    md_path = output / "tactical_scale_benchmark.md"
    frame.to_csv(csv_path, index=False)
    json_path.write_text(frame.to_json(orient="records", indent=2), encoding="utf-8")
    md_path.write_text(_benchmark_markdown(frame), encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


def _benchmark_markdown(frame: pd.DataFrame) -> str:
    columns = [
        "num_blocks",
        "years",
        "periods_per_year",
        "num_systems",
        "objective",
        "termination_condition",
        "runtime_s",
        "build_time_s",
        "solve_time_s",
        "model_number_of_variables",
        "model_number_of_constraints",
    ]
    available = [column for column in columns if column in frame.columns]
    lines = [
        "# Tactical–Operational Scale Benchmark",
        "",
        "| " + " | ".join(available) + " |",
        "|" + "---|" * len(available),
    ]
    for row in frame[available].itertuples(index=False):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines) + "\n"


__all__ = [
    "TacticalScaleConfig",
    "generate_tactical_scale_scenario",
    "run_tactical_scale_benchmark",
    "write_tactical_scale_benchmark",
]
