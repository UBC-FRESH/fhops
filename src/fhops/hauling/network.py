"""Network and data preparation for Phase II daily truck scheduling.

Phase II takes the integer truckloads from the Phase I flow plan and turns them into individual
loads on a single working day. This module builds the normalised :class:`ScheduleProblem` that the
continuous-time MIP in :mod:`fhops.hauling.schedule` solves.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from fhops.hauling.contract import Contractor, HaulingConfig, LoaderLocationKind, Truck, TruckType

if TYPE_CHECKING:
    from fhops.hauling.flow import FlowSolveResult
    from fhops.hauling.marine import MarineScheduleProblem
    from fhops.scenario.contract import Scenario

__all__ = [
    "ScheduleProblem",
    "Truckload",
    "build_schedule_problem",
    "build_schedule_problem_from_loads",
]


@dataclass(frozen=True, slots=True)
class Truckload:
    """One individual truckload on the scheduling day.

    Attributes
    ----------
    load_id:
        Unique identifier within the day.
    day:
        Relative hauling-horizon day (one-indexed).
    block_id:
        Pickup block.
    yard_id:
        Delivery sort yard.
    contractor_id:
        Contractor responsible for the load.
    truck_type_id:
        Compatible truck type.
    sorted:
        ``True`` for a roadside-sorted load, ``False`` for an unsorted load.
    volume_m3:
        Nominal load volume. Phase II uses it for reporting; the scheduling constraints use the
        truck type's capacity and the load count, not the exact partial volume.
    leg:
        ``road`` for a direct block-to-yard haul, ``pickup`` for the block-to-origin-port drayage
        leg, or ``delivery`` for the destination-port-to-yard drayage leg.
    marine_route_id:
        Marine route identifier for drayage loads; ``None`` for road loads.
    """

    load_id: str
    day: int
    block_id: str
    yard_id: str
    contractor_id: str
    truck_type_id: str
    sorted: bool
    volume_m3: float
    leg: str = "road"
    marine_route_id: str | None = None


@dataclass(frozen=True, slots=True)
class ScheduleProblem:
    """Normalised Phase II scheduling data.

    Attributes
    ----------
    scenario_name:
        Parent scenario name.
    day:
        Relative hauling-horizon day being scheduled.
    scenario_day:
        Parent-scenario day (``start_day + day - 1``).
    horizon_minutes:
        Daily time horizon, ``regular_minutes + max_overtime_minutes``.
    depot_id:
        The single central depot used for this first scheduling cut.
    loads:
        Individual truckloads.
    trucks:
        Enabled trucks from the contract.
    truck_types / contractors:
        Contract records keyed by id.
    pickup_loaders / delivery_loaders:
        ``location_id -> tuple of loader ids``.
    loader_service:
        ``loader_id -> service minutes``.
    block_to_yard / yard_to_block:
        ``(block, yard, truck_type) -> minutes``.
    depot_to_block / yard_to_depot:
        ``(location, truck_type) -> minutes``.
    regular_minutes / max_overtime_minutes:
        Driver policy.
    overtime_violation_penalty_per_minute:
        Soft penalty per minute above ``regular_minutes + max_overtime_minutes`` used by the SA
        solver. The exact MIP treats the limit as hard.
    marine:
        Optional marine scheduling data for barge cycles and port loaders. ``None`` for road-only
        days.
    """

    scenario_name: str
    day: int
    scenario_day: int
    horizon_minutes: float
    depot_id: str
    loads: tuple[Truckload, ...]
    trucks: tuple[Truck, ...]
    truck_types: dict[str, TruckType]
    contractors: dict[str, Contractor]
    pickup_loaders: dict[str, tuple[str, ...]]
    delivery_loaders: dict[str, tuple[str, ...]]
    loader_service: dict[str, float]
    block_to_yard: dict[tuple[str, str, str], float]
    yard_to_block: dict[tuple[str, str, str], float]
    depot_to_block: dict[tuple[str, str], float]
    yard_to_depot: dict[tuple[str, str], float]
    regular_minutes: float
    max_overtime_minutes: float
    overtime_violation_penalty_per_minute: float
    marine: MarineScheduleProblem | None = None

    def load_by_id(self, load_id: str) -> Truckload:
        """Return a load by id."""
        return next(load for load in self.loads if load.load_id == load_id)

    def compatible_trucks(self, load: Truckload) -> tuple[Truck, ...]:
        """Return enabled trucks that can carry a load."""
        return tuple(
            truck
            for truck in self.trucks
            if truck.enabled
            and truck.contractor_id == load.contractor_id
            and truck.truck_type_id == load.truck_type_id
        )

    def pickup_loaders_for(self, load: Truckload) -> tuple[str, ...]:
        """Return the pickup loaders at a load's block."""
        return self.pickup_loaders.get(load.block_id, ())

    def delivery_loaders_for(self, load: Truckload) -> tuple[str, ...]:
        """Return the delivery loaders at a load's yard."""
        return self.delivery_loaders.get(load.yard_id, ())

    def pickup_loads(self) -> tuple[Truckload, ...]:
        """Return the loads sorted by block id and load id."""
        return tuple(sorted(self.loads, key=lambda load: (load.block_id, load.load_id)))

    def delivery_loads(self) -> tuple[Truckload, ...]:
        """Return the loads sorted by yard id and load id."""
        return tuple(sorted(self.loads, key=lambda load: (load.yard_id, load.load_id)))

    def load_travel_minutes(self, load: Truckload) -> float:
        """Return the loaded block-to-yard travel time."""
        return self.block_to_yard[(load.block_id, load.yard_id, load.truck_type_id)]

    def empty_travel_minutes(self, previous: Truckload, following: Truckload) -> float:
        """Return the empty travel time from ``previous``'s yard to ``following``'s block.

        Marine drayage stages are separate physical movements: a truck that delivers to the
        destination port cannot carry a pickup load from the origin block without a deadhead that
        the first release does not model. Missing cross-stage pairs receive a synthetic
        full-day deadhead so the MIP can express the transition as infeasible rather than raising
        a key error; a schedule that uses one is reported as a validation warning.
        """
        key = (previous.yard_id, following.block_id, following.truck_type_id)
        if key in self.yard_to_block:
            return self.yard_to_block[key]
        marine_legs = {"pickup", "delivery"}
        if previous.leg in marine_legs or following.leg in marine_legs:
            return self.horizon_minutes
        raise KeyError(
            "No road leg from "
            f"{previous.yard_id} to {following.block_id} for truck type "
            f"{following.truck_type_id}"
        )

    def depot_to_load_minutes(self, load: Truckload) -> float:
        """Return the depot-to-pickup travel time."""
        return self.depot_to_block[(load.block_id, load.truck_type_id)]

    def load_to_depot_minutes(self, load: Truckload) -> float:
        """Return the delivery-to-depot travel time."""
        return self.yard_to_depot[(load.yard_id, load.truck_type_id)]


def build_schedule_problem(
    scenario: Scenario,
    flow_result: FlowSolveResult,
    day: int,
) -> ScheduleProblem:
    """Build a scheduling problem from a Phase I result and a selected day.

    Parameters
    ----------
    scenario:
        Scenario with a ``hauling`` section.
    flow_result:
        Result from :func:`fhops.hauling.flow.solve_flow`.
    day:
        Relative hauling-horizon day to schedule.

    Returns
    -------
    ScheduleProblem
        Normalised loads, trucks, loaders, and travel times.

    Raises
    ------
    ValueError
        When the day is outside the horizon, the scenario has no hauling section, the day has no
        truckloads, or a required loader, depot leg, or haul arc is missing.
    """
    config = scenario.hauling
    if config is None:
        raise ValueError("Scenario has no hauling section")
    if day < 1 or day > config.planning_horizon_days:
        raise ValueError(
            f"day {day} is outside the hauling horizon 1..{config.planning_horizon_days}"
        )
    rows = flow_result.truckloads
    if rows.empty:
        loads: list[Truckload] = []
    else:
        day_rows = rows[rows["day"] == day]
        loads = _expand_loads(config, day_rows.to_dict("records"))
    marine_rows = getattr(flow_result, "marine_truckloads", None)
    if marine_rows is not None and not marine_rows.empty:
        marine_day_rows = marine_rows[marine_rows["day"] == day]
        loads.extend(_expand_marine_loads(config, marine_day_rows.to_dict("records")))
    problem = build_schedule_problem_from_loads(scenario, loads, day)
    from fhops.hauling.marine import build_marine_schedule_problem

    marine_problem = build_marine_schedule_problem(scenario, flow_result, day)
    return replace(problem, marine=marine_problem)


def build_schedule_problem_from_loads(
    scenario: Scenario,
    loads: Sequence[Truckload],
    day: int,
) -> ScheduleProblem:
    """Build a scheduling problem from an explicit load list.

    This is the test and experimentation entry point. The production path is
    :func:`build_schedule_problem`.

    Parameters
    ----------
    scenario:
        Scenario with a ``hauling`` section.
    loads:
        Individual loads on the selected day.
    day:
        Relative hauling-horizon day.

    Returns
    -------
    ScheduleProblem
        Normalised scheduling data.

    Raises
    ------
    ValueError
        When the day is invalid, the scenario has no hauling section, the contract has more than
        one depot, or a required loader/travel leg is missing.
    """
    config = scenario.hauling
    if config is None:
        raise ValueError("Scenario has no hauling section")
    if day < 1 or day > config.planning_horizon_days:
        raise ValueError(
            f"day {day} is outside the hauling horizon 1..{config.planning_horizon_days}"
        )
    if not loads:
        raise ValueError(f"day {day} has no truckloads to schedule")
    if len(config.depots) != 1:
        raise ValueError(
            f"Phase II requires exactly one depot; scenario has {len(config.depots)} depots"
        )
    depot = config.depots[0]
    truck_types = {truck_type.id: truck_type for truck_type in config.truck_types}
    contractors = {contractor.id: contractor for contractor in config.contractors}
    trucks = tuple(truck for truck in config.trucks if truck.enabled)
    if not trucks:
        raise ValueError("Phase II requires at least one enabled truck")

    pickup_loaders: dict[str, tuple[str, ...]] = {}
    delivery_loaders: dict[str, tuple[str, ...]] = {}
    loader_service: dict[str, float] = {}
    for loader in config.loader_locations:
        service = loader.service_minutes or config.default_loader_service_minutes
        loader_service[loader.loader_id] = service
        if loader.location_kind is LoaderLocationKind.PICKUP:
            target = pickup_loaders
        elif loader.location_kind is LoaderLocationKind.DELIVERY:
            target = delivery_loaders
        else:
            # A port loader handles both the inbound drayage drop and the outbound barge/drayage
            # service at the same terminal.
            for port_target in (pickup_loaders, delivery_loaders):
                current = port_target.get(loader.location_id, ())
                port_target[loader.location_id] = (*current, loader.loader_id)
            continue
        current = target.get(loader.location_id, ())
        target[loader.location_id] = (*current, loader.loader_id)

    for load in loads:
        if not pickup_loaders.get(load.block_id):
            raise ValueError(
                f"No pickup loader at block_id={load.block_id} for load {load.load_id}"
            )
        if not delivery_loaders.get(load.yard_id):
            raise ValueError(
                f"No delivery loader at yard_id={load.yard_id} for load {load.load_id}"
            )
        if load.truck_type_id not in truck_types:
            raise ValueError(
                f"Load {load.load_id} references unknown truck_type_id={load.truck_type_id}"
            )
        if load.contractor_id not in contractors:
            raise ValueError(
                f"Load {load.load_id} references unknown contractor_id={load.contractor_id}"
            )

    haul_arcs = {(arc.block_id, arc.yard_id, arc.truck_type_id): arc for arc in config.haul_arcs}
    depot_legs = {
        (leg.location_id, leg.truck_type_id): leg.travel_minutes for leg in config.depot_legs
    }
    block_to_yard: dict[tuple[str, str, str], float] = {}
    yard_to_block: dict[tuple[str, str, str], float] = {}
    depot_to_block: dict[tuple[str, str], float] = {}
    yard_to_depot: dict[tuple[str, str], float] = {}

    # Populate every arc, not only the loads on this day. A truck may deliver to one yard and
    # then travel empty to a block whose own load goes to another yard.
    for arc_key, arc in haul_arcs.items():
        block_id, yard_id, truck_type_id = arc_key
        block_to_yard[arc_key] = arc.travel_minutes
        yard_to_block[(yard_id, block_id, truck_type_id)] = arc.empty_travel_minutes()
    for leg in config.port_legs:
        if leg.side.value == "origin":
            forward = (leg.location_id, leg.port_id, leg.truck_type_id)
            reverse = (leg.port_id, leg.location_id, leg.truck_type_id)
        else:
            forward = (leg.port_id, leg.location_id, leg.truck_type_id)
            reverse = (leg.location_id, leg.port_id, leg.truck_type_id)
        block_to_yard[forward] = leg.travel_minutes
        yard_to_block[reverse] = leg.empty_travel_minutes()
    for (location_id, truck_type_id), minutes in depot_legs.items():
        depot_to_block[(location_id, truck_type_id)] = minutes
        yard_to_depot[(location_id, truck_type_id)] = minutes

    for load in loads:
        arc_key = (load.block_id, load.yard_id, load.truck_type_id)
        if arc_key not in block_to_yard:
            raise ValueError(
                "No road or port leg for load "
                f"{load.load_id}: block_id={load.block_id}, yard_id={load.yard_id}, "
                f"truck_type_id={load.truck_type_id}"
            )
        if (load.block_id, load.truck_type_id) not in depot_legs:
            raise ValueError(
                f"No depot leg from depot {depot.id} to block_id={load.block_id} "
                f"for truck_type_id={load.truck_type_id}"
            )
        if (load.yard_id, load.truck_type_id) not in depot_legs:
            raise ValueError(
                f"No depot leg from yard_id={load.yard_id} to depot {depot.id} "
                f"for truck_type_id={load.truck_type_id}"
            )

    return ScheduleProblem(
        scenario_name=scenario.name,
        day=day,
        scenario_day=config.start_day + day - 1,
        horizon_minutes=(
            config.driver_policy.regular_minutes + config.driver_policy.max_overtime_minutes
        ),
        depot_id=depot.id,
        loads=tuple(loads),
        trucks=trucks,
        truck_types=truck_types,
        contractors=contractors,
        pickup_loaders=pickup_loaders,
        delivery_loaders=delivery_loaders,
        loader_service=loader_service,
        block_to_yard=block_to_yard,
        yard_to_block=yard_to_block,
        depot_to_block=depot_to_block,
        yard_to_depot=yard_to_depot,
        regular_minutes=config.driver_policy.regular_minutes,
        max_overtime_minutes=config.driver_policy.max_overtime_minutes,
        overtime_violation_penalty_per_minute=(
            config.driver_policy.overtime_violation_penalty_per_minute
        ),
    )


def _expand_loads(config: HaulingConfig, rows: Iterable[Any]) -> list[Truckload]:
    """Expand Phase I truckload counts into individual :class:`Truckload` records."""
    truck_types = {truck_type.id: truck_type for truck_type in config.truck_types}
    loads: list[Truckload] = []
    counters: dict[tuple[str, str, str, str, str, bool], int] = {}
    for record in rows:
        day = int(record["day"])
        block_id = str(record["block_id"])
        yard_id = str(record["yard_id"])
        contractor_id = str(record["contractor_id"])
        truck_type_id = str(record["truck_type_id"])
        sorted_count = int(record["sorted_truckloads"])
        unsorted_count = int(record["unsorted_truckloads"])
        capacity = truck_types[truck_type_id].capacity_m3
        for is_sorted, count in ((True, sorted_count), (False, unsorted_count)):
            for _ in range(count):
                key = (
                    str(day),
                    block_id,
                    yard_id,
                    contractor_id,
                    truck_type_id,
                    is_sorted,
                )
                index = counters.get(key, 0) + 1
                counters[key] = index
                kind = "s" if is_sorted else "u"
                loads.append(
                    Truckload(
                        load_id=(
                            f"d{day}-{block_id}-{yard_id}-{contractor_id}-"
                            f"{truck_type_id}-{kind}{index}"
                        ),
                        day=day,
                        block_id=block_id,
                        yard_id=yard_id,
                        contractor_id=contractor_id,
                        truck_type_id=truck_type_id,
                        sorted=is_sorted,
                        volume_m3=capacity,
                    )
                )
    return loads


def _expand_marine_loads(config: HaulingConfig, rows: Iterable[Any]) -> list[Truckload]:
    """Expand Phase I marine drayage counts into individual truckload records."""
    truck_types = {truck_type.id: truck_type for truck_type in config.truck_types}
    loads: list[Truckload] = []
    counters: dict[tuple[str, str, str, str, str, bool], int] = {}
    for record in rows:
        day = int(record["day"])
        route_id = str(record["marine_route_id"])
        leg = str(record["leg"])
        block_id = str(record["block_id"])
        yard_id = str(record["yard_id"])
        contractor_id = str(record["contractor_id"])
        truck_type_id = str(record["truck_type_id"])
        sorted_count = int(record["sorted_truckloads"])
        unsorted_count = int(record["unsorted_truckloads"])
        capacity = truck_types[truck_type_id].capacity_m3
        for is_sorted, count in ((True, sorted_count), (False, unsorted_count)):
            for _ in range(count):
                key = (str(day), route_id, leg, contractor_id, truck_type_id, is_sorted)
                index = counters.get(key, 0) + 1
                counters[key] = index
                kind = "s" if is_sorted else "u"
                loads.append(
                    Truckload(
                        load_id=(
                            f"d{day}-{route_id}-{leg}-{contractor_id}-{truck_type_id}-{kind}{index}"
                        ),
                        day=day,
                        block_id=block_id,
                        yard_id=yard_id,
                        contractor_id=contractor_id,
                        truck_type_id=truck_type_id,
                        sorted=is_sorted,
                        volume_m3=capacity,
                        leg=leg,
                        marine_route_id=route_id,
                    )
                )
    return loads
