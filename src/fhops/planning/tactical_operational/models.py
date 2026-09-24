"""Pydantic contract for TOPM-inspired tactical–operational planning scenarios.

The models in this module describe aggregate, multi-period planning inputs. They are intentionally
separate from :class:`fhops.scenario.contract.Scenario`, which remains the stable schema ``1.0.0``
contract for detailed day/shift machine scheduling.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TACTICAL_OPERATIONAL_SCHEMA_VERSION = "0.1.0"
TACTICAL_OPERATIONAL_PLANNING_LEVEL = "tactical_operational"


class PeriodLevel(StrEnum):
    """Supported tactical–operational period resolutions."""

    SHIFT = "shift"
    DAY = "day"
    WEEK = "week"
    FOUR_WEEK = "four_week"
    MONTH = "month"
    SEASON = "season"
    YEAR = "year"


class PlanningPeriod(BaseModel):
    """Aggregate planning period with optional hierarchy and discounting metadata."""

    model_config = ConfigDict(extra="forbid")

    period_id: str
    level: PeriodLevel
    sequence: int = Field(ge=1)
    start_date: date
    end_date: date
    duration_days: int | None = Field(default=None, ge=1)
    available_hours: float | None = Field(default=None, gt=0)
    parent_period_id: str | None = None
    discount_factor: float = Field(default=1.0, gt=0, le=1)
    season_tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_dates_and_duration(self) -> PlanningPeriod:
        if self.end_date < self.start_date:
            raise ValueError("PlanningPeriod.end_date must be >= start_date")
        duration = (self.end_date - self.start_date).days + 1
        if self.duration_days is None:
            self.duration_days = duration
        elif self.duration_days != duration:
            raise ValueError(
                "PlanningPeriod.duration_days must equal the inclusive date span "
                f"({self.duration_days} != {duration})"
            )
        if self.parent_period_id == self.period_id:
            raise ValueError("PlanningPeriod.parent_period_id cannot equal period_id")
        return self


class Product(BaseModel):
    """A product/species-grade tracked through harvest, transport, and facility inventory."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    species_group: str | None = None
    grade: str | None = None


class PlanningUnit(BaseModel):
    """Aggregate harvestable unit with area and product yields."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    gross_area_ha: float = Field(gt=0)
    operable_area_ha: float = Field(gt=0)
    forest_class: str | None = None
    initial_state: str | None = None
    product_yields_m3_per_ha: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_area(self) -> PlanningUnit:
        if self.operable_area_ha > self.gross_area_ha:
            raise ValueError("PlanningUnit.operable_area_ha cannot exceed gross_area_ha")
        for product_id, value in self.product_yields_m3_per_ha.items():
            if not product_id:
                raise ValueError("PlanningUnit product yield keys must be non-empty")
            if value < 0:
                raise ValueError("PlanningUnit product yields must be non-negative")
        return self


class HarvestSystemOption(BaseModel):
    """Eligible block × system × period harvest option with quantity and cost bounds."""

    model_config = ConfigDict(extra="forbid")

    option_id: str
    block_id: str
    system_id: str
    period_id: str
    eligible: bool = True
    min_area_ha: float = Field(default=0.0, ge=0)
    max_area_ha: float | None = Field(default=None, gt=0)
    variable_cost_per_m3: float = Field(default=0.0, ge=0)
    fixed_cost: float = Field(default=0.0, ge=0)
    productivity_m3_per_period: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> HarvestSystemOption:
        if self.max_area_ha is not None and self.min_area_ha > self.max_area_ha:
            raise ValueError("HarvestSystemOption.min_area_ha cannot exceed max_area_ha")
        return self


class FleetCapacity(BaseModel):
    """Aggregate production capacity for a harvest system in one period."""

    model_config = ConfigDict(extra="forbid")

    system_id: str
    period_id: str
    capacity_m3: float | None = Field(default=None, ge=0)
    capacity_hours: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _has_capacity(self) -> FleetCapacity:
        if self.capacity_m3 is None and self.capacity_hours is None:
            raise ValueError("FleetCapacity requires capacity_m3 and/or capacity_hours")
        return self


class Facility(BaseModel):
    """Mill, terminal, or customer that accepts one or more products."""

    model_config = ConfigDict(extra="forbid")

    facility_id: str
    facility_type: str | None = None
    accepted_products: list[str] = Field(default_factory=list)
    terminal_inventory_value_per_m3: dict[str, float] | None = None

    @field_validator("terminal_inventory_value_per_m3")
    @classmethod
    def _terminal_values_non_negative(
        cls, value: dict[str, float] | None
    ) -> dict[str, float] | None:
        if value is None:
            return value
        for product_id, amount in value.items():
            if not product_id:
                raise ValueError("Facility terminal inventory product IDs must be non-empty")
            if amount < 0:
                raise ValueError("Facility terminal inventory values must be non-negative")
        return value


class FacilityDemand(BaseModel):
    """Facility/product/period demand envelope and optional delivered product value."""

    model_config = ConfigDict(extra="forbid")

    facility_id: str
    product_id: str
    period_id: str
    minimum_m3: float = Field(default=0.0, ge=0)
    target_m3: float | None = Field(default=None, ge=0)
    maximum_m3: float | None = Field(default=None, ge=0)
    value_per_m3: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> FacilityDemand:
        target = self.target_m3 if self.target_m3 is not None else self.minimum_m3
        if target < self.minimum_m3:
            raise ValueError("FacilityDemand.target_m3 cannot be below minimum_m3")
        if self.maximum_m3 is not None and target > self.maximum_m3:
            raise ValueError("FacilityDemand.target_m3 cannot exceed maximum_m3")
        return self


class InitialInventory(BaseModel):
    """Opening product inventory at a facility."""

    model_config = ConfigDict(extra="forbid")

    facility_id: str
    product_id: str
    opening_m3: float = Field(ge=0)


class TransportArc(BaseModel):
    """Eligible product flow arc from a block/origin to a facility for one period."""

    model_config = ConfigDict(extra="forbid")

    arc_id: str
    origin_id: str
    destination_id: str
    product_id: str
    mode: str = "truck"
    period_id: str
    cost_per_m3: float = Field(default=0.0, ge=0)
    capacity_m3: float | None = Field(default=None, ge=0)
    distance_km: float | None = Field(default=None, ge=0)


class RoadProject(BaseModel):
    """Candidate road project with activation timing, cost, and throughput capacity."""

    model_config = ConfigDict(extra="forbid")

    road_id: str
    build_cost: float = Field(default=0.0, ge=0)
    maintenance_cost_per_period: float = Field(default=0.0, ge=0)
    earliest_period_id: str | None = None
    capacity_m3_per_period: float | None = Field(default=None, ge=0)


class RoadDependency(BaseModel):
    """Directed prerequisite relationship between two road projects."""

    model_config = ConfigDict(extra="forbid")

    road_id: str
    depends_on_road_id: str


class BlockRoadAccess(BaseModel):
    """Mapping from a planning unit to a road that can enable harvest access."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    road_id: str


class SilvicultureTransition(BaseModel):
    """Required follow-up activity generated by a block/system harvest decision."""

    model_config = ConfigDict(extra="forbid")

    transition_id: str
    block_id: str
    system_id: str
    activity_id: str
    earliest_period_id: str
    cost_per_ha: float = Field(default=0.0, ge=0)
    required: bool = True
    next_state: str | None = None


class FleetOption(BaseModel):
    """Optional fleet acquisition that adds system capacity over an economic life."""

    model_config = ConfigDict(extra="forbid")

    option_id: str
    system_id: str
    purchase_period_id: str
    purchase_cost: float = Field(default=0.0, ge=0)
    capacity_m3_per_period: float = Field(gt=0)
    max_units: int = Field(default=0, ge=0)
    economic_life_periods: int = Field(default=1, ge=1)


class ExternalSupply(BaseModel):
    """Optional outside wood purchase source feeding a facility."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    destination_id: str
    product_id: str
    period_id: str
    minimum_m3: float = Field(default=0.0, ge=0)
    maximum_m3: float | None = Field(default=None, ge=0)
    delivered_cost_per_m3: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> ExternalSupply:
        if self.maximum_m3 is not None and self.minimum_m3 > self.maximum_m3:
            raise ValueError("ExternalSupply.minimum_m3 cannot exceed maximum_m3")
        return self


class Economics(BaseModel):
    """Currency, base-year, discounting, and objective metadata for tactical planning."""

    model_config = ConfigDict(extra="forbid")

    currency: str = "CAD"
    base_year: int = Field(default=2026, ge=1900)
    discount_rate_per_year: float = Field(default=0.0, ge=0)
    objective_profile: str = "min_discounted_delivered_cost"

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Economics.currency must be non-empty")
        return cleaned


class TacticalOperationalScenario(BaseModel):
    """Validated aggregate planning contract for TOPM-inspired FHOPS scenarios.

    The schema uses long-form, dimension-flexible tables. Cross-validation checks all period,
    product, block, system-option, facility, transport, inventory, and external-supply references.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    planning_level: str = TACTICAL_OPERATIONAL_PLANNING_LEVEL
    schema_version: str = TACTICAL_OPERATIONAL_SCHEMA_VERSION
    economics: Economics = Field(default_factory=Economics)
    periods: list[PlanningPeriod]
    products: list[Product]
    planning_units: list[PlanningUnit]
    harvest_system_options: list[HarvestSystemOption]
    fleet_capacity: list[FleetCapacity] = Field(default_factory=list)
    facilities: list[Facility]
    facility_demand: list[FacilityDemand] = Field(default_factory=list)
    initial_inventory: list[InitialInventory] = Field(default_factory=list)
    transport_arcs: list[TransportArc] = Field(default_factory=list)
    external_supply: list[ExternalSupply] = Field(default_factory=list)
    roads: list[RoadProject] = Field(default_factory=list)
    road_dependencies: list[RoadDependency] = Field(default_factory=list)
    block_road_access: list[BlockRoadAccess] = Field(default_factory=list)
    silviculture_transitions: list[SilvicultureTransition] = Field(default_factory=list)
    fleet_options: list[FleetOption] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _schema_supported(cls, value: str) -> str:
        if value != TACTICAL_OPERATIONAL_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported tactical-operational schema_version="
                f"{value}; supported: {TACTICAL_OPERATIONAL_SCHEMA_VERSION}"
            )
        return value

    @field_validator("planning_level")
    @classmethod
    def _planning_level_supported(cls, value: str) -> str:
        if value != TACTICAL_OPERATIONAL_PLANNING_LEVEL:
            raise ValueError(
                "planning_level must be 'tactical_operational' for TacticalOperationalScenario"
            )
        return value

    @staticmethod
    def _unique_ids(rows: list[Any], field: str, label: str) -> set[str]:
        values = [getattr(row, field) for row in rows]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ValueError(f"Duplicate {label} identifiers: {duplicates}")
        return set(values)

    @model_validator(mode="after")
    def _cross_validate(self) -> TacticalOperationalScenario:
        period_ids = self._unique_ids(self.periods, "period_id", "period")
        product_ids = self._unique_ids(self.products, "product_id", "product")
        block_ids = self._unique_ids(self.planning_units, "block_id", "planning unit")
        option_ids = self._unique_ids(self.harvest_system_options, "option_id", "harvest option")
        self._unique_ids(self.facilities, "facility_id", "facility")
        arc_ids = self._unique_ids(self.transport_arcs, "arc_id", "transport arc")
        road_ids = self._unique_ids(self.roads, "road_id", "road")
        self._unique_ids(self.silviculture_transitions, "transition_id", "silviculture transition")
        self._unique_ids(self.fleet_options, "option_id", "fleet option")

        sequences = [period.sequence for period in self.periods]
        if len(sequences) != len(set(sequences)):
            raise ValueError("PlanningPeriod sequence values must be unique")
        for period in self.periods:
            if period.parent_period_id and period.parent_period_id not in period_ids:
                raise ValueError(
                    f"Period {period.period_id} references unknown parent_period_id="
                    f"{period.parent_period_id}"
                )

        blocks = {unit.block_id: unit for unit in self.planning_units}
        facilities = {facility.facility_id: facility for facility in self.facilities}

        for unit in self.planning_units:
            unknown_products = set(unit.product_yields_m3_per_ha) - product_ids
            if unknown_products:
                raise ValueError(
                    f"Planning unit {unit.block_id} has yields for unknown products: "
                    f"{sorted(unknown_products)}"
                )

        for option in self.harvest_system_options:
            if option.block_id not in block_ids:
                raise ValueError(f"Harvest option {option.option_id} references unknown block")
            if option.period_id not in period_ids:
                raise ValueError(f"Harvest option {option.option_id} references unknown period")
            max_area = option.max_area_ha
            if max_area is not None and max_area > blocks[option.block_id].operable_area_ha:
                raise ValueError(
                    f"Harvest option {option.option_id} max_area_ha exceeds operable block area"
                )

        for capacity in self.fleet_capacity:
            if capacity.period_id not in period_ids:
                raise ValueError("FleetCapacity references unknown period")

        for demand in self.facility_demand:
            facility = facilities.get(demand.facility_id)
            if facility is None:
                raise ValueError("FacilityDemand references unknown facility")
            if demand.product_id not in product_ids:
                raise ValueError("FacilityDemand references unknown product")
            if facility.accepted_products and demand.product_id not in facility.accepted_products:
                raise ValueError(
                    f"Facility {facility.facility_id} does not accept product {demand.product_id}"
                )
            if demand.period_id not in period_ids:
                raise ValueError("FacilityDemand references unknown period")

        for inventory in self.initial_inventory:
            facility = facilities.get(inventory.facility_id)
            if facility is None:
                raise ValueError("InitialInventory references unknown facility")
            if inventory.product_id not in product_ids:
                raise ValueError("InitialInventory references unknown product")
            if (
                facility.accepted_products
                and inventory.product_id not in facility.accepted_products
            ):
                raise ValueError(
                    f"Facility {facility.facility_id} does not accept product {inventory.product_id}"
                )

        for arc in self.transport_arcs:
            if arc.origin_id not in block_ids:
                raise ValueError(f"Transport arc {arc.arc_id} references unknown origin block")
            facility = facilities.get(arc.destination_id)
            if facility is None:
                raise ValueError(f"Transport arc {arc.arc_id} references unknown destination")
            if arc.product_id not in product_ids:
                raise ValueError(f"Transport arc {arc.arc_id} references unknown product")
            if facility.accepted_products and arc.product_id not in facility.accepted_products:
                raise ValueError(
                    f"Transport arc {arc.arc_id} carries product {arc.product_id} to a facility "
                    "that does not accept it"
                )
            if arc.period_id not in period_ids:
                raise ValueError(f"Transport arc {arc.arc_id} references unknown period")

        for supply in self.external_supply:
            facility = facilities.get(supply.destination_id)
            if facility is None:
                raise ValueError("ExternalSupply references unknown destination facility")
            if supply.product_id not in product_ids:
                raise ValueError("ExternalSupply references unknown product")
            if facility.accepted_products and supply.product_id not in facility.accepted_products:
                raise ValueError(
                    f"ExternalSupply delivers {supply.product_id} to a facility that does not accept it"
                )
            if supply.period_id not in period_ids:
                raise ValueError("ExternalSupply references unknown period")

        for road in self.roads:
            if road.earliest_period_id and road.earliest_period_id not in period_ids:
                raise ValueError("RoadProject references unknown earliest_period_id")

        for dependency in self.road_dependencies:
            if dependency.road_id not in road_ids:
                raise ValueError("RoadDependency references unknown road_id")
            if dependency.depends_on_road_id not in road_ids:
                raise ValueError("RoadDependency references unknown depends_on_road_id")
            if dependency.road_id == dependency.depends_on_road_id:
                raise ValueError("RoadDependency cannot make a road depend on itself")

        for access in self.block_road_access:
            if access.block_id not in block_ids:
                raise ValueError("BlockRoadAccess references unknown block_id")
            if access.road_id not in road_ids:
                raise ValueError("BlockRoadAccess references unknown road_id")

        for transition in self.silviculture_transitions:
            if transition.block_id not in block_ids:
                raise ValueError("SilvicultureTransition references unknown block_id")
            if transition.earliest_period_id not in period_ids:
                raise ValueError("SilvicultureTransition references unknown earliest_period_id")

        for fleet_option in self.fleet_options:
            if fleet_option.purchase_period_id not in period_ids:
                raise ValueError("FleetOption references unknown purchase_period_id")

        if not option_ids:
            raise ValueError("TacticalOperationalScenario requires at least one harvest option")
        if not arc_ids and not self.external_supply:
            raise ValueError(
                "TacticalOperationalScenario requires transport arcs and/or external supply"
            )
        return self

    def dimension_summary(self) -> dict[str, int]:
        """Return model-dimension counts used by CLI validation and telemetry."""
        return {
            "periods": len(self.periods),
            "products": len(self.products),
            "planning_units": len(self.planning_units),
            "harvest_system_options": len(self.harvest_system_options),
            "fleet_capacity_records": len(self.fleet_capacity),
            "facilities": len(self.facilities),
            "facility_demand_records": len(self.facility_demand),
            "initial_inventory_records": len(self.initial_inventory),
            "transport_arcs": len(self.transport_arcs),
            "external_supply_records": len(self.external_supply),
            "road_projects": len(self.roads),
            "road_dependencies": len(self.road_dependencies),
            "block_road_access_records": len(self.block_road_access),
            "silviculture_transitions": len(self.silviculture_transitions),
            "fleet_options": len(self.fleet_options),
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible round-trip representation of the scenario."""
        return self.model_dump(mode="json")


__all__ = [
    "BlockRoadAccess",
    "Economics",
    "ExternalSupply",
    "Facility",
    "FacilityDemand",
    "FleetCapacity",
    "FleetOption",
    "HarvestSystemOption",
    "InitialInventory",
    "PeriodLevel",
    "PlanningPeriod",
    "PlanningUnit",
    "Product",
    "RoadDependency",
    "RoadProject",
    "SilvicultureTransition",
    "TACTICAL_OPERATIONAL_PLANNING_LEVEL",
    "TACTICAL_OPERATIONAL_SCHEMA_VERSION",
    "TacticalOperationalScenario",
    "TransportArc",
]
