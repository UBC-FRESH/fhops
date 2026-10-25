"""Marine barge-cycle scheduling and port synchronization.

The road scheduler in :mod:`fhops.hauling.schedule` routes trucks and loaders. A marine route adds
a second equipment class: a barge that loads at an origin port, sails a water arc, unloads at a
destination port, and returns empty. This module turns the Phase I barge trips into a deterministic
single-day barge schedule with:

- one row per barge trip;
- port-loader assignment and non-overlapping terminal service;
- barge load, sail, unload, and empty-return times;
- the synchronized road pickup and delivery windows for the drayage legs.

The deterministic scheduler is deliberately small and auditable. It complements the exact truck
MIP and the SA solver; it does not replace either. The exact truck MIP schedules the road loads
(including the drayage legs when a marine route is present), while this module schedules the water
leg. The returned road windows are the handoff between the two schedules and are reported, not
hard-linked, in the first release.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd

from fhops.hauling.contract import (
    Barge,
    BargeType,
    HaulingConfig,
    LoaderLocationKind,
    MarineRoute,
    Port,
    PortSide,
    TruckType,
)

if TYPE_CHECKING:
    from fhops.hauling.flow import FlowSolveResult
    from fhops.scenario.contract import Scenario

__all__ = [
    "BargeSchedulePlan",
    "BargeScheduleResult",
    "MarineScheduleProblem",
    "MarineTripRequest",
    "build_marine_schedule_problem",
    "schedule_barge_trips",
    "validate_barge_schedule",
]

_BARGE_SCHEDULE_COLUMNS = [
    "trip_id",
    "day",
    "scenario_day",
    "marine_route_id",
    "barge_id",
    "contractor_id",
    "barge_type_id",
    "origin_port_id",
    "destination_port_id",
    "water_arc_id",
    "origin_port_loader_id",
    "destination_port_loader_id",
    "volume_m3",
    "load_start",
    "load_finish",
    "departure",
    "arrival",
    "unload_start",
    "unload_finish",
    "return_finish",
    "waiting_origin",
    "waiting_destination",
    "load_minutes",
    "sail_minutes",
    "unload_minutes",
    "return_minutes",
    "origin_handling_minutes",
    "destination_handling_minutes",
    "pickup_truck_depart",
    "pickup_truck_arrive",
    "delivery_truck_depart",
    "delivery_truck_arrive",
    "barge_variable_cost",
    "handling_cost",
    "total_cost",
]
_BARGE_SUMMARY_COLUMNS = [
    "barge_id",
    "contractor_id",
    "barge_type_id",
    "trips",
    "volume_m3",
    "load_minutes",
    "sail_minutes",
    "unload_minutes",
    "return_minutes",
    "first_departure",
    "last_return",
    "fixed_cost",
    "variable_cost",
    "handling_cost",
    "total_cost",
]


@dataclass(frozen=True, slots=True)
class MarineTripRequest:
    """One Phase I barge-trip request for a route/day.

    Attributes
    ----------
    route_id:
        Marine route identifier.
    contractor_id / truck_type_id / barge_type_id:
        Responsible contractor, drayage truck type, and barge type.
    origin_port_id / destination_port_id / water_arc_id:
        Water-leg topology.
    volume_m3:
        Water-leg volume in cubic metres.
    trips:
        Number of barge trips that carry ``volume_m3``.
    load_minutes / unload_minutes / sail_minutes / return_minutes:
        Barge service and sailing times per trip.
    origin_handling_minutes / destination_handling_minutes:
        Terminal handling time per trip at each port.
    origin_handling_cost / destination_handling_cost:
        Terminal handling cost per trip at each port.
    pickup_travel_minutes / delivery_travel_minutes:
        Loaded road drayage travel times used to place the synchronized road windows.
    truck_capacity:
        Drayage truck capacity in cubic metres.
    barge_variable_cost_per_trip:
        Variable barge cost per trip.
    """

    route_id: str
    contractor_id: str
    truck_type_id: str
    barge_type_id: str
    origin_port_id: str
    destination_port_id: str
    water_arc_id: str
    volume_m3: float
    trips: int
    load_minutes: float
    unload_minutes: float
    sail_minutes: float
    return_minutes: float
    origin_handling_minutes: float
    destination_handling_minutes: float
    origin_handling_cost: float
    destination_handling_cost: float
    pickup_travel_minutes: float
    delivery_travel_minutes: float
    truck_capacity: float
    barge_variable_cost_per_trip: float


@dataclass(frozen=True, slots=True)
class MarineScheduleProblem:
    """Normalised marine scheduling data for one day.

    Attributes
    ----------
    scenario_name / day / scenario_day / horizon_minutes:
        Run context.
    requests:
        Barge-trip requests from Phase I.
    barges:
        Enabled barges keyed by id.
    barge_types:
        Barge types keyed by id.
    ports:
        Ports keyed by id.
    port_loaders:
        ``port_id -> tuple of loader ids``. A port loader serves both barge handling and drayage.
    loader_service:
        ``loader_id -> service minutes``.
    """

    scenario_name: str
    day: int
    scenario_day: int
    horizon_minutes: float
    requests: tuple[MarineTripRequest, ...]
    barges: dict[str, Barge]
    barge_types: dict[str, BargeType]
    ports: dict[str, Port]
    port_loaders: dict[str, tuple[str, ...]]
    loader_service: dict[str, float]


@dataclass(frozen=True, slots=True)
class BargeSchedulePlan:
    """Deterministic barge and port-loader assignment.

    Attributes
    ----------
    barge_trips:
        ``route_id -> tuple of (barge_id, origin_loader_id, destination_loader_id)`` in schedule
        order.
    """

    barge_trips: dict[str, tuple[tuple[str, str, str], ...]]


@dataclass(slots=True)
class BargeScheduleResult:
    """Barge schedule payload attached to a Phase II or Phase III result.

    Attributes
    ----------
    status:
        ``feasible`` when every request was scheduled, ``empty`` when there were no requests.
    schedule / summary:
        Trip-level and barge-level DataFrames.
    plan:
        Deterministic assignment plan.
    objective:
        Total barge fixed, variable, and terminal handling cost.
    fixed_cost:
        Fixed dispatch cost of the barges used.
    runtime_seconds:
        Scheduler wall time.
    error:
        Optional diagnostic.
    """

    status: str
    schedule: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_BARGE_SCHEDULE_COLUMNS)
    )
    summary: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_BARGE_SUMMARY_COLUMNS)
    )
    plan: BargeSchedulePlan | None = None
    objective: float = 0.0
    fixed_cost: float = 0.0
    runtime_seconds: float = 0.0
    error: str | None = None


def build_marine_schedule_problem(
    scenario: Scenario,
    flow_result: FlowSolveResult,
    day: int,
) -> MarineScheduleProblem | None:
    """Build the marine scheduling input from a Phase I result.

    Parameters
    ----------
    scenario:
        Scenario with a ``hauling`` section.
    flow_result:
        Phase I result. The ``barge_trips`` table supplies the trip counts and water volumes.
    day:
        Relative hauling-horizon day to schedule.

    Returns
    -------
    MarineScheduleProblem | None
        ``None`` when the day has no barge trips.

    Raises
    ------
    ValueError
        When a barge trip references an unknown route, a port has no loader, or the contract lacks
        an enabled barge for the route.
    """
    config = scenario.hauling
    if config is None:
        raise ValueError("Scenario has no hauling section")
    if day < 1 or day > config.planning_horizon_days:
        raise ValueError(
            f"day {day} is outside the hauling horizon 1..{config.planning_horizon_days}"
        )
    trips = getattr(flow_result, "barge_trips", None)
    if trips is None or trips.empty:
        return None
    day_rows = trips[trips["day"] == day]
    requests: list[MarineTripRequest] = []
    for record in day_rows.to_dict("records"):
        count = int(record["barge_trips"])
        if count <= 0:
            continue
        route = config.marine_route(str(record["marine_route_id"]))
        water_arc = config.water_arc(str(record["water_arc_id"]))
        barge_type = config.barge_type(str(record["barge_type_id"]))
        origin_leg = config.port_leg_for(route, PortSide.ORIGIN)
        destination_leg = config.port_leg_for(route, PortSide.DESTINATION)
        if origin_leg is None or destination_leg is None:
            raise ValueError(f"MarineRoute {route.id} is missing an origin or destination PortLeg")
        load_minutes = _minutes(record.get("barge_load_minutes"), count) / count
        unload_minutes = _minutes(record.get("barge_unload_minutes"), count) / count
        sail_minutes = _minutes(record.get("sail_minutes"), count) / count
        barge_variable = max(
            0.0,
            _minutes(record.get("barge_variable_cost"), 0.0) / count,
        )
        requests.append(
            MarineTripRequest(
                route_id=route.id,
                contractor_id=route.contractor_id,
                truck_type_id=route.truck_type_id,
                barge_type_id=barge_type.id,
                origin_port_id=route.origin_port_id,
                destination_port_id=route.destination_port_id,
                water_arc_id=water_arc.id,
                volume_m3=_minutes(record.get("water_m3"), 0.0),
                trips=count,
                load_minutes=load_minutes,
                unload_minutes=unload_minutes,
                sail_minutes=sail_minutes,
                return_minutes=water_arc.empty_travel_minutes(),
                origin_handling_minutes=_minutes(record.get("origin_handling_minutes"), count)
                / count,
                destination_handling_minutes=_minutes(
                    record.get("destination_handling_minutes"), count
                )
                / count,
                origin_handling_cost=_minutes(record.get("origin_handling_cost"), count) / count,
                destination_handling_cost=_minutes(record.get("destination_handling_cost"), count)
                / count,
                pickup_travel_minutes=origin_leg.travel_minutes,
                delivery_travel_minutes=destination_leg.travel_minutes,
                truck_capacity=_truck_capacity(config, route),
                barge_variable_cost_per_trip=barge_variable,
            )
        )
    if not requests:
        return None

    port_loaders: dict[str, tuple[str, ...]] = {}
    loader_service: dict[str, float] = {}
    for loader in config.loader_locations:
        service = loader.service_minutes or config.default_loader_service_minutes
        loader_service[loader.loader_id] = service
        if loader.location_kind is LoaderLocationKind.PORT:
            current = port_loaders.get(loader.location_id, ())
            port_loaders[loader.location_id] = (*current, loader.loader_id)
    for request in requests:
        for port_id in (request.origin_port_id, request.destination_port_id):
            if not port_loaders.get(port_id):
                raise ValueError(
                    f"No port loader at port_id={port_id} for marine route "
                    f"{request.route_id}; bind a LoaderLocation with location_kind=port"
                )

    return MarineScheduleProblem(
        scenario_name=scenario.name,
        day=day,
        scenario_day=config.start_day + day - 1,
        horizon_minutes=(
            config.driver_policy.regular_minutes + config.driver_policy.max_overtime_minutes
        ),
        requests=tuple(requests),
        barges={barge.id: barge for barge in config.barges if barge.enabled},
        barge_types={barge_type.id: barge_type for barge_type in config.barge_types},
        ports={port.id: port for port in config.ports},
        port_loaders=port_loaders,
        loader_service=loader_service,
    )


def schedule_barge_trips(problem: MarineScheduleProblem) -> BargeScheduleResult:
    """Schedule barge trips deterministically with port-loader synchronization.

    The scheduler assigns each trip to the compatible barge that becomes available first, and to
    the compatible port loader that becomes available first at each end. It is a deterministic
    list scheduler, not an optimiser.

    Parameters
    ----------
    problem:
        Normalised marine scheduling data.

    Returns
    -------
    BargeScheduleResult
        One row per barge trip plus a barge-level summary.
    """
    start = time.perf_counter()
    if not problem.requests:
        return BargeScheduleResult(status="empty", runtime_seconds=time.perf_counter() - start)

    barge_available: dict[str, float] = {barge_id: 0.0 for barge_id in problem.barges}
    loader_available: dict[str, float] = {loader_id: 0.0 for loader_id in problem.loader_service}
    schedule_rows: list[dict[str, Any]] = []
    plan: dict[str, tuple[tuple[str, str, str], ...]] = {}
    for request in problem.requests:
        compatible = [
            barge
            for barge in problem.barges.values()
            if barge.contractor_id == request.contractor_id
            and barge.barge_type_id == request.barge_type_id
        ]
        if not compatible:
            return BargeScheduleResult(
                status="error",
                runtime_seconds=time.perf_counter() - start,
                error=(
                    f"No enabled barge of type {request.barge_type_id} for contractor "
                    f"{request.contractor_id}"
                ),
            )
        trip_plan: list[tuple[str, str, str]] = []
        volume_per_trip = request.volume_m3 / request.trips if request.trips else 0.0
        for trip_index in range(request.trips):
            barge = min(
                compatible,
                key=lambda candidate: (barge_available[candidate.id], candidate.id),
            )
            origin_loader = _earliest_loader(
                problem.port_loaders[request.origin_port_id],
                loader_available,
            )
            destination_loader = _earliest_loader(
                problem.port_loaders[request.destination_port_id],
                loader_available,
            )
            barge_free = barge_available[barge.id]
            load_start = max(barge_free, loader_available[origin_loader])
            load_finish = load_start + request.load_minutes + request.origin_handling_minutes
            departure = load_finish
            arrival = departure + request.sail_minutes
            unload_start = max(arrival, loader_available[destination_loader])
            unload_finish = (
                unload_start + request.unload_minutes + request.destination_handling_minutes
            )
            return_finish = unload_finish + request.return_minutes
            barge_available[barge.id] = return_finish
            loader_available[origin_loader] = load_finish
            loader_available[destination_loader] = unload_finish
            trip_id = f"d{problem.day}-{request.route_id}-barge{trip_index + 1}"
            handling_cost = request.origin_handling_cost + request.destination_handling_cost
            schedule_rows.append(
                {
                    "trip_id": trip_id,
                    "day": problem.day,
                    "scenario_day": problem.scenario_day,
                    "marine_route_id": request.route_id,
                    "barge_id": barge.id,
                    "contractor_id": request.contractor_id,
                    "barge_type_id": request.barge_type_id,
                    "origin_port_id": request.origin_port_id,
                    "destination_port_id": request.destination_port_id,
                    "water_arc_id": request.water_arc_id,
                    "origin_port_loader_id": origin_loader,
                    "destination_port_loader_id": destination_loader,
                    "volume_m3": volume_per_trip,
                    "load_start": load_start,
                    "load_finish": load_finish,
                    "departure": departure,
                    "arrival": arrival,
                    "unload_start": unload_start,
                    "unload_finish": unload_finish,
                    "return_finish": return_finish,
                    "waiting_origin": max(0.0, load_start - barge_free),
                    "waiting_destination": max(0.0, unload_start - arrival),
                    "load_minutes": request.load_minutes,
                    "sail_minutes": request.sail_minutes,
                    "unload_minutes": request.unload_minutes,
                    "return_minutes": request.return_minutes,
                    "origin_handling_minutes": request.origin_handling_minutes,
                    "destination_handling_minutes": request.destination_handling_minutes,
                    "pickup_truck_depart": max(0.0, load_start - request.pickup_travel_minutes),
                    "pickup_truck_arrive": load_start,
                    "delivery_truck_depart": unload_finish,
                    "delivery_truck_arrive": (unload_finish + request.delivery_travel_minutes),
                    "barge_variable_cost": request.barge_variable_cost_per_trip,
                    "handling_cost": handling_cost,
                    "total_cost": request.barge_variable_cost_per_trip + handling_cost,
                }
            )
            trip_plan.append((barge.id, origin_loader, destination_loader))
        plan[request.route_id] = tuple(trip_plan)

    schedule = pd.DataFrame(schedule_rows, columns=_BARGE_SCHEDULE_COLUMNS)
    summary = _summarise_barges(schedule, problem)
    fixed_cost = float(summary["fixed_cost"].sum()) if not summary.empty else 0.0
    variable_and_handling = float(schedule["total_cost"].sum()) if not schedule.empty else 0.0
    return BargeScheduleResult(
        status="feasible",
        schedule=schedule,
        summary=summary,
        plan=BargeSchedulePlan(
            barge_trips={route_id: tuple(trips) for route_id, trips in plan.items()}
        ),
        objective=fixed_cost + variable_and_handling,
        fixed_cost=fixed_cost,
        runtime_seconds=time.perf_counter() - start,
    )


def validate_barge_schedule(
    problem: MarineScheduleProblem,
    schedule: pd.DataFrame,
) -> list[str]:
    """Validate a barge schedule against its problem.

    Parameters
    ----------
    problem:
        Marine scheduling data.
    schedule:
        Barge schedule DataFrame produced by :func:`schedule_barge_trips`.

    Returns
    -------
    list[str]
        Human-readable violations. An empty list means the schedule is valid.
    """
    errors: list[str] = []
    if schedule.empty:
        return errors
    expected_trips = sum(request.trips for request in problem.requests)
    if len(schedule) != expected_trips:
        errors.append(f"Expected {expected_trips} barge trips, found {len(schedule)}")
    for row in schedule.to_dict("records"):
        if row["load_finish"] < row["load_start"]:
            errors.append(f"{row['trip_id']}: load finish precedes load start")
        if row["arrival"] < row["departure"]:
            errors.append(f"{row['trip_id']}: arrival precedes departure")
        if row["unload_finish"] < row["unload_start"]:
            errors.append(f"{row['trip_id']}: unload finish precedes unload start")
        if row["barge_id"] not in problem.barges:
            errors.append(f"{row['trip_id']}: unknown barge_id={row['barge_id']}")
        if row["origin_port_loader_id"] not in problem.loader_service:
            errors.append(
                f"{row['trip_id']}: unknown origin port loader {row['origin_port_loader_id']}"
            )
        if row["destination_port_loader_id"] not in problem.loader_service:
            errors.append(
                f"{row['trip_id']}: unknown destination port loader "
                f"{row['destination_port_loader_id']}"
            )
        if row["pickup_truck_arrive"] < row["load_start"] - 1e-6:
            errors.append(f"{row['trip_id']}: pickup truck arrives after loading starts")
    # No barge or port loader may serve two overlapping trips.
    errors.extend(_overlap_errors(schedule, "barge_id", "load_start", "return_finish"))
    errors.extend(
        _overlap_errors(
            schedule,
            "origin_port_loader_id",
            "load_start",
            "load_finish",
        )
    )
    errors.extend(
        _overlap_errors(
            schedule,
            "destination_port_loader_id",
            "unload_start",
            "unload_finish",
        )
    )
    return errors


def _overlap_errors(
    schedule: pd.DataFrame,
    resource: str,
    start_column: str,
    finish_column: str,
) -> list[str]:
    """Return overlap diagnostics for one resource column."""
    errors: list[str] = []
    for resource_id, group in schedule.groupby(resource):
        ordered = group.sort_values(start_column)
        previous_finish: float | None = None
        previous_trip: str | None = None
        for row in ordered.to_dict("records"):
            if previous_finish is not None and row[start_column] < previous_finish - 1e-6:
                errors.append(
                    f"{resource}={resource_id}: {row['trip_id']} overlaps {previous_trip}"
                )
            previous_finish = row[finish_column]
            previous_trip = row["trip_id"]
    return errors


def _summarise_barges(
    schedule: pd.DataFrame,
    problem: MarineScheduleProblem,
) -> pd.DataFrame:
    """Aggregate a trip-level barge schedule by barge."""
    if schedule.empty:
        return pd.DataFrame(columns=_BARGE_SUMMARY_COLUMNS)
    grouped = schedule.groupby(["barge_id", "contractor_id", "barge_type_id"], as_index=False).agg(
        trips=("trip_id", "count"),
        volume_m3=("volume_m3", "sum"),
        load_minutes=("load_minutes", "sum"),
        sail_minutes=("sail_minutes", "sum"),
        unload_minutes=("unload_minutes", "sum"),
        return_minutes=("return_minutes", "sum"),
        first_departure=("departure", "min"),
        last_return=("return_finish", "max"),
        variable_cost=("barge_variable_cost", "sum"),
        handling_cost=("handling_cost", "sum"),
        total_cost=("total_cost", "sum"),
    )
    grouped["fixed_cost"] = grouped["barge_type_id"].map(
        lambda barge_type_id: problem.barge_types[barge_type_id].fixed_cost
    )
    grouped["total_cost"] = grouped["fixed_cost"] + grouped["total_cost"]
    return grouped.loc[:, _BARGE_SUMMARY_COLUMNS]


def _earliest_loader(loader_ids: tuple[str, ...], available: dict[str, float]) -> str:
    """Return the compatible loader that becomes available first."""
    if not loader_ids:
        raise ValueError("No port loader is available")
    return min(loader_ids, key=lambda loader_id: (available.get(loader_id, 0.0), loader_id))


def _minutes(value: Any, default: float) -> float:
    """Coerce a CSV/DataFrame value to minutes, using ``default`` for missing values."""
    if value is None:
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(numeric):
        return default
    return numeric


def _truck_capacity(config: HaulingConfig, route: MarineRoute) -> float:
    """Return the drayage truck capacity for a route."""
    truck_type: TruckType = next(
        item for item in config.truck_types if item.id == route.truck_type_id
    )
    return truck_type.capacity_m3
