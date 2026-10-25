"""Phase II continuous-time daily truck routing and scheduling.

This module implements the second phase of Ghotb's decomposition: a mixed-integer program that
assigns Phase I truckloads to compatible trucks and contractors, routes the trucks from a central
depot, and synchronises trucks with stationary loaders at pickup and delivery. Time is continuous,
so the model returns arrival, waiting, service, and return times rather than slot assignments.

The formulation follows Chapter 4 of Ghotb (2023), with the corrections recorded in
``notes/hauling_formulation_audit.md``:

- each truckload is assigned to exactly one compatible truck;
- each truck has a start/end route and a sequence of loads, with MTZ subtour elimination;
- each pickup and delivery load is assigned to one loader at its location;
- loaders have a total order and no overlapping service;
- trucks and loaders share the service start time, so waiting is the gap between arrival and start;
- regular time and overtime are separate variables, so overtime is charged exactly.

The exact MIP is intended for small and medium daily instances. The simulated-annealing solver in
P11.4 handles the large case.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pyomo.environ as pyo
from pyomo.contrib.solver.common.util import NoFeasibleSolutionError
from pyomo.opt import SolverFactory

from fhops.hauling.network import ScheduleProblem, Truckload

__all__ = [
    "SchedulePlan",
    "ScheduleSolveResult",
    "build_schedule_model",
    "simulate_plan",
    "solve_schedule",
    "validate_schedule",
]

_SCHEDULE_COLUMNS = [
    "load_id",
    "truck_id",
    "contractor_id",
    "truck_type_id",
    "block_id",
    "yard_id",
    "sorted",
    "volume_m3",
    "pickup_loader_id",
    "delivery_loader_id",
    "arrival_pickup",
    "pickup_start",
    "pickup_finish",
    "waiting_pickup",
    "arrival_delivery",
    "delivery_start",
    "delivery_finish",
    "waiting_delivery",
    "load_order",
    "truck_return_time",
    "regular_minutes",
    "overtime_minutes",
]
_TRUCK_COLUMNS = [
    "truck_id",
    "contractor_id",
    "truck_type_id",
    "used",
    "loads",
    "return_time",
    "regular_minutes",
    "overtime_minutes",
    "fixed_cost",
    "variable_cost",
    "overtime_cost",
    "total_cost",
]
_LOADER_COLUMNS = [
    "loader_id",
    "kind",
    "location_id",
    "loads",
    "busy_minutes",
    "first_start",
    "last_finish",
]


@dataclass(frozen=True, slots=True)
class SchedulePlan:
    """A route and loader-order plan for a scheduling problem.

    Attributes
    ----------
    routes:
        ``truck_id -> ordered tuple of load ids``.
    pickup_loader / delivery_loader:
        ``load_id -> loader_id``.
    pickup_order / delivery_order:
        ``loader_id -> ordered tuple of load ids``.
    """

    routes: dict[str, tuple[str, ...]]
    pickup_loader: dict[str, str]
    delivery_loader: dict[str, str]
    pickup_order: dict[str, tuple[str, ...]]
    delivery_order: dict[str, tuple[str, ...]]


@dataclass(slots=True)
class ScheduleSolveResult:
    """Result payload for a Phase II solve.

    Attributes
    ----------
    status:
        ``optimal``, ``feasible``, ``infeasible``, ``unbounded``, or ``error``.
    objective / fixed_cost / variable_cost / overtime_cost:
        Objective components.
    schedule / truck_summary / loader_summary:
        DataFrames with the documented schemas.
    plan:
        The route and loader-order plan, when a solution exists.
    solver / termination / runtime_seconds / solver_error:
        Solver provenance and diagnostics.
    """

    status: str
    objective: float | None
    fixed_cost: float | None
    variable_cost: float | None
    overtime_cost: float | None
    schedule: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=_SCHEDULE_COLUMNS))
    truck_summary: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_TRUCK_COLUMNS)
    )
    loader_summary: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=_LOADER_COLUMNS)
    )
    plan: SchedulePlan | None = None
    solver: str = "highs"
    termination: str = ""
    runtime_seconds: float = 0.0
    solver_error: str | None = None


def build_schedule_model(problem: ScheduleProblem) -> pyo.ConcreteModel:
    """Build the Phase II continuous-time scheduling MIP.

    Parameters
    ----------
    problem:
        Normalised scheduling data from :func:`fhops.hauling.network.build_schedule_problem`.

    Returns
    -------
    pyomo.ConcreteModel
        Minimisation model with a single ``objective``.

    Raises
    ------
    ValueError
        When a load has no compatible truck or no loader.
    """
    loads = {load.load_id: load for load in problem.loads}
    trucks = {truck.id: truck for truck in problem.trucks}
    if not loads:
        raise ValueError("ScheduleProblem has no loads")
    if not trucks:
        raise ValueError("ScheduleProblem has no enabled trucks")

    compatible_loads_by_truck: dict[str, list[Truckload]] = {truck_id: [] for truck_id in trucks}
    compatible_trucks_by_load: dict[str, list[str]] = {load_id: [] for load_id in loads}
    for truck_id, truck in trucks.items():
        for load_id, load in loads.items():
            if (
                truck.contractor_id == load.contractor_id
                and truck.truck_type_id == load.truck_type_id
            ):
                compatible_loads_by_truck[truck_id].append(load)
                compatible_trucks_by_load[load_id].append(truck_id)
    for load_id, truck_ids in compatible_trucks_by_load.items():
        if not truck_ids:
            raise ValueError(f"Load {load_id} has no compatible truck")
    for load_id, load in loads.items():
        if not problem.pickup_loaders_for(load):
            raise ValueError(f"Load {load_id} has no pickup loader")
        if not problem.delivery_loaders_for(load):
            raise ValueError(f"Load {load_id} has no delivery loader")

    assign_pairs = [
        (truck_id, load.load_id)
        for truck_id in trucks
        for load in compatible_loads_by_truck[truck_id]
    ]
    order_pairs = [
        (truck_id, left.load_id, right.load_id)
        for truck_id in trucks
        for left in compatible_loads_by_truck[truck_id]
        for right in compatible_loads_by_truck[truck_id]
        if left.load_id != right.load_id
    ]
    pickup_loader_pairs = [
        (load_id, loader_id)
        for load_id, load in loads.items()
        for loader_id in problem.pickup_loaders_for(load)
    ]
    delivery_loader_pairs = [
        (load_id, loader_id)
        for load_id, load in loads.items()
        for loader_id in problem.delivery_loaders_for(load)
    ]

    loads_by_pickup_loader: dict[str, list[str]] = {}
    for load_id, loader_id in pickup_loader_pairs:
        loads_by_pickup_loader.setdefault(loader_id, []).append(load_id)
    loads_by_delivery_loader: dict[str, list[str]] = {}
    for load_id, loader_id in delivery_loader_pairs:
        loads_by_delivery_loader.setdefault(loader_id, []).append(load_id)
    pickup_before_pairs = [
        (left, right, loader_id)
        for loader_id, loader_loads in loads_by_pickup_loader.items()
        for left_index, left in enumerate(loader_loads)
        for right in loader_loads[left_index + 1 :]
    ]
    delivery_before_pairs = [
        (left, right, loader_id)
        for loader_id, loader_loads in loads_by_delivery_loader.items()
        for left_index, left in enumerate(loader_loads)
        for right in loader_loads[left_index + 1 :]
    ]

    model = pyo.ConcreteModel(name=f"hauling-schedule-{problem.scenario_name}")
    model.problem = problem
    model.Loads = pyo.Set(initialize=list(loads))
    model.Trucks = pyo.Set(initialize=list(trucks))
    model.AssignPairs = pyo.Set(initialize=assign_pairs, dimen=2)
    model.OrderPairs = pyo.Set(initialize=order_pairs, dimen=3)
    model.PickupLoaderPairs = pyo.Set(initialize=pickup_loader_pairs, dimen=2)
    model.DeliveryLoaderPairs = pyo.Set(initialize=delivery_loader_pairs, dimen=2)
    model.PickupBeforePairs = pyo.Set(initialize=pickup_before_pairs, dimen=3)
    model.DeliveryBeforePairs = pyo.Set(initialize=delivery_before_pairs, dimen=3)

    horizon = problem.horizon_minutes
    big_m = 2.0 * horizon
    model.z = pyo.Var(model.AssignPairs, domain=pyo.Binary, initialize=0)
    model.start = pyo.Var(model.AssignPairs, domain=pyo.Binary, initialize=0)
    model.end = pyo.Var(model.AssignPairs, domain=pyo.Binary, initialize=0)
    model.order = pyo.Var(model.OrderPairs, domain=pyo.Binary, initialize=0)
    model.used = pyo.Var(model.Trucks, domain=pyo.Binary, initialize=0)
    model.route_pos = pyo.Var(
        model.AssignPairs, domain=pyo.NonNegativeReals, bounds=(0, len(loads))
    )
    model.pick_assign = pyo.Var(model.PickupLoaderPairs, domain=pyo.Binary, initialize=0)
    model.delivery_assign = pyo.Var(model.DeliveryLoaderPairs, domain=pyo.Binary, initialize=0)
    model.pick_before = pyo.Var(model.PickupBeforePairs, domain=pyo.Binary, initialize=0)
    model.delivery_before = pyo.Var(model.DeliveryBeforePairs, domain=pyo.Binary, initialize=0)
    model.arr_pick = pyo.Var(model.AssignPairs, domain=pyo.NonNegativeReals, bounds=(0, horizon))
    model.arr_delivery = pyo.Var(
        model.AssignPairs, domain=pyo.NonNegativeReals, bounds=(0, horizon)
    )
    model.pick_start = pyo.Var(model.Loads, domain=pyo.NonNegativeReals, bounds=(0, horizon))
    model.pick_finish = pyo.Var(model.Loads, domain=pyo.NonNegativeReals, bounds=(0, horizon))
    model.delivery_start = pyo.Var(model.Loads, domain=pyo.NonNegativeReals, bounds=(0, horizon))
    model.delivery_finish = pyo.Var(model.Loads, domain=pyo.NonNegativeReals, bounds=(0, horizon))
    model.return_time = pyo.Var(model.Trucks, domain=pyo.NonNegativeReals, bounds=(0, horizon))
    model.regular = pyo.Var(
        model.Trucks, domain=pyo.NonNegativeReals, bounds=(0, problem.regular_minutes)
    )
    model.overtime = pyo.Var(
        model.Trucks,
        domain=pyo.NonNegativeReals,
        bounds=(0, problem.max_overtime_minutes),
    )

    def pickup_duration_rule(mdl, load_id: str):
        return sum(
            mdl.pick_assign[load_id, loader_id] * problem.loader_service[loader_id]
            for loader_id in problem.pickup_loaders_for(loads[load_id])
        )

    def delivery_duration_rule(mdl, load_id: str):
        return sum(
            mdl.delivery_assign[load_id, loader_id] * problem.loader_service[loader_id]
            for loader_id in problem.delivery_loaders_for(loads[load_id])
        )

    model.pickup_duration = pyo.Expression(model.Loads, rule=pickup_duration_rule)
    model.delivery_duration = pyo.Expression(model.Loads, rule=delivery_duration_rule)

    def load_assignment_rule(mdl, load_id: str):
        return sum(mdl.z[truck_id, load_id] for truck_id in compatible_trucks_by_load[load_id]) == 1

    model.load_assignment = pyo.Constraint(model.Loads, rule=load_assignment_rule)

    def used_link_rule(mdl, truck_id: str, load_id: str):
        return mdl.z[truck_id, load_id] <= mdl.used[truck_id]

    model.used_link = pyo.Constraint(model.AssignPairs, rule=used_link_rule)

    def start_sum_rule(mdl, truck_id: str):
        return (
            sum(mdl.start[truck_id, load.load_id] for load in compatible_loads_by_truck[truck_id])
            == mdl.used[truck_id]
        )

    def end_sum_rule(mdl, truck_id: str):
        return (
            sum(mdl.end[truck_id, load.load_id] for load in compatible_loads_by_truck[truck_id])
            == mdl.used[truck_id]
        )

    model.start_sum = pyo.Constraint(model.Trucks, rule=start_sum_rule)
    model.end_sum = pyo.Constraint(model.Trucks, rule=end_sum_rule)

    def route_out_rule(mdl, truck_id: str, load_id: str):
        incoming = sum(
            mdl.order[truck_id, previous.load_id, load_id]
            for previous in compatible_loads_by_truck[truck_id]
            if previous.load_id != load_id
        )
        return mdl.z[truck_id, load_id] == mdl.start[truck_id, load_id] + incoming

    def route_in_rule(mdl, truck_id: str, load_id: str):
        outgoing = sum(
            mdl.order[truck_id, load_id, following.load_id]
            for following in compatible_loads_by_truck[truck_id]
            if following.load_id != load_id
        )
        return mdl.z[truck_id, load_id] == mdl.end[truck_id, load_id] + outgoing

    model.route_out = pyo.Constraint(model.AssignPairs, rule=route_out_rule)
    model.route_in = pyo.Constraint(model.AssignPairs, rule=route_in_rule)

    def order_link_left_rule(mdl, truck_id: str, left: str, right: str):
        return mdl.order[truck_id, left, right] <= mdl.z[truck_id, left]

    def order_link_right_rule(mdl, truck_id: str, left: str, right: str):
        return mdl.order[truck_id, left, right] <= mdl.z[truck_id, right]

    model.order_link_left = pyo.Constraint(model.OrderPairs, rule=order_link_left_rule)
    model.order_link_right = pyo.Constraint(model.OrderPairs, rule=order_link_right_rule)

    def route_pos_lower_rule(mdl, truck_id: str, load_id: str):
        return mdl.route_pos[truck_id, load_id] >= mdl.z[truck_id, load_id]

    def route_pos_upper_rule(mdl, truck_id: str, load_id: str):
        return mdl.route_pos[truck_id, load_id] <= len(loads) * mdl.z[truck_id, load_id]

    def route_pos_order_rule(mdl, truck_id: str, left: str, right: str):
        return mdl.route_pos[truck_id, right] >= mdl.route_pos[truck_id, left] + 1 - len(loads) * (
            1 - mdl.order[truck_id, left, right]
        )

    model.route_pos_lower = pyo.Constraint(model.AssignPairs, rule=route_pos_lower_rule)
    model.route_pos_upper = pyo.Constraint(model.AssignPairs, rule=route_pos_upper_rule)
    model.route_pos_order = pyo.Constraint(model.OrderPairs, rule=route_pos_order_rule)

    def pickup_loader_sum_rule(mdl, load_id: str):
        return (
            sum(
                mdl.pick_assign[load_id, loader_id]
                for loader_id in problem.pickup_loaders_for(loads[load_id])
            )
            == 1
        )

    def delivery_loader_sum_rule(mdl, load_id: str):
        return (
            sum(
                mdl.delivery_assign[load_id, loader_id]
                for loader_id in problem.delivery_loaders_for(loads[load_id])
            )
            == 1
        )

    model.pickup_loader_sum = pyo.Constraint(model.Loads, rule=pickup_loader_sum_rule)
    model.delivery_loader_sum = pyo.Constraint(model.Loads, rule=delivery_loader_sum_rule)

    def pickup_no_overlap_rule(mdl, left: str, right: str, loader_id: str):
        assigned = 2 - mdl.pick_assign[left, loader_id] - mdl.pick_assign[right, loader_id]
        return (
            mdl.pick_start[left] + mdl.pickup_duration[left]
            <= mdl.pick_start[right]
            + big_m * (1 - mdl.pick_before[left, right, loader_id])
            + big_m * assigned
        )

    def pickup_no_overlap_reverse_rule(mdl, left: str, right: str, loader_id: str):
        assigned = 2 - mdl.pick_assign[left, loader_id] - mdl.pick_assign[right, loader_id]
        return (
            mdl.pick_start[right] + mdl.pickup_duration[right]
            <= mdl.pick_start[left]
            + big_m * mdl.pick_before[left, right, loader_id]
            + big_m * assigned
        )

    def delivery_no_overlap_rule(mdl, left: str, right: str, loader_id: str):
        assigned = 2 - mdl.delivery_assign[left, loader_id] - mdl.delivery_assign[right, loader_id]
        return (
            mdl.delivery_start[left] + mdl.delivery_duration[left]
            <= mdl.delivery_start[right]
            + big_m * (1 - mdl.delivery_before[left, right, loader_id])
            + big_m * assigned
        )

    def delivery_no_overlap_reverse_rule(mdl, left: str, right: str, loader_id: str):
        assigned = 2 - mdl.delivery_assign[left, loader_id] - mdl.delivery_assign[right, loader_id]
        return (
            mdl.delivery_start[right] + mdl.delivery_duration[right]
            <= mdl.delivery_start[left]
            + big_m * mdl.delivery_before[left, right, loader_id]
            + big_m * assigned
        )

    model.pickup_no_overlap = pyo.Constraint(model.PickupBeforePairs, rule=pickup_no_overlap_rule)
    model.pickup_no_overlap_reverse = pyo.Constraint(
        model.PickupBeforePairs, rule=pickup_no_overlap_reverse_rule
    )
    model.delivery_no_overlap = pyo.Constraint(
        model.DeliveryBeforePairs, rule=delivery_no_overlap_rule
    )
    model.delivery_no_overlap_reverse = pyo.Constraint(
        model.DeliveryBeforePairs, rule=delivery_no_overlap_reverse_rule
    )

    def start_depot_rule(mdl, truck_id: str, load_id: str):
        return mdl.arr_pick[truck_id, load_id] >= (
            problem.depot_to_load_minutes(loads[load_id])
            - big_m * (1 - mdl.start[truck_id, load_id])
        )

    def order_travel_rule(mdl, truck_id: str, left: str, right: str):
        return mdl.arr_pick[truck_id, right] >= (
            mdl.delivery_finish[left]
            + problem.empty_travel_minutes(loads[left], loads[right])
            - big_m * (1 - mdl.order[truck_id, left, right])
        )

    def arrival_pickup_rule(mdl, truck_id: str, load_id: str):
        return mdl.arr_pick[truck_id, load_id] <= (
            mdl.pick_start[load_id] + big_m * (1 - mdl.z[truck_id, load_id])
        )

    def pickup_finish_rule(mdl, load_id: str):
        return mdl.pick_finish[load_id] == mdl.pick_start[load_id] + mdl.pickup_duration[load_id]

    def arrival_delivery_rule(mdl, truck_id: str, load_id: str):
        return mdl.arr_delivery[truck_id, load_id] >= (
            mdl.pick_finish[load_id]
            + problem.load_travel_minutes(loads[load_id])
            - big_m * (1 - mdl.z[truck_id, load_id])
        )

    def delivery_arrival_start_rule(mdl, truck_id: str, load_id: str):
        return mdl.arr_delivery[truck_id, load_id] <= (
            mdl.delivery_start[load_id] + big_m * (1 - mdl.z[truck_id, load_id])
        )

    def delivery_finish_rule(mdl, load_id: str):
        return (
            mdl.delivery_finish[load_id]
            == mdl.delivery_start[load_id] + mdl.delivery_duration[load_id]
        )

    def return_to_depot_rule(mdl, truck_id: str, load_id: str):
        return mdl.return_time[truck_id] >= (
            mdl.delivery_finish[load_id]
            + problem.load_to_depot_minutes(loads[load_id])
            - big_m * (1 - mdl.end[truck_id, load_id])
        )

    def time_definition_rule(mdl, truck_id: str):
        return mdl.regular[truck_id] + mdl.overtime[truck_id] == mdl.return_time[truck_id]

    model.start_depot = pyo.Constraint(model.AssignPairs, rule=start_depot_rule)
    model.order_travel = pyo.Constraint(model.OrderPairs, rule=order_travel_rule)
    model.arrival_pickup = pyo.Constraint(model.AssignPairs, rule=arrival_pickup_rule)
    model.pickup_finish_def = pyo.Constraint(model.Loads, rule=pickup_finish_rule)
    model.arrival_delivery = pyo.Constraint(model.AssignPairs, rule=arrival_delivery_rule)
    model.delivery_arrival_start = pyo.Constraint(
        model.AssignPairs, rule=delivery_arrival_start_rule
    )
    model.delivery_finish_def = pyo.Constraint(model.Loads, rule=delivery_finish_rule)
    model.return_to_depot = pyo.Constraint(model.AssignPairs, rule=return_to_depot_rule)
    model.time_definition = pyo.Constraint(model.Trucks, rule=time_definition_rule)

    model.fixed_cost_expr = sum(
        problem.truck_types[trucks[truck_id].truck_type_id].fixed_cost * model.used[truck_id]
        for truck_id in trucks
    )
    model.variable_cost_expr = sum(
        problem.truck_types[trucks[truck_id].truck_type_id].variable_cost_per_minute
        * model.regular[truck_id]
        for truck_id in trucks
    )
    model.overtime_cost_expr = sum(
        problem.truck_types[trucks[truck_id].truck_type_id].overtime_cost_per_minute
        * model.overtime[truck_id]
        for truck_id in trucks
    )
    model.objective = pyo.Objective(
        expr=model.fixed_cost_expr + model.variable_cost_expr + model.overtime_cost_expr,
        sense=pyo.minimize,
    )
    return model


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


def solve_schedule(
    problem: ScheduleProblem,
    *,
    solver: str = "highs",
    time_limit: float | None = None,
    gap: float | None = None,
    tee: bool = False,
    solver_options: dict[str, Any] | None = None,
) -> ScheduleSolveResult:
    """Solve the Phase II scheduling MIP.

    Parameters
    ----------
    problem:
        Normalised scheduling data.
    solver:
        Pyomo solver name. ``highs`` is the default; ``gurobi`` is used when installed and licensed.
    time_limit:
        Optional solver time limit in seconds.
    gap:
        Optional relative MIP gap target.
    tee:
        Stream the solver log.
    solver_options:
        Additional solver options forwarded verbatim.

    Returns
    -------
    ScheduleSolveResult
        Schedule, truck summary, loader summary, plan, objective components, and solver
        provenance.
    """
    model = build_schedule_model(problem)
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
        return ScheduleSolveResult(
            status="infeasible",
            objective=None,
            fixed_cost=None,
            variable_cost=None,
            overtime_cost=None,
            solver=solver,
            runtime_seconds=time.perf_counter() - solve_start,
            solver_error=f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 - the result payload carries the diagnostic
        return ScheduleSolveResult(
            status="error",
            objective=None,
            fixed_cost=None,
            variable_cost=None,
            overtime_cost=None,
            solver=solver,
            runtime_seconds=time.perf_counter() - solve_start,
            solver_error=f"{type(exc).__name__}: {exc}",
        )

    runtime = time.perf_counter() - solve_start
    termination = str(results.solver.termination_condition).lower()
    if termination in {"optimal", "locallyoptimal", "globallyoptimal"}:
        status = "optimal"
    elif termination == "feasible":
        status = "feasible"
    elif termination in {"infeasible", "infeasibleorunbounded"}:
        status = "infeasible"
    elif termination == "unbounded":
        status = "unbounded"
    else:
        status = "error"
    if status not in {"optimal", "feasible"}:
        message = getattr(results.solver, "message", None)
        return ScheduleSolveResult(
            status=status,
            objective=None,
            fixed_cost=None,
            variable_cost=None,
            overtime_cost=None,
            solver=solver,
            termination=termination,
            runtime_seconds=runtime,
            solver_error=str(message) if message else None,
        )
    return _extract_schedule_result(problem, model, status, termination, solver, runtime)


def _extract_schedule_result(
    problem: ScheduleProblem,
    model: pyo.ConcreteModel,
    status: str,
    termination: str,
    solver: str,
    runtime: float,
) -> ScheduleSolveResult:
    """Convert a solved scheduling model into a :class:`ScheduleSolveResult`."""
    loads = {load.load_id: load for load in problem.loads}
    trucks = {truck.id: truck for truck in problem.trucks}
    assigned_truck: dict[str, str] = {}
    pickup_loader: dict[str, str] = {}
    delivery_loader: dict[str, str] = {}
    for load_id in loads:
        for (truck_id, candidate_load), variable in model.z.items():
            if candidate_load == load_id and float(pyo.value(variable)) > 0.5:
                assigned_truck[load_id] = truck_id
                break
        for (candidate_load, loader_id), variable in model.pick_assign.items():
            if candidate_load == load_id and float(pyo.value(variable)) > 0.5:
                pickup_loader[load_id] = loader_id
                break
        for (candidate_load, loader_id), variable in model.delivery_assign.items():
            if candidate_load == load_id and float(pyo.value(variable)) > 0.5:
                delivery_loader[load_id] = loader_id
                break

    route_position: dict[tuple[str, str], float] = {
        (truck_id, load_id): float(pyo.value(variable))
        for (truck_id, load_id), variable in model.route_pos.items()
    }
    routes: dict[str, tuple[str, ...]] = {}
    for truck_id in trucks:
        route_loads = [
            load_id for load_id, assigned in assigned_truck.items() if assigned == truck_id
        ]
        route_loads.sort(key=lambda load_id: route_position[(truck_id, load_id)])
        routes[truck_id] = tuple(route_loads)

    pickup_order: dict[str, tuple[str, ...]] = {}
    for loader_id in problem.loader_service:
        load_ids = [load_id for load_id, assigned in pickup_loader.items() if assigned == loader_id]
        load_ids.sort(key=lambda load_id: float(pyo.value(model.pick_start[load_id])))
        if load_ids:
            pickup_order[loader_id] = tuple(load_ids)
    delivery_order: dict[str, tuple[str, ...]] = {}
    for loader_id in problem.loader_service:
        load_ids = [
            load_id for load_id, assigned in delivery_loader.items() if assigned == loader_id
        ]
        load_ids.sort(key=lambda load_id: float(pyo.value(model.delivery_start[load_id])))
        if load_ids:
            delivery_order[loader_id] = tuple(load_ids)

    schedule_rows: list[dict[str, Any]] = []
    for load_id, load in loads.items():
        truck_id = assigned_truck[load_id]
        pick_start = float(pyo.value(model.pick_start[load_id]))
        pick_finish = float(pyo.value(model.pick_finish[load_id]))
        delivery_start = float(pyo.value(model.delivery_start[load_id]))
        delivery_finish = float(pyo.value(model.delivery_finish[load_id]))
        arrival_pickup = float(pyo.value(model.arr_pick[truck_id, load_id]))
        arrival_delivery = float(pyo.value(model.arr_delivery[truck_id, load_id]))
        schedule_rows.append(
            {
                "load_id": load_id,
                "truck_id": truck_id,
                "contractor_id": load.contractor_id,
                "truck_type_id": load.truck_type_id,
                "block_id": load.block_id,
                "yard_id": load.yard_id,
                "sorted": load.sorted,
                "volume_m3": load.volume_m3,
                "pickup_loader_id": pickup_loader[load_id],
                "delivery_loader_id": delivery_loader[load_id],
                "arrival_pickup": arrival_pickup,
                "pickup_start": pick_start,
                "pickup_finish": pick_finish,
                "waiting_pickup": max(0.0, pick_start - arrival_pickup),
                "arrival_delivery": arrival_delivery,
                "delivery_start": delivery_start,
                "delivery_finish": delivery_finish,
                "waiting_delivery": max(0.0, delivery_start - arrival_delivery),
                "load_order": int(round(route_position[(truck_id, load_id)])),
                "truck_return_time": float(pyo.value(model.return_time[truck_id])),
                "regular_minutes": float(pyo.value(model.regular[truck_id])),
                "overtime_minutes": float(pyo.value(model.overtime[truck_id])),
            }
        )

    truck_rows: list[dict[str, Any]] = []
    for truck_id, truck in trucks.items():
        truck_type = problem.truck_types[truck.truck_type_id]
        used = float(pyo.value(model.used[truck_id])) > 0.5
        loads_count = len(routes[truck_id])
        regular = float(pyo.value(model.regular[truck_id]))
        overtime = float(pyo.value(model.overtime[truck_id]))
        fixed = truck_type.fixed_cost if used else 0.0
        variable = truck_type.variable_cost_per_minute * regular
        overtime_cost = truck_type.overtime_cost_per_minute * overtime
        truck_rows.append(
            {
                "truck_id": truck_id,
                "contractor_id": truck.contractor_id,
                "truck_type_id": truck.truck_type_id,
                "used": used,
                "loads": loads_count,
                "return_time": float(pyo.value(model.return_time[truck_id])),
                "regular_minutes": regular,
                "overtime_minutes": overtime,
                "fixed_cost": fixed,
                "variable_cost": variable,
                "overtime_cost": overtime_cost,
                "total_cost": fixed + variable + overtime_cost,
            }
        )

    loader_rows: list[dict[str, Any]] = []
    for loader_id, service in problem.loader_service.items():
        load_ids = [load_id for load_id, assigned in pickup_loader.items() if assigned == loader_id]
        kind = "pickup"
        starts = [float(pyo.value(model.pick_start[load_id])) for load_id in load_ids]
        finishes = [float(pyo.value(model.pick_finish[load_id])) for load_id in load_ids]
        if not load_ids:
            load_ids = [
                load_id for load_id, assigned in delivery_loader.items() if assigned == loader_id
            ]
            kind = "delivery"
            starts = [float(pyo.value(model.delivery_start[load_id])) for load_id in load_ids]
            finishes = [float(pyo.value(model.delivery_finish[load_id])) for load_id in load_ids]
        location = ""
        for load_id in load_ids:
            load = loads[load_id]
            location = load.block_id if kind == "pickup" else load.yard_id
            break
        loader_rows.append(
            {
                "loader_id": loader_id,
                "kind": kind,
                "location_id": location,
                "loads": len(load_ids),
                "busy_minutes": len(load_ids) * service,
                "first_start": min(starts) if starts else 0.0,
                "last_finish": max(finishes) if finishes else 0.0,
            }
        )

    schedule = (
        pd.DataFrame(schedule_rows, columns=_SCHEDULE_COLUMNS)
        .sort_values(["load_id"])
        .reset_index(drop=True)
    )
    truck_summary = (
        pd.DataFrame(truck_rows, columns=_TRUCK_COLUMNS)
        .sort_values(["truck_id"])
        .reset_index(drop=True)
    )
    loader_summary = (
        pd.DataFrame(loader_rows, columns=_LOADER_COLUMNS)
        .sort_values(["loader_id"])
        .reset_index(drop=True)
    )
    plan = SchedulePlan(
        routes=routes,
        pickup_loader=pickup_loader,
        delivery_loader=delivery_loader,
        pickup_order=pickup_order,
        delivery_order=delivery_order,
    )

    return ScheduleSolveResult(
        status=status,
        objective=float(pyo.value(model.objective)),
        fixed_cost=float(pyo.value(model.fixed_cost_expr)),
        variable_cost=float(pyo.value(model.variable_cost_expr)),
        overtime_cost=float(pyo.value(model.overtime_cost_expr)),
        schedule=schedule,
        truck_summary=truck_summary,
        loader_summary=loader_summary,
        plan=plan,
        solver=solver,
        termination=termination,
        runtime_seconds=runtime,
    )


def simulate_plan(problem: ScheduleProblem, plan: SchedulePlan) -> pd.DataFrame:
    """Recompute the earliest schedule for a fixed route and loader order.

    The simulator solves the max-plus system defined by the truck routes and loader sequences by
    fixed-point iteration. It is independent of the MIP's time variables and is used as a
    verification oracle for the model.

    Parameters
    ----------
    problem:
        Scheduling data.
    plan:
        Truck routes and loader orders.

    Returns
    -------
    pandas.DataFrame
        One row per load with ``arrival_pickup``, ``pickup_start``, ``pickup_finish``,
        ``arrival_delivery``, ``delivery_start``, ``delivery_finish``, and ``load_order``.
    """
    loads = {load.load_id: load for load in problem.loads}
    previous_in_route: dict[str, str | None] = {}
    route_position: dict[str, int] = {}
    for _truck_id, route in plan.routes.items():
        route_previous: str | None = None
        for position, load_id in enumerate(route, start=1):
            previous_in_route[load_id] = route_previous
            route_position[load_id] = position
            route_previous = load_id

    previous_in_pickup: dict[str, str | None] = {}
    for _loader_id, order in plan.pickup_order.items():
        pickup_previous: str | None = None
        for load_id in order:
            previous_in_pickup[load_id] = pickup_previous
            pickup_previous = load_id
    previous_in_delivery: dict[str, str | None] = {}
    for _loader_id, order in plan.delivery_order.items():
        delivery_previous: str | None = None
        for load_id in order:
            previous_in_delivery[load_id] = delivery_previous
            delivery_previous = load_id

    times: dict[str, dict[str, float]] = {
        load_id: {
            "arrival_pickup": 0.0,
            "pickup_start": 0.0,
            "pickup_finish": 0.0,
            "arrival_delivery": 0.0,
            "delivery_start": 0.0,
            "delivery_finish": 0.0,
        }
        for load_id in loads
    }
    for _ in range(1000):
        changed = False
        for load_id, load in loads.items():
            previous = previous_in_route[load_id]
            if previous is None:
                arrival_pickup = problem.depot_to_load_minutes(load)
            else:
                arrival_pickup = times[previous]["delivery_finish"] + problem.empty_travel_minutes(
                    loads[previous], load
                )
            pickup_previous = previous_in_pickup.get(load_id)
            loader_available = (
                0.0 if pickup_previous is None else times[pickup_previous]["pickup_finish"]
            )
            pickup_start = max(arrival_pickup, loader_available)
            pickup_finish = pickup_start + problem.loader_service[plan.pickup_loader[load_id]]
            arrival_delivery = pickup_finish + problem.load_travel_minutes(load)
            delivery_previous = previous_in_delivery.get(load_id)
            delivery_available = (
                0.0 if delivery_previous is None else times[delivery_previous]["delivery_finish"]
            )
            delivery_start = max(arrival_delivery, delivery_available)
            delivery_finish = delivery_start + problem.loader_service[plan.delivery_loader[load_id]]
            updated = {
                "arrival_pickup": arrival_pickup,
                "pickup_start": pickup_start,
                "pickup_finish": pickup_finish,
                "arrival_delivery": arrival_delivery,
                "delivery_start": delivery_start,
                "delivery_finish": delivery_finish,
            }
            for key, value in updated.items():
                if abs(times[load_id][key] - value) > 1e-6:
                    changed = True
                    times[load_id][key] = value
        if not changed:
            break

    rows = []
    for load_id, load in loads.items():
        rows.append(
            {
                "load_id": load_id,
                "truck_id": next(
                    truck_id for truck_id, route in plan.routes.items() if load_id in route
                ),
                "arrival_pickup": times[load_id]["arrival_pickup"],
                "pickup_start": times[load_id]["pickup_start"],
                "pickup_finish": times[load_id]["pickup_finish"],
                "arrival_delivery": times[load_id]["arrival_delivery"],
                "delivery_start": times[load_id]["delivery_start"],
                "delivery_finish": times[load_id]["delivery_finish"],
                "load_order": route_position[load_id],
            }
        )
    return pd.DataFrame(rows).sort_values("load_id").reset_index(drop=True)


def validate_schedule(problem: ScheduleProblem, schedule: pd.DataFrame) -> list[str]:
    """Check a schedule for compatibility, synchronisation, and overlap violations.

    Parameters
    ----------
    problem:
        Scheduling data.
    schedule:
        A schedule table, usually ``ScheduleSolveResult.schedule``.

    Returns
    -------
    list[str]
        Human-readable violations. An empty list means the schedule is feasible.
    """
    violations: list[str] = []
    loads = {load.load_id: load for load in problem.loads}
    required = {
        "load_id",
        "truck_id",
        "pickup_loader_id",
        "delivery_loader_id",
        "arrival_pickup",
        "pickup_start",
        "pickup_finish",
        "arrival_delivery",
        "delivery_start",
        "delivery_finish",
    }
    missing = required - set(schedule.columns)
    if missing:
        return [f"schedule is missing columns: {sorted(missing)}"]

    assigned_trucks: set[str] = set()
    for _, row in schedule.iterrows():
        load = loads.get(str(row["load_id"]))
        if load is None:
            violations.append(f"unknown load_id={row['load_id']}")
            continue
        truck = next((truck for truck in problem.trucks if truck.id == row["truck_id"]), None)
        if truck is None:
            violations.append(f"load {load.load_id} references unknown truck {row['truck_id']}")
        elif truck.contractor_id != load.contractor_id or truck.truck_type_id != load.truck_type_id:
            violations.append(f"load {load.load_id} assigned to incompatible truck {truck.id}")
        if row["pickup_loader_id"] not in problem.pickup_loaders_for(load):
            violations.append(f"load {load.load_id} has an invalid pickup loader")
        if row["delivery_loader_id"] not in problem.delivery_loaders_for(load):
            violations.append(f"load {load.load_id} has an invalid delivery loader")
        if row["pickup_start"] + 1e-6 < row["arrival_pickup"]:
            violations.append(f"load {load.load_id} pickup starts before the truck arrives")
        if row["delivery_start"] + 1e-6 < row["arrival_delivery"]:
            violations.append(f"load {load.load_id} delivery starts before the truck arrives")
        expected_pick_finish = row["pickup_start"] + problem.loader_service[row["pickup_loader_id"]]
        if abs(row["pickup_finish"] - expected_pick_finish) > 1e-5:
            violations.append(f"load {load.load_id} pickup finish is inconsistent")
        expected_delivery_finish = (
            row["delivery_start"] + problem.loader_service[row["delivery_loader_id"]]
        )
        if abs(row["delivery_finish"] - expected_delivery_finish) > 1e-5:
            violations.append(f"load {load.load_id} delivery finish is inconsistent")
        assigned_trucks.add(str(row["truck_id"]))

    for truck_id in assigned_trucks:
        truck_rows = schedule[schedule["truck_id"] == truck_id].sort_values("load_order")
        previous = None
        for _, row in truck_rows.iterrows():
            load = loads[str(row["load_id"])]
            if previous is None:
                if row["arrival_pickup"] + 1e-6 < problem.depot_to_load_minutes(load):
                    violations.append(
                        f"truck {truck_id} leaves the depot too late for {load.load_id}"
                    )
            else:
                previous_load = loads[str(previous["load_id"])]
                required_arrival = previous["delivery_finish"] + problem.empty_travel_minutes(
                    previous_load, load
                )
                if row["arrival_pickup"] + 1e-6 < required_arrival:
                    violations.append(
                        f"truck {truck_id} cannot reach {load.load_id} after {previous_load.load_id}"
                    )
            previous = row
        if previous is not None:
            last_load = loads[str(previous["load_id"])]
            required_return = previous["delivery_finish"] + problem.load_to_depot_minutes(last_load)
            if previous["truck_return_time"] + 1e-6 < required_return:
                violations.append(f"truck {truck_id} return time is too early")

    for loader_id in problem.loader_service:
        for kind, column in (("pickup", "pickup_loader_id"), ("delivery", "delivery_loader_id")):
            rows = schedule[schedule[column] == loader_id].sort_values(f"{kind}_start")
            previous_finish = None
            for _, row in rows.iterrows():
                if previous_finish is not None and row[f"{kind}_start"] + 1e-6 < previous_finish:
                    violations.append(f"loader {loader_id} has overlapping {kind} service")
                previous_finish = row[f"{kind}_finish"]
    return violations
