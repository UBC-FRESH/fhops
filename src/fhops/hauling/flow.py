"""Phase I monthly flow model for operational log hauling.

This module implements the first phase of Ghotb's decomposition: a bi-objective mixed-integer
program for daily sorted and unsorted log flows from blocks to sort yards, with yard processing,
inventory, contractor compatibility, fleet capacity, and contractor workload balance. The
bi-objective model is solved by goal programming.

The formulation is documented in ``notes/hauling_formulation_audit.md`` (equations 3-1 to 3-23).
The implementation deliberately tightens the thesis in three places:

- compatibility is enforced by index restriction instead of a big-M;
- the absolute workload deviation is linearised with two inequalities;
- goal deviations are non-negative continuous variables (the thesis/paper disagree on which one is
  integer).

The model is built from a validated :class:`fhops.scenario.contract.Scenario` with a ``hauling:``
section. It does not import or modify the operational or tactical MILPs.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyomo.environ as pyo
from pyomo.contrib.solver.common.util import NoFeasibleSolutionError
from pyomo.opt import SolverFactory

from fhops.hauling.contract import HaulingConfig, LoaderLocationKind, PortSide

if TYPE_CHECKING:
    from fhops.scenario.contract import Scenario

__all__ = [
    "FlowSolveResult",
    "HaulingFlowProblem",
    "MarineLane",
    "build_flow_model",
    "build_flow_problem",
    "solve_flow",
    "summarize_flow_result",
]

Day = int
Key5 = tuple[str, str, str, str, int]
Key6 = tuple[str, str, str, str, str, int]

_FLOW_COLUMNS = [
    "day",
    "scenario_day",
    "block_id",
    "yard_id",
    "log_sort_id",
    "contractor_id",
    "truck_type_id",
    "sorted_m3",
    "unsorted_m3",
]
_TRUCKLOAD_COLUMNS = [
    "day",
    "scenario_day",
    "block_id",
    "yard_id",
    "contractor_id",
    "truck_type_id",
    "sorted_truckloads",
    "unsorted_truckloads",
    "total_truckloads",
]
_INVENTORY_COLUMNS = [
    "day",
    "scenario_day",
    "yard_id",
    "log_sort_id",
    "unsorted_inventory_m3",
    "water_inventory_m3",
    "processed_m3",
    "demand_m3",
]
_BLOCK_INVENTORY_COLUMNS = [
    "block_id",
    "log_sort_id",
    "sorted_inventory_m3",
    "unsorted_inventory_m3",
]
_WORKLOAD_COLUMNS = [
    "day",
    "scenario_day",
    "contractor_id",
    "truckloads",
    "preferred_truckloads",
    "deviation",
]
_MARINE_FLOW_COLUMNS = [
    "day",
    "scenario_day",
    "arrival_day",
    "arrival_scenario_day",
    "marine_route_id",
    "block_id",
    "yard_id",
    "log_sort_id",
    "contractor_id",
    "truck_type_id",
    "barge_type_id",
    "origin_port_id",
    "destination_port_id",
    "water_arc_id",
    "sorted",
    "pickup_road_m3",
    "water_m3",
    "delivery_road_m3",
    "pickup_truckloads",
    "delivery_truckloads",
    "barge_trips",
    "origin_handling_m3",
    "destination_handling_m3",
    "barge_load_minutes",
    "barge_unload_minutes",
    "sail_minutes",
    "barge_cycle_minutes",
    "origin_handling_cost",
    "destination_handling_cost",
    "barge_variable_cost",
    "drayage_cost",
    "total_cost",
]
_BARGE_TRIP_COLUMNS = [
    "day",
    "scenario_day",
    "marine_route_id",
    "contractor_id",
    "truck_type_id",
    "barge_type_id",
    "origin_port_id",
    "destination_port_id",
    "water_arc_id",
    "water_m3",
    "barge_trips",
    "arrival_day",
    "arrival_scenario_day",
    "transit_days",
    "occupancy_days",
    "barge_cycle_minutes",
    "barge_load_minutes",
    "barge_unload_minutes",
    "sail_minutes",
    "origin_handling_minutes",
    "destination_handling_minutes",
    "origin_handling_cost",
    "destination_handling_cost",
    "barge_variable_cost",
    "handling_cost",
    "total_cost",
]
_PORT_INVENTORY_COLUMNS = [
    "day",
    "scenario_day",
    "port_id",
    "log_sort_id",
    "opening_inventory_m3",
    "inbound_m3",
    "outbound_m3",
    "inventory_m3",
    "handled_m3",
]
_MARINE_TRUCKLOAD_COLUMNS = [
    "day",
    "scenario_day",
    "marine_route_id",
    "leg",
    "block_id",
    "yard_id",
    "contractor_id",
    "truck_type_id",
    "sorted_truckloads",
    "unsorted_truckloads",
    "total_truckloads",
]


@dataclass(frozen=True, slots=True)
class MarineLane:
    """Normalised Phase I data for one marine route.

    A lane bundles the road pickup leg, the water leg, terminal handling at both ports, and the road
    delivery leg. The Phase I model treats the lane as an alternative supply path from a block to a
    yard, while still reporting the three physical legs separately.

    Attributes
    ----------
    route_id:
        Marine-route identifier.
    block_id / yard_id:
        Pickup block and delivery sort yard.
    origin_port_id / destination_port_id:
        Loading and unloading ports.
    contractor_id / truck_type_id:
        Contractor and road truck type for the drayage legs.
    barge_type_id / water_arc_id:
        Barge equipment and sailing arc.
    pickup_travel_minutes / pickup_return_minutes:
        Loaded and empty road times between the block and the origin port.
    delivery_travel_minutes / delivery_return_minutes:
        Loaded and empty road times between the destination port and the yard.
    water_travel_minutes / water_return_minutes:
        Loaded and empty sailing times.
    load_minutes / unload_minutes:
        Barge loading and unloading service times.
    origin_handling_minutes / destination_handling_minutes:
        Terminal handling time at each port.
    origin_handling_cost / destination_handling_cost:
        Terminal handling cost per barge trip at each port.
    barge_capacity / truck_capacity:
        Cargo capacities in cubic metres.
    barge_cycle_minutes:
        Round-trip barge time including loading, unloading, and terminal handling.
    arrival_lag_days:
        Whole-day lag between a departure and cargo arrival at the destination.
        ``0`` means same-day delivery.
    occupancy_days:
        Whole days a barge is occupied by the round trip. Used by the
        sliding-window fleet constraint.
    pickup_cycle_minutes / delivery_cycle_minutes:
        Round-trip drayage truck time on each side.
    barge_cost_per_trip:
        Variable barge cost plus terminal handling cost for one trip.
    pickup_drayage_cost_per_m3 / delivery_drayage_cost_per_m3:
        Road truck variable cost per cubic metre on each drayage leg.
    drayage_cost_per_m3:
        Sum of the pickup and delivery drayage rates, kept for reporting.
    can_carry_sorted / can_carry_unsorted:
        Barge-type compatibility flags.
    """

    route_id: str
    block_id: str
    yard_id: str
    origin_port_id: str
    destination_port_id: str
    contractor_id: str
    truck_type_id: str
    barge_type_id: str
    water_arc_id: str
    pickup_travel_minutes: float
    pickup_return_minutes: float
    delivery_travel_minutes: float
    delivery_return_minutes: float
    water_travel_minutes: float
    water_return_minutes: float
    load_minutes: float
    unload_minutes: float
    origin_handling_minutes: float
    destination_handling_minutes: float
    origin_handling_cost: float
    destination_handling_cost: float
    barge_capacity: float
    truck_capacity: float
    barge_cycle_minutes: float
    arrival_lag_days: int
    occupancy_days: int
    pickup_cycle_minutes: float
    delivery_cycle_minutes: float
    barge_cost_per_trip: float
    pickup_drayage_cost_per_m3: float
    delivery_drayage_cost_per_m3: float
    drayage_cost_per_m3: float
    can_carry_sorted: bool
    can_carry_unsorted: bool


@dataclass(frozen=True, slots=True)
class HaulingFlowProblem:
    """Normalised Phase I data derived from a scenario's hauling section.

    Attributes
    ----------
    scenario_name:
        Parent scenario name.
    start_day:
        One-indexed parent-scenario day where the hauling horizon starts.
    horizon_days:
        Number of days in the Phase I horizon.
    days:
        Relative days ``1..horizon_days``.
    blocks / yards / sorts / truck_types / contractors:
        Ordered entity identifiers.
    supply_sorted / supply_unsorted:
        ``(block_id, log_sort_id) -> m3``. Zero-supply pairs are omitted.
    demand:
        ``(yard_id, log_sort_id, relative_day) -> m3``. Missing pairs are zero.
    cycle_minutes:
        ``(block_id, yard_id, truck_type_id) ->`` round-trip plus loading/unloading minutes.
    transport_cost:
        ``(block_id, yard_id, truck_type_id) ->`` cost per started truckload.
    capacity:
        ``truck_type_id -> m3``.
    fleet_count:
        ``(contractor_id, truck_type_id) ->`` number of enabled trucks.
    preferred:
        ``contractor_id ->`` preferred daily truckloads (``None`` when not supplied).
    contractor_block_allowlist:
        Allowed ``(contractor_id, block_id)`` pairs. Empty means every contractor may serve every
        block.
    can_carry_sorted / can_carry_unsorted:
        Truck-type flags.
    yard_storage / yard_sorted_capacity / yard_unsorted_capacity / yard_total_capacity:
        ``yard_id ->`` capacity.
    initial_unsorted / initial_water:
        ``(yard_id, log_sort_id) ->`` opening inventory.
    regular_minutes:
        Regular truck minutes per day.
    roadside_penalty:
        Cost per m3 left at a block at the end of the horizon.
    default_service_minutes:
        Fallback loader service time.
    pickup_service / delivery_service:
        ``location_id ->`` service minutes.
    marine_lanes:
        ``route_id -> MarineLane``. Empty for a road-only problem.
    marine_ports / marine_port_storage / marine_port_initial / marine_port_daily_handling:
        Port ids and their storage, opening inventory, and optional daily handling caps.
    marine_barge_fleet:
        ``(contractor_id, barge_type_id) ->`` number of enabled barges.
    port_inventory_penalty:
        Cost per m3 left at a port at the end of the horizon.
    """

    scenario_name: str
    start_day: int
    horizon_days: int
    days: tuple[int, ...]
    blocks: tuple[str, ...]
    yards: tuple[str, ...]
    sorts: tuple[str, ...]
    truck_types: tuple[str, ...]
    contractors: tuple[str, ...]
    supply_sorted: dict[tuple[str, str], float]
    supply_unsorted: dict[tuple[str, str], float]
    demand: dict[tuple[str, str, int], float]
    cycle_minutes: dict[tuple[str, str, str], float]
    transport_cost: dict[tuple[str, str, str], float]
    capacity: dict[str, float]
    fleet_count: dict[tuple[str, str], int]
    preferred: dict[str, float | None]
    contractor_block_allowlist: frozenset[tuple[str, str]]
    can_carry_sorted: dict[str, bool]
    can_carry_unsorted: dict[str, bool]
    yard_storage: dict[str, float]
    yard_sorted_capacity: dict[str, float]
    yard_unsorted_capacity: dict[str, float]
    yard_total_capacity: dict[str, float]
    initial_unsorted: dict[tuple[str, str], float]
    initial_water: dict[tuple[str, str], float]
    regular_minutes: float
    roadside_penalty: float
    default_service_minutes: float
    pickup_service: dict[str, float]
    delivery_service: dict[str, float]
    marine_lanes: dict[str, MarineLane] = field(default_factory=dict)
    marine_ports: tuple[str, ...] = ()
    marine_port_storage: dict[str, float] = field(default_factory=dict)
    marine_port_initial: dict[tuple[str, str], float] = field(default_factory=dict)
    marine_port_daily_handling: dict[str, float | None] = field(default_factory=dict)
    marine_barge_fleet: dict[tuple[str, str], int] = field(default_factory=dict)
    port_inventory_penalty: float = 0.0

    def marine_routes(self) -> tuple[MarineLane, ...]:
        """Return marine lanes in route-id order."""
        return tuple(self.marine_lanes[route_id] for route_id in sorted(self.marine_lanes))

    def has_marine(self) -> bool:
        """Return whether the problem contains any marine routes."""
        return bool(self.marine_lanes)

    def contractor_can_serve(self, contractor_id: str, block_id: str) -> bool:
        """Return whether a contractor may serve a block under the allowlist rule."""
        if not self.contractor_block_allowlist:
            return True
        return (contractor_id, block_id) in self.contractor_block_allowlist

    def demand_for(self, yard_id: str, log_sort_id: str, day: int) -> float:
        """Return demand for one yard/sort/day (zero when absent)."""
        return self.demand.get((yard_id, log_sort_id, day), 0.0)


@dataclass(slots=True)
class FlowSolveResult:
    """Result payload for a Phase I solve.

    Attributes
    ----------
    status:
        ``optimal``, ``feasible``, ``infeasible``, ``unbounded``, or ``error``.
    objective:
        Value of the objective that was actually solved (cost, workload, or the normalized goal
        objective).
    cost_objective:
        Value of Ghotb's ``Z1`` at the returned solution.
    workload_objective:
        Value of Ghotb's ``Z2`` at the returned solution.
    goal_deviations:
        ``cost`` and ``workload`` positive deviations when a goal-programming solve ran.
    goal1 / goal2:
        Goals used by the goal-programming solve.
    preferred_truckloads:
        Preferred daily truckloads used for the workload objective.
    flows / truckloads / yard_inventory / block_inventory / contractor_workload:
        DataFrames with the documented schemas.
    marine_flows / barge_trips / port_inventory / marine_truckloads:
        Marine-leg volume, barge trip, terminal inventory, and drayage truckload tables. They are
        empty for road-only scenarios.
    solver / termination / runtime_seconds / gap / solver_error:
        Solver provenance and diagnostics.
    """

    status: str
    objective: float | None
    cost_objective: float | None
    workload_objective: float | None
    goal_deviations: dict[str, float] = field(default_factory=dict)
    goal1: float | None = None
    goal2: float | None = None
    preferred_truckloads: dict[str, float] = field(default_factory=dict)
    flows: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=_FLOW_COLUMNS))
    truckloads: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_TRUCKLOAD_COLUMNS)
    )
    yard_inventory: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_INVENTORY_COLUMNS)
    )
    block_inventory: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_BLOCK_INVENTORY_COLUMNS)
    )
    contractor_workload: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_WORKLOAD_COLUMNS)
    )
    marine_flows: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_MARINE_FLOW_COLUMNS)
    )
    barge_trips: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_BARGE_TRIP_COLUMNS)
    )
    port_inventory: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_PORT_INVENTORY_COLUMNS)
    )
    marine_truckloads: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_MARINE_TRUCKLOAD_COLUMNS)
    )
    solver: str = "highs"
    termination: str = ""
    runtime_seconds: float = 0.0
    gap: float | None = None
    solver_error: str | None = None


def build_flow_problem(scenario: Scenario) -> HaulingFlowProblem:
    """Build a :class:`HaulingFlowProblem` from a validated scenario.

    Parameters
    ----------
    scenario:
        Scenario with a non-``None`` ``hauling`` section.

    Returns
    -------
    HaulingFlowProblem
        Normalised data ready for :func:`build_flow_model` and :func:`solve_flow`.

    Raises
    ------
    ValueError
        When the scenario has no hauling section, or a supply/demand/arc combination cannot be
        represented by the contract.
    """
    config = scenario.hauling
    if config is None:
        raise ValueError("Scenario has no hauling section")

    blocks = tuple(block.id for block in scenario.blocks)
    yards = tuple(yard.id for yard in config.sort_yards)
    sorts = tuple(sort.id for sort in config.log_sorts)
    truck_types = tuple(truck_type.id for truck_type in config.truck_types)
    contractors = tuple(contractor.id for contractor in config.contractors)
    days = tuple(range(1, config.planning_horizon_days + 1))

    supply_sorted = {
        (row.block_id, row.log_sort_id): row.sorted_m3 for row in config.supply if row.sorted_m3 > 0
    }
    supply_unsorted = {
        (row.block_id, row.log_sort_id): row.unsorted_m3
        for row in config.supply
        if row.unsorted_m3 > 0
    }
    demand = {
        (row.yard_id, row.log_sort_id, row.day): row.volume_m3
        for row in config.demand
        if row.volume_m3 > 0
    }

    pickup_service = _location_service_minutes(config, LoaderLocationKind.PICKUP)
    delivery_service = _location_service_minutes(config, LoaderLocationKind.DELIVERY)

    cycle_minutes: dict[tuple[str, str, str], float] = {}
    transport_cost: dict[tuple[str, str, str], float] = {}
    capacity: dict[str, float] = {
        truck_type.id: truck_type.capacity_m3 for truck_type in config.truck_types
    }
    for arc in config.haul_arcs:
        pickup = pickup_service.get(arc.block_id, config.default_loader_service_minutes)
        delivery = delivery_service.get(arc.yard_id, config.default_loader_service_minutes)
        cycle = 2.0 * arc.travel_minutes + pickup + delivery
        key = (arc.block_id, arc.yard_id, arc.truck_type_id)
        cycle_minutes[key] = cycle
        truck_type = _truck_type_by_id(config, arc.truck_type_id)
        transport_cost[key] = truck_type.variable_cost_per_minute * cycle

    fleet_count: dict[tuple[str, str], int] = {}
    for truck in config.trucks:
        if not truck.enabled:
            continue
        truck_key = (truck.contractor_id, truck.truck_type_id)
        fleet_count[truck_key] = fleet_count.get(truck_key, 0) + 1

    (
        marine_lanes,
        marine_ports,
        marine_port_storage,
        marine_port_initial,
        marine_port_daily_handling,
        marine_barge_fleet,
    ) = _build_marine_lanes(config, sorts)

    preferred = {
        contractor.id: contractor.preferred_daily_truckloads for contractor in config.contractors
    }
    allowlist = frozenset((rule.contractor_id, rule.block_id) for rule in config.contractor_blocks)

    yard_storage = {yard.id: yard.unsorted_storage_m3 for yard in config.sort_yards}
    yard_sorted_capacity = {
        yard.id: yard.sorted_processing_m3_per_day for yard in config.sort_yards
    }
    yard_unsorted_capacity = {
        yard.id: yard.unsorted_processing_m3_per_day for yard in config.sort_yards
    }
    yard_total_capacity = {yard.id: yard.total_processing_m3_per_day for yard in config.sort_yards}
    initial_unsorted = {
        (yard.id, sort_id): yard.initial_unsorted_inventory_m3
        for yard in config.sort_yards
        for sort_id in sorts
    }
    initial_water = {
        (yard.id, sort_id): yard.initial_water_inventory_m3
        for yard in config.sort_yards
        for sort_id in sorts
    }

    return HaulingFlowProblem(
        scenario_name=scenario.name,
        start_day=config.start_day,
        horizon_days=config.planning_horizon_days,
        days=days,
        blocks=blocks,
        yards=yards,
        sorts=sorts,
        truck_types=truck_types,
        contractors=contractors,
        supply_sorted=supply_sorted,
        supply_unsorted=supply_unsorted,
        demand=demand,
        cycle_minutes=cycle_minutes,
        transport_cost=transport_cost,
        capacity=capacity,
        fleet_count=fleet_count,
        preferred=preferred,
        contractor_block_allowlist=allowlist,
        can_carry_sorted={
            truck_type.id: truck_type.can_carry_sorted for truck_type in config.truck_types
        },
        can_carry_unsorted={
            truck_type.id: truck_type.can_carry_unsorted for truck_type in config.truck_types
        },
        yard_storage=yard_storage,
        yard_sorted_capacity=yard_sorted_capacity,
        yard_unsorted_capacity=yard_unsorted_capacity,
        yard_total_capacity=yard_total_capacity,
        initial_unsorted=initial_unsorted,
        initial_water=initial_water,
        regular_minutes=config.driver_policy.regular_minutes,
        roadside_penalty=config.roadside_inventory_penalty_per_m3,
        default_service_minutes=config.default_loader_service_minutes,
        pickup_service=pickup_service,
        delivery_service=delivery_service,
        marine_lanes=marine_lanes,
        marine_ports=marine_ports,
        marine_port_storage=marine_port_storage,
        marine_port_initial=marine_port_initial,
        marine_port_daily_handling=marine_port_daily_handling,
        marine_barge_fleet=marine_barge_fleet,
        port_inventory_penalty=config.port_inventory_penalty_per_m3,
    )


def _build_marine_lanes(
    config: HaulingConfig,
    sorts: tuple[str, ...],
) -> tuple[
    dict[str, MarineLane],
    tuple[str, ...],
    dict[str, float],
    dict[tuple[str, str], float],
    dict[str, float | None],
    dict[tuple[str, str], int],
]:
    """Build normalised marine lanes and port data from the contract."""
    lanes: dict[str, MarineLane] = {}
    ports = tuple(port.id for port in config.ports)
    port_storage = {port.id: port.storage_m3 for port in config.ports}
    port_initial = {
        (port.id, sort_id): port.initial_inventory_m3 for port in config.ports for sort_id in sorts
    }
    port_daily_handling = {port.id: port.daily_handling_m3 for port in config.ports}
    barge_fleet: dict[tuple[str, str], int] = {}
    for barge in config.barges:
        if not barge.enabled:
            continue
        key = (barge.contractor_id, barge.barge_type_id)
        barge_fleet[key] = barge_fleet.get(key, 0) + 1

    truck_types = {truck_type.id: truck_type for truck_type in config.truck_types}
    for route in config.marine_routes:
        water_arc = config.water_arc(route.water_arc_id)
        barge_type = config.barge_type(water_arc.barge_type_id)
        origin_port = config.port(route.origin_port_id)
        destination_port = config.port(route.destination_port_id)
        origin_leg = config.port_leg_for(route, PortSide.ORIGIN)
        destination_leg = config.port_leg_for(route, PortSide.DESTINATION)
        if origin_leg is None or destination_leg is None:
            raise ValueError(f"MarineRoute {route.id} is missing an origin or destination PortLeg")
        truck_type = truck_types[route.truck_type_id]
        load_minutes = (
            water_arc.load_minutes
            if water_arc.load_minutes is not None
            else barge_type.load_minutes
        )
        unload_minutes = (
            water_arc.unload_minutes
            if water_arc.unload_minutes is not None
            else barge_type.unload_minutes
        )
        barge_cycle = (
            water_arc.travel_minutes
            + water_arc.empty_travel_minutes()
            + load_minutes
            + unload_minutes
            + origin_port.handling_minutes_per_trip
            + destination_port.handling_minutes_per_trip
        )
        transit_minutes = (
            water_arc.travel_minutes + unload_minutes + destination_port.handling_minutes_per_trip
        )
        regular_minutes = config.driver_policy.regular_minutes
        arrival_lag_days = (
            0
            if transit_minutes <= regular_minutes
            else math.ceil(transit_minutes / regular_minutes)
        )
        occupancy_days = max(1, math.ceil(barge_cycle / regular_minutes))
        pickup_cycle = origin_leg.travel_minutes + origin_leg.empty_travel_minutes()
        delivery_cycle = destination_leg.travel_minutes + destination_leg.empty_travel_minutes()
        barge_cost = (
            barge_type.variable_cost_per_minute * barge_cycle
            + origin_port.handling_cost_per_trip
            + destination_port.handling_cost_per_trip
        )
        pickup_drayage_cost = (
            truck_type.variable_cost_per_minute * pickup_cycle
        ) / truck_type.capacity_m3
        delivery_drayage_cost = (
            truck_type.variable_cost_per_minute * delivery_cycle
        ) / truck_type.capacity_m3
        drayage_cost = pickup_drayage_cost + delivery_drayage_cost
        lanes[route.id] = MarineLane(
            route_id=route.id,
            block_id=route.block_id,
            yard_id=route.yard_id,
            origin_port_id=route.origin_port_id,
            destination_port_id=route.destination_port_id,
            contractor_id=route.contractor_id,
            truck_type_id=route.truck_type_id,
            barge_type_id=barge_type.id,
            water_arc_id=water_arc.id,
            pickup_travel_minutes=origin_leg.travel_minutes,
            pickup_return_minutes=origin_leg.empty_travel_minutes(),
            delivery_travel_minutes=destination_leg.travel_minutes,
            delivery_return_minutes=destination_leg.empty_travel_minutes(),
            water_travel_minutes=water_arc.travel_minutes,
            water_return_minutes=water_arc.empty_travel_minutes(),
            load_minutes=load_minutes,
            unload_minutes=unload_minutes,
            origin_handling_minutes=origin_port.handling_minutes_per_trip,
            destination_handling_minutes=destination_port.handling_minutes_per_trip,
            origin_handling_cost=origin_port.handling_cost_per_trip,
            destination_handling_cost=destination_port.handling_cost_per_trip,
            barge_capacity=barge_type.capacity_m3,
            truck_capacity=truck_type.capacity_m3,
            barge_cycle_minutes=barge_cycle,
            arrival_lag_days=arrival_lag_days,
            occupancy_days=occupancy_days,
            pickup_cycle_minutes=pickup_cycle,
            delivery_cycle_minutes=delivery_cycle,
            barge_cost_per_trip=barge_cost,
            pickup_drayage_cost_per_m3=pickup_drayage_cost,
            delivery_drayage_cost_per_m3=delivery_drayage_cost,
            drayage_cost_per_m3=drayage_cost,
            can_carry_sorted=barge_type.can_carry_sorted,
            can_carry_unsorted=barge_type.can_carry_unsorted,
        )
    return (
        lanes,
        ports,
        port_storage,
        port_initial,
        port_daily_handling,
        barge_fleet,
    )


def _truck_type_by_id(config: HaulingConfig, truck_type_id: str):  # noqa: ANN202
    """Return a truck type by id (the contract guarantees it exists)."""
    return next(item for item in config.truck_types if item.id == truck_type_id)


def _location_service_minutes(
    config: HaulingConfig,
    kind: LoaderLocationKind,
) -> dict[str, float]:
    """Return the fastest configured service time per pickup/delivery location."""
    service: dict[str, float] = {}
    for loader in config.loader_locations:
        if loader.location_kind is not kind:
            continue
        minutes = loader.service_minutes or config.default_loader_service_minutes
        current = service.get(loader.location_id)
        service[loader.location_id] = minutes if current is None else min(current, minutes)
    return service


def build_flow_model(
    problem: HaulingFlowProblem,
    *,
    objective: str = "cost",
    preferred: dict[str, float] | None = None,
    goals: tuple[float, float] | None = None,
    weights: tuple[float, float] = (1.0, 1.0),
) -> pyo.ConcreteModel:
    """Build the Phase I Pyomo model.

    Parameters
    ----------
    problem:
        Normalised hauling data.
    objective:
        ``"cost"`` (Ghotb's ``Z1``), ``"workload"`` (``Z2``), or ``"goal"`` (goal programming).
    preferred:
        Preferred daily truckloads per contractor. ``None`` uses 0 for the workload constraint;
        :func:`solve_flow` derives values from a cost-only solve when needed.
    goals:
        ``(Goal1, Goal2)`` for the goal-programming objective. Required when ``objective="goal"``
        unless :func:`solve_flow` derives them.
    weights:
        ``(w1, w2)`` goal weights. Must be non-negative and not both zero when
        ``objective="goal"``.

    Returns
    -------
    pyomo.ConcreteModel
        Model with ``cost_expr``, ``workload_expr``, and a single ``objective`` component.

    Raises
    ------
    ValueError
        For an unknown objective or invalid goal weights/goals.
    """
    if objective not in {"cost", "workload", "goal"}:
        raise ValueError("objective must be 'cost', 'workload', or 'goal'")
    if objective == "goal":
        if goals is None:
            raise ValueError("goals are required for objective='goal'")
        if any(weight < 0 for weight in weights) or sum(weights) == 0:
            raise ValueError("goal weights must be non-negative and not both zero")

    phi = {contractor: 0.0 for contractor in problem.contractors}
    if preferred is not None:
        phi.update(
            {contractor: preferred.get(contractor, 0.0) for contractor in problem.contractors}
        )

    model = pyo.ConcreteModel(name=f"hauling-flow-{problem.scenario_name}")
    model.problem = problem

    sorted_supply_keys = sorted(problem.supply_sorted)
    unsorted_supply_keys = sorted(problem.supply_unsorted)
    arc_keys = sorted(problem.cycle_minutes)

    sorted_keys: list[Key6] = []
    unsorted_keys: list[Key6] = []
    sorted_by_supply: dict[tuple[str, str], list[Key6]] = {}
    unsorted_by_supply: dict[tuple[str, str], list[Key6]] = {}
    sorted_by_yard_sort_day: dict[tuple[str, str, int], list[Key6]] = {}
    unsorted_by_yard_sort_day: dict[tuple[str, str, int], list[Key6]] = {}
    sorted_by_yard_day: dict[tuple[str, int], list[Key6]] = {}
    unsorted_by_yard_day: dict[tuple[str, int], list[Key6]] = {}
    sorted_by_contractor_day: dict[tuple[str, int], list[Key6]] = {}
    unsorted_by_contractor_day: dict[tuple[str, int], list[Key6]] = {}
    sorted_by_contractor_truck_day: dict[tuple[str, str, int], list[Key6]] = {}
    unsorted_by_contractor_truck_day: dict[tuple[str, str, int], list[Key6]] = {}

    for block_id, yard_id, truck_type_id in arc_keys:
        if not problem.can_carry_sorted[truck_type_id]:
            continue
        for contractor_id in problem.contractors:
            if not problem.contractor_can_serve(contractor_id, block_id):
                continue
            if problem.fleet_count.get((contractor_id, truck_type_id), 0) <= 0:
                continue
            for sort_id in problem.sorts:
                if (block_id, sort_id) not in problem.supply_sorted:
                    continue
                for day in problem.days:
                    key = (block_id, yard_id, sort_id, contractor_id, truck_type_id, day)
                    sorted_keys.append(key)
                    sorted_by_supply.setdefault((block_id, sort_id), []).append(key)
                    sorted_by_yard_sort_day.setdefault((yard_id, sort_id, day), []).append(key)
                    sorted_by_yard_day.setdefault((yard_id, day), []).append(key)
                    sorted_by_contractor_day.setdefault((contractor_id, day), []).append(key)
                    sorted_by_contractor_truck_day.setdefault(
                        (contractor_id, truck_type_id, day), []
                    ).append(key)

    for block_id, yard_id, truck_type_id in arc_keys:
        if not problem.can_carry_unsorted[truck_type_id]:
            continue
        for contractor_id in problem.contractors:
            if not problem.contractor_can_serve(contractor_id, block_id):
                continue
            if problem.fleet_count.get((contractor_id, truck_type_id), 0) <= 0:
                continue
            for sort_id in problem.sorts:
                if (block_id, sort_id) not in problem.supply_unsorted:
                    continue
                for day in problem.days:
                    key = (block_id, yard_id, sort_id, contractor_id, truck_type_id, day)
                    unsorted_keys.append(key)
                    unsorted_by_supply.setdefault((block_id, sort_id), []).append(key)
                    unsorted_by_yard_sort_day.setdefault((yard_id, sort_id, day), []).append(key)
                    unsorted_by_yard_day.setdefault((yard_id, day), []).append(key)
                    unsorted_by_contractor_day.setdefault((contractor_id, day), []).append(key)
                    unsorted_by_contractor_truck_day.setdefault(
                        (contractor_id, truck_type_id, day), []
                    ).append(key)

    unsorted_load_keys: list[Key5] = []
    unsorted_volume_keys_by_load: dict[Key5, list[Key6]] = {}
    for key in unsorted_keys:
        block_id, yard_id, _sort_id, contractor_id, truck_type_id, day = key
        load_key = (block_id, yard_id, contractor_id, truck_type_id, day)
        if load_key not in unsorted_volume_keys_by_load:
            unsorted_volume_keys_by_load[load_key] = []
            unsorted_load_keys.append(load_key)
        unsorted_volume_keys_by_load[load_key].append(key)

    marine_sorted_keys: list[tuple[str, str, int]] = []
    marine_unsorted_keys: list[tuple[str, str, int]] = []
    marine_pickup_sorted_by_supply: dict[tuple[str, str], list[tuple[str, str, int]]] = {}
    marine_pickup_unsorted_by_supply: dict[tuple[str, str], list[tuple[str, str, int]]] = {}
    marine_delivery_sorted_by_yard_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_delivery_unsorted_by_yard_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_water_by_route_day: dict[tuple[str, int], list[tuple[str, str, int]]] = {}
    marine_pickup_by_port_sort_day: dict[tuple[str, str, int], list[tuple[str, str, int]]] = {}
    marine_water_out_by_port_sort_day: dict[tuple[str, str, int], list[tuple[str, str, int]]] = {}
    marine_water_in_by_port_sort_day: dict[tuple[str, str, int], list[tuple[str, str, int]]] = {}
    marine_delivery_by_port_sort_day: dict[tuple[str, str, int], list[tuple[str, str, int]]] = {}
    marine_pickup_sorted_by_port_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_pickup_unsorted_by_port_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_water_out_sorted_by_port_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_water_out_unsorted_by_port_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_water_in_sorted_by_port_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_water_in_unsorted_by_port_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_delivery_sorted_by_port_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_delivery_unsorted_by_port_sort_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_sorted_by_contractor_day: dict[tuple[str, int], list[tuple[str, str, int]]] = {}
    marine_unsorted_by_contractor_day: dict[tuple[str, int], list[tuple[str, str, int]]] = {}
    marine_delivery_sorted_by_contractor_day: dict[tuple[str, int], list[tuple[str, str, int]]] = {}
    marine_delivery_unsorted_by_contractor_day: dict[
        tuple[str, int], list[tuple[str, str, int]]
    ] = {}
    marine_by_contractor_truck_day: dict[tuple[str, str, int], list[tuple[str, str, int]]] = {}
    marine_sorted_by_contractor_truck_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_unsorted_by_contractor_truck_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_delivery_sorted_by_contractor_truck_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}
    marine_delivery_unsorted_by_contractor_truck_day: dict[
        tuple[str, str, int], list[tuple[str, str, int]]
    ] = {}

    for route_id in sorted(problem.marine_lanes):
        lane = problem.marine_lanes[route_id]
        if not problem.contractor_can_serve(lane.contractor_id, lane.block_id):
            continue
        if problem.fleet_count.get((lane.contractor_id, lane.truck_type_id), 0) <= 0:
            continue
        for day in problem.days:
            marine_water_by_route_day.setdefault((route_id, day), [])
        for sort_id in problem.sorts:
            if lane.can_carry_sorted and (lane.block_id, sort_id) in problem.supply_sorted:
                for day in problem.days:
                    arrival_day = day + lane.arrival_lag_days
                    if arrival_day > problem.horizon_days:
                        continue
                    marine_key = (route_id, sort_id, day)
                    marine_sorted_keys.append(marine_key)
                    marine_pickup_sorted_by_supply.setdefault((lane.block_id, sort_id), []).append(
                        marine_key
                    )
                    marine_delivery_sorted_by_yard_sort_day.setdefault(
                        (lane.yard_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_water_by_route_day[(route_id, day)].append(marine_key)
                    marine_pickup_by_port_sort_day.setdefault(
                        (lane.origin_port_id, sort_id, day), []
                    ).append(marine_key)
                    marine_pickup_sorted_by_port_sort_day.setdefault(
                        (lane.origin_port_id, sort_id, day), []
                    ).append(marine_key)
                    marine_water_out_by_port_sort_day.setdefault(
                        (lane.origin_port_id, sort_id, day), []
                    ).append(marine_key)
                    marine_water_out_sorted_by_port_sort_day.setdefault(
                        (lane.origin_port_id, sort_id, day), []
                    ).append(marine_key)
                    marine_water_in_by_port_sort_day.setdefault(
                        (lane.destination_port_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_water_in_sorted_by_port_sort_day.setdefault(
                        (lane.destination_port_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_delivery_by_port_sort_day.setdefault(
                        (lane.destination_port_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_delivery_sorted_by_port_sort_day.setdefault(
                        (lane.destination_port_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_sorted_by_contractor_day.setdefault(
                        (lane.contractor_id, day), []
                    ).append(marine_key)
                    marine_by_contractor_truck_day.setdefault(
                        (lane.contractor_id, lane.truck_type_id, day), []
                    ).append(marine_key)
                    marine_sorted_by_contractor_truck_day.setdefault(
                        (lane.contractor_id, lane.truck_type_id, day), []
                    ).append(marine_key)
                    marine_delivery_sorted_by_contractor_day.setdefault(
                        (lane.contractor_id, arrival_day), []
                    ).append(marine_key)
                    marine_delivery_sorted_by_contractor_truck_day.setdefault(
                        (lane.contractor_id, lane.truck_type_id, arrival_day), []
                    ).append(marine_key)
            if lane.can_carry_unsorted and (lane.block_id, sort_id) in problem.supply_unsorted:
                for day in problem.days:
                    arrival_day = day + lane.arrival_lag_days
                    if arrival_day > problem.horizon_days:
                        continue
                    marine_key = (route_id, sort_id, day)
                    marine_unsorted_keys.append(marine_key)
                    marine_pickup_unsorted_by_supply.setdefault(
                        (lane.block_id, sort_id), []
                    ).append(marine_key)
                    marine_delivery_unsorted_by_yard_sort_day.setdefault(
                        (lane.yard_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_water_by_route_day[(route_id, day)].append(marine_key)
                    marine_pickup_by_port_sort_day.setdefault(
                        (lane.origin_port_id, sort_id, day), []
                    ).append(marine_key)
                    marine_pickup_unsorted_by_port_sort_day.setdefault(
                        (lane.origin_port_id, sort_id, day), []
                    ).append(marine_key)
                    marine_water_out_by_port_sort_day.setdefault(
                        (lane.origin_port_id, sort_id, day), []
                    ).append(marine_key)
                    marine_water_out_unsorted_by_port_sort_day.setdefault(
                        (lane.origin_port_id, sort_id, day), []
                    ).append(marine_key)
                    marine_water_in_by_port_sort_day.setdefault(
                        (lane.destination_port_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_water_in_unsorted_by_port_sort_day.setdefault(
                        (lane.destination_port_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_delivery_by_port_sort_day.setdefault(
                        (lane.destination_port_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_delivery_unsorted_by_port_sort_day.setdefault(
                        (lane.destination_port_id, sort_id, arrival_day), []
                    ).append(marine_key)
                    marine_unsorted_by_contractor_day.setdefault(
                        (lane.contractor_id, day), []
                    ).append(marine_key)
                    marine_by_contractor_truck_day.setdefault(
                        (lane.contractor_id, lane.truck_type_id, day), []
                    ).append(marine_key)
                    marine_unsorted_by_contractor_truck_day.setdefault(
                        (lane.contractor_id, lane.truck_type_id, day), []
                    ).append(marine_key)
                    marine_delivery_unsorted_by_contractor_day.setdefault(
                        (lane.contractor_id, arrival_day), []
                    ).append(marine_key)
                    marine_delivery_unsorted_by_contractor_truck_day.setdefault(
                        (lane.contractor_id, lane.truck_type_id, arrival_day), []
                    ).append(marine_key)

    marine_trip_keys = sorted(
        (route_id, day) for route_id in problem.marine_lanes for day in problem.days
    )
    port_sort_day_keys = [
        (port_id, sort_id, day)
        for port_id in problem.marine_ports
        for sort_id in problem.sorts
        for day in problem.days
    ]
    marine_barge_fleet_keys = [
        (contractor_id, barge_type_id, day)
        for contractor_id, barge_type_id in problem.marine_barge_fleet
        for day in problem.days
        if problem.marine_barge_fleet.get((contractor_id, barge_type_id), 0) > 0
    ]

    yard_sort_day_keys = [
        (yard_id, sort_id, day)
        for yard_id in problem.yards
        for sort_id in problem.sorts
        for day in problem.days
    ]
    yard_day_keys = [(yard_id, day) for yard_id in problem.yards for day in problem.days]
    fleet_keys = [
        (contractor_id, truck_type_id, day)
        for contractor_id in problem.contractors
        for truck_type_id in problem.truck_types
        for day in problem.days
        if problem.fleet_count.get((contractor_id, truck_type_id), 0) > 0
    ]
    workload_keys = [
        (contractor_id, day) for contractor_id in problem.contractors for day in problem.days
    ]

    model.SortedKeys = pyo.Set(initialize=sorted_keys, dimen=6)
    model.UnsortedKeys = pyo.Set(initialize=unsorted_keys, dimen=6)
    model.UnsortedLoadKeys = pyo.Set(initialize=unsorted_load_keys, dimen=5)
    model.SortedSupplyKeys = pyo.Set(initialize=sorted_supply_keys, dimen=2)
    model.UnsortedSupplyKeys = pyo.Set(initialize=unsorted_supply_keys, dimen=2)
    model.YardSortDayKeys = pyo.Set(initialize=yard_sort_day_keys, dimen=3)
    model.YardDayKeys = pyo.Set(initialize=yard_day_keys, dimen=2)
    model.FleetKeys = pyo.Set(initialize=fleet_keys, dimen=3)
    model.WorkloadKeys = pyo.Set(initialize=workload_keys, dimen=2)
    model.MarineSortedKeys = pyo.Set(initialize=marine_sorted_keys, dimen=3)
    model.MarineUnsortedKeys = pyo.Set(initialize=marine_unsorted_keys, dimen=3)
    model.MarineTripKeys = pyo.Set(initialize=marine_trip_keys, dimen=2)
    model.PortSortDayKeys = pyo.Set(initialize=port_sort_day_keys, dimen=3)
    model.MarineBargeFleetKeys = pyo.Set(initialize=marine_barge_fleet_keys, dimen=3)

    model.vw = pyo.Var(model.SortedKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.vc = pyo.Var(model.UnsortedKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.nw = pyo.Var(model.SortedKeys, domain=pyo.NonNegativeIntegers, initialize=0)
    model.nc = pyo.Var(model.UnsortedLoadKeys, domain=pyo.NonNegativeIntegers, initialize=0)
    model.ibw = pyo.Var(model.SortedSupplyKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.ibc = pyo.Var(model.UnsortedSupplyKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.ic = pyo.Var(model.YardSortDayKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.iw = pyo.Var(model.YardSortDayKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.pv = pyo.Var(model.YardSortDayKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.u = pyo.Var(model.WorkloadKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.mpw = pyo.Var(model.MarineSortedKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.mpc = pyo.Var(model.MarineUnsortedKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.mww = pyo.Var(model.MarineSortedKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.mwc = pyo.Var(model.MarineUnsortedKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.mdw = pyo.Var(model.MarineSortedKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.mdc = pyo.Var(model.MarineUnsortedKeys, domain=pyo.NonNegativeReals, initialize=0.0)
    model.mt = pyo.Var(model.MarineTripKeys, domain=pyo.NonNegativeIntegers, initialize=0)
    model.pi = pyo.Var(model.PortSortDayKeys, domain=pyo.NonNegativeReals, initialize=0.0)

    def sorted_supply_balance_rule(mdl, block_id: str, sort_id: str):
        return (
            sum(mdl.vw[key] for key in sorted_by_supply.get((block_id, sort_id), []))
            + sum(
                mdl.mpw[key] for key in marine_pickup_sorted_by_supply.get((block_id, sort_id), [])
            )
            + mdl.ibw[block_id, sort_id]
            == problem.supply_sorted[block_id, sort_id]
        )

    model.sorted_supply_balance = pyo.Constraint(
        model.SortedSupplyKeys, rule=sorted_supply_balance_rule
    )

    def unsorted_supply_balance_rule(mdl, block_id: str, sort_id: str):
        return (
            sum(mdl.vc[key] for key in unsorted_by_supply.get((block_id, sort_id), []))
            + sum(
                mdl.mpc[key]
                for key in marine_pickup_unsorted_by_supply.get((block_id, sort_id), [])
            )
            + mdl.ibc[block_id, sort_id]
            == problem.supply_unsorted[block_id, sort_id]
        )

    model.unsorted_supply_balance = pyo.Constraint(
        model.UnsortedSupplyKeys, rule=unsorted_supply_balance_rule
    )

    def sorted_truckload_lower_rule(
        mdl, block_id, yard_id, sort_id, contractor_id, truck_type_id, day
    ):
        capacity = problem.capacity[truck_type_id]
        return (
            mdl.vw[block_id, yard_id, sort_id, contractor_id, truck_type_id, day]
            >= (mdl.nw[block_id, yard_id, sort_id, contractor_id, truck_type_id, day] - 1)
            * capacity
        )

    def sorted_truckload_upper_rule(
        mdl, block_id, yard_id, sort_id, contractor_id, truck_type_id, day
    ):
        capacity = problem.capacity[truck_type_id]
        return mdl.vw[block_id, yard_id, sort_id, contractor_id, truck_type_id, day] <= (
            mdl.nw[block_id, yard_id, sort_id, contractor_id, truck_type_id, day] * capacity
        )

    model.sorted_truckload_lower = pyo.Constraint(
        model.SortedKeys, rule=sorted_truckload_lower_rule
    )
    model.sorted_truckload_upper = pyo.Constraint(
        model.SortedKeys, rule=sorted_truckload_upper_rule
    )

    def unsorted_truckload_lower_rule(mdl, block_id, yard_id, contractor_id, truck_type_id, day):
        capacity = problem.capacity[truck_type_id]
        volume = sum(
            mdl.vc[key]
            for key in unsorted_volume_keys_by_load.get(
                (block_id, yard_id, contractor_id, truck_type_id, day), []
            )
        )
        return (
            volume >= (mdl.nc[block_id, yard_id, contractor_id, truck_type_id, day] - 1) * capacity
        )

    def unsorted_truckload_upper_rule(mdl, block_id, yard_id, contractor_id, truck_type_id, day):
        capacity = problem.capacity[truck_type_id]
        volume = sum(
            mdl.vc[key]
            for key in unsorted_volume_keys_by_load.get(
                (block_id, yard_id, contractor_id, truck_type_id, day), []
            )
        )
        return volume <= (mdl.nc[block_id, yard_id, contractor_id, truck_type_id, day] * capacity)

    model.unsorted_truckload_lower = pyo.Constraint(
        model.UnsortedLoadKeys, rule=unsorted_truckload_lower_rule
    )
    model.unsorted_truckload_upper = pyo.Constraint(
        model.UnsortedLoadKeys, rule=unsorted_truckload_upper_rule
    )

    def workload_lower_rule(mdl, contractor_id: str, day: int):
        loads = _contractor_day_truckloads(
            mdl,
            contractor_id,
            day,
            sorted_by_contractor_day,
            unsorted_by_contractor_day,
            marine_sorted_by_contractor_day,
            marine_unsorted_by_contractor_day,
            marine_delivery_sorted_by_contractor_day,
            marine_delivery_unsorted_by_contractor_day,
            problem,
        )
        return loads - phi[contractor_id] <= mdl.u[contractor_id, day]

    def workload_upper_rule(mdl, contractor_id: str, day: int):
        loads = _contractor_day_truckloads(
            mdl,
            contractor_id,
            day,
            sorted_by_contractor_day,
            unsorted_by_contractor_day,
            marine_sorted_by_contractor_day,
            marine_unsorted_by_contractor_day,
            marine_delivery_sorted_by_contractor_day,
            marine_delivery_unsorted_by_contractor_day,
            problem,
        )
        return phi[contractor_id] - loads <= mdl.u[contractor_id, day]

    model.workload_lower = pyo.Constraint(model.WorkloadKeys, rule=workload_lower_rule)
    model.workload_upper = pyo.Constraint(model.WorkloadKeys, rule=workload_upper_rule)

    def unsorted_inventory_rule(mdl, yard_id: str, sort_id: str, day: int):
        previous = (
            problem.initial_unsorted[(yard_id, sort_id)]
            if day == 1
            else mdl.ic[yard_id, sort_id, day - 1]
        )
        delivered = sum(
            mdl.vc[key] for key in unsorted_by_yard_sort_day.get((yard_id, sort_id, day), [])
        ) + sum(
            mdl.mdc[key]
            for key in marine_delivery_unsorted_by_yard_sort_day.get((yard_id, sort_id, day), [])
        )
        return mdl.ic[yard_id, sort_id, day] == previous + delivered - mdl.pv[yard_id, sort_id, day]

    def water_inventory_rule(mdl, yard_id: str, sort_id: str, day: int):
        previous = (
            problem.initial_water[(yard_id, sort_id)]
            if day == 1
            else mdl.iw[yard_id, sort_id, day - 1]
        )
        delivered = sum(
            mdl.vw[key] for key in sorted_by_yard_sort_day.get((yard_id, sort_id, day), [])
        ) + sum(
            mdl.mdw[key]
            for key in marine_delivery_sorted_by_yard_sort_day.get((yard_id, sort_id, day), [])
        )
        demand = problem.demand_for(yard_id, sort_id, day)
        return (
            mdl.iw[yard_id, sort_id, day]
            == previous + delivered + mdl.pv[yard_id, sort_id, day] - demand
        )

    model.unsorted_inventory = pyo.Constraint(model.YardSortDayKeys, rule=unsorted_inventory_rule)
    model.water_inventory = pyo.Constraint(model.YardSortDayKeys, rule=water_inventory_rule)

    def yard_storage_rule(mdl, yard_id: str, day: int):
        return (
            sum(mdl.ic[yard_id, sort_id, day] for sort_id in problem.sorts)
            <= problem.yard_storage[yard_id]
        )

    def yard_sorted_capacity_rule(mdl, yard_id: str, day: int):
        keys = sorted_by_yard_day.get((yard_id, day), [])
        if not keys:
            return pyo.Constraint.Skip
        return sum(mdl.vw[key] for key in keys) <= problem.yard_sorted_capacity[yard_id]

    def yard_unsorted_capacity_rule(mdl, yard_id: str, day: int):
        return (
            sum(mdl.pv[yard_id, sort_id, day] for sort_id in problem.sorts)
            <= problem.yard_unsorted_capacity[yard_id]
        )

    def yard_total_capacity_rule(mdl, yard_id: str, day: int):
        return (
            sum(mdl.vw[key] for key in sorted_by_yard_day.get((yard_id, day), []))
            + sum(mdl.pv[yard_id, sort_id, day] for sort_id in problem.sorts)
            <= problem.yard_total_capacity[yard_id]
        )

    model.yard_storage = pyo.Constraint(model.YardDayKeys, rule=yard_storage_rule)
    model.yard_sorted_capacity = pyo.Constraint(model.YardDayKeys, rule=yard_sorted_capacity_rule)
    model.yard_unsorted_capacity = pyo.Constraint(
        model.YardDayKeys, rule=yard_unsorted_capacity_rule
    )
    model.yard_total_capacity = pyo.Constraint(model.YardDayKeys, rule=yard_total_capacity_rule)

    def port_inventory_rule(mdl, port_id: str, sort_id: str, day: int):
        previous = (
            problem.marine_port_initial.get((port_id, sort_id), 0.0)
            if day == 1
            else mdl.pi[port_id, sort_id, day - 1]
        )
        inbound = (
            sum(
                mdl.mpw[key]
                for key in marine_pickup_sorted_by_port_sort_day.get((port_id, sort_id, day), [])
            )
            + sum(
                mdl.mww[key]
                for key in marine_water_in_sorted_by_port_sort_day.get((port_id, sort_id, day), [])
            )
            + sum(
                mdl.mpc[key]
                for key in marine_pickup_unsorted_by_port_sort_day.get((port_id, sort_id, day), [])
            )
            + sum(
                mdl.mwc[key]
                for key in marine_water_in_unsorted_by_port_sort_day.get(
                    (port_id, sort_id, day), []
                )
            )
        )
        outbound = (
            sum(
                mdl.mww[key]
                for key in marine_water_out_sorted_by_port_sort_day.get((port_id, sort_id, day), [])
            )
            + sum(
                mdl.mdw[key]
                for key in marine_delivery_sorted_by_port_sort_day.get((port_id, sort_id, day), [])
            )
            + sum(
                mdl.mwc[key]
                for key in marine_water_out_unsorted_by_port_sort_day.get(
                    (port_id, sort_id, day), []
                )
            )
            + sum(
                mdl.mdc[key]
                for key in marine_delivery_unsorted_by_port_sort_day.get(
                    (port_id, sort_id, day), []
                )
            )
        )
        return mdl.pi[port_id, sort_id, day] == previous + inbound - outbound

    def port_storage_rule(mdl, port_id: str, day: int):
        capacity = problem.marine_port_storage.get(port_id, 0.0)
        if capacity <= 0:
            return pyo.Constraint.Skip
        return sum(mdl.pi[port_id, sort_id, day] for sort_id in problem.sorts) <= capacity

    def port_handling_rule(mdl, port_id: str, day: int):
        capacity = problem.marine_port_daily_handling.get(port_id)
        if capacity is None:
            return pyo.Constraint.Skip
        handled = (
            sum(
                mdl.mww[key]
                for sort_id in problem.sorts
                for key in marine_water_out_sorted_by_port_sort_day.get((port_id, sort_id, day), [])
            )
            + sum(
                mdl.mwc[key]
                for sort_id in problem.sorts
                for key in marine_water_out_unsorted_by_port_sort_day.get(
                    (port_id, sort_id, day), []
                )
            )
            + sum(
                mdl.mww[key]
                for sort_id in problem.sorts
                for key in marine_water_in_sorted_by_port_sort_day.get((port_id, sort_id, day), [])
            )
            + sum(
                mdl.mwc[key]
                for sort_id in problem.sorts
                for key in marine_water_in_unsorted_by_port_sort_day.get(
                    (port_id, sort_id, day), []
                )
            )
        )
        return handled <= capacity

    model.port_inventory = pyo.Constraint(model.PortSortDayKeys, rule=port_inventory_rule)
    model.port_storage = pyo.Constraint(model.YardDayKeys, rule=port_storage_rule)
    model.port_handling = pyo.Constraint(model.YardDayKeys, rule=port_handling_rule)

    def barge_capacity_upper_rule(mdl, route_id: str, day: int):
        lane = problem.marine_lanes[route_id]
        volume = _route_day_water(mdl, route_id, day)
        return volume <= lane.barge_capacity * mdl.mt[route_id, day]

    def barge_capacity_lower_rule(mdl, route_id: str, day: int):
        lane = problem.marine_lanes[route_id]
        volume = _route_day_water(mdl, route_id, day)
        return volume >= (mdl.mt[route_id, day] - 1) * lane.barge_capacity

    def barge_fleet_capacity_rule(mdl, contractor_id: str, barge_type_id: str, day: int):
        route_ids = [
            route_id
            for route_id in problem.marine_lanes
            if problem.marine_lanes[route_id].contractor_id == contractor_id
            and problem.marine_lanes[route_id].barge_type_id == barge_type_id
        ]
        if not route_ids:
            return pyo.Constraint.Skip
        # A barge is occupied for the whole round trip. Count every departure
        # whose occupancy window still covers this day.
        trips = 0
        for route_id in route_ids:
            lane = problem.marine_lanes[route_id]
            first_day = max(1, day - lane.occupancy_days + 1)
            trips += sum(mdl.mt[route_id, start_day] for start_day in range(first_day, day + 1))
        available = problem.marine_barge_fleet.get((contractor_id, barge_type_id), 0)
        return trips <= available

    def barge_departure_cutoff_rule(mdl, route_id: str, day: int):
        lane = problem.marine_lanes[route_id]
        latest_start = problem.horizon_days - lane.occupancy_days + 1
        if day <= latest_start:
            return pyo.Constraint.Skip
        return mdl.mt[route_id, day] == 0

    model.marine_barge_capacity_upper = pyo.Constraint(
        model.MarineTripKeys, rule=barge_capacity_upper_rule
    )
    model.marine_barge_capacity_lower = pyo.Constraint(
        model.MarineTripKeys, rule=barge_capacity_lower_rule
    )
    model.marine_barge_fleet_capacity = pyo.Constraint(
        model.MarineBargeFleetKeys, rule=barge_fleet_capacity_rule
    )
    model.marine_departure_cutoff = pyo.Constraint(
        model.MarineTripKeys, rule=barge_departure_cutoff_rule
    )

    def marine_delivery_sorted_link_rule(mdl, route_id: str, sort_id: str, day: int):
        return mdl.mdw[route_id, sort_id, day] == mdl.mww[route_id, sort_id, day]

    def marine_delivery_unsorted_link_rule(mdl, route_id: str, sort_id: str, day: int):
        return mdl.mdc[route_id, sort_id, day] == mdl.mwc[route_id, sort_id, day]

    model.marine_delivery_sorted_link = pyo.Constraint(
        model.MarineSortedKeys, rule=marine_delivery_sorted_link_rule
    )
    model.marine_delivery_unsorted_link = pyo.Constraint(
        model.MarineUnsortedKeys, rule=marine_delivery_unsorted_link_rule
    )

    def fleet_capacity_rule(mdl, contractor_id: str, truck_type_id: str, day: int):
        sorted_keys = sorted_by_contractor_truck_day.get((contractor_id, truck_type_id, day), [])
        unsorted_keys = _unique_unsorted_load_keys(
            unsorted_by_contractor_truck_day.get((contractor_id, truck_type_id, day), [])
        )
        marine_sorted_keys = marine_sorted_by_contractor_truck_day.get(
            (contractor_id, truck_type_id, day), []
        )
        marine_unsorted_keys = marine_unsorted_by_contractor_truck_day.get(
            (contractor_id, truck_type_id, day), []
        )
        marine_delivery_sorted_keys = marine_delivery_sorted_by_contractor_truck_day.get(
            (contractor_id, truck_type_id, day), []
        )
        marine_delivery_unsorted_keys = marine_delivery_unsorted_by_contractor_truck_day.get(
            (contractor_id, truck_type_id, day), []
        )
        if (
            not sorted_keys
            and not unsorted_keys
            and not marine_sorted_keys
            and not marine_unsorted_keys
            and not marine_delivery_sorted_keys
            and not marine_delivery_unsorted_keys
        ):
            return pyo.Constraint.Skip
        minutes = sum(mdl.nw[key] * _cycle_for_key(problem, key) for key in sorted_keys) + sum(
            mdl.nc[key] * _cycle_for_load_key(problem, key) for key in unsorted_keys
        )
        marine_minutes = (
            sum(
                mdl.mpw[key]
                / problem.marine_lanes[key[0]].truck_capacity
                * problem.marine_lanes[key[0]].pickup_cycle_minutes
                for key in marine_sorted_keys
            )
            + sum(
                mdl.mpc[key]
                / problem.marine_lanes[key[0]].truck_capacity
                * problem.marine_lanes[key[0]].pickup_cycle_minutes
                for key in marine_unsorted_keys
            )
            + sum(
                mdl.mdw[key]
                / problem.marine_lanes[key[0]].truck_capacity
                * problem.marine_lanes[key[0]].delivery_cycle_minutes
                for key in marine_delivery_sorted_keys
            )
            + sum(
                mdl.mdc[key]
                / problem.marine_lanes[key[0]].truck_capacity
                * problem.marine_lanes[key[0]].delivery_cycle_minutes
                for key in marine_delivery_unsorted_keys
            )
        )
        available = problem.fleet_count.get((contractor_id, truck_type_id), 0) * (
            problem.regular_minutes
        )
        return minutes + marine_minutes <= available

    model.fleet_capacity = pyo.Constraint(model.FleetKeys, rule=fleet_capacity_rule)

    inventory_keys = sorted(set(sorted_supply_keys) | set(unsorted_supply_keys))
    marine_drayage_cost = sum(
        model.mpw[key] * problem.marine_lanes[key[0]].pickup_drayage_cost_per_m3
        + model.mdw[key] * problem.marine_lanes[key[0]].delivery_drayage_cost_per_m3
        for key in marine_sorted_keys
    ) + sum(
        model.mpc[key] * problem.marine_lanes[key[0]].pickup_drayage_cost_per_m3
        + model.mdc[key] * problem.marine_lanes[key[0]].delivery_drayage_cost_per_m3
        for key in marine_unsorted_keys
    )
    marine_barge_cost = sum(
        model.mt[route_id, day] * problem.marine_lanes[route_id].barge_cost_per_trip
        for route_id, day in marine_trip_keys
    )
    port_inventory_penalty = problem.port_inventory_penalty * sum(
        model.pi[port_id, sort_id, problem.days[-1]]
        for port_id in problem.marine_ports
        for sort_id in problem.sorts
    )
    model.cost_expr = (
        sum(
            mdl_load * problem.transport_cost[(block_id, yard_id, truck_type_id)]
            for (block_id, yard_id, truck_type_id) in problem.transport_cost
            for mdl_load in _load_count_expressions(
                model,
                block_id,
                yard_id,
                truck_type_id,
                sorted_by_contractor_truck_day,
                unsorted_by_contractor_truck_day,
            )
        )
        + problem.roadside_penalty
        * sum(
            (model.ibw[block_id, sort_id] if (block_id, sort_id) in sorted_supply_keys else 0.0)
            + (model.ibc[block_id, sort_id] if (block_id, sort_id) in unsorted_supply_keys else 0.0)
            for block_id, sort_id in inventory_keys
        )
        + marine_drayage_cost
        + marine_barge_cost
        + port_inventory_penalty
    )
    model.workload_expr = sum(model.u[contractor_id, day] for contractor_id, day in workload_keys)

    if objective == "cost":
        model.objective = pyo.Objective(expr=model.cost_expr, sense=pyo.minimize)
    elif objective == "workload":
        model.objective = pyo.Objective(expr=model.workload_expr, sense=pyo.minimize)
    else:
        goal1, goal2 = goals  # type: ignore[misc]
        model.dev_cost = pyo.Var(domain=pyo.NonNegativeReals, initialize=0.0)
        model.dev_workload = pyo.Var(domain=pyo.NonNegativeReals, initialize=0.0)
        model.goal_cost = pyo.Constraint(expr=model.cost_expr - model.dev_cost <= goal1)
        model.goal_workload = pyo.Constraint(expr=model.workload_expr - model.dev_workload <= goal2)
        cost_scale = max(abs(goal1), 1.0)
        workload_scale = max(sum(phi.values()), 1.0)
        model.objective = pyo.Objective(
            expr=weights[0] * model.dev_cost / cost_scale
            + weights[1] * model.dev_workload / workload_scale,
            sense=pyo.minimize,
        )

    return model


def _route_day_water(
    model: pyo.ConcreteModel,
    route_id: str,
    day: int,
) -> Any:
    """Return the water-volume expression for one marine route/day."""
    return sum(
        model.mww[key] for key in model.MarineSortedKeys if key[0] == route_id and key[2] == day
    ) + sum(
        model.mwc[key] for key in model.MarineUnsortedKeys if key[0] == route_id and key[2] == day
    )


def _cycle_for_key(problem: HaulingFlowProblem, key: Key6) -> float:
    """Return the cycle minutes for a sorted key."""
    block_id, yard_id, _sort_id, _contractor_id, truck_type_id, _day = key
    return problem.cycle_minutes[(block_id, yard_id, truck_type_id)]


def _cycle_for_load_key(problem: HaulingFlowProblem, key: Key5) -> float:
    """Return the cycle minutes for an unsorted-load key."""
    block_id, yard_id, _contractor_id, truck_type_id, _day = key
    return problem.cycle_minutes[(block_id, yard_id, truck_type_id)]


def _contractor_day_truckloads(
    model: pyo.ConcreteModel,
    contractor_id: str,
    day: int,
    sorted_by_contractor_day: dict[tuple[str, int], list[Key6]],
    unsorted_by_contractor_day: dict[tuple[str, int], list[Key6]],
    marine_sorted_by_contractor_day: dict[tuple[str, int], list[tuple[str, str, int]]]
    | None = None,
    marine_unsorted_by_contractor_day: dict[tuple[str, int], list[tuple[str, str, int]]]
    | None = None,
    marine_delivery_sorted_by_contractor_day: dict[tuple[str, int], list[tuple[str, str, int]]]
    | None = None,
    marine_delivery_unsorted_by_contractor_day: dict[tuple[str, int], list[tuple[str, str, int]]]
    | None = None,
    problem: HaulingFlowProblem | None = None,
):
    """Return the contractor/day truckload expression (road plus marine drayage)."""
    sorted_loads = sum(
        model.nw[key] for key in sorted_by_contractor_day.get((contractor_id, day), [])
    )
    unsorted_loads = sum(
        model.nc[key]
        for key in _unique_unsorted_load_keys(
            unsorted_by_contractor_day.get((contractor_id, day), [])
        )
    )
    marine_loads = 0
    if problem is not None:
        for key in (marine_sorted_by_contractor_day or {}).get((contractor_id, day), []):
            capacity = problem.marine_lanes[key[0]].truck_capacity
            marine_loads += model.mpw[key] / capacity
        for key in (marine_unsorted_by_contractor_day or {}).get((contractor_id, day), []):
            capacity = problem.marine_lanes[key[0]].truck_capacity
            marine_loads += model.mpc[key] / capacity
        for key in (marine_delivery_sorted_by_contractor_day or {}).get((contractor_id, day), []):
            capacity = problem.marine_lanes[key[0]].truck_capacity
            marine_loads += model.mdw[key] / capacity
        for key in (marine_delivery_unsorted_by_contractor_day or {}).get((contractor_id, day), []):
            capacity = problem.marine_lanes[key[0]].truck_capacity
            marine_loads += model.mdc[key] / capacity
    return sorted_loads + unsorted_loads + marine_loads


def _unique_unsorted_load_keys(keys: list[Key6]) -> list[Key5]:
    """Collapse unsorted volume keys to their shared truckload key, preserving order."""
    seen: set[Key5] = set()
    unique: list[Key5] = []
    for block_id, yard_id, _sort_id, contractor_id, truck_type_id, day in keys:
        key = (block_id, yard_id, contractor_id, truck_type_id, day)
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def _load_count_expressions(
    model: pyo.ConcreteModel,
    block_id: str,
    yard_id: str,
    truck_type_id: str,
    sorted_by_contractor_truck_day: dict[tuple[str, str, int], list[Key6]],
    unsorted_by_contractor_truck_day: dict[tuple[str, str, int], list[Key6]],
):
    """Yield sorted and unsorted load-count expressions for one arc and truck type."""
    for (_contractor_id, type_id, _day), keys in sorted_by_contractor_truck_day.items():
        if type_id != truck_type_id:
            continue
        for key in keys:
            if key[0] == block_id and key[1] == yard_id:
                yield model.nw[key]
    for (_contractor_id, type_id, _day), keys in unsorted_by_contractor_truck_day.items():
        if type_id != truck_type_id:
            continue
        for load_key in _unique_unsorted_load_keys(keys):
            if load_key[0] == block_id and load_key[1] == yard_id:
                yield model.nc[load_key]


def _solver_options(
    solver_name: str,
    time_limit: float | None,
    gap: float | None,
    solver_options: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return solver options with portable time-limit and gap names."""
    options = dict(solver_options or {})
    if time_limit is not None:
        if solver_name in {"highs", "appsi_highs"}:
            options.setdefault("time_limit", time_limit)
        elif solver_name.startswith("gurobi"):
            options.setdefault("TimeLimit", time_limit)
        else:
            options.setdefault("timelimit", time_limit)
    if gap is not None:
        if solver_name in {"highs", "appsi_highs"}:
            options.setdefault("mip_rel_gap", gap)
        elif solver_name.startswith("gurobi"):
            options.setdefault("MIPGap", gap)
        else:
            options.setdefault("mipgap", gap)
    return options


def solve_flow(
    problem: HaulingFlowProblem,
    *,
    objective: str = "cost",
    solver: str = "highs",
    time_limit: float | None = None,
    gap: float | None = None,
    weights: tuple[float, float] = (1.0, 1.0),
    goals: tuple[float, float] | None = None,
    preferred: dict[str, float] | None = None,
    tee: bool = False,
    solver_options: dict[str, Any] | None = None,
) -> FlowSolveResult:
    """Solve the Phase I flow model.

    Parameters
    ----------
    problem:
        Normalised hauling data.
    objective:
        ``"cost"``, ``"workload"``, or ``"goal"``.
    solver:
        Pyomo solver name. ``highs`` is the default; ``gurobi`` is used when installed and licensed.
    time_limit:
        Optional solver time limit in seconds.
    gap:
        Optional relative MIP gap target.
    weights:
        Goal weights for ``objective="goal"``.
    goals:
        ``(Goal1, Goal2)``. When omitted for a goal solve, a cost-only solve supplies ``Goal1`` and
        ``Goal2`` is set to zero; preferred truckloads are derived from the same cost-only plan.
    preferred:
        Preferred daily truckloads per contractor. When omitted, the contract values are used, or
        the cost-only plan's daily averages for a goal solve.
    tee:
        Stream the solver log.
    solver_options:
        Additional solver options forwarded verbatim.

    Returns
    -------
    FlowSolveResult
        Result payload with objective values, DataFrames, solver provenance, and diagnostics.
    """
    goals_used: tuple[float, float] | None = None
    if objective == "goal":
        if goals is None or preferred is None:
            cost_result = solve_flow(
                problem,
                objective="cost",
                solver=solver,
                time_limit=time_limit,
                gap=gap,
                tee=tee,
                solver_options=solver_options,
            )
            if cost_result.status not in {"optimal", "feasible"}:
                return cost_result
            if goals is None:
                goals = (cost_result.cost_objective or 0.0, 0.0)
            if preferred is None:
                preferred = _derive_preferred(problem, cost_result)
        goals_used = goals
        model = build_flow_model(
            problem,
            objective="goal",
            preferred=preferred,
            goals=goals,
            weights=weights,
        )
    else:
        if preferred is None:
            preferred = {
                contractor: float(problem.preferred.get(contractor) or 0.0)
                for contractor in problem.contractors
            }
        model = build_flow_model(
            problem,
            objective=objective,
            preferred=preferred,
            weights=weights,
        )

    solve_start = time.perf_counter()
    try:
        solver_instance = SolverFactory(solver)
        if not solver_instance.available(exception_flag=False):
            raise RuntimeError(f"Solver '{solver}' is not available")
        options = _solver_options(solver, time_limit, gap, solver_options)
        if options:
            solver_instance.options.update(options)
        results = solver_instance.solve(model, tee=tee)
    except NoFeasibleSolutionError as exc:
        return FlowSolveResult(
            status="infeasible",
            objective=None,
            cost_objective=None,
            workload_objective=None,
            solver=solver,
            runtime_seconds=time.perf_counter() - solve_start,
            solver_error=f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 - the result payload carries the diagnostic
        return FlowSolveResult(
            status="error",
            objective=None,
            cost_objective=None,
            workload_objective=None,
            solver=solver,
            runtime_seconds=time.perf_counter() - solve_start,
            solver_error=f"{type(exc).__name__}: {exc}",
        )

    runtime = time.perf_counter() - solve_start
    termination = str(results.solver.termination_condition).lower()
    if termination in {"optimal", "locallyoptimal", "globallyoptimal"}:
        status = "optimal"
    elif termination in {
        "feasible",
        "maxtimelimit",
        "maxiterations",
        "maxevaluations",
        "objectivelimit",
        "timelimit",
    }:
        status = "feasible"
    elif termination in {"infeasible", "infeasibleorunbounded"}:
        status = "infeasible"
    elif termination == "unbounded":
        status = "unbounded"
    else:
        status = "error"

    if status not in {"optimal", "feasible"}:
        message = getattr(results.solver, "message", None)
        return FlowSolveResult(
            status=status,
            objective=None,
            cost_objective=None,
            workload_objective=None,
            solver=solver,
            termination=termination,
            runtime_seconds=runtime,
            solver_error=str(message) if message else None,
        )

    if objective == "goal":
        phi_used = (
            preferred
            if preferred is not None
            else {
                contractor: float(problem.preferred.get(contractor) or 0.0)
                for contractor in problem.contractors
            }
        )
    else:
        phi_used = (
            preferred
            if preferred is not None
            else {contractor: 0.0 for contractor in problem.contractors}
        )
    return _extract_result(
        problem,
        model,
        status,
        termination,
        solver,
        runtime,
        phi_used,
        goals_used,
    )


def _derive_preferred(
    problem: HaulingFlowProblem,
    cost_result: FlowSolveResult,
) -> dict[str, float]:
    """Derive each contractor's preferred daily truckloads from a cost-only plan."""
    if cost_result.contractor_workload.empty:
        return {contractor: 0.0 for contractor in problem.contractors}
    totals = cost_result.contractor_workload.groupby("contractor_id")["truckloads"].sum()
    return {
        contractor: float(totals.get(contractor, 0.0)) / problem.horizon_days
        for contractor in problem.contractors
    }


def _extract_result(
    problem: HaulingFlowProblem,
    model: pyo.ConcreteModel,
    status: str,
    termination: str,
    solver: str,
    runtime: float,
    phi: dict[str, float],
    goals: tuple[float, float] | None,
) -> FlowSolveResult:
    """Convert a solved Pyomo model into a :class:`FlowSolveResult`."""
    flow_rows: list[dict[str, Any]] = []
    for key in model.SortedKeys:
        block_id, yard_id, sort_id, contractor_id, truck_type_id, day = key
        sorted_m3 = float(pyo.value(model.vw[key]))
        unsorted_m3 = 0.0
        if sorted_m3 > 1e-8:
            flow_rows.append(
                _flow_row(
                    problem,
                    day,
                    block_id,
                    yard_id,
                    sort_id,
                    contractor_id,
                    truck_type_id,
                    sorted_m3,
                    unsorted_m3,
                )
            )
    for key in model.UnsortedKeys:
        block_id, yard_id, sort_id, contractor_id, truck_type_id, day = key
        unsorted_m3 = float(pyo.value(model.vc[key]))
        if unsorted_m3 > 1e-8:
            flow_rows.append(
                _flow_row(
                    problem,
                    day,
                    block_id,
                    yard_id,
                    sort_id,
                    contractor_id,
                    truck_type_id,
                    0.0,
                    unsorted_m3,
                )
            )

    truckload_rows: list[dict[str, Any]] = []
    for key in model.SortedKeys:
        block_id, yard_id, sort_id, contractor_id, truck_type_id, day = key
        loads = int(round(pyo.value(model.nw[key])))
        if loads <= 0:
            continue
        truckload_rows.append(
            _truckload_row(problem, day, block_id, yard_id, contractor_id, truck_type_id, loads, 0)
        )
    for key in model.UnsortedLoadKeys:
        block_id, yard_id, contractor_id, truck_type_id, day = key
        loads = int(round(pyo.value(model.nc[key])))
        if loads <= 0:
            continue
        truckload_rows.append(
            _truckload_row(problem, day, block_id, yard_id, contractor_id, truck_type_id, 0, loads)
        )

    inventory_rows: list[dict[str, Any]] = []
    for key in model.YardSortDayKeys:
        yard_id, sort_id, day = key
        inventory_rows.append(
            {
                "day": day,
                "scenario_day": problem.start_day + day - 1,
                "yard_id": yard_id,
                "log_sort_id": sort_id,
                "unsorted_inventory_m3": float(pyo.value(model.ic[key])),
                "water_inventory_m3": float(pyo.value(model.iw[key])),
                "processed_m3": float(pyo.value(model.pv[key])),
                "demand_m3": problem.demand_for(yard_id, sort_id, day),
            }
        )

    sorted_supply_set = set(model.SortedSupplyKeys)
    unsorted_supply_set = set(model.UnsortedSupplyKeys)
    inventory_keys = sorted(sorted_supply_set | unsorted_supply_set)
    block_inventory_rows = [
        {
            "block_id": block_id,
            "log_sort_id": sort_id,
            "sorted_inventory_m3": (
                float(pyo.value(model.ibw[block_id, sort_id]))
                if (block_id, sort_id) in sorted_supply_set
                else 0.0
            ),
            "unsorted_inventory_m3": (
                float(pyo.value(model.ibc[block_id, sort_id]))
                if (block_id, sort_id) in unsorted_supply_set
                else 0.0
            ),
        }
        for block_id, sort_id in inventory_keys
    ]

    workload_rows: list[dict[str, Any]] = []
    for key in model.WorkloadKeys:
        contractor_id, day = key
        loads = _contractor_day_truckloads(
            model,
            contractor_id,
            day,
            _sorted_by_contractor_day(model),
            _unsorted_by_contractor_day(model),
            _marine_sorted_by_contractor_day(model),
            _marine_unsorted_by_contractor_day(model),
            _marine_delivery_sorted_by_contractor_day(model),
            _marine_delivery_unsorted_by_contractor_day(model),
            problem,
        )
        value = float(pyo.value(loads))
        workload_rows.append(
            {
                "day": day,
                "scenario_day": problem.start_day + day - 1,
                "contractor_id": contractor_id,
                "truckloads": value,
                "preferred_truckloads": float(phi.get(contractor_id, 0.0)),
                "deviation": float(pyo.value(model.u[key])),
            }
        )

    flows = pd.DataFrame(flow_rows, columns=_FLOW_COLUMNS)
    truckloads = _aggregate_truckloads(pd.DataFrame(truckload_rows, columns=_TRUCKLOAD_COLUMNS))
    yard_inventory = pd.DataFrame(inventory_rows, columns=_INVENTORY_COLUMNS)
    block_inventory = pd.DataFrame(block_inventory_rows, columns=_BLOCK_INVENTORY_COLUMNS)
    contractor_workload = pd.DataFrame(workload_rows, columns=_WORKLOAD_COLUMNS)
    (
        marine_flows,
        barge_trips,
        port_inventory,
        marine_truckloads,
    ) = _extract_marine_result(problem, model)

    goal_deviations: dict[str, float] = {}
    if hasattr(model, "dev_cost"):
        goal_deviations = {
            "cost": float(pyo.value(model.dev_cost)),
            "workload": float(pyo.value(model.dev_workload)),
        }
    goal1, goal2 = goals if goals is not None else (None, None)

    return FlowSolveResult(
        status=status,
        objective=float(pyo.value(model.objective)),
        cost_objective=float(pyo.value(model.cost_expr)),
        workload_objective=float(pyo.value(model.workload_expr)),
        goal_deviations=goal_deviations,
        goal1=goal1,
        goal2=goal2,
        preferred_truckloads=dict(phi),
        flows=flows,
        truckloads=truckloads,
        yard_inventory=yard_inventory,
        block_inventory=block_inventory,
        contractor_workload=contractor_workload,
        marine_flows=marine_flows,
        barge_trips=barge_trips,
        port_inventory=port_inventory,
        marine_truckloads=marine_truckloads,
        solver=solver,
        termination=termination,
        runtime_seconds=runtime,
    )


def _extract_marine_result(
    problem: HaulingFlowProblem,
    model: pyo.ConcreteModel,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Convert marine model variables into the Phase I marine tables."""
    if not problem.marine_lanes:
        return (
            pd.DataFrame(columns=_MARINE_FLOW_COLUMNS),
            pd.DataFrame(columns=_BARGE_TRIP_COLUMNS),
            pd.DataFrame(columns=_PORT_INVENTORY_COLUMNS),
            pd.DataFrame(columns=_MARINE_TRUCKLOAD_COLUMNS),
        )

    flow_rows: list[dict[str, Any]] = []
    for sorted_flag, keys, pickup_var, water_var, delivery_var in (
        (True, model.MarineSortedKeys, model.mpw, model.mww, model.mdw),
        (False, model.MarineUnsortedKeys, model.mpc, model.mwc, model.mdc),
    ):
        for key in keys:
            route_id, sort_id, day = key
            lane = problem.marine_lanes[route_id]
            pickup_m3 = float(pyo.value(pickup_var[key]))
            water_m3 = float(pyo.value(water_var[key]))
            delivery_m3 = float(pyo.value(delivery_var[key]))
            if max(pickup_m3, water_m3, delivery_m3) <= 1e-8:
                continue
            arrival_day = day + lane.arrival_lag_days
            flow_rows.append(
                {
                    "day": day,
                    "scenario_day": problem.start_day + day - 1,
                    "arrival_day": arrival_day,
                    "arrival_scenario_day": problem.start_day + arrival_day - 1,
                    "marine_route_id": route_id,
                    "block_id": lane.block_id,
                    "yard_id": lane.yard_id,
                    "log_sort_id": sort_id,
                    "contractor_id": lane.contractor_id,
                    "truck_type_id": lane.truck_type_id,
                    "barge_type_id": lane.barge_type_id,
                    "origin_port_id": lane.origin_port_id,
                    "destination_port_id": lane.destination_port_id,
                    "water_arc_id": lane.water_arc_id,
                    "sorted": sorted_flag,
                    "pickup_road_m3": pickup_m3,
                    "water_m3": water_m3,
                    "delivery_road_m3": delivery_m3,
                    "pickup_truckloads": _ceil_loads(pickup_m3, lane.truck_capacity),
                    "delivery_truckloads": _ceil_loads(delivery_m3, lane.truck_capacity),
                    "barge_trips": 0,
                    "origin_handling_m3": water_m3,
                    "destination_handling_m3": water_m3,
                    "barge_load_minutes": 0.0,
                    "barge_unload_minutes": 0.0,
                    "sail_minutes": 0.0,
                    "barge_cycle_minutes": 0.0,
                    "origin_handling_cost": 0.0,
                    "destination_handling_cost": 0.0,
                    "barge_variable_cost": 0.0,
                    "drayage_cost": (
                        pickup_m3 * lane.pickup_drayage_cost_per_m3
                        + delivery_m3 * lane.delivery_drayage_cost_per_m3
                    ),
                    "total_cost": 0.0,
                }
            )

    # Allocate integer trips to the sort rows of each route/day, then fill trip-level costs.
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in flow_rows:
        grouped.setdefault((row["marine_route_id"], row["day"]), []).append(row)
    for (route_id, day), rows in grouped.items():
        lane = problem.marine_lanes[route_id]
        total_trips = int(round(float(pyo.value(model.mt[route_id, day]))))
        allocation = _allocate_integer_units(
            [float(row["water_m3"]) for row in rows],
            total_trips,
        )
        for row, trips in zip(rows, allocation, strict=True):
            row["barge_trips"] = trips
            row["barge_load_minutes"] = trips * lane.load_minutes
            row["barge_unload_minutes"] = trips * lane.unload_minutes
            row["sail_minutes"] = trips * lane.water_travel_minutes
            row["barge_cycle_minutes"] = trips * lane.barge_cycle_minutes
            row["origin_handling_cost"] = trips * lane.origin_handling_cost
            row["destination_handling_cost"] = trips * lane.destination_handling_cost
            handling = row["origin_handling_cost"] + row["destination_handling_cost"]
            row["barge_variable_cost"] = max(0.0, trips * lane.barge_cost_per_trip - handling)
            row["total_cost"] = row["barge_variable_cost"] + handling + row["drayage_cost"]

    marine_flows = pd.DataFrame(flow_rows, columns=_MARINE_FLOW_COLUMNS)
    if not marine_flows.empty:
        marine_flows = marine_flows.sort_values(
            ["day", "marine_route_id", "log_sort_id"]
        ).reset_index(drop=True)

    trip_rows: list[dict[str, Any]] = []
    for route_id, day in model.MarineTripKeys:
        lane = problem.marine_lanes[route_id]
        trips = int(round(float(pyo.value(model.mt[route_id, day]))))
        if trips <= 0:
            continue
        # Recompute the route/day water volume from the two variable sets without assuming a
        # particular sort mix.
        water_m3 = sum(
            float(pyo.value(model.mww[key]))
            for key in model.MarineSortedKeys
            if key[0] == route_id and key[2] == day
        ) + sum(
            float(pyo.value(model.mwc[key]))
            for key in model.MarineUnsortedKeys
            if key[0] == route_id and key[2] == day
        )
        handling = trips * (lane.origin_handling_cost + lane.destination_handling_cost)
        trip_rows.append(
            {
                "day": day,
                "scenario_day": problem.start_day + day - 1,
                "marine_route_id": route_id,
                "contractor_id": lane.contractor_id,
                "truck_type_id": lane.truck_type_id,
                "barge_type_id": lane.barge_type_id,
                "origin_port_id": lane.origin_port_id,
                "destination_port_id": lane.destination_port_id,
                "water_arc_id": lane.water_arc_id,
                "water_m3": water_m3,
                "barge_trips": trips,
                "arrival_day": day + lane.arrival_lag_days,
                "arrival_scenario_day": problem.start_day + day + lane.arrival_lag_days - 1,
                "transit_days": lane.arrival_lag_days,
                "occupancy_days": lane.occupancy_days,
                "barge_cycle_minutes": trips * lane.barge_cycle_minutes,
                "barge_load_minutes": trips * lane.load_minutes,
                "barge_unload_minutes": trips * lane.unload_minutes,
                "sail_minutes": trips * lane.water_travel_minutes,
                "origin_handling_minutes": trips * lane.origin_handling_minutes,
                "destination_handling_minutes": trips * lane.destination_handling_minutes,
                "origin_handling_cost": trips * lane.origin_handling_cost,
                "destination_handling_cost": trips * lane.destination_handling_cost,
                "barge_variable_cost": max(0.0, trips * lane.barge_cost_per_trip - handling),
                "handling_cost": handling,
                "total_cost": trips * lane.barge_cost_per_trip,
            }
        )
    barge_trips = pd.DataFrame(trip_rows, columns=_BARGE_TRIP_COLUMNS)
    if not barge_trips.empty:
        barge_trips = barge_trips.sort_values(["day", "marine_route_id"]).reset_index(drop=True)

    port_rows: list[dict[str, Any]] = []
    for port_id, sort_id, day in model.PortSortDayKeys:
        opening = (
            problem.marine_port_initial.get((port_id, sort_id), 0.0)
            if day == 1
            else float(pyo.value(model.pi[port_id, sort_id, day - 1]))
        )
        inbound = 0.0
        outbound = 0.0
        for key in (
            *[key for key in model.MarineSortedKeys if key[0] in problem.marine_lanes],
            *[key for key in model.MarineUnsortedKeys if key[0] in problem.marine_lanes],
        ):
            route_id, candidate_sort, candidate_day = key
            if candidate_sort != sort_id:
                continue
            lane = problem.marine_lanes[route_id]
            if key in model.MarineSortedKeys:
                pickup, water, delivery = model.mpw[key], model.mww[key], model.mdw[key]
            else:
                pickup, water, delivery = model.mpc[key], model.mwc[key], model.mdc[key]
            if lane.origin_port_id == port_id and candidate_day == day:
                inbound += float(pyo.value(pickup))
                outbound += float(pyo.value(water))
            if lane.destination_port_id == port_id and candidate_day + lane.arrival_lag_days == day:
                inbound += float(pyo.value(water))
                outbound += float(pyo.value(delivery))
        handled = max(inbound, outbound)
        port_rows.append(
            {
                "day": day,
                "scenario_day": problem.start_day + day - 1,
                "port_id": port_id,
                "log_sort_id": sort_id,
                "opening_inventory_m3": opening,
                "inbound_m3": inbound,
                "outbound_m3": outbound,
                "inventory_m3": float(pyo.value(model.pi[port_id, sort_id, day])),
                "handled_m3": handled,
            }
        )
    port_inventory = pd.DataFrame(port_rows, columns=_PORT_INVENTORY_COLUMNS)

    truck_rows: list[dict[str, Any]] = []
    for row in flow_rows:
        lane = problem.marine_lanes[row["marine_route_id"]]
        sorted_loads = row["pickup_truckloads"] if row["sorted"] else 0
        unsorted_loads = 0 if row["sorted"] else row["pickup_truckloads"]
        truck_rows.append(
            {
                "day": row["day"],
                "scenario_day": row["scenario_day"],
                "marine_route_id": row["marine_route_id"],
                "leg": "pickup",
                "block_id": lane.block_id,
                "yard_id": lane.origin_port_id,
                "contractor_id": lane.contractor_id,
                "truck_type_id": lane.truck_type_id,
                "sorted_truckloads": sorted_loads,
                "unsorted_truckloads": unsorted_loads,
                "total_truckloads": sorted_loads + unsorted_loads,
            }
        )
        sorted_loads = row["delivery_truckloads"] if row["sorted"] else 0
        unsorted_loads = 0 if row["sorted"] else row["delivery_truckloads"]
        truck_rows.append(
            {
                "day": row["arrival_day"],
                "scenario_day": row["arrival_scenario_day"],
                "marine_route_id": row["marine_route_id"],
                "leg": "delivery",
                "block_id": lane.destination_port_id,
                "yard_id": lane.yard_id,
                "contractor_id": lane.contractor_id,
                "truck_type_id": lane.truck_type_id,
                "sorted_truckloads": sorted_loads,
                "unsorted_truckloads": unsorted_loads,
                "total_truckloads": sorted_loads + unsorted_loads,
            }
        )
    marine_truckloads = pd.DataFrame(truck_rows, columns=_MARINE_TRUCKLOAD_COLUMNS)
    if not marine_truckloads.empty:
        marine_truckloads = (
            marine_truckloads.groupby(
                [
                    "day",
                    "scenario_day",
                    "marine_route_id",
                    "leg",
                    "block_id",
                    "yard_id",
                    "contractor_id",
                    "truck_type_id",
                ],
                as_index=False,
            )[["sorted_truckloads", "unsorted_truckloads"]]
            .sum()
            .assign(
                total_truckloads=lambda frame: (
                    frame["sorted_truckloads"] + frame["unsorted_truckloads"]
                )
            )
            .loc[:, _MARINE_TRUCKLOAD_COLUMNS]
        )
    return marine_flows, barge_trips, port_inventory, marine_truckloads


def _flow_row(
    problem: HaulingFlowProblem,
    day: int,
    block_id: str,
    yard_id: str,
    sort_id: str,
    contractor_id: str,
    truck_type_id: str,
    sorted_m3: float,
    unsorted_m3: float,
) -> dict[str, Any]:
    """Build one flow output row."""
    return {
        "day": day,
        "scenario_day": problem.start_day + day - 1,
        "block_id": block_id,
        "yard_id": yard_id,
        "log_sort_id": sort_id,
        "contractor_id": contractor_id,
        "truck_type_id": truck_type_id,
        "sorted_m3": sorted_m3,
        "unsorted_m3": unsorted_m3,
    }


def _ceil_loads(volume_m3: float, capacity_m3: float) -> int:
    """Return the number of started loads for a volume (zero for an empty volume)."""
    if volume_m3 <= 1e-8:
        return 0
    return int(math.ceil(volume_m3 / capacity_m3 - 1e-9))


def _allocate_integer_units(weights: list[float], total: int) -> list[int]:
    """Allocate an integer total across weights using the largest-remainder rule."""
    if total <= 0:
        return [0 for _ in weights]
    weight_sum = sum(weights)
    if weight_sum <= 0:
        allocation = [0 for _ in weights]
        allocation[0] = total
        return allocation
    raw = [total * weight / weight_sum for weight in weights]
    allocation = [int(math.floor(value)) for value in raw]
    remainder = total - sum(allocation)
    order = sorted(
        range(len(weights)),
        key=lambda index: (raw[index] - allocation[index], weights[index]),
        reverse=True,
    )
    for index in order[:remainder]:
        allocation[index] += 1
    return allocation


def _truckload_row(
    problem: HaulingFlowProblem,
    day: int,
    block_id: str,
    yard_id: str,
    contractor_id: str,
    truck_type_id: str,
    sorted_loads: int,
    unsorted_loads: int,
) -> dict[str, Any]:
    """Build one truckload output row."""
    return {
        "day": day,
        "scenario_day": problem.start_day + day - 1,
        "block_id": block_id,
        "yard_id": yard_id,
        "contractor_id": contractor_id,
        "truck_type_id": truck_type_id,
        "sorted_truckloads": sorted_loads,
        "unsorted_truckloads": unsorted_loads,
        "total_truckloads": sorted_loads + unsorted_loads,
    }


def _aggregate_truckloads(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate sorted and unsorted truckload rows to one row per key."""
    if frame.empty:
        return frame
    group_columns = [
        "day",
        "scenario_day",
        "block_id",
        "yard_id",
        "contractor_id",
        "truck_type_id",
    ]
    aggregated = frame.groupby(group_columns, as_index=False)[
        ["sorted_truckloads", "unsorted_truckloads"]
    ].sum()
    aggregated["total_truckloads"] = (
        aggregated["sorted_truckloads"] + aggregated["unsorted_truckloads"]
    )
    return aggregated[_TRUCKLOAD_COLUMNS].sort_values(group_columns).reset_index(drop=True)


def _sorted_by_contractor_day(model: pyo.ConcreteModel) -> dict[tuple[str, int], list[Key6]]:
    """Rebuild the sorted contractor/day index from the model sets."""
    index: dict[tuple[str, int], list[Key6]] = {}
    for key in model.SortedKeys:
        contractor_id, day = key[3], key[5]
        index.setdefault((contractor_id, day), []).append(key)
    return index


def _unsorted_by_contractor_day(model: pyo.ConcreteModel) -> dict[tuple[str, int], list[Key6]]:
    """Rebuild the unsorted contractor/day index from the model sets."""
    index: dict[tuple[str, int], list[Key6]] = {}
    for key in model.UnsortedKeys:
        contractor_id, day = key[3], key[5]
        index.setdefault((contractor_id, day), []).append(key)
    return index


def _marine_sorted_by_contractor_day(
    model: pyo.ConcreteModel,
) -> dict[tuple[str, int], list[tuple[str, str, int]]]:
    """Rebuild the marine sorted contractor/day index from the model sets."""
    index: dict[tuple[str, int], list[tuple[str, str, int]]] = {}
    problem: HaulingFlowProblem | None = getattr(model, "problem", None)
    if problem is None:
        return index
    for key in model.MarineSortedKeys:
        lane = problem.marine_lanes[key[0]]
        index.setdefault((lane.contractor_id, key[2]), []).append(key)
    return index


def _marine_unsorted_by_contractor_day(
    model: pyo.ConcreteModel,
) -> dict[tuple[str, int], list[tuple[str, str, int]]]:
    """Rebuild the marine unsorted contractor/day index from the model sets."""
    index: dict[tuple[str, int], list[tuple[str, str, int]]] = {}
    problem: HaulingFlowProblem | None = getattr(model, "problem", None)
    if problem is None:
        return index
    for key in model.MarineUnsortedKeys:
        lane = problem.marine_lanes[key[0]]
        index.setdefault((lane.contractor_id, key[2]), []).append(key)
    return index


def _marine_delivery_sorted_by_contractor_day(
    model: pyo.ConcreteModel,
) -> dict[tuple[str, int], list[tuple[str, str, int]]]:
    """Rebuild the marine sorted delivery contractor/arrival-day index."""
    index: dict[tuple[str, int], list[tuple[str, str, int]]] = {}
    problem: HaulingFlowProblem | None = getattr(model, "problem", None)
    if problem is None:
        return index
    for key in model.MarineSortedKeys:
        lane = problem.marine_lanes[key[0]]
        arrival_day = key[2] + lane.arrival_lag_days
        if arrival_day <= problem.horizon_days:
            index.setdefault((lane.contractor_id, arrival_day), []).append(key)
    return index


def _marine_delivery_unsorted_by_contractor_day(
    model: pyo.ConcreteModel,
) -> dict[tuple[str, int], list[tuple[str, str, int]]]:
    """Rebuild the marine unsorted delivery contractor/arrival-day index."""
    index: dict[tuple[str, int], list[tuple[str, str, int]]] = {}
    problem: HaulingFlowProblem | None = getattr(model, "problem", None)
    if problem is None:
        return index
    for key in model.MarineUnsortedKeys:
        lane = problem.marine_lanes[key[0]]
        arrival_day = key[2] + lane.arrival_lag_days
        if arrival_day <= problem.horizon_days:
            index.setdefault((lane.contractor_id, arrival_day), []).append(key)
    return index


def summarize_flow_result(result: FlowSolveResult) -> str:
    """Return a compact human-readable summary of a Phase I solve.

    Parameters
    ----------
    result:
        Result payload from :func:`solve_flow`.

    Returns
    -------
    str
        Multi-line summary suitable for a CLI or notebook cell. It reports status, objective
        values, goal deviations, truckloads, delivered volume, and the ending yard inventory.
    """
    lines = [
        f"status: {result.status}",
        f"solver: {result.solver} ({result.termination or 'n/a'})",
        f"runtime_s: {result.runtime_seconds:.3f}",
    ]
    if result.solver_error:
        lines.append(f"solver_error: {result.solver_error}")
    if result.cost_objective is not None:
        lines.append(f"cost_objective: {result.cost_objective:.3f}")
    if result.workload_objective is not None:
        lines.append(f"workload_objective: {result.workload_objective:.3f}")
    if result.goal1 is not None:
        lines.append(
            "goals: "
            f"cost={result.goal1:.3f}, workload={result.goal2 if result.goal2 is not None else 0.0:.3f}"
        )
    if result.goal_deviations:
        lines.append(
            "goal_deviations: "
            f"cost={result.goal_deviations.get('cost', 0.0):.3f}, "
            f"workload={result.goal_deviations.get('workload', 0.0):.3f}"
        )
    if not result.flows.empty:
        delivered = float(result.flows[["sorted_m3", "unsorted_m3"]].to_numpy().sum())
        lines.append(f"delivered_m3: {delivered:.3f}")
    if not result.truckloads.empty:
        lines.append(
            "truckloads: "
            f"sorted={int(result.truckloads['sorted_truckloads'].sum())}, "
            f"unsorted={int(result.truckloads['unsorted_truckloads'].sum())}, "
            f"total={int(result.truckloads['total_truckloads'].sum())}"
        )
    if not result.yard_inventory.empty:
        ending = (
            result.yard_inventory.sort_values(["yard_id", "log_sort_id", "day"])
            .groupby(["yard_id", "log_sort_id"], as_index=False)
            .last()
        )
        lines.append(
            "ending_yard_inventory_m3: "
            f"unsorted={ending['unsorted_inventory_m3'].sum():.3f}, "
            f"water={ending['water_inventory_m3'].sum():.3f}"
        )
    if not result.marine_flows.empty:
        lines.append(
            "marine: "
            f"water_m3={result.marine_flows['water_m3'].sum():.3f}, "
            f"barge_trips={int(result.barge_trips['barge_trips'].sum())}, "
            "terminal_handling_m3="
            f"{result.marine_flows['origin_handling_m3'].sum() + result.marine_flows['destination_handling_m3'].sum():.3f}"
        )
    return "\n".join(lines)
