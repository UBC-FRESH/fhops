"""Operational MILP driver (solve + watch wrappers).

The driver builds the operational Pyomo model, optionally seeds it with an incumbent schedule
(warm start / MIP start), dispatches it to the requested solver, and converts the solution back
into an assignment table.

Warm-start dispatch per solver (see :func:`solve_operational_milp`):

* ``highs`` / ``appsi_highs`` — Pyomo's default ``highs`` plugin (``pyomo.contrib.solver``) does
  not accept MIP starts, so seeded solves are routed through the APPSI HiGHS interface
  (``appsi_highs``), which hands every seeded variable value to ``highspy.Highs.setSolution``.
  The HiGHS log is captured to report whether the start was accepted.
* Legacy Pyomo plugins whose ``warm_start_capable()`` is ``True`` (``gurobi``, ``gurobi_direct``,
  ``gurobi_persistent``, ``cbc`` ≥ 2.8, ``cplex``, …) receive ``warmstart=True`` as before.
* Any other solver is called without a warm start and a :class:`MilpWarmStartWarning` is emitted.
"""

from __future__ import annotations

import logging
import math
import re
import warnings
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory

from fhops.evaluation.sequencing import SequencingTracker, build_role_priority
from fhops.model.milp.data import OperationalMilpBundle, ShiftKey
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.operational_problem import OperationalProblem

ASSIGNMENT_COLUMNS = [
    "machine_id",
    "block_id",
    "day",
    "shift_id",
    "assigned",
    "production",
]

__all__ = ["MilpWarmStartWarning", "solve_operational_milp"]

_HIGHS_SOLVER_NAMES = frozenset({"highs", "appsi_highs"})
_HIGHS_LOGGER_NAME = "fhops.model.milp.driver.highs"
_LIMIT_TERMINATIONS = frozenset(
    {"maxtimelimit", "maxiterations", "maxevaluations", "objectivelimit"}
)
_HIGHS_START_ACCEPTED = re.compile(r"MIP start solution is feasible", re.IGNORECASE)
_HIGHS_START_REJECTED = re.compile(
    r"MIP start solution is infeasible|cannot yield feasible solution|"
    r"User-supplied solution .* has violations",
    re.IGNORECASE,
)
_HIGHS_START_LINE = re.compile(r"MIP start|user-supplied", re.IGNORECASE)


class MilpWarmStartWarning(UserWarning):
    """Warning emitted when an incumbent cannot be passed to the selected MILP solver.

    Raised (via :func:`warnings.warn`) by :func:`solve_operational_milp` when
    ``incumbent_assignments`` is supplied but the solver interface has no MIP-start support (or the
    APPSI HiGHS interface is unavailable). The solve still runs, just without the warm start.
    """


class _LineCollector(logging.Handler):
    """Logging handler that keeps the formatted messages it receives."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


@dataclass(slots=True)
class _IncumbentState:
    assignment_lookup: dict[tuple[str, ShiftKey], str]
    production_lookup: dict[tuple[str, str, ShiftKey], float]
    role_prod_lookup: dict[tuple[str, str, ShiftKey], float]
    role_assignment_counts: dict[tuple[str, str, ShiftKey], int]
    landing_usage: dict[tuple[str, int], int]
    leftover_by_block: dict[str, float]
    block_terminal_total: dict[str, float] | None = None
    block_generic_total: dict[str, float] | None = None


def solve_operational_milp(
    bundle: OperationalMilpBundle,
    solver: str = "highs",
    time_limit: int | None = None,
    gap: float | None = None,
    tee: bool = False,
    solver_options: Mapping[str, object] | None = None,
    incumbent_assignments: pd.DataFrame | None = None,
    context: OperationalProblem | None = None,
) -> dict[str, Any]:
    """
    Solve the operational MILP given a prepared bundle.

    Parameters
    ----------
    bundle :
        Operational bundle emitted by :func:`fhops.model.milp.operational.build_operational_model`.
    solver :
        Solver name understood by ``pyomo.opt.SolverFactory`` (``highs`` by default, ``gurobi`` for
        large ladders).
    time_limit :
        Optional second budget forwarded to the solver (``None`` leaves the solver default).
    gap :
        Optional relative MIP gap target (0–1). We set both ``mipgap`` (Gurobi/CPLEX style) and
        ``mip_rel_gap`` (HiGHS style) so callers do not need to remember solver-specific keywords.
    tee :
        When ``True`` stream the solver log to stdout.
    solver_options :
        Additional ``name → value`` overrides forwarded verbatim to the solver (e.g.,
        ``{"Threads": 36, "LogFile": "med42.log"}`` for Gurobi).
    incumbent_assignments :
        Optional :class:`pandas.DataFrame` with ``machine_id``, ``block_id``, ``day``, ``shift_id``,
        and optional ``assigned``/``production`` columns. When provided we derive every state
        variable implied by the schedule (assignments, production, transitions, mobilisation flags,
        inventories, landing surplus) and pass it to the solver as a MIP start (see *Notes* for
        the per-solver mechanism). The solver will still discard the start if the incumbent is
        infeasible; right now only tiny7/small21 benefit measurably, whereas med42/large84 respond
        better to the solver’s own heuristics.
    context :
        :class:`fhops.optimization.operational_problem.OperationalProblem` describing the scenario.
        Required if the incumbent needs to be expanded into loader and landing state (the CLI and
        benchmark harness populate this automatically).

    Returns
    -------
    dict
        Dictionary carrying ``objective``, ``production``, ``assignments`` (DataFrame), solver
        status/termination metadata (``solver_status``, ``termination_condition``), and a
        ``warm_start`` dictionary. ``objective`` is ``None`` when the solver returns no feasible
        solution. A solve stopped by a limit (time, iterations, objective) that still holds a
        feasible incumbent reports that incumbent's objective and assignments.

        ``warm_start`` keys:

        ``requested`` (bool)
            ``True`` when ``incumbent_assignments`` was non-empty.
        ``seeded_slots`` (int)
            Number of ``(machine, shift)`` assignment slots seeded from the incumbent.
        ``method`` (str | None)
            ``"appsi_highs"`` (HiGHS MIP start via ``highspy.Highs.setSolution``),
            ``"pyomo_warmstart"`` (legacy ``solve(..., warmstart=True)``), or ``None`` when no
            warm start was passed to the solver.
        ``solver`` (str)
            Pyomo solver name actually used (``appsi_highs`` for seeded HiGHS solves).
        ``accepted`` (bool | None)
            HiGHS only: ``True`` when the log reports ``MIP start solution is feasible``,
            ``False`` when HiGHS reports the start infeasible, ``None`` when unknown (other
            solvers, or no start passed).
        ``solver_messages`` (list[str])
            HiGHS log lines that mention the MIP start (empty for other solvers).

    Warns
    -----
    MilpWarmStartWarning
        When an incumbent was supplied but the solver interface cannot take a MIP start (the solve
        continues without it).

    Notes
    -----
    Warm starts per solver:

    * ``highs`` (default) and ``appsi_highs``: seeded solves use Pyomo's APPSI HiGHS interface
      (``SolverFactory("appsi_highs")``) with ``warmstart=True``. Pyomo's default ``highs``
      plugin (``pyomo.contrib.solver``'s ``LegacySolverWrapper``) rejects the ``warmstart``
      keyword, so it is only used for unseeded solves. HiGHS prints
      ``MIP start solution is feasible, objective value is …`` when it adopts the start.
    * ``gurobi``, ``gurobi_direct``, ``gurobi_persistent``, ``cplex``, ``cbc`` (≥ 2.8) and other
      legacy plugins that report ``warm_start_capable()``: ``warmstart=True`` is forwarded
      unchanged.
    * Anything else (e.g., ``glpk`` or other ``pyomo.contrib.solver`` interfaces): solved without
      a warm start and a :class:`MilpWarmStartWarning` is emitted.


    Locks (``bundle.locked_assignments``) and initial state (``bundle.initial_*``, from
    ``Scenario.initial_state``) are enforced by the model itself (see
    :func:`fhops.model.milp.operational.build_operational_model`). Incumbents are overlaid with the
    locks before seeding, and seeded inventories start from the carried-in staged volumes.

    The warm-start plumbing is “best effort”: setting ``incumbent_assignments`` is always safe, but
    it only accelerates a solve if the incumbent is close to feasible for the operational MILP.
    Today that means tiny7/small21 runs reuse the incumbent immediately, while med42/large84 usually
    ignore the seed and rely on Gurobi/HiGHS built-in heuristics.
    """

    model = build_operational_model(bundle)
    meta = getattr(model, "_warm_start_meta", None)
    if meta is not None and context is not None:
        meta["operational_problem"] = context
    seeded = 0
    if incumbent_assignments is not None:
        seeded = _apply_incumbent_start(model, incumbent_assignments)

    opt, solver_used, method = _create_solver(solver, warm_start=seeded > 0)
    warm_info: dict[str, Any] = {
        "requested": incumbent_assignments is not None and not incumbent_assignments.empty,
        "seeded_slots": seeded,
        "method": method,
        "solver": solver_used,
        "accepted": None,
        "solver_messages": [],
    }
    if time_limit is not None:
        opt.options["time_limit"] = time_limit
    if gap is not None:
        # Different solvers expect different gap parameter names.
        opt.options["mipgap"] = gap  # Gurobi/CPLEX-style
        if solver.lower() not in {"gurobi", "cplex"}:
            opt.options["mip_rel_gap"] = gap  # HiGHS-style
    if solver_options:
        for key, value in solver_options.items():
            opt.options[str(key)] = value
    solve_kwargs: dict[str, object] = {"tee": tee, "load_solutions": True}
    if method is not None:
        solve_kwargs["warmstart"] = True

    if method == "appsi_highs":
        result, has_solution, log_lines = _solve_appsi_highs(opt, model, solve_kwargs)
        accepted, messages = _parse_highs_start_log(log_lines)
        warm_info["accepted"] = accepted
        warm_info["solver_messages"] = messages
    else:
        result = opt.solve(model, **solve_kwargs)
        has_solution = None
    status = str(result.solver.status).lower()
    termination = str(result.solver.termination_condition).lower()
    if has_solution is not None:
        # APPSI path: values are only in the model when a solution was explicitly loaded.
        solved = has_solution
    else:
        solved = termination in {"optimal", "feasible"} or status in {"optimal", "feasible"}
        if not solved and termination in _LIMIT_TERMINATIONS:
            solved = _has_incumbent(result, model)
    if solved:
        assignments = _extract_assignments(model)
        prod = sum(pyo.value(model.prod[idx]) for idx in model.prod)
    else:
        assignments = pd.DataFrame(columns=ASSIGNMENT_COLUMNS)
        prod = 0.0
    return {
        "objective": pyo.value(model.objective) if solved else None,
        "production": prod,
        "assignments": assignments,
        "solver_status": str(result.solver.status),
        "termination_condition": str(result.solver.termination_condition),
        "warm_start": warm_info,
    }


def _create_solver(solver: str, *, warm_start: bool) -> tuple[Any, str, str | None]:
    """Instantiate the Pyomo solver and decide how (or whether) to pass a warm start.

    Parameters
    ----------
    solver :
        Solver name requested by the caller (``SolverFactory`` name).
    warm_start :
        ``True`` when the model carries seeded variable values.

    Returns
    -------
    tuple
        ``(opt, solver_used, method)`` where ``method`` is ``"appsi_highs"``,
        ``"pyomo_warmstart"``, or ``None`` (no warm start). Emits :class:`MilpWarmStartWarning`
        when ``warm_start`` is requested but unsupported.
    """

    solver_key = solver.strip().lower()
    if not warm_start:
        return SolverFactory(solver), solver, None

    if solver_key in _HIGHS_SOLVER_NAMES:
        appsi = SolverFactory("appsi_highs")
        if _solver_available(appsi):
            return appsi, "appsi_highs", "appsi_highs"
        warnings.warn(
            "The APPSI HiGHS interface (SolverFactory('appsi_highs')) is unavailable, so the "
            "incumbent cannot be passed to HiGHS as a MIP start; solving without a warm start.",
            MilpWarmStartWarning,
            stacklevel=3,
        )
        return SolverFactory(solver), solver, None

    opt = SolverFactory(solver)
    if _accepts_warmstart_keyword(opt):
        return opt, solver, "pyomo_warmstart"
    warnings.warn(
        f"Solver '{solver}' does not support MIP warm starts through Pyomo; solving without the "
        "incumbent. Use solver='highs' or a warm-start-capable solver (gurobi, cbc, cplex).",
        MilpWarmStartWarning,
        stacklevel=3,
    )
    return opt, solver, None


def _solver_available(opt: Any) -> bool:
    try:
        return bool(opt.available(exception_flag=False))
    except Exception:
        return False


def _accepts_warmstart_keyword(opt: Any) -> bool:
    """Return ``True`` when ``opt.solve(..., warmstart=True)`` is supported and meaningful."""

    try:
        from pyomo.contrib.solver.common.base import LegacySolverWrapper
    except ImportError:  # pragma: no cover - older Pyomo without contrib.solver
        LegacySolverWrapper = None
    if LegacySolverWrapper is not None and isinstance(opt, LegacySolverWrapper):
        return False
    capable = getattr(opt, "warm_start_capable", None)
    if not callable(capable):
        return False
    try:
        return bool(capable())
    except Exception:
        # e.g. the CBC plugin probes the executable version and fails when it is missing.
        return False


def _solve_appsi_highs(
    opt: Any, model: pyo.ConcreteModel, solve_kwargs: Mapping[str, object]
) -> tuple[Any, bool, list[str]]:
    """Run a warm-started APPSI HiGHS solve, capturing the HiGHS log.

    Solutions are loaded explicitly (``load_solutions=False`` + ``opt.load_vars()``) because the
    APPSI interface raises when asked to load a solution that does not exist. The HiGHS log is
    routed to a private logger (also streamed to stdout when ``tee=True``) so the caller can tell
    whether the MIP start was accepted.

    Returns
    -------
    tuple
        ``(legacy_results, has_solution, log_lines)``.
    """

    collector = _LineCollector()
    highs_logger = logging.getLogger(_HIGHS_LOGGER_NAME)
    previous_level = highs_logger.level
    previous_propagate = highs_logger.propagate
    highs_logger.addHandler(collector)
    highs_logger.setLevel(logging.DEBUG)
    highs_logger.propagate = False
    config = getattr(opt, "config", None)
    if config is not None:
        try:
            config.solver_output_logger = highs_logger
            config.log_level = logging.DEBUG
        except (AttributeError, ValueError):
            pass
    kwargs = dict(solve_kwargs)
    kwargs["load_solutions"] = False
    try:
        result = opt.solve(model, **kwargs)
        solution = getattr(result, "solution", None)
        has_solution = bool(solution is not None and len(solution) > 0)
        if has_solution:
            opt.load_vars()
    finally:
        highs_logger.removeHandler(collector)
        highs_logger.setLevel(previous_level)
        highs_logger.propagate = previous_propagate
    return result, has_solution, collector.lines


def _parse_highs_start_log(lines: list[str]) -> tuple[bool | None, list[str]]:
    """Return ``(accepted, messages)`` extracted from HiGHS log lines about the MIP start."""

    messages: list[str] = []
    repair_infeasible = False
    awaiting_repair_status = False
    for raw in lines:
        line = raw.strip()
        if _HIGHS_START_LINE.search(line):
            messages.append(line)
            awaiting_repair_status = "attempting to find feasible solution" in line.lower()
        elif awaiting_repair_status and line.lower().startswith("model status"):
            # Outcome of the LP/MIP HiGHS solves to complete the user-supplied discrete values.
            messages.append(line)
            repair_infeasible = "infeasible" in line.lower()
            awaiting_repair_status = False
    if any(_HIGHS_START_ACCEPTED.search(line) for line in messages):
        return True, messages
    if repair_infeasible or any(_HIGHS_START_REJECTED.search(line) for line in messages):
        return False, messages
    return None, messages


def _has_incumbent(result: Any, model: pyo.ConcreteModel) -> bool:
    """Return ``True`` when legacy results report a finite incumbent objective."""

    problem = getattr(result, "problem", None)
    if problem is None:
        return False
    try:
        maximize = model.objective.sense == pyo.maximize
        bound = problem.lower_bound if maximize else problem.upper_bound
        return bound is not None and math.isfinite(float(bound))
    except (AttributeError, TypeError, ValueError):
        return False


def _extract_assignments(model: pyo.ConcreteModel) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (machine_id, block_id, day, shift_id), var in model.x.items():
        assigned_value = pyo.value(var)
        production_value = pyo.value(model.prod[machine_id, block_id, (day, shift_id)])
        if assigned_value > 0.5 or production_value > 1e-6:
            rows.append(
                {
                    "machine_id": machine_id,
                    "block_id": block_id,
                    "day": int(day),
                    "shift_id": shift_id,
                    "assigned": int(assigned_value > 0.5),
                    "production": float(production_value),
                }
            )
    if rows:
        return pd.DataFrame(rows, columns=ASSIGNMENT_COLUMNS)
    return pd.DataFrame(columns=ASSIGNMENT_COLUMNS)


def _apply_incumbent_start(model: pyo.ConcreteModel, assignments: pd.DataFrame | None) -> int:
    """
    Populate Pyomo variable starting values from an incumbent assignment matrix.

    Parameters
    ----------
    model :
        Operational Pyomo model returned by :func:`build_operational_model`.
    assignments :
        DataFrame with at least ``machine_id``, ``block_id``, ``day``, and ``shift_id`` columns,
        optionally carrying ``assigned``/``production`` floats.

    Returns
    -------
    int
        Count of assignment slots seeded (used to decide whether Pyomo should enable ``warmstart``).

    Notes
    -----
    When the operational builder attaches warm-start metadata we reconstruct the entire schedule
    state (transition binaries, activation flags, loader inventories, landing surplus, leftovers).
    Otherwise we fall back to seeding only the ``x``/``prod`` variables so callers can still supply a
    partial incumbent. Solvers may still discard the start if other integer variables remain unset
    or if the incumbent violates constraints by a large margin.
    """

    if assignments is None or assignments.empty:
        return 0

    required = {"machine_id", "block_id", "day", "shift_id"}
    missing = required - set(assignments.columns)
    if missing:
        raise ValueError(
            "Incumbent assignments missing required columns: " + ", ".join(sorted(missing))
        )

    meta = getattr(model, "_warm_start_meta", None)
    if meta is None:
        return _seed_basic_assignments(model, assignments)

    state = _build_incumbent_state(model, assignments, meta)
    if state is None or not state.assignment_lookup:
        return _seed_basic_assignments(model, assignments)
    _seed_model_from_state(model, meta, state)
    return len(state.assignment_lookup)


def _seed_basic_assignments(model: pyo.ConcreteModel, assignments: pd.DataFrame) -> int:
    """Fallback seeding that only sets x/prod for provided rows."""

    seeded = 0
    has_assigned = "assigned" in assignments.columns
    has_production = "production" in assignments.columns
    for row in assignments.itertuples(index=False):
        machine_id = getattr(row, "machine_id")
        block_id = getattr(row, "block_id")
        day_value = getattr(row, "day")
        shift_value = getattr(row, "shift_id")

        try:
            day = int(day_value)
        except (TypeError, ValueError):
            continue
        shift_id = str(shift_value)
        shift_tuple = (day, shift_id)
        try:
            x_var = model.x[machine_id, block_id, shift_tuple]
        except KeyError:
            continue

        assigned_val = 1.0
        if has_assigned:
            assigned_raw = getattr(row, "assigned")
            if pd.notna(assigned_raw):
                try:
                    assigned_val = float(assigned_raw)
                except (TypeError, ValueError):
                    assigned_val = 1.0
        if assigned_val <= 0:
            continue

        x_var.set_value(1.0)
        x_var.stale = False
        seeded += 1

        if has_production:
            prod_raw = getattr(row, "production")
            if pd.notna(prod_raw):
                try:
                    prod_val = float(prod_raw)
                except (TypeError, ValueError):
                    continue
                try:
                    prod_var = model.prod[machine_id, block_id, shift_tuple]
                except KeyError:
                    continue
                prod_var.set_value(prod_val)
                prod_var.stale = False

    return seeded


def _derive_state_with_tracker(
    ctx: OperationalProblem,
    bundle: OperationalMilpBundle,
    assignment_lookup: dict[tuple[str, ShiftKey], str],
    provided_prod: dict[tuple[str, str, ShiftKey], float],
) -> dict[str, dict]:
    sc = ctx.problem.scenario
    shift_keys = ctx.shift_keys
    rate = bundle.production_rates
    machine_roles = bundle.machine_roles
    allowed_roles = ctx.allowed_roles
    windows = bundle.windows
    availability_day = bundle.availability_day
    availability_shift = bundle.availability_shift
    blackout = ctx.blackout_shifts
    landing_of = bundle.landing_for_block

    plan: dict[str, dict[ShiftKey, str | None]] = {
        machine.id: {shift: None for shift in shift_keys} for machine in sc.machines
    }
    for (machine_id, shift), block_id in assignment_lookup.items():
        if machine_id in plan:
            plan[machine_id][shift] = block_id

    tracker = SequencingTracker(ctx)
    role_priority = build_role_priority(ctx)
    ordered_machines = sorted(
        sc.machines,
        key=lambda m: (role_priority.get(machine_roles.get(m.id) or "", 999), m.id),
    )

    production_lookup: dict[tuple[str, str, ShiftKey], float] = {}
    role_prod_lookup: defaultdict[tuple[str, str, ShiftKey], float] = defaultdict(float)
    role_assignment_counts: defaultdict[tuple[str, str, ShiftKey], int] = defaultdict(int)
    landing_usage: defaultdict[tuple[str, int], int] = defaultdict(int)

    for day, shift_id in shift_keys:
        for machine in ordered_machines:
            slot_block: str | None = plan[machine.id].get((day, shift_id))
            assigned_block = slot_block
            locked_block = ctx.lock_for(machine.id, day, shift_id)
            if locked_block is not None:
                assigned_block = locked_block

            if (
                availability_shift.get((machine.id, day, shift_id), 1) == 0
                or availability_day.get((machine.id, day), 1) == 0
                or (machine.id, day, shift_id) in blackout
            ):
                continue

            if assigned_block is None:
                continue

            role = machine_roles.get(machine.id)
            allowed = allowed_roles.get(assigned_block)
            if allowed is not None and role is not None and role not in allowed:
                continue

            earliest, latest = windows[assigned_block]
            if day < earliest or day > latest:
                continue

            rate_value = rate.get((machine.id, assigned_block), 0.0)
            if rate_value <= 0.0:
                continue

            key = (machine.id, assigned_block, (day, shift_id))
            proposed = provided_prod.get(key, rate_value)
            sequencing = tracker.process(day, machine.id, assigned_block, proposed, shift_id)
            prod_units = max(0.0, sequencing.production_units)
            production_lookup[key] = prod_units

            if role is not None:
                role_key = (role, assigned_block, (day, shift_id))
                role_prod_lookup[role_key] += prod_units
                role_assignment_counts[role_key] += 1

            landing_id = landing_of.get(assigned_block)
            if landing_id is not None:
                landing_usage[(landing_id, day)] += 1

    tracker.finalize()
    leftover_by_block = {
        block_id: max(0.0, remaining) for block_id, remaining in tracker.remaining_work.items()
    }

    return {
        "production_lookup": production_lookup,
        "role_prod_lookup": dict(role_prod_lookup),
        "role_assignment_counts": dict(role_assignment_counts),
        "landing_usage": dict(landing_usage),
        "leftover_by_block": leftover_by_block,
    }


def _derive_state_with_rates(
    bundle: OperationalMilpBundle,
    assignment_lookup: dict[tuple[str, ShiftKey], str],
    provided_prod: dict[tuple[str, str, ShiftKey], float],
    terminal_pairs: set[tuple[str, str]],
) -> dict[str, dict]:
    machine_roles = bundle.machine_roles
    landing_for_block = bundle.landing_for_block
    production_lookup: dict[tuple[str, str, ShiftKey], float] = {}
    role_prod_lookup: defaultdict[tuple[str, str, ShiftKey], float] = defaultdict(float)
    role_assignment_counts: defaultdict[tuple[str, str, ShiftKey], int] = defaultdict(int)
    landing_usage: defaultdict[tuple[str, int], int] = defaultdict(int)
    block_terminal_total: defaultdict[str, float] = defaultdict(float)
    block_generic_total: defaultdict[str, float] = defaultdict(float)

    for (machine_id, shift), block_id in assignment_lookup.items():
        key = (machine_id, block_id, shift)
        if key in provided_prod:
            prod_val = provided_prod[key]
        else:
            prod_val = bundle.production_rates.get((machine_id, block_id), 0.0)
        production_lookup[key] = prod_val
        block_generic_total[block_id] += prod_val
        role = machine_roles.get(machine_id)
        if role:
            role_key = (role, block_id, shift)
            role_prod_lookup[role_key] += prod_val
            role_assignment_counts[role_key] += 1
            if (role, block_id) in terminal_pairs:
                block_terminal_total[block_id] += prod_val
        landing_id = landing_for_block.get(block_id)
        if landing_id is not None:
            landing_usage[(landing_id, shift[0])] += 1

    leftover_by_block = {
        blk: max(0.0, bundle.work_required.get(blk, 0.0) - block_generic_total.get(blk, 0.0))
        for blk in bundle.blocks
    }

    return {
        "production_lookup": production_lookup,
        "role_prod_lookup": dict(role_prod_lookup),
        "role_assignment_counts": dict(role_assignment_counts),
        "landing_usage": dict(landing_usage),
        "leftover_by_block": leftover_by_block,
        "block_terminal_total": dict(block_terminal_total),
        "block_generic_total": dict(block_generic_total),
    }


def _build_incumbent_state(
    model: pyo.ConcreteModel, assignments: pd.DataFrame, meta: Mapping[str, Any]
) -> _IncumbentState | None:
    bundle: OperationalMilpBundle | None = meta.get("bundle")
    shift_list: tuple[ShiftKey, ...] | None = meta.get("shift_list")
    if bundle is None or not shift_list:
        return None

    shift_lookup = {shift for shift in model.S}
    machines = set(bundle.machines)
    blocks = set(bundle.blocks)
    terminal_pairs = set(meta.get("terminal_pairs", ()))

    assignment_lookup: dict[tuple[str, ShiftKey], str] = {}
    provided_production: dict[tuple[str, str, ShiftKey], float] = {}

    has_assigned = "assigned" in assignments.columns
    has_production = "production" in assignments.columns

    for row in assignments.itertuples(index=False):
        machine_id = str(getattr(row, "machine_id"))
        if machine_id not in machines:
            raise ValueError(f"Incumbent references unknown machine_id={machine_id}")

        block_raw = getattr(row, "block_id")
        if pd.isna(block_raw):
            continue
        block_id = str(block_raw)
        if block_id not in blocks:
            raise ValueError(f"Incumbent references unknown block_id={block_id}")

        try:
            day = int(getattr(row, "day"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid incumbent day for machine={machine_id}") from exc
        shift_id = str(getattr(row, "shift_id"))
        shift_tuple: ShiftKey = (day, shift_id)
        if shift_tuple not in shift_lookup:
            raise ValueError(
                f"Incumbent references shift {(day, shift_id)} that is not in the MILP grid"
            )

        assigned_val = 1.0
        if has_assigned:
            assigned_raw = getattr(row, "assigned")
            if pd.notna(assigned_raw):
                try:
                    assigned_val = float(assigned_raw)
                except (TypeError, ValueError):
                    assigned_val = 1.0
        if assigned_val <= 0:
            continue

        slot_key = (machine_id, shift_tuple)
        if slot_key in assignment_lookup:
            raise ValueError(
                f"Duplicate incumbent row for machine={machine_id} day={day} shift={shift_id}"
            )
        assignment_lookup[slot_key] = block_id

        if has_production:
            prod_raw = getattr(row, "production")
            if pd.notna(prod_raw):
                try:
                    prod_val = max(0.0, float(prod_raw))
                except (TypeError, ValueError):
                    prod_val = 0.0
                provided_production[(machine_id, block_id, shift_tuple)] = prod_val

    _apply_bundle_locks(bundle, shift_list, assignment_lookup)

    context: OperationalProblem | None = meta.get("operational_problem")
    if context is not None:
        derived = _derive_state_with_tracker(
            context,
            bundle,
            assignment_lookup,
            provided_production,
        )
        return _IncumbentState(
            assignment_lookup=assignment_lookup,
            production_lookup=derived["production_lookup"],
            role_prod_lookup=derived["role_prod_lookup"],
            role_assignment_counts=derived["role_assignment_counts"],
            landing_usage=derived["landing_usage"],
            leftover_by_block=derived["leftover_by_block"],
        )

    # Fallback derivation relies on raw production rates.
    derived = _derive_state_with_rates(
        bundle,
        assignment_lookup,
        provided_production,
        terminal_pairs,
    )
    return _IncumbentState(
        assignment_lookup=assignment_lookup,
        production_lookup=derived["production_lookup"],
        role_prod_lookup=derived["role_prod_lookup"],
        role_assignment_counts=derived["role_assignment_counts"],
        landing_usage=derived["landing_usage"],
        leftover_by_block=derived["leftover_by_block"],
        block_terminal_total=derived["block_terminal_total"],
        block_generic_total=derived["block_generic_total"],
    )


def _apply_bundle_locks(
    bundle: OperationalMilpBundle,
    shift_list: tuple[ShiftKey, ...],
    assignment_lookup: dict[tuple[str, ShiftKey], str],
) -> None:
    """Overlay ``bundle.locked_assignments`` onto an incumbent assignment lookup (in place).

    Locked slots take the locked block when the machine is available and are cleared otherwise,
    mirroring the ``locked_assignment`` constraints so the seeded ``x`` values respect locks.
    """

    if not bundle.locked_assignments:
        return
    for machine_id, block_id, lock_day, lock_shift in bundle.locked_assignments:
        for slot in shift_list:
            day, shift_id = slot
            if day != lock_day or (lock_shift is not None and shift_id != lock_shift):
                continue
            key = (machine_id, slot)
            shift_flag = bundle.availability_shift.get((machine_id, day, shift_id))
            if shift_flag is not None:
                available = shift_flag == 1
            else:
                available = bundle.availability_day.get((machine_id, day), 1) == 1
            if available:
                assignment_lookup[key] = block_id
            else:
                assignment_lookup.pop(key, None)


def _seed_model_from_state(
    model: pyo.ConcreteModel, meta: Mapping[str, Any], state: _IncumbentState
) -> None:
    bundle: OperationalMilpBundle = meta["bundle"]
    assignment_lookup = state.assignment_lookup
    production_lookup = state.production_lookup
    role_prod_lookup = state.role_prod_lookup
    role_assignment_counts = state.role_assignment_counts
    landing_usage = state.landing_usage
    shift_list: tuple[ShiftKey, ...] = meta.get("shift_list") or tuple(model.S)
    prev_shift_map: Mapping[ShiftKey, ShiftKey | None] = meta.get("prev_shift_map", {})
    inventory_pairs: tuple[tuple[str, str], ...] = tuple(meta.get("inventory_pairs", ()))
    role_upstream: Mapping[tuple[str, str], tuple[str, ...]] = meta.get("role_upstream", {})
    loader_batch_volume: Mapping[tuple[str, str], float] = meta.get("loader_batch_volume", {})
    block_terminal_roles: Mapping[str, tuple[str, ...]] = meta.get("block_terminal_roles", {})

    def _slot_key(day: int, shift_id: str) -> ShiftKey:
        return (int(day), str(shift_id))

    for (machine_id, block_id, day, shift_id), var in model.x.items():
        shift = _slot_key(day, shift_id)
        value = 1.0 if assignment_lookup.get((machine_id, shift)) == block_id else 0.0
        var.set_value(value)
        var.stale = False

    for (machine_id, block_id, day, shift_id), var in model.prod.items():
        shift = _slot_key(day, shift_id)
        key = (machine_id, block_id, shift)
        var.set_value(production_lookup.get(key, 0.0))
        var.stale = False

    for (role, block_id, day, shift_id), var in model.role_prod.items():
        shift = _slot_key(day, shift_id)
        key = (role, block_id, shift)
        var.set_value(role_prod_lookup.get(key, 0.0))
        var.stale = False

    if hasattr(model, "y"):
        for (machine_id, prev_blk, curr_blk, day, shift_id), var in model.y.items():
            shift = _slot_key(day, shift_id)
            prev_slot = prev_shift_map.get(shift)
            value = 0.0
            if prev_slot is not None:
                prev_block = assignment_lookup.get((machine_id, prev_slot))
                curr_block = assignment_lookup.get((machine_id, shift))
                if prev_block == prev_blk and curr_block == curr_blk:
                    value = 1.0
            var.set_value(value)
            var.stale = False

    if hasattr(model, "role_active"):
        for (role, block_id, day, shift_id), var in model.role_active.items():
            shift = _slot_key(day, shift_id)
            key = (role, block_id, shift)
            var.set_value(1.0 if role_assignment_counts.get(key, 0) > 0 else 0.0)
            var.stale = False

    if hasattr(model, "role_cumulative") and hasattr(model, "upstream_done"):
        cumulative: dict[tuple[str, str], float] = {}
        cumulative_before: dict[tuple[str, str, ShiftKey], float] = {}
        for day, shift_id in shift_list:
            shift = _slot_key(day, shift_id)
            for role, block_id in model.CumulativePairs:
                pair = (role, block_id)
                cumulative_before[(role, block_id, shift)] = cumulative.get(pair, 0.0)
                cumulative[pair] = cumulative.get(pair, 0.0) + role_prod_lookup.get(
                    (role, block_id, shift), 0.0
                )
                cum_var = model.role_cumulative[role, block_id, day, shift_id]
                cum_var.set_value(cumulative[pair])
                cum_var.stale = False
        for (role, block_id, day, shift_id), var in model.upstream_done.items():
            shift = _slot_key(day, shift_id)
            done = all(
                cumulative_before.get((up_role, block_id, shift), 0.0) + 1e-9
                >= bundle.initial_role_remaining.get(
                    (block_id, up_role), bundle.work_required.get(block_id, 0.0)
                )
                for up_role in role_upstream.get((role, block_id), ())
            )
            var.set_value(1.0 if done else 0.0)
            var.stale = False

    if hasattr(model, "loads") and hasattr(model, "loader_partial"):
        for (role, block_id, day, shift_id), load_var in model.loads.items():
            shift = _slot_key(day, shift_id)
            batch = loader_batch_volume.get((role, block_id), 0.0)
            prod_value = role_prod_lookup.get((role, block_id, shift), 0.0)
            if batch > 0:
                full_loads = int(prod_value // batch)
                remainder = prod_value - full_loads * batch
                if remainder >= batch - 1e-6:
                    full_loads += 1
                    remainder = 0.0
            else:
                full_loads = 0
                remainder = prod_value
            load_var.set_value(full_loads)
            load_var.stale = False
            loader_partial = model.loader_partial[role, block_id, day, shift_id]
            loader_partial.set_value(remainder)
            loader_partial.stale = False

    if hasattr(model, "landing_surplus") and hasattr(model, "Landing"):
        for landing_id in model.Landing:
            cap = bundle.landing_capacity.get(landing_id, 0)
            for day in model.D:
                usage = landing_usage.get((landing_id, day), 0)
                surplus = max(0.0, float(usage - cap))
                var = model.landing_surplus[landing_id, day]
                var.set_value(surplus)
                var.stale = False

    if inventory_pairs:
        initial_start: Mapping[tuple[str, str], float] = meta.get("initial_inventory_start", {})
        inventory_prev: dict[tuple[str, str], float] = {
            pair: float(initial_start.get(pair, 0.0)) for pair in inventory_pairs
        }
        for day, shift_id in shift_list:
            shift = _slot_key(day, shift_id)
            for role, block_id in inventory_pairs:
                start_value = inventory_prev[(role, block_id)]
                inv_start = model.inventory_start[role, block_id, day, shift_id]
                inv_start.set_value(start_value)
                inv_start.stale = False
                upstream_roles = role_upstream.get((role, block_id), ())
                upstream_sum = sum(
                    role_prod_lookup.get((up_role, block_id, shift), 0.0)
                    for up_role in upstream_roles
                )
                consumed = role_prod_lookup.get((role, block_id, shift), 0.0)
                end_value = start_value + upstream_sum - consumed
                if end_value < -1e-5:
                    end_value = 0.0
                else:
                    end_value = max(0.0, end_value)
                inv_var = model.inventory[role, block_id, day, shift_id]
                inv_var.set_value(end_value)
                inv_var.stale = False
                inventory_prev[(role, block_id)] = end_value

    leftover_map = state.leftover_by_block or {}
    for block_id in model.B:
        if leftover_map:
            leftover_val = leftover_map.get(block_id, 0.0)
        else:
            required = bundle.work_required.get(block_id, 0.0)
            terminal_roles = block_terminal_roles.get(block_id)
            if terminal_roles:
                completed = (
                    state.block_terminal_total.get(block_id, 0.0)
                    if state.block_terminal_total
                    else 0.0
                )
            else:
                completed = (
                    state.block_generic_total.get(block_id, 0.0)
                    if state.block_generic_total
                    else 0.0
                )
            leftover_val = max(0.0, required - completed)
        var = model.leftover[block_id]
        var.set_value(leftover_val)
        var.stale = False
