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


class TransportMode(StrEnum):
    """Transport mode for a haul leg.

    Road legs use a :class:`TruckType`; water legs use a :class:`BargeType`. Rail is reserved for a
    later extension and is not accepted by the road or water models yet.
    """

    ROAD = "road"
    WATER = "water"
    RAIL = "rail"


class LoaderLocationKind(StrEnum):
    """Whether a loader serves a pickup, delivery, or port/terminal node.

    ``PORT`` loaders serve both the road drayage and the barge load/unload activity at a port.
    """

    PICKUP = "pickup"
    DELIVERY = "delivery"
    PORT = "port"


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

    @field_validator("id")
    @classmethod
    def _reject_vessel_alias(cls, value: str) -> str:
        stripped = value.strip()
        tokens = ("barge", "vessel", "ferry", "marine", "ship")
        if any(token in stripped.lower() for token in tokens):
            raise ValueError(
                f"TruckType id={stripped!r} looks like a marine vessel. Barges are not truck "
                "types: declare a BargeType, a Barge, a Port pair, a WaterArc, and a MarineRoute "
                "instead of aliasing the vessel as a TruckType."
            )
        return stripped


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


class PortSide(StrEnum):
    """Which end of a marine route a road drayage leg serves.

    ``ORIGIN`` is the block-to-port leg on the loading side; ``DESTINATION`` is the port-to-yard
    leg on the unloading side.
    """

    ORIGIN = "origin"
    DESTINATION = "destination"


class BargeType(BaseModel):
    """A homogeneous barge/vessel type used on a water haul leg.

    Attributes
    ----------
    id:
        Unique barge-type identifier.
    capacity_m3:
        Cargo capacity in cubic metres per barge trip. Must be greater than zero.
    fixed_cost:
        Fixed cost of dispatching a barge for the day, in scenario currency. Non-negative.
        Phase II uses it; Phase I charges only variable, handling, and trip costs.
    variable_cost_per_minute:
        Variable cost per minute of barge working time. Non-negative.
    overtime_cost_per_minute:
        Overtime cost per barge minute. Non-negative.
    load_minutes:
        Default loading time at the origin port, in minutes. Non-negative.
    unload_minutes:
        Default unloading time at the destination port, in minutes. Non-negative.
    can_carry_sorted:
        Whether the barge may carry roadside-sorted loads. Defaults to ``True``.
    can_carry_unsorted:
        Whether the barge may carry unsorted loads. Defaults to ``True``.
    """

    id: str
    capacity_m3: float
    fixed_cost: float = 0.0
    variable_cost_per_minute: float = 0.0
    overtime_cost_per_minute: float = 0.0
    load_minutes: float = 0.0
    unload_minutes: float = 0.0
    can_carry_sorted: bool = True
    can_carry_unsorted: bool = True

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("BargeType.id must be non-empty")
        return value.strip()

    @field_validator("capacity_m3")
    @classmethod
    def _capacity_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("BargeType.capacity_m3 must be > 0")
        return value

    @field_validator(
        "fixed_cost",
        "variable_cost_per_minute",
        "overtime_cost_per_minute",
        "load_minutes",
        "unload_minutes",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("BargeType cost and service fields must be non-negative")
        return value

    @model_validator(mode="after")
    def _carries_something(self) -> BargeType:
        if not self.can_carry_sorted and not self.can_carry_unsorted:
            raise ValueError(
                f"BargeType must be able to carry sorted or unsorted logs (barge_type_id={self.id})"
            )
        return self


class Barge(BaseModel):
    """An individual barge or vessel owned by a contractor.

    Attributes
    ----------
    id:
        Unique barge identifier. Phase II uses it as the vessel label.
    contractor_id:
        Contractor that owns and dispatches the barge.
    barge_type_id:
        Barge type that determines capacity, cost, and load compatibility.
    enabled:
        Set ``False`` to keep the barge in the contract but exclude it from a solve.
    notes:
        Optional free-form note surfaced in reports.
    """

    id: str
    contractor_id: str
    barge_type_id: str
    enabled: bool = True
    notes: str | None = None

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Barge.id must be non-empty")
        return value.strip()


class Port(BaseModel):
    """A port or barge terminal at one end of a water leg.

    Attributes
    ----------
    id:
        Unique port identifier. It is the location key used by water arcs, port legs, and port
        loader locations.
    name:
        Optional human-readable label.
    storage_m3:
        Total log-storage capacity at the terminal, in cubic metres. Non-negative; zero means no
        spare storage constraint is modelled.
    initial_inventory_m3:
        Opening inventory for every log sort at the port. Non-negative.
    handling_minutes_per_trip:
        Terminal handling time charged once per barge trip at this port. Non-negative.
    handling_cost_per_trip:
        Terminal handling cost charged once per barge trip at this port. Non-negative.
    daily_handling_m3:
        Optional daily throughput cap in cubic metres. ``None`` means uncapped.
    """

    id: str
    name: str | None = None
    storage_m3: float = 0.0
    initial_inventory_m3: float = 0.0
    handling_minutes_per_trip: float = 0.0
    handling_cost_per_trip: float = 0.0
    daily_handling_m3: float | None = None

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Port.id must be non-empty")
        return value.strip()

    @field_validator(
        "storage_m3",
        "initial_inventory_m3",
        "handling_minutes_per_trip",
        "handling_cost_per_trip",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Port storage, inventory, and handling fields must be non-negative")
        return value

    @field_validator("daily_handling_m3")
    @classmethod
    def _throughput_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("Port.daily_handling_m3 must be > 0 when supplied")
        return value


class WaterArc(BaseModel):
    """A sailing leg between two ports for one barge type.

    Attributes
    ----------
    id:
        Unique water-arc identifier referenced by :class:`MarineRoute`.
    origin_port_id:
        Loading port identifier.
    destination_port_id:
        Unloading port identifier.
    barge_type_id:
        Barge type that can sail the arc.
    travel_minutes:
        Loaded sailing time in minutes. Must be greater than zero.
    distance_km:
        Optional sailing distance for reporting and cost checks. Non-negative.
    return_travel_minutes:
        Optional empty return sailing time. When ``None``, Phase I/II use ``travel_minutes``.
    load_minutes:
        Optional loading-time override for this arc. When ``None``, the barge type default is used.
    unload_minutes:
        Optional unloading-time override for this arc. When ``None``, the barge type default is
        used.
    """

    id: str
    origin_port_id: str
    destination_port_id: str
    barge_type_id: str
    travel_minutes: float
    distance_km: float | None = None
    return_travel_minutes: float | None = None
    load_minutes: float | None = None
    unload_minutes: float | None = None

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("WaterArc.id must be non-empty")
        return value.strip()

    @field_validator("travel_minutes")
    @classmethod
    def _travel_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("WaterArc.travel_minutes must be > 0")
        return value

    @field_validator("distance_km")
    @classmethod
    def _distance_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("WaterArc.distance_km must be non-negative")
        return value

    @field_validator("return_travel_minutes", "load_minutes", "unload_minutes")
    @classmethod
    def _positive_when_supplied(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("WaterArc time overrides must be > 0 when supplied")
        return value

    def empty_travel_minutes(self) -> float:
        """Return the empty return sailing time from the destination to the origin."""
        return (
            self.return_travel_minutes
            if self.return_travel_minutes is not None
            else self.travel_minutes
        )


class PortLeg(BaseModel):
    """A road drayage leg between a block/yard and a port.

    Attributes
    ----------
    port_id:
        Port identifier.
    location_id:
        Block identifier for an origin-side leg or sort-yard identifier for a destination-side
        leg.
    side:
        ``origin`` for the block-to-port leg, ``destination`` for the port-to-yard leg.
    truck_type_id:
        Truck type that performs the drayage.
    travel_minutes:
        Loaded one-way travel time in minutes. Must be greater than zero.
    distance_km:
        Optional road distance. Non-negative.
    return_travel_minutes:
        Optional empty return time. When ``None``, the loaded time is used.
    """

    port_id: str
    location_id: str
    side: PortSide
    truck_type_id: str
    travel_minutes: float
    distance_km: float | None = None
    return_travel_minutes: float | None = None

    @field_validator("travel_minutes")
    @classmethod
    def _travel_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("PortLeg.travel_minutes must be > 0")
        return value

    @field_validator("distance_km")
    @classmethod
    def _distance_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("PortLeg.distance_km must be non-negative")
        return value

    @field_validator("return_travel_minutes")
    @classmethod
    def _return_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("PortLeg.return_travel_minutes must be > 0 when supplied")
        return value

    def empty_travel_minutes(self) -> float:
        """Return the empty return time between the port and the land location."""
        return (
            self.return_travel_minutes
            if self.return_travel_minutes is not None
            else self.travel_minutes
        )


class MarineRoute(BaseModel):
    """A complete block-to-yard chain with a water leg between two ports.

    The route is a composite of a road pickup leg, terminal handling at both ports, a barge sailing
    leg, and a road delivery leg. Phase I treats it as an alternative to a direct road
    :class:`HaulArc`; Phase II schedules the drayage loads and barge trips separately.

    Attributes
    ----------
    id:
        Unique marine-route identifier.
    block_id:
        Origin block for the pickup drayage leg.
    yard_id:
        Destination sort yard for the delivery drayage leg.
    origin_port_id:
        Loading port.
    destination_port_id:
        Unloading port.
    water_arc_id:
        Sailing arc. Its barge type provides capacity, cost, and load compatibility.
    contractor_id:
        Contractor responsible for the route. The contractor must own an enabled barge of the
        water arc's type and at least one enabled truck of ``truck_type_id``.
    truck_type_id:
        Road truck type used for the pickup and delivery drayage legs.
    """

    id: str
    block_id: str
    yard_id: str
    origin_port_id: str
    destination_port_id: str
    water_arc_id: str
    contractor_id: str
    truck_type_id: str

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("MarineRoute.id must be non-empty")
        return value.strip()

    @model_validator(mode="after")
    def _ports_differ(self) -> MarineRoute:
        if self.origin_port_id == self.destination_port_id:
            raise ValueError(
                f"MarineRoute origin and destination ports must differ (route_id={self.id})"
            )
        return self


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
    """A feasible one-way road haul leg from a block to a sort yard for one truck type.

    Water legs are not represented as ``HaulArc`` records. Declare a :class:`WaterArc`,
    :class:`Port` pair, :class:`BargeType`, and :class:`MarineRoute` instead. The ``mode`` field is
    explicit so a report can distinguish road arcs without inferring the mode from identifiers.

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
    mode:
        Transport mode. Only ``road`` is accepted here; water and rail legs use their dedicated
        models.
    """

    block_id: str
    yard_id: str
    truck_type_id: str
    travel_minutes: float
    distance_km: float | None = None
    return_travel_minutes: float | None = None
    mode: TransportMode = TransportMode.ROAD

    @field_validator("mode")
    @classmethod
    def _road_only(cls, value: TransportMode) -> TransportMode:
        if value is not TransportMode.ROAD:
            raise ValueError(
                "HaulArc supports only mode=road. Use WaterArc + MarineRoute for water legs; a "
                "barge is not a truck type."
            )
        return value

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
    haul_arcs:
        The Phase I road flow inputs.
    barge_types / barges:
        Marine equipment. Barges are first-class vessels, never aliases of truck types.
    ports / water_arcs / port_legs / marine_routes:
        The marine path: terminal nodes, sailing legs, road drayage legs, and complete block-to-yard
        chains with a water segment.
    contractor_blocks:
        Optional contractor-to-block allowlist. When empty, all contractors may serve all blocks.
    compatibility:
        Optional explicit exceptions. Reserved for later phases.
    driver_policy:
        Regular and overtime rules for Phase II and Phase III.
    roadside_inventory_penalty_per_m3:
        Penalty per cubic metre of sorted or unsorted volume left at a block at the end of the
        Phase I horizon (Ghotb's ``P``). Non-negative.
    port_inventory_penalty_per_m3:
        Penalty per cubic metre of log volume left at a port at the end of the Phase I horizon.
        Non-negative. Zero lets the model store volume at a terminal for free.
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
    barge_types: list[BargeType] = Field(default_factory=list)
    barges: list[Barge] = Field(default_factory=list)
    ports: list[Port] = Field(default_factory=list)
    water_arcs: list[WaterArc] = Field(default_factory=list)
    port_legs: list[PortLeg] = Field(default_factory=list)
    marine_routes: list[MarineRoute] = Field(default_factory=list)
    contractor_blocks: list[ContractorBlock] = Field(default_factory=list)
    compatibility: list[ContractCompatibility] = Field(default_factory=list)
    driver_policy: DriverPolicy = Field(default_factory=DriverPolicy)
    roadside_inventory_penalty_per_m3: float = 0.0
    port_inventory_penalty_per_m3: float = 0.0
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
        "port_inventory_penalty_per_m3",
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
        if not self.haul_arcs and not self.marine_routes:
            raise ValueError("HaulingConfig requires at least one haul arc or one marine route")

        log_sort_ids = _unique_ids(self.log_sorts, "id", "log sort")
        contractor_ids = _unique_ids(self.contractors, "id", "contractor")
        truck_type_ids = _unique_ids(self.truck_types, "id", "truck type")
        _unique_ids(self.trucks, "id", "truck")
        depot_ids = _unique_ids(self.depots, "id", "depot")
        yard_ids = _unique_ids(self.sort_yards, "id", "sort yard")
        barge_type_ids = _unique_ids(self.barge_types, "id", "barge type")
        _unique_ids(self.barges, "id", "barge")
        port_ids = _unique_ids(self.ports, "id", "port")
        water_arc_ids = _unique_ids(self.water_arcs, "id", "water arc")
        _unique_ids(self.marine_routes, "id", "marine route")

        marine_lists_present = any(
            (
                self.barges,
                self.barge_types,
                self.ports,
                self.water_arcs,
                self.port_legs,
                self.marine_routes,
            )
        )
        if self.marine_routes and not self.barge_types:
            raise ValueError("MarineRoute requires at least one BargeType")
        if self.marine_routes and not self.barges:
            raise ValueError("MarineRoute requires at least one Barge")
        if self.marine_routes and not self.ports:
            raise ValueError("MarineRoute requires at least two Port records")
        if self.marine_routes and not self.water_arcs:
            raise ValueError("MarineRoute requires at least one WaterArc")
        if marine_lists_present and not self.marine_routes:
            raise ValueError(
                "Marine entities are present but no MarineRoute connects them to a block and yard"
            )

        for barge in self.barges:
            if barge.contractor_id not in contractor_ids:
                raise ValueError(
                    f"Barge {barge.id} references unknown contractor_id={barge.contractor_id}"
                )
            if barge.barge_type_id not in barge_type_ids:
                raise ValueError(
                    f"Barge {barge.id} references unknown barge_type_id={barge.barge_type_id}"
                )

        for arc in self.water_arcs:
            if arc.origin_port_id not in port_ids:
                raise ValueError(
                    f"WaterArc {arc.id} references unknown origin_port_id={arc.origin_port_id}"
                )
            if arc.destination_port_id not in port_ids:
                raise ValueError(
                    "WaterArc "
                    f"{arc.id} references unknown destination_port_id={arc.destination_port_id}"
                )
            if arc.barge_type_id not in barge_type_ids:
                raise ValueError(
                    f"WaterArc {arc.id} references unknown barge_type_id={arc.barge_type_id}"
                )

        for leg in self.port_legs:
            if leg.port_id not in port_ids:
                raise ValueError(f"PortLeg references unknown port_id={leg.port_id}")
            if leg.truck_type_id not in truck_type_ids:
                raise ValueError(f"PortLeg references unknown truck_type_id={leg.truck_type_id}")
        seen_port_legs: set[tuple[str, str, PortSide, str]] = set()
        for leg in self.port_legs:
            key = (leg.port_id, leg.location_id, leg.side, leg.truck_type_id)
            if key in seen_port_legs:
                raise ValueError(
                    "PortLeg lists the same port/location/side/truck-type combination more than "
                    f"once: {leg.port_id}/{leg.location_id}/{leg.side}/{leg.truck_type_id}"
                )
            seen_port_legs.add(key)

        water_arc_by_id = {arc.id: arc for arc in self.water_arcs}
        barge_types_by_id = {barge_type.id: barge_type for barge_type in self.barge_types}
        seen_routes: set[tuple[str, str, str, str]] = set()
        for route in self.marine_routes:
            if route.contractor_id not in contractor_ids:
                raise ValueError(
                    f"MarineRoute {route.id} references unknown contractor_id={route.contractor_id}"
                )
            if route.truck_type_id not in truck_type_ids:
                raise ValueError(
                    f"MarineRoute {route.id} references unknown truck_type_id={route.truck_type_id}"
                )
            if route.origin_port_id not in port_ids:
                raise ValueError(
                    f"MarineRoute {route.id} references unknown origin_port_id={route.origin_port_id}"
                )
            if route.destination_port_id not in port_ids:
                raise ValueError(
                    "MarineRoute "
                    f"{route.id} references unknown destination_port_id={route.destination_port_id}"
                )
            if route.water_arc_id not in water_arc_ids:
                raise ValueError(
                    f"MarineRoute {route.id} references unknown water_arc_id={route.water_arc_id}"
                )
            water_arc = water_arc_by_id[route.water_arc_id]
            if (water_arc.origin_port_id, water_arc.destination_port_id) != (
                route.origin_port_id,
                route.destination_port_id,
            ):
                raise ValueError(
                    f"MarineRoute {route.id} ports do not match WaterArc {water_arc.id}"
                )
            barge_type = barge_types_by_id[water_arc.barge_type_id]
            if not any(
                barge.enabled
                and barge.contractor_id == route.contractor_id
                and barge.barge_type_id == barge_type.id
                for barge in self.barges
            ):
                raise ValueError(
                    f"MarineRoute {route.id} has no enabled barge of type "
                    f"{barge_type.id} for contractor {route.contractor_id}"
                )
            if not self.trucks_for(route.contractor_id, route.truck_type_id):
                raise ValueError(
                    f"MarineRoute {route.id} has no enabled truck of type "
                    f"{route.truck_type_id} for contractor {route.contractor_id}"
                )
            origin_leg = self._port_leg_for(route, PortSide.ORIGIN)
            destination_leg = self._port_leg_for(route, PortSide.DESTINATION)
            if origin_leg is None:
                raise ValueError(
                    f"MarineRoute {route.id} has no origin PortLeg for port "
                    f"{route.origin_port_id}, block {route.block_id}, truck type {route.truck_type_id}"
                )
            if destination_leg is None:
                raise ValueError(
                    f"MarineRoute {route.id} has no destination PortLeg for port "
                    f"{route.destination_port_id}, yard {route.yard_id}, truck type "
                    f"{route.truck_type_id}"
                )
            route_key = (
                route.block_id,
                route.yard_id,
                route.truck_type_id,
                water_arc.barge_type_id,
            )
            if route_key in seen_routes:
                raise ValueError(
                    "MarineRoute lists the same block/yard/truck-type/barge-type combination more "
                    f"than once: {route_key}"
                )
            seen_routes.add(route_key)

        for truck in self.trucks:
            if truck.contractor_id not in contractor_ids:
                raise ValueError(
                    f"Truck {truck.id} references unknown contractor_id={truck.contractor_id}"
                )
            if truck.truck_type_id not in truck_type_ids:
                raise ValueError(
                    f"Truck {truck.id} references unknown truck_type_id={truck.truck_type_id}"
                )

        for depot_leg in self.depot_legs:
            if depot_leg.depot_id not in depot_ids:
                raise ValueError(f"DepotLeg references unknown depot_id={depot_leg.depot_id}")
            if depot_leg.truck_type_id not in truck_type_ids:
                raise ValueError(
                    f"DepotLeg references unknown truck_type_id={depot_leg.truck_type_id}"
                )

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
            if (
                loader.location_kind is LoaderLocationKind.PORT
                and loader.location_id not in port_ids
            ):
                raise ValueError(
                    f"Port loader {loader.loader_id} points at unknown port: {loader.location_id}"
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
        for haul_arc in self.haul_arcs:
            if haul_arc.yard_id not in yard_ids:
                raise ValueError(f"HaulArc references unknown yard_id={haul_arc.yard_id}")
            if haul_arc.truck_type_id not in truck_type_ids:
                raise ValueError(
                    f"HaulArc references unknown truck_type_id={haul_arc.truck_type_id}"
                )
            arc_key = (haul_arc.block_id, haul_arc.yard_id, haul_arc.truck_type_id)
            if arc_key in seen_arcs:
                raise ValueError(
                    "HaulArc lists the same block/yard/truck-type triple more than once: "
                    f"{haul_arc.block_id}/{haul_arc.yard_id}/{haul_arc.truck_type_id}"
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

    def barge_type_ids(self) -> set[str]:
        """Return the set of barge-type identifiers."""
        return {barge_type.id for barge_type in self.barge_types}

    def barge_ids(self) -> set[str]:
        """Return the set of barge identifiers."""
        return {barge.id for barge in self.barges}

    def port_ids(self) -> set[str]:
        """Return the set of port identifiers."""
        return {port.id for port in self.ports}

    def marine_route_ids(self) -> set[str]:
        """Return the set of marine-route identifiers."""
        return {route.id for route in self.marine_routes}

    def marine_route(self, route_id: str) -> MarineRoute:
        """Return a marine route by id.

        Raises
        ------
        KeyError
            When ``route_id`` is not defined.
        """
        return next(route for route in self.marine_routes if route.id == route_id)

    def water_arc(self, water_arc_id: str) -> WaterArc:
        """Return a water arc by id.

        Raises
        ------
        KeyError
            When ``water_arc_id`` is not defined.
        """
        return next(arc for arc in self.water_arcs if arc.id == water_arc_id)

    def barge_type(self, barge_type_id: str) -> BargeType:
        """Return a barge type by id.

        Raises
        ------
        KeyError
            When ``barge_type_id`` is not defined.
        """
        return next(barge_type for barge_type in self.barge_types if barge_type.id == barge_type_id)

    def port(self, port_id: str) -> Port:
        """Return a port by id.

        Raises
        ------
        KeyError
            When ``port_id`` is not defined.
        """
        return next(port for port in self.ports if port.id == port_id)

    def port_leg_for(
        self,
        route: MarineRoute,
        side: PortSide,
    ) -> PortLeg | None:
        """Return the drayage leg for one side of a marine route, if configured."""
        return self._port_leg_for(route, side)

    def _port_leg_for(self, route: MarineRoute, side: PortSide) -> PortLeg | None:
        """Return a route's drayage leg for one side."""
        port_id = route.origin_port_id if side is PortSide.ORIGIN else route.destination_port_id
        location_id = route.block_id if side is PortSide.ORIGIN else route.yard_id
        return next(
            (
                leg
                for leg in self.port_legs
                if leg.port_id == port_id
                and leg.location_id == location_id
                and leg.side is side
                and leg.truck_type_id == route.truck_type_id
            ),
            None,
        )

    def barges_for(self, contractor_id: str, barge_type_id: str) -> list[Barge]:
        """Return enabled barges of one contractor and type."""
        return [
            barge
            for barge in self.barges
            if barge.enabled
            and barge.contractor_id == contractor_id
            and barge.barge_type_id == barge_type_id
        ]

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
            if (
                loader.location_kind is LoaderLocationKind.PORT
                and loader.location_id not in self.port_ids()
            ):
                raise ValueError(
                    f"Port loader {loader.loader_id} points at unknown port: {loader.location_id}"
                )
        for leg in self.depot_legs:
            if (
                leg.location_id not in block_ids
                and leg.location_id not in self.yard_ids()
                and leg.location_id not in self.port_ids()
            ):
                raise ValueError(
                    f"DepotLeg location_id={leg.location_id} is neither a block, a yard, nor a port"
                )
        for port_leg in self.port_legs:
            if port_leg.side is PortSide.ORIGIN:
                if port_leg.location_id not in block_ids:
                    raise ValueError(
                        f"Origin PortLeg references unknown block_id={port_leg.location_id}"
                    )
            elif port_leg.location_id not in self.yard_ids():
                raise ValueError(
                    f"Destination PortLeg references unknown yard_id={port_leg.location_id}"
                )
        for route in self.marine_routes:
            if route.block_id not in block_ids:
                raise ValueError(
                    f"MarineRoute {route.id} references unknown block_id={route.block_id}"
                )
            if route.yard_id not in self.yard_ids():
                raise ValueError(
                    f"MarineRoute {route.id} references unknown yard_id={route.yard_id}"
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
    "Barge",
    "BargeType",
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
    "MarineRoute",
    "Port",
    "PortLeg",
    "PortSide",
    "SortYard",
    "TransportMode",
    "Truck",
    "TruckType",
    "WaterArc",
]
