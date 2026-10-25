"""Pydantic contracts for operational log hauling.

The hauling layer is an optional extension to :class:`fhops.scenario.contract.Scenario`. It adds
the entities that the harvesting and tactical-operational models do not carry: log sorts,
contractors, truck types and trucks, depots, sort yards, haul arcs, loader location bindings, and
the driver policy from Ghotb (2023).

The contract is deliberately a *data* layer. It validates identifiers, units, ranges, and cross
references; it does not build or solve an optimisation model. The Phase I flow model, Phase II
scheduling model, and Phase III simulated-annealing solver live in sibling modules.

References
----------
Ghotb, S. (2023). *Optimization of Log Logistics at the Operational Level Considering Sorting
Decisions and Synchronization Requirements*. PhD thesis, University of British Columbia.
<https://hdl.handle.net/2429/85563>
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class LoaderLocationKind(StrEnum):
    """Whether a loader serves a pickup (block) or a delivery (sort yard/mill) node."""

    PICKUP = "pickup"
    DELIVERY = "delivery"


class LogSort(BaseModel):
    """A log assortment handled by the hauling network.

    Attributes
    ----------
    id:
        Unique log-sort identifier referenced by supply, demand, and compatibility records.
    product_id:
        Optional link to a tactical-operational ``Product.product_id``. The hauling layer does not
        require the tactical contract; when the link is present it must be non-empty.
    sorted:
        ``True`` for a roadside-sorted sort, ``False`` for an unsorted sort that is processed at a
        yard. Phase I carries both sorted and unsorted supply for every sort (Ghotb's ``SW`` and
        ``SC`` parameters); this flag describes the kind of load, not a restriction on supply.
    description:
        Optional human-readable label.
    """

    id: str
    product_id: str | None = None
    sorted: bool = True
    description: str | None = None

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("LogSort.id must be non-empty")
        return value.strip()

    @field_validator("product_id")
    @classmethod
    def _product_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("LogSort.product_id must be non-empty when supplied")
        return stripped


class Contractor(BaseModel):
    """A log-trucking contractor.

    Attributes
    ----------
    id:
        Unique contractor identifier referenced by trucks and block eligibility.
    name:
        Optional human-readable label.
    preferred_daily_truckloads:
        Desired number of truckloads per day used by the Phase I social objective (Ghotb's
        ``phi_o``). ``None`` lets Phase I derive the preferred level from the cost-only solve.
    """

    id: str
    name: str | None = None
    preferred_daily_truckloads: float | None = None

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Contractor.id must be non-empty")
        return value.strip()

    @field_validator("preferred_daily_truckloads")
    @classmethod
    def _preferred_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Contractor.preferred_daily_truckloads must be non-negative")
        return value


class TruckType(BaseModel):
    """A homogeneous truck type with capacity, costs, and load compatibility.

    Attributes
    ----------
    id:
        Unique truck-type identifier.
    capacity_m3:
        Payload capacity in cubic metres (Ghotb's ``Q_r``). Must be greater than zero.
    fixed_cost:
        Fixed operating cost of dispatching a truck of this type for the day, in scenario currency
        (Ghotb's ``FC_k``). Non-negative.
    variable_cost_per_minute:
        Variable operating cost per minute of regular working time (``VC_k``). Non-negative.
    overtime_cost_per_minute:
        Overtime cost per minute (``OC_k``). Non-negative.
    can_carry_sorted:
        Whether the type may carry roadside-sorted loads (``gamma_r``).
    can_carry_unsorted:
        Whether the type may carry unsorted loads (``epsilon_r``).
    """

    id: str
    capacity_m3: float
    fixed_cost: float = 0.0
    variable_cost_per_minute: float = 0.0
    overtime_cost_per_minute: float = 0.0
    can_carry_sorted: bool = True
    can_carry_unsorted: bool = True

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("TruckType.id must be non-empty")
        return value.strip()

    @field_validator("capacity_m3")
    @classmethod
    def _capacity_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("TruckType.capacity_m3 must be > 0")
        return value

    @field_validator("fixed_cost", "variable_cost_per_minute", "overtime_cost_per_minute")
    @classmethod
    def _cost_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("TruckType cost fields must be non-negative")
        return value

    @model_validator(mode="after")
    def _carries_something(self) -> TruckType:
        if not self.can_carry_sorted and not self.can_carry_unsorted:
            raise ValueError(
                f"TruckType must be able to carry sorted or unsorted logs (truck_type_id={self.id})"
            )
        return self


class Truck(BaseModel):
    """An individual truck owned by a contractor.

    Attributes
    ----------
    id:
        Unique truck identifier. Phase II uses this as the vehicle label.
    contractor_id:
        Contractor that owns and dispatches the truck.
    truck_type_id:
        Truck type that determines capacity, cost, and load compatibility.
    enabled:
        Set ``False`` to keep a truck in the contract but exclude it from a solve.
    notes:
        Optional free-form note surfaced in reports.
    """

    id: str
    contractor_id: str
    truck_type_id: str
    enabled: bool = True
    notes: str | None = None

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Truck.id must be non-empty")
        return value.strip()


class Depot(BaseModel):
    """A central depot where trucks start and end their daily routes.

    Attributes
    ----------
    id:
        Unique depot identifier. It is also the location key used by :class:`DepotLeg`.
    name:
        Optional human-readable label.
    """

    id: str
    name: str | None = None

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Depot.id must be non-empty")
        return value.strip()


class DepotLeg(BaseModel):
    """Travel time between a depot and a pickup or delivery location.

    Attributes
    ----------
    depot_id:
        Depot identifier.
    location_id:
        Block or sort-yard identifier. The contract validates it against the scenario's blocks and
        the hauling contract's yards.
    truck_type_id:
        Truck type for which the travel time applies.
    travel_minutes:
        One-way travel time in minutes. Must be greater than zero.
    """

    depot_id: str
    location_id: str
    truck_type_id: str
    travel_minutes: float

    @field_validator("travel_minutes")
    @classmethod
    def _travel_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("DepotLeg.travel_minutes must be > 0")
        return value


class SortYard(BaseModel):
    """A sort yard or mill that receives logs and may process unsorted volume.

    Attributes
    ----------
    id:
        Unique yard identifier. It is also the delivery location key used by loaders, demand, and
        haul arcs.
    facility_id:
        Optional link to a tactical-operational ``Facility.facility_id``.
    unsorted_storage_m3:
        Maximum unsorted inventory that can be stored at the yard (Ghotb's ``SC_y``).
    sorted_processing_m3_per_day:
        Daily capacity for sorted logs (``CW_y``).
    unsorted_processing_m3_per_day:
        Daily capacity for sorting unsorted logs (``CC_y``).
    total_processing_m3_per_day:
        Daily total processing capacity for sorted and unsorted logs (``CY_y``). Must be at least
        the larger of the two component capacities.
    initial_unsorted_inventory_m3:
        Unsorted inventory at the start of the first day. Non-negative.
    initial_water_inventory_m3:
        Processed/water inventory at the start of the first day. Non-negative.
    """

    id: str
    facility_id: str | None = None
    unsorted_storage_m3: float = 0.0
    sorted_processing_m3_per_day: float = 0.0
    unsorted_processing_m3_per_day: float = 0.0
    total_processing_m3_per_day: float = 0.0
    initial_unsorted_inventory_m3: float = 0.0
    initial_water_inventory_m3: float = 0.0

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("SortYard.id must be non-empty")
        return value.strip()

    @field_validator(
        "unsorted_storage_m3",
        "sorted_processing_m3_per_day",
        "unsorted_processing_m3_per_day",
        "total_processing_m3_per_day",
        "initial_unsorted_inventory_m3",
        "initial_water_inventory_m3",
    )
    @classmethod
    def _capacity_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("SortYard capacity and inventory fields must be non-negative")
        return value

    @model_validator(mode="after")
    def _total_covers_components(self) -> SortYard:
        component_max = max(
            self.sorted_processing_m3_per_day,
            self.unsorted_processing_m3_per_day,
        )
        if self.total_processing_m3_per_day < component_max:
            raise ValueError(
                "SortYard.total_processing_m3_per_day must be >= each component capacity "
                f"(yard_id={self.id})"
            )
        return self


class LoaderLocation(BaseModel):
    """Binding between a FHOPS machine (the loader) and a hauling location.

    Attributes
    ----------
    loader_id:
        Machine identifier from ``Scenario.machines``. The machine is the physical loader.
    location_id:
        Block identifier for a pickup loader or sort-yard identifier for a delivery loader.
    location_kind:
        ``pickup`` or ``delivery``; must agree with ``location_id``.
    service_minutes:
        Optional loading/unloading service time override. When ``None``, the model uses the value
        configured by Phase II. Must be greater than zero when supplied.
    """

    loader_id: str
    location_id: str
    location_kind: LoaderLocationKind
    service_minutes: float | None = None

    @field_validator("service_minutes")
    @classmethod
    def _service_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("LoaderLocation.service_minutes must be > 0 when supplied")
        return value


class HaulingSupply(BaseModel):
    """Available sorted and unsorted volume of one log sort at one block.

    Attributes
    ----------
    block_id:
        Block identifier from ``Scenario.blocks``.
    log_sort_id:
        Log-sort identifier from the hauling contract.
    sorted_m3:
        Roadside-sorted supply in cubic metres (Ghotb's ``SW_bs``). Non-negative.
    unsorted_m3:
        Unsorted supply in cubic metres (``SC_bs``). Non-negative.
    """

    block_id: str
    log_sort_id: str
    sorted_m3: float = 0.0
    unsorted_m3: float = 0.0

    @field_validator("sorted_m3", "unsorted_m3")
    @classmethod
    def _volume_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("HaulingSupply volumes must be non-negative")
        return value

    @model_validator(mode="after")
    def _has_volume(self) -> HaulingSupply:
        if self.sorted_m3 <= 0 and self.unsorted_m3 <= 0:
            raise ValueError(
                "HaulingSupply must carry a positive sorted_m3 or unsorted_m3 "
                f"(block_id={self.block_id}, log_sort_id={self.log_sort_id})"
            )
        return self


class HaulingDemand(BaseModel):
    """Demand for one log sort at one yard on one day of the hauling horizon.

    Attributes
    ----------
    yard_id:
        Sort-yard identifier from the hauling contract.
    log_sort_id:
        Log-sort identifier from the hauling contract.
    day:
        One-indexed day relative to the hauling horizon (not the parent scenario horizon).
    volume_m3:
        Required volume in cubic metres. Non-negative.
    """

    yard_id: str
    log_sort_id: str
    day: int
    volume_m3: float

    @field_validator("day")
    @classmethod
    def _day_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("HaulingDemand.day must be >= 1")
        return value

    @field_validator("volume_m3")
    @classmethod
    def _volume_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("HaulingDemand.volume_m3 must be non-negative")
        return value


class HaulArc(BaseModel):
    """A feasible one-way haul leg from a block to a sort yard for one truck type.

    Attributes
    ----------
    block_id:
        Origin block identifier.
    yard_id:
        Destination sort-yard identifier.
    truck_type_id:
        Truck type that can traverse the arc.
    travel_minutes:
        Loaded travel time in minutes, including any arc-specific delay but excluding loading and
        unloading. Must be greater than zero.
    distance_km:
        Optional distance for reporting and cost checks. Non-negative.
    return_travel_minutes:
        Optional empty return time from the yard to the block. When ``None``, Phase II uses
        ``travel_minutes`` for the empty leg as well.
    """

    block_id: str
    yard_id: str
    truck_type_id: str
    travel_minutes: float
    distance_km: float | None = None
    return_travel_minutes: float | None = None

    @field_validator("travel_minutes")
    @classmethod
    def _travel_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("HaulArc.travel_minutes must be > 0")
        return value

    @field_validator("distance_km")
    @classmethod
    def _distance_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("HaulArc.distance_km must be non-negative")
        return value

    @field_validator("return_travel_minutes")
    @classmethod
    def _return_travel_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("HaulArc.return_travel_minutes must be > 0 when supplied")
        return value

    def empty_travel_minutes(self) -> float:
        """Return the empty return time from the yard to the block."""
        return (
            self.return_travel_minutes
            if self.return_travel_minutes is not None
            else self.travel_minutes
        )


class ContractorBlock(BaseModel):
    """Eligibility of a contractor to serve a block.

    When the contract contains no ``contractor_blocks`` entries, every contractor may serve every
    block. When it contains any entry, the list is treated as an allowlist: only the listed
    contractor/block pairs are eligible. This mirrors Ghotb's ``alpha_bo`` parameter.
    """

    contractor_id: str
    block_id: str


class DriverPolicy(BaseModel):
    """Regular-time, overtime, and overtime-violation policy for truck drivers.

    Attributes
    ----------
    regular_minutes:
        Regular working minutes per truck per day. The thesis case uses 510 (8.5 h).
    max_overtime_minutes:
        Maximum overtime that may be assigned before a violation penalty applies. The thesis case
        uses 150 (2.5 h).
    overtime_violation_penalty_per_minute:
        Penalty per minute of overtime above ``max_overtime_minutes``. Phase III may use this as a
        soft penalty; Phase II treats the limit as a hard constraint.
    """

    regular_minutes: float = 510.0
    max_overtime_minutes: float = 150.0
    overtime_violation_penalty_per_minute: float = 0.0

    @field_validator("regular_minutes")
    @classmethod
    def _regular_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("DriverPolicy.regular_minutes must be > 0")
        return value

    @field_validator("max_overtime_minutes", "overtime_violation_penalty_per_minute")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("DriverPolicy overtime fields must be non-negative")
        return value


class ContractCompatibility(BaseModel):
    """Explicit compatibility override for a contractor, block, truck type, or log sort.

    The first release derives most compatibility from ownership and truck-type flags. This model is
    reserved for later exceptions and is not required. When ``allowed`` is ``False``, the matching
    combination is refused; when ``True``, it is explicitly allowed. At least one target field must
    be present.
    """

    contractor_id: str
    block_id: str | None = None
    truck_type_id: str | None = None
    log_sort_id: str | None = None
    allowed: bool = True

    @model_validator(mode="after")
    def _has_target(self) -> ContractCompatibility:
        if self.block_id is None and self.truck_type_id is None and self.log_sort_id is None:
            raise ValueError(
                "ContractCompatibility requires block_id, truck_type_id, or log_sort_id"
            )
        return self


class HaulingConfig(BaseModel):
    """Optional ``hauling:`` section of a FHOPS scenario.

    The config carries Ghotb's operational log-hauling entities. It is validated against the parent
    scenario so every block, machine, and horizon reference is real. It does not require the
    tactical-operational contract; ``product_id`` and ``facility_id`` links are optional.

    Attributes
    ----------
    planning_horizon_days:
        Number of working days in the Phase I horizon. Defaults to 20 (four weeks).
    start_day:
        One-indexed day of the parent scenario where the hauling horizon starts.
    log_sorts / contractors / truck_types / trucks / depots / sort_yards:
        Core entity lists.
    depot_legs:
        Optional travel times from each depot to blocks and yards, by truck type.
    loader_locations:
        Bindings from FHOPS ``Machine`` records to pickup or delivery locations.
    supply / demand / haul_arcs:
        The Phase I flow inputs.
    contractor_blocks:
        Optional contractor-to-block allowlist. When empty, all contractors may serve all blocks.
    compatibility:
        Optional explicit exceptions. Reserved for later phases.
    driver_policy:
        Regular and overtime rules for Phase II and Phase III.
    roadside_inventory_penalty_per_m3:
        Penalty per cubic metre of sorted or unsorted volume left at a block at the end of the
        Phase I horizon (Ghotb's ``P``). Non-negative.
    loader_travel_cost_per_km:
        Loader travel cost per kilometre (Ghotb's ``DC_l``). The thesis case uses stationary
        loaders, so this defaults to zero. Non-negative.
    default_loader_service_minutes:
        Fallback loading/unloading service time when ``LoaderLocation.service_minutes`` is omitted.
        Must be greater than zero.
    """

    planning_horizon_days: int = 20
    start_day: int = 1
    log_sorts: list[LogSort]
    contractors: list[Contractor]
    truck_types: list[TruckType]
    trucks: list[Truck]
    depots: list[Depot]
    sort_yards: list[SortYard]
    depot_legs: list[DepotLeg] = Field(default_factory=list)
    loader_locations: list[LoaderLocation] = Field(default_factory=list)
    supply: list[HaulingSupply]
    demand: list[HaulingDemand] = Field(default_factory=list)
    haul_arcs: list[HaulArc]
    contractor_blocks: list[ContractorBlock] = Field(default_factory=list)
    compatibility: list[ContractCompatibility] = Field(default_factory=list)
    driver_policy: DriverPolicy = Field(default_factory=DriverPolicy)
    roadside_inventory_penalty_per_m3: float = 0.0
    loader_travel_cost_per_km: float = 0.0
    default_loader_service_minutes: float = 20.0

    @field_validator("planning_horizon_days")
    @classmethod
    def _horizon_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("HaulingConfig.planning_horizon_days must be >= 1")
        return value

    @field_validator("start_day")
    @classmethod
    def _start_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("HaulingConfig.start_day must be >= 1")
        return value

    @field_validator(
        "roadside_inventory_penalty_per_m3",
        "loader_travel_cost_per_km",
    )
    @classmethod
    def _cost_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("HaulingConfig cost parameters must be non-negative")
        return value

    @field_validator("default_loader_service_minutes")
    @classmethod
    def _service_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("HaulingConfig.default_loader_service_minutes must be > 0")
        return value

    @model_validator(mode="after")
    def _validate_internal_references(self) -> HaulingConfig:
        if not self.trucks:
            raise ValueError("HaulingConfig requires at least one truck")
        if not self.depots:
            raise ValueError("HaulingConfig requires at least one depot")
        if not self.haul_arcs:
            raise ValueError("HaulingConfig requires at least one haul arc")

        log_sort_ids = _unique_ids(self.log_sorts, "id", "log sort")
        contractor_ids = _unique_ids(self.contractors, "id", "contractor")
        truck_type_ids = _unique_ids(self.truck_types, "id", "truck type")
        _unique_ids(self.trucks, "id", "truck")
        depot_ids = _unique_ids(self.depots, "id", "depot")
        yard_ids = _unique_ids(self.sort_yards, "id", "sort yard")

        for truck in self.trucks:
            if truck.contractor_id not in contractor_ids:
                raise ValueError(
                    f"Truck {truck.id} references unknown contractor_id={truck.contractor_id}"
                )
            if truck.truck_type_id not in truck_type_ids:
                raise ValueError(
                    f"Truck {truck.id} references unknown truck_type_id={truck.truck_type_id}"
                )

        for leg in self.depot_legs:
            if leg.depot_id not in depot_ids:
                raise ValueError(f"DepotLeg references unknown depot_id={leg.depot_id}")
            if leg.truck_type_id not in truck_type_ids:
                raise ValueError(f"DepotLeg references unknown truck_type_id={leg.truck_type_id}")

        for loader in self.loader_locations:
            if loader.location_kind is LoaderLocationKind.PICKUP and loader.location_id in yard_ids:
                raise ValueError(
                    f"Pickup loader {loader.loader_id} points at a yard: {loader.location_id}"
                )
            if (
                loader.location_kind is LoaderLocationKind.DELIVERY
                and loader.location_id not in yard_ids
            ):
                raise ValueError(
                    f"Delivery loader {loader.loader_id} points at unknown yard: "
                    f"{loader.location_id}"
                )

        seen_supply: set[tuple[str, str]] = set()
        for supply in self.supply:
            if supply.log_sort_id not in log_sort_ids:
                raise ValueError(
                    f"HaulingSupply references unknown log_sort_id={supply.log_sort_id}"
                )
            supply_key = (supply.block_id, supply.log_sort_id)
            if supply_key in seen_supply:
                raise ValueError(
                    "HaulingSupply lists the same block/log-sort pair more than once: "
                    f"{supply.block_id}/{supply.log_sort_id}"
                )
            seen_supply.add(supply_key)

        seen_demand: set[tuple[str, str, int]] = set()
        for demand in self.demand:
            if demand.yard_id not in yard_ids:
                raise ValueError(f"HaulingDemand references unknown yard_id={demand.yard_id}")
            if demand.log_sort_id not in log_sort_ids:
                raise ValueError(
                    f"HaulingDemand references unknown log_sort_id={demand.log_sort_id}"
                )
            if demand.day > self.planning_horizon_days:
                raise ValueError(
                    f"HaulingDemand day {demand.day} exceeds "
                    f"planning_horizon_days={self.planning_horizon_days}"
                )
            demand_key = (demand.yard_id, demand.log_sort_id, demand.day)
            if demand_key in seen_demand:
                raise ValueError(
                    "HaulingDemand lists the same yard/log-sort/day more than once: "
                    f"{demand.yard_id}/{demand.log_sort_id}/{demand.day}"
                )
            seen_demand.add(demand_key)

        seen_arcs: set[tuple[str, str, str]] = set()
        for arc in self.haul_arcs:
            if arc.yard_id not in yard_ids:
                raise ValueError(f"HaulArc references unknown yard_id={arc.yard_id}")
            if arc.truck_type_id not in truck_type_ids:
                raise ValueError(f"HaulArc references unknown truck_type_id={arc.truck_type_id}")
            arc_key = (arc.block_id, arc.yard_id, arc.truck_type_id)
            if arc_key in seen_arcs:
                raise ValueError(
                    "HaulArc lists the same block/yard/truck-type triple more than once: "
                    f"{arc.block_id}/{arc.yard_id}/{arc.truck_type_id}"
                )
            seen_arcs.add(arc_key)

        for rule in self.contractor_blocks:
            if rule.contractor_id not in contractor_ids:
                raise ValueError(
                    f"ContractorBlock references unknown contractor_id={rule.contractor_id}"
                )

        for override in self.compatibility:
            if override.contractor_id not in contractor_ids:
                raise ValueError(
                    "ContractCompatibility references unknown contractor_id="
                    f"{override.contractor_id}"
                )
            if override.truck_type_id is not None and override.truck_type_id not in truck_type_ids:
                raise ValueError(
                    "ContractCompatibility references unknown truck_type_id="
                    f"{override.truck_type_id}"
                )
            if override.log_sort_id is not None and override.log_sort_id not in log_sort_ids:
                raise ValueError(
                    f"ContractCompatibility references unknown log_sort_id={override.log_sort_id}"
                )

        return self

    def log_sort_ids(self) -> set[str]:
        """Return the set of log-sort identifiers."""
        return {sort.id for sort in self.log_sorts}

    def contractor_ids(self) -> set[str]:
        """Return the set of contractor identifiers."""
        return {contractor.id for contractor in self.contractors}

    def truck_type_ids(self) -> set[str]:
        """Return the set of truck-type identifiers."""
        return {truck_type.id for truck_type in self.truck_types}

    def truck_ids(self) -> set[str]:
        """Return the set of truck identifiers."""
        return {truck.id for truck in self.trucks}

    def depot_ids(self) -> set[str]:
        """Return the set of depot identifiers."""
        return {depot.id for depot in self.depots}

    def yard_ids(self) -> set[str]:
        """Return the set of sort-yard identifiers."""
        return {yard.id for yard in self.sort_yards}

    def contractor_can_serve_block(self, contractor_id: str, block_id: str) -> bool:
        """Return whether a contractor may serve a block under the allowlist rule."""
        if not self.contractor_blocks:
            return True
        return any(
            rule.contractor_id == contractor_id and rule.block_id == block_id
            for rule in self.contractor_blocks
        )

    def trucks_for(self, contractor_id: str, truck_type_id: str) -> list[Truck]:
        """Return enabled trucks of one contractor and type."""
        return [
            truck
            for truck in self.trucks
            if truck.enabled
            and truck.contractor_id == contractor_id
            and truck.truck_type_id == truck_type_id
        ]

    def validate_against_scenario(
        self,
        *,
        block_ids: set[str],
        machine_ids: set[str],
        num_days: int,
    ) -> None:
        """Validate references to the parent scenario and its horizon.

        Parameters
        ----------
        block_ids:
            Every block identifier defined by the scenario.
        machine_ids:
            Every machine identifier defined by the scenario (loaders are machines).
        num_days:
            Parent scenario horizon length.

        Raises
        ------
        ValueError
            When a block, loader, or horizon reference is invalid.
        """
        if self.start_day + self.planning_horizon_days - 1 > num_days:
            raise ValueError(
                "HaulingConfig horizon "
                f"[{self.start_day}, {self.start_day + self.planning_horizon_days - 1}] "
                f"exceeds scenario num_days={num_days}"
            )

        for supply in self.supply:
            if supply.block_id not in block_ids:
                raise ValueError(f"HaulingSupply references unknown block_id={supply.block_id}")
        for arc in self.haul_arcs:
            if arc.block_id not in block_ids:
                raise ValueError(f"HaulArc references unknown block_id={arc.block_id}")
        for rule in self.contractor_blocks:
            if rule.block_id not in block_ids:
                raise ValueError(f"ContractorBlock references unknown block_id={rule.block_id}")
        for override in self.compatibility:
            if override.block_id is not None and override.block_id not in block_ids:
                raise ValueError(
                    f"ContractCompatibility references unknown block_id={override.block_id}"
                )
        for loader in self.loader_locations:
            if loader.loader_id not in machine_ids:
                raise ValueError(f"LoaderLocation references unknown machine_id={loader.loader_id}")
            if (
                loader.location_kind is LoaderLocationKind.PICKUP
                and loader.location_id not in block_ids
            ):
                raise ValueError(
                    f"Pickup loader {loader.loader_id} points at unknown block: "
                    f"{loader.location_id}"
                )
        for leg in self.depot_legs:
            if leg.location_id not in block_ids and leg.location_id not in self.yard_ids():
                raise ValueError(
                    f"DepotLeg location_id={leg.location_id} is neither a block nor a yard"
                )


def _unique_ids(items: Sequence[BaseModel], field: str, label: str) -> set[str]:
    seen: set[str] = set()
    for item in items:
        value = getattr(item, field)
        if value in seen:
            raise ValueError(f"Duplicate {label} {field}={value}")
        seen.add(value)
    return seen


__all__ = [
    "ContractCompatibility",
    "Contractor",
    "ContractorBlock",
    "Depot",
    "DepotLeg",
    "DriverPolicy",
    "HaulArc",
    "HaulingConfig",
    "HaulingDemand",
    "HaulingSupply",
    "LoaderLocation",
    "LoaderLocationKind",
    "LogSort",
    "SortYard",
    "Truck",
    "TruckType",
]
