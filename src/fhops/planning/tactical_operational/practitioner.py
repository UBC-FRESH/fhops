"""Practitioner-scale synthetic tactical–operational validation case."""

from __future__ import annotations

import random

from fhops.planning.tactical_operational.models import (
    BlockRoadAccess,
    Economics,
    ExternalSupply,
    Facility,
    FacilityDemand,
    FleetCapacity,
    FleetOption,
    HarvestSystemOption,
    InitialInventory,
    PlanningPeriod,
    PlanningUnit,
    Product,
    RoadDependency,
    RoadProject,
    SilvicultureTransition,
    TacticalOperationalScenario,
    TransportArc,
)
from fhops.planning.tactical_operational.time import four_week_periods


def generate_tactical_practitioner_case(seed: int = 2601) -> TacticalOperationalScenario:
    """Generate a redistributable practitioner-scale tactical planning case.

    The case is synthetic but shaped like a small BC-style tenure: 24 blocks across terrain/access
    classes, three harvest systems, three products, two mills, seasonal availability, road
    dependencies, silviculture obligations, and one optional fleet expansion. No restricted source
    values are used; all coefficients are generated for validation rather than empirical inference.
    """
    rng = random.Random(seed)
    periods: list[PlanningPeriod] = []
    sequence = 1
    for year in (2027, 2028):
        for period in four_week_periods(year, periods=4):
            periods.append(period.model_copy(update={"sequence": sequence}))
            sequence += 1

    products = [
        Product(product_id="sawlog", species_group="mixed_conifer", grade="sawlog"),
        Product(product_id="pulp", species_group="mixed_conifer", grade="pulp"),
        Product(product_id="biomass", species_group="mixed_conifer", grade="energy"),
    ]
    facilities = [
        Facility(
            facility_id="coastal_sawmill",
            facility_type="sawmill",
            accepted_products=["sawlog"],
            terminal_inventory_value_per_m3={"sawlog": 12.0},
        ),
        Facility(
            facility_id="interior_pulp",
            facility_type="pulp_mill",
            accepted_products=["pulp", "biomass"],
            terminal_inventory_value_per_m3={"pulp": 7.0, "biomass": 3.0},
        ),
    ]

    blocks: list[PlanningUnit] = []
    for index in range(24):
        block_id = f"PB{index + 1:02d}"
        terrain = "steep" if index % 4 == 3 else ("moderate" if index % 4 == 1 else "gentle")
        area = rng.uniform(12.0, 36.0)
        yield_multiplier = {"gentle": 1.0, "moderate": 0.9, "steep": 0.75}[terrain]
        blocks.append(
            PlanningUnit(
                block_id=block_id,
                gross_area_ha=area,
                operable_area_ha=area,
                forest_class=terrain,
                initial_state="standing",
                product_yields_m3_per_ha={
                    "sawlog": 110.0 * yield_multiplier,
                    "pulp": 45.0 * yield_multiplier,
                    "biomass": 12.0 * yield_multiplier,
                },
            )
        )

    systems = {
        "ground_fb_skid": {"cost": 21.0, "capacity": 1450.0},
        "ctl_forwarder": {"cost": 24.0, "capacity": 1250.0},
        "cable_skyline": {"cost": 31.0, "capacity": 950.0},
    }
    options: list[HarvestSystemOption] = []
    fleet_capacity: list[FleetCapacity] = []
    for period in periods:
        for system_id, spec in systems.items():
            fleet_capacity.append(
                FleetCapacity(
                    system_id=system_id,
                    period_id=period.period_id,
                    capacity_m3=spec["capacity"],
                )
            )
    for block in blocks:
        eligible_systems = ["ground_fb_skid"] if block.forest_class == "gentle" else []
        if block.forest_class == "moderate":
            eligible_systems.extend(["ground_fb_skid", "ctl_forwarder"])
        if block.forest_class == "steep":
            eligible_systems.append("cable_skyline")
        for system_id in eligible_systems:
            for period in periods:
                if system_id == "ground_fb_skid" and "breakup" in period.season_tags:
                    continue
                option_id = f"{block.block_id}__{system_id}__{period.period_id}"
                options.append(
                    HarvestSystemOption(
                        option_id=option_id,
                        block_id=block.block_id,
                        system_id=system_id,
                        period_id=period.period_id,
                        min_area_ha=3.0,
                        max_area_ha=block.operable_area_ha,
                        variable_cost_per_m3=systems[system_id]["cost"] + rng.uniform(-1.5, 1.5),
                        fixed_cost=250.0 if system_id == "cable_skyline" else 120.0,
                        productivity_m3_per_period=systems[system_id]["capacity"] * 0.9,
                    )
                )

    roads = [
        RoadProject(
            road_id="trunk_north",
            build_cost=18000.0,
            maintenance_cost_per_period=250.0,
            earliest_period_id=periods[0].period_id,
            capacity_m3_per_period=4200.0,
        ),
        RoadProject(
            road_id="spur_mid",
            build_cost=6500.0,
            maintenance_cost_per_period=120.0,
            earliest_period_id=periods[0].period_id,
            capacity_m3_per_period=1800.0,
        ),
        RoadProject(
            road_id="spur_steep",
            build_cost=9200.0,
            maintenance_cost_per_period=180.0,
            earliest_period_id=periods[0].period_id,
            capacity_m3_per_period=1200.0,
        ),
    ]
    road_dependencies = [RoadDependency(road_id="spur_steep", depends_on_road_id="trunk_north")]
    block_access: list[BlockRoadAccess] = []
    for block in blocks:
        road_id = "trunk_north" if block.forest_class == "gentle" else "spur_mid"
        if block.forest_class == "steep":
            road_id = "spur_steep"
        block_access.append(BlockRoadAccess(block_id=block.block_id, road_id=road_id))

    transport_arcs: list[TransportArc] = []
    for block in blocks:
        for period in periods:
            transport_arcs.extend(
                [
                    TransportArc(
                        arc_id=f"{block.block_id}__saw__{period.period_id}",
                        origin_id=block.block_id,
                        destination_id="coastal_sawmill",
                        product_id="sawlog",
                        period_id=period.period_id,
                        cost_per_m3=7.5 + (2.0 if block.forest_class == "steep" else 0.0),
                        capacity_m3=1000.0,
                    ),
                    TransportArc(
                        arc_id=f"{block.block_id}__pulp__{period.period_id}",
                        origin_id=block.block_id,
                        destination_id="interior_pulp",
                        product_id="pulp",
                        period_id=period.period_id,
                        cost_per_m3=8.5 + (2.5 if block.forest_class == "steep" else 0.0),
                        capacity_m3=800.0,
                    ),
                    TransportArc(
                        arc_id=f"{block.block_id}__bio__{period.period_id}",
                        origin_id=block.block_id,
                        destination_id="interior_pulp",
                        product_id="biomass",
                        period_id=period.period_id,
                        cost_per_m3=11.0,
                        capacity_m3=300.0,
                    ),
                ]
            )

    demand: list[FacilityDemand] = []
    for period in periods:
        demand.extend(
            [
                FacilityDemand(
                    facility_id="coastal_sawmill",
                    product_id="sawlog",
                    period_id=period.period_id,
                    minimum_m3=1800.0,
                    target_m3=2200.0,
                    maximum_m3=2600.0,
                    value_per_m3=58.0,
                ),
                FacilityDemand(
                    facility_id="interior_pulp",
                    product_id="pulp",
                    period_id=period.period_id,
                    minimum_m3=700.0,
                    target_m3=900.0,
                    maximum_m3=1100.0,
                    value_per_m3=31.0,
                ),
                FacilityDemand(
                    facility_id="interior_pulp",
                    product_id="biomass",
                    period_id=period.period_id,
                    minimum_m3=60.0,
                    target_m3=90.0,
                    maximum_m3=140.0,
                    value_per_m3=12.0,
                ),
            ]
        )

    return TacticalOperationalScenario(
        name="practitioner-tactical-case",
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
        planning_units=blocks,
        harvest_system_options=options,
        fleet_capacity=fleet_capacity,
        facilities=facilities,
        facility_demand=demand,
        initial_inventory=[
            InitialInventory(facility_id="coastal_sawmill", product_id="sawlog", opening_m3=150.0),
            InitialInventory(facility_id="interior_pulp", product_id="pulp", opening_m3=80.0),
            InitialInventory(facility_id="interior_pulp", product_id="biomass", opening_m3=10.0),
        ],
        transport_arcs=transport_arcs,
        external_supply=[
            ExternalSupply(
                source_id="open_market",
                destination_id="coastal_sawmill",
                product_id="sawlog",
                period_id=periods[0].period_id,
                minimum_m3=0.0,
                maximum_m3=250.0,
                delivered_cost_per_m3=72.0,
            )
        ],
        roads=roads,
        road_dependencies=road_dependencies,
        block_road_access=block_access,
        silviculture_transitions=[
            SilvicultureTransition(
                transition_id=f"ground_replant_{block.block_id}",
                block_id=block.block_id,
                system_id="ground_fb_skid",
                activity_id="replanting",
                earliest_period_id=periods[min(2, len(periods) - 1)].period_id,
                cost_per_ha=85.0,
                required=True,
                next_state="regenerating",
            )
            for block in blocks
            if block.forest_class in {"gentle", "moderate"}
        ],
        fleet_options=[
            FleetOption(
                option_id="cable_second_yarder",
                system_id="cable_skyline",
                purchase_period_id=periods[1].period_id,
                purchase_cost=9500.0,
                capacity_m3_per_period=450.0,
                max_units=1,
                economic_life_periods=6,
            )
        ],
    )


__all__ = ["generate_tactical_practitioner_case"]
