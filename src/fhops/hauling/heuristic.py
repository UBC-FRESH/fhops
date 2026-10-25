"""Phase III simulated annealing for daily log-truck scheduling.

This module implements the solution approach of Ghotb (2023), Chapter 5: a permutation-based
representation of truck routes, a shortest-processing-time (SPT) schedule decoder, swap/reversion/
insertion neighbourhoods, and a geometric cooling schedule. It is the large-instance path; the
exact MIP in :mod:`fhops.hauling.schedule` remains the oracle for small days.

The decoder is deliberately built on top of :func:`fhops.hauling.schedule.simulate_plan`, so the
timing logic is shared with the exact-model verification oracle. It derives loader orders from
projected arrival times (SPT) and then recomputes the earliest schedule for the fixed routes and
loader orders.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from fhops.hauling.network import ScheduleProblem, Truckload
from fhops.hauling.schedule import SchedulePlan, simulate_plan

__all__ = [
    "HaulingSAResult",
    "SAConfig",
    "SolutionEvaluation",
    "decode_routes",
    "evaluate_routes",
    "initial_solution",
    "solve_sa",
    "summarize_sa_result",
]

RouteSolution = dict[str, tuple[str, ...]]
_OPERATORS = ("swap", "reversion", "insertion")
_HISTORY_COLUMNS = [
    "iteration",
    "temperature",
    "current_objective",
    "best_objective",
    "accepted",
    "operator",
]


@dataclass(slots=True)
class SAConfig:
    """Simulated-annealing configuration.

    Attributes
    ----------
    initial_temperature:
        Starting temperature. The thesis Taguchi calibration selects 300.
    min_temperature_ratio:
        Stop when ``temperature <= initial_temperature * min_temperature_ratio``. The thesis uses
        ``0.0005``.
    cooling_rate:
        Geometric cooling factor. The thesis uses ``0.95``.
    iterations_per_temperature:
        Moves evaluated at each temperature. The thesis uses 90.
    max_iterations:
        Optional hard cap on evaluated moves. ``None`` uses the temperature schedule.
    time_limit_seconds:
        Optional wall-clock cap. ``None`` disables it.
    seed:
        RNG seed for reproducibility.
    operator_weights:
        Relative weights for ``swap``, ``reversion``, and ``insertion``. Must be non-negative and
        not all zero.
    overtime_violation_penalty_per_minute:
        Penalty per minute above the daily horizon. ``None`` uses the scenario's driver policy.
    """

    initial_temperature: float = 300.0
    min_temperature_ratio: float = 0.0005
    cooling_rate: float = 0.95
    iterations_per_temperature: int = 90
    max_iterations: int | None = None
    time_limit_seconds: float | None = None
    seed: int = 42
    operator_weights: dict[str, float] = field(
        default_factory=lambda: {"swap": 1.0, "reversion": 1.0, "insertion": 1.0}
    )
    overtime_violation_penalty_per_minute: float | None = None

    def __post_init__(self) -> None:
        if self.initial_temperature <= 0:
            raise ValueError("initial_temperature must be > 0")
        if not 0 < self.min_temperature_ratio < 1:
            raise ValueError("min_temperature_ratio must be in (0, 1)")
        if not 0 < self.cooling_rate < 1:
            raise ValueError("cooling_rate must be in (0, 1)")
        if self.iterations_per_temperature < 1:
            raise ValueError("iterations_per_temperature must be >= 1")
        unknown = set(self.operator_weights) - set(_OPERATORS)
        if unknown:
            raise ValueError(f"Unknown SA operators: {sorted(unknown)}")
        if any(weight < 0 for weight in self.operator_weights.values()):
            raise ValueError("operator weights must be non-negative")
        if sum(self.operator_weights.values()) <= 0:
            raise ValueError("at least one operator weight must be positive")


@dataclass(slots=True)
class SolutionEvaluation:
    """Cost and schedule evaluation of one route solution.

    Attributes
    ----------
    objective:
        Total cost including fixed, variable, overtime, and overtime-violation penalty.
    fixed_cost / variable_cost / overtime_cost / violation_cost:
        Cost components.
    violation_minutes:
        Total minutes above ``regular_minutes + max_overtime_minutes``.
    schedule / truck_summary / loader_summary:
        DataFrames with the Phase II output schemas.
    plan:
        The decoded route and loader-order plan.
    """

    objective: float
    fixed_cost: float
    variable_cost: float
    overtime_cost: float
    violation_cost: float
    violation_minutes: float
    schedule: pd.DataFrame
    truck_summary: pd.DataFrame
    loader_summary: pd.DataFrame
    plan: SchedulePlan


@dataclass(slots=True)
class HaulingSAResult:
    """Result payload for a simulated-annealing run.

    Attributes
    ----------
    status:
        ``feasible`` when a schedule was evaluated; ``error`` only for an invalid problem.
    objective / fixed_cost / variable_cost / overtime_cost / violation_cost:
        Best-solution cost components.
    violation_minutes:
        Best-solution overtime violation.
    schedule / truck_summary / loader_summary / plan:
        Best-solution artefacts.
    iterations / accepted / runtime_seconds / seed:
        Search provenance.
    history:
        Per-move objective trace.
    """

    status: str
    objective: float | None
    fixed_cost: float | None
    variable_cost: float | None
    overtime_cost: float | None
    violation_cost: float | None
    violation_minutes: float | None
    schedule: pd.DataFrame
    truck_summary: pd.DataFrame
    loader_summary: pd.DataFrame
    plan: SchedulePlan | None
    iterations: int
    accepted: int
    runtime_seconds: float
    seed: int
    history: pd.DataFrame
    solver_error: str | None = None


def decode_routes(problem: ScheduleProblem, routes: RouteSolution) -> SchedulePlan:
    """Decode a route solution into a loader assignment and SPT loader order.

    Parameters
    ----------
    problem:
        Scheduling data.
    routes:
        ``truck_id -> ordered tuple of load ids``. Every load must appear exactly once.

    Returns
    -------
    SchedulePlan
        Loader assignments and pickup/delivery orders derived from projected arrival times.

    Raises
    ------
    ValueError
        When a route references an unknown load, a load is missing, or a load appears more than
        once.
    """
    loads = {load.load_id: load for load in problem.loads}
    seen: set[str] = set()
    for truck_id, route in routes.items():
        if truck_id not in {truck.id for truck in problem.trucks}:
            raise ValueError(f"Route references unknown truck_id={truck_id}")
        for load_id in route:
            if load_id not in loads:
                raise ValueError(f"Route references unknown load_id={load_id}")
            if load_id in seen:
                raise ValueError(f"Route contains load_id={load_id} more than once")
            seen.add(load_id)
    missing = set(loads) - seen
    if missing:
        raise ValueError(f"Route solution is missing loads: {sorted(missing)}")

    pickup_loader = {
        load_id: min(
            problem.pickup_loaders_for(load),
            key=lambda loader_id: (problem.loader_service[loader_id], loader_id),
        )
        for load_id, load in loads.items()
    }
    delivery_loader = {
        load_id: min(
            problem.delivery_loaders_for(load),
            key=lambda loader_id: (problem.loader_service[loader_id], loader_id),
        )
        for load_id, load in loads.items()
    }

    raw_pickup: dict[str, float] = {}
    raw_delivery: dict[str, float] = {}
    for route in routes.values():
        previous: Truckload | None = None
        previous_delivery_finish = 0.0
        for load_id in route:
            load = loads[load_id]
            arrival_pickup = (
                problem.depot_to_load_minutes(load)
                if previous is None
                else previous_delivery_finish + problem.empty_travel_minutes(previous, load)
            )
            pickup_finish = arrival_pickup + problem.loader_service[pickup_loader[load_id]]
            arrival_delivery = pickup_finish + problem.load_travel_minutes(load)
            delivery_finish = arrival_delivery + problem.loader_service[delivery_loader[load_id]]
            raw_pickup[load_id] = arrival_pickup
            raw_delivery[load_id] = arrival_delivery
            previous = load
            previous_delivery_finish = delivery_finish

    pickup_order: dict[str, tuple[str, ...]] = {}
    for loader_id in problem.loader_service:
        loader_loads = [
            load_id for load_id, assigned in pickup_loader.items() if assigned == loader_id
        ]
        if loader_loads:
            pickup_order[loader_id] = tuple(
                sorted(loader_loads, key=lambda load_id: (raw_pickup[load_id], load_id))
            )
    delivery_order: dict[str, tuple[str, ...]] = {}
    for loader_id in problem.loader_service:
        loader_loads = [
            load_id for load_id, assigned in delivery_loader.items() if assigned == loader_id
        ]
        if loader_loads:
            delivery_order[loader_id] = tuple(
                sorted(loader_loads, key=lambda load_id: (raw_delivery[load_id], load_id))
            )

    return SchedulePlan(
        routes={truck_id: tuple(route) for truck_id, route in routes.items()},
        pickup_loader=pickup_loader,
        delivery_loader=delivery_loader,
        pickup_order=pickup_order,
        delivery_order=delivery_order,
    )


def evaluate_routes(
    problem: ScheduleProblem,
    routes: RouteSolution,
    config: SAConfig | None = None,
) -> SolutionEvaluation:
    """Evaluate a route solution with the SPT decoder and cost model.

    Parameters
    ----------
    problem:
        Scheduling data.
    routes:
        Truck routes.
    config:
        Optional SA configuration for the overtime-violation penalty. ``None`` uses the scenario's
        driver policy.

    Returns
    -------
    SolutionEvaluation
        Cost components, schedule, truck/loader summaries, and the decoded plan.
    """
    config = config or SAConfig()
    plan = decode_routes(problem, routes)
    timing = simulate_plan(problem, plan)
    loads = {load.load_id: load for load in problem.loads}
    trucks = {truck.id: truck for truck in problem.trucks}
    penalty_rate = (
        config.overtime_violation_penalty_per_minute
        if config.overtime_violation_penalty_per_minute is not None
        else problem.overtime_violation_penalty_per_minute
    )

    rows: list[dict[str, Any]] = []
    truck_returns: dict[str, float] = {}
    for truck_id, route in routes.items():
        if not route:
            truck_returns[truck_id] = 0.0
            continue
        last_load = loads[route[-1]]
        last_row = timing[timing["load_id"] == last_load.load_id].iloc[0]
        truck_returns[truck_id] = float(
            last_row["delivery_finish"]
        ) + problem.load_to_depot_minutes(last_load)

    for _, timing_row in timing.iterrows():
        load = loads[str(timing_row["load_id"])]
        truck_id = str(timing_row["truck_id"])
        return_time = truck_returns[truck_id]
        regular = min(return_time, problem.regular_minutes)
        overtime = min(
            max(0.0, return_time - problem.regular_minutes),
            problem.max_overtime_minutes,
        )
        rows.append(
            {
                "load_id": load.load_id,
                "truck_id": truck_id,
                "contractor_id": load.contractor_id,
                "truck_type_id": load.truck_type_id,
                "block_id": load.block_id,
                "yard_id": load.yard_id,
                "sorted": load.sorted,
                "volume_m3": load.volume_m3,
                "pickup_loader_id": plan.pickup_loader[load.load_id],
                "delivery_loader_id": plan.delivery_loader[load.load_id],
                "arrival_pickup": float(timing_row["arrival_pickup"]),
                "pickup_start": float(timing_row["pickup_start"]),
                "pickup_finish": float(timing_row["pickup_finish"]),
                "waiting_pickup": max(
                    0.0, float(timing_row["pickup_start"]) - float(timing_row["arrival_pickup"])
                ),
                "arrival_delivery": float(timing_row["arrival_delivery"]),
                "delivery_start": float(timing_row["delivery_start"]),
                "delivery_finish": float(timing_row["delivery_finish"]),
                "waiting_delivery": max(
                    0.0,
                    float(timing_row["delivery_start"]) - float(timing_row["arrival_delivery"]),
                ),
                "load_order": int(timing_row["load_order"]),
                "truck_return_time": return_time,
                "regular_minutes": regular,
                "overtime_minutes": overtime,
            }
        )
    schedule = pd.DataFrame(rows)

    truck_rows: list[dict[str, Any]] = []
    fixed_total = 0.0
    variable_total = 0.0
    overtime_total = 0.0
    violation_total = 0.0
    violation_minutes_total = 0.0
    for truck_id, truck in trucks.items():
        truck_type = problem.truck_types[truck.truck_type_id]
        route = routes.get(truck_id, ())
        if not route:
            truck_rows.append(
                {
                    "truck_id": truck_id,
                    "contractor_id": truck.contractor_id,
                    "truck_type_id": truck.truck_type_id,
                    "used": False,
                    "loads": 0,
                    "return_time": 0.0,
                    "regular_minutes": 0.0,
                    "overtime_minutes": 0.0,
                    "fixed_cost": 0.0,
                    "variable_cost": 0.0,
                    "overtime_cost": 0.0,
                    "violation_minutes": 0.0,
                    "violation_cost": 0.0,
                    "total_cost": 0.0,
                }
            )
            continue
        return_time = truck_returns[truck_id]
        regular = min(return_time, problem.regular_minutes)
        overtime = min(
            max(0.0, return_time - problem.regular_minutes),
            problem.max_overtime_minutes,
        )
        violation = max(0.0, return_time - (problem.regular_minutes + problem.max_overtime_minutes))
        fixed = truck_type.fixed_cost
        variable = truck_type.variable_cost_per_minute * regular
        overtime_cost = truck_type.overtime_cost_per_minute * overtime
        violation_cost = violation * penalty_rate
        total = fixed + variable + overtime_cost + violation_cost
        fixed_total += fixed
        variable_total += variable
        overtime_total += overtime_cost
        violation_total += violation_cost
        violation_minutes_total += violation
        truck_rows.append(
            {
                "truck_id": truck_id,
                "contractor_id": truck.contractor_id,
                "truck_type_id": truck.truck_type_id,
                "used": True,
                "loads": len(route),
                "return_time": return_time,
                "regular_minutes": regular,
                "overtime_minutes": overtime,
                "fixed_cost": fixed,
                "variable_cost": variable,
                "overtime_cost": overtime_cost,
                "violation_minutes": violation,
                "violation_cost": violation_cost,
                "total_cost": total,
            }
        )

    loader_rows: list[dict[str, Any]] = []
    for loader_id, service in problem.loader_service.items():
        pickup_loads = [
            load_id for load_id, assigned in plan.pickup_loader.items() if assigned == loader_id
        ]
        delivery_loads = [
            load_id for load_id, assigned in plan.delivery_loader.items() if assigned == loader_id
        ]
        if pickup_loads:
            kind = "pickup"
            load_ids = pickup_loads
            starts = schedule[schedule["load_id"].isin(load_ids)]["pickup_start"]
            finishes = schedule[schedule["load_id"].isin(load_ids)]["pickup_finish"]
            location = loads[pickup_loads[0]].block_id
        elif delivery_loads:
            kind = "delivery"
            load_ids = delivery_loads
            starts = schedule[schedule["load_id"].isin(load_ids)]["delivery_start"]
            finishes = schedule[schedule["load_id"].isin(load_ids)]["delivery_finish"]
            location = loads[delivery_loads[0]].yard_id
        else:
            continue
        loader_rows.append(
            {
                "loader_id": loader_id,
                "kind": kind,
                "location_id": location,
                "loads": len(load_ids),
                "busy_minutes": len(load_ids) * service,
                "first_start": float(starts.min()) if len(starts) else 0.0,
                "last_finish": float(finishes.max()) if len(finishes) else 0.0,
            }
        )

    schedule = schedule.sort_values("load_id").reset_index(drop=True)
    truck_summary = pd.DataFrame(truck_rows).sort_values("truck_id").reset_index(drop=True)
    loader_summary = pd.DataFrame(loader_rows)
    if not loader_summary.empty:
        loader_summary = loader_summary.sort_values("loader_id").reset_index(drop=True)
    objective = fixed_total + variable_total + overtime_total + violation_total
    return SolutionEvaluation(
        objective=objective,
        fixed_cost=fixed_total,
        variable_cost=variable_total,
        overtime_cost=overtime_total,
        violation_cost=violation_total,
        violation_minutes=violation_minutes_total,
        schedule=schedule,
        truck_summary=truck_summary,
        loader_summary=loader_summary,
        plan=plan,
    )


def initial_solution(problem: ScheduleProblem, rng: random.Random) -> RouteSolution:
    """Build a randomized feasible initial route solution.

    Loads are visited in a stable order and assigned to the compatible truck with the fewest loads
    (ties broken randomly). This keeps every load assigned to a compatible truck and spreads work
    across the fleet before searching.
    """
    routes: dict[str, list[str]] = {truck.id: [] for truck in problem.trucks}
    ordered_loads = sorted(
        problem.loads, key=lambda load: (load.block_id, load.yard_id, load.load_id)
    )
    for load in ordered_loads:
        compatible = problem.compatible_trucks(load)
        if not compatible:
            raise ValueError(f"Load {load.load_id} has no compatible truck")
        fewest = min(len(routes[truck.id]) for truck in compatible)
        candidates = [truck for truck in compatible if len(routes[truck.id]) == fewest]
        target = rng.choice(candidates)
        routes[target.id].append(load.load_id)
    return {truck_id: tuple(load_ids) for truck_id, load_ids in routes.items()}


def _routes_to_lists(routes: RouteSolution) -> dict[str, list[str]]:
    """Return a mutable copy of a route solution."""
    return {truck_id: list(route) for truck_id, route in routes.items()}


def _weighted_operator(rng: random.Random, weights: dict[str, float]) -> str:
    """Choose an operator by weight."""
    operators = list(weights)
    return rng.choices(operators, weights=[weights[name] for name in operators], k=1)[0]


def neighbor_solution(
    problem: ScheduleProblem,
    routes: RouteSolution,
    rng: random.Random,
    config: SAConfig,
) -> tuple[RouteSolution, str]:
    """Generate one neighbouring solution.

    Parameters
    ----------
    problem:
        Scheduling data.
    routes:
        Current routes.
    rng:
        RNG instance.
    config:
        SA configuration (operator weights).

    Returns
    -------
    tuple[RouteSolution, str]
        The neighbour and the operator that produced it. If no valid move is found after ten
        attempts, the original routes are returned with ``"none"``.
    """
    for _ in range(10):
        operator = _weighted_operator(rng, config.operator_weights)
        candidate = _routes_to_lists(routes)
        if operator == "swap":
            truck_ids = [truck_id for truck_id, route in candidate.items() if len(route) >= 2]
            if not truck_ids:
                continue
            truck_id = rng.choice(truck_ids)
            left, right = rng.sample(range(len(candidate[truck_id])), 2)
            candidate[truck_id][left], candidate[truck_id][right] = (
                candidate[truck_id][right],
                candidate[truck_id][left],
            )
            return {truck_id: tuple(route) for truck_id, route in candidate.items()}, operator
        if operator == "reversion":
            truck_ids = [truck_id for truck_id, route in candidate.items() if len(route) >= 2]
            if not truck_ids:
                continue
            truck_id = rng.choice(truck_ids)
            left, right = sorted(rng.sample(range(len(candidate[truck_id])), 2))
            candidate[truck_id][left : right + 1] = reversed(candidate[truck_id][left : right + 1])
            return {truck_id: tuple(route) for truck_id, route in candidate.items()}, operator
        if operator == "insertion":
            source_ids = [truck_id for truck_id, route in candidate.items() if route]
            if not source_ids:
                continue
            source_id = rng.choice(source_ids)
            position = rng.randrange(len(candidate[source_id]))
            load_id = candidate[source_id][position]
            load = problem.load_by_id(load_id)
            target_ids = [truck.id for truck in problem.compatible_trucks(load)]
            if not target_ids:
                continue
            target_id = rng.choice(target_ids)
            candidate[source_id].pop(position)
            insert_at = rng.randrange(len(candidate[target_id]) + 1)
            if source_id == target_id and insert_at == position:
                insert_at = rng.randrange(len(candidate[target_id]) + 1)
            candidate[target_id].insert(insert_at, load_id)
            if candidate == _routes_to_lists(routes):
                continue
            return {truck_id: tuple(route) for truck_id, route in candidate.items()}, operator
    return routes, "none"


def solve_sa(
    problem: ScheduleProblem,
    config: SAConfig | None = None,
) -> HaulingSAResult:
    """Run the simulated-annealing scheduler.

    Parameters
    ----------
    problem:
        Scheduling data.
    config:
        SA configuration. ``None`` uses the thesis-derived defaults.

    Returns
    -------
    HaulingSAResult
        Best schedule, cost components, summaries, search provenance, and history.
    """
    config = config or SAConfig()
    rng = random.Random(config.seed)
    start = time.perf_counter()
    history: list[dict[str, Any]] = []
    try:
        current = initial_solution(problem, rng)
        current_eval = evaluate_routes(problem, current, config)
    except Exception as exc:  # noqa: BLE001 - the result payload carries the diagnostic
        return HaulingSAResult(
            status="error",
            objective=None,
            fixed_cost=None,
            variable_cost=None,
            overtime_cost=None,
            violation_cost=None,
            violation_minutes=None,
            schedule=pd.DataFrame(),
            truck_summary=pd.DataFrame(),
            loader_summary=pd.DataFrame(),
            plan=None,
            iterations=0,
            accepted=0,
            runtime_seconds=time.perf_counter() - start,
            seed=config.seed,
            history=pd.DataFrame(columns=_HISTORY_COLUMNS),
            solver_error=f"{type(exc).__name__}: {exc}",
        )

    best_eval = current_eval
    temperature = config.initial_temperature
    min_temperature = config.initial_temperature * config.min_temperature_ratio
    max_iterations = config.max_iterations if config.max_iterations is not None else math.inf
    iterations = 0
    accepted = 0
    stop = False
    while temperature >= min_temperature and not stop:
        for _ in range(config.iterations_per_temperature):
            if iterations >= max_iterations:
                stop = True
                break
            if (
                config.time_limit_seconds is not None
                and time.perf_counter() - start >= config.time_limit_seconds
            ):
                stop = True
                break
            candidate, operator = neighbor_solution(problem, current, rng, config)
            if candidate is current or candidate == current:
                continue
            candidate_eval = evaluate_routes(problem, candidate, config)
            delta = candidate_eval.objective - current_eval.objective
            accept = delta <= 0 or rng.random() < math.exp(-delta / temperature)
            if accept:
                current = candidate
                current_eval = candidate_eval
                accepted += 1
            if candidate_eval.objective < best_eval.objective:
                best_eval = candidate_eval
            iterations += 1
            history.append(
                {
                    "iteration": iterations,
                    "temperature": temperature,
                    "current_objective": current_eval.objective,
                    "best_objective": best_eval.objective,
                    "accepted": accept,
                    "operator": operator,
                }
            )
        temperature *= config.cooling_rate

    return HaulingSAResult(
        status="feasible",
        objective=best_eval.objective,
        fixed_cost=best_eval.fixed_cost,
        variable_cost=best_eval.variable_cost,
        overtime_cost=best_eval.overtime_cost,
        violation_cost=best_eval.violation_cost,
        violation_minutes=best_eval.violation_minutes,
        schedule=best_eval.schedule,
        truck_summary=best_eval.truck_summary,
        loader_summary=best_eval.loader_summary,
        plan=best_eval.plan,
        iterations=iterations,
        accepted=accepted,
        runtime_seconds=time.perf_counter() - start,
        seed=config.seed,
        history=pd.DataFrame(history, columns=_HISTORY_COLUMNS),
    )


def summarize_sa_result(result: HaulingSAResult) -> str:
    """Return a compact human-readable SA summary."""
    lines = [
        f"status: {result.status}",
        f"seed: {result.seed}",
        f"iterations: {result.iterations}",
        f"accepted: {result.accepted}",
        f"runtime_s: {result.runtime_seconds:.3f}",
    ]
    if result.solver_error:
        lines.append(f"solver_error: {result.solver_error}")
    if result.objective is not None:
        lines.append(f"objective: {result.objective:.3f}")
        lines.append(f"fixed_cost: {result.fixed_cost:.3f}")
        lines.append(f"variable_cost: {result.variable_cost:.3f}")
        lines.append(f"overtime_cost: {result.overtime_cost:.3f}")
        lines.append(f"violation_cost: {result.violation_cost:.3f}")
        lines.append(f"violation_minutes: {result.violation_minutes:.3f}")
    if not result.schedule.empty:
        lines.append(f"loads: {len(result.schedule)}")
        lines.append(f"trucks_used: {int(result.truck_summary['used'].sum())}")
    return "\n".join(lines)
