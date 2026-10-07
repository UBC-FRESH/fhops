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

import io
import logging
import math
import re
import sys
import warnings
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory

from fhops.evaluation.sequencing import SequencingTracker, build_role_priority
from fhops.model.milp.data import OperationalMilpBundle, ShiftKey, resolve_locked_slots
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

__all__ = ["MilpSolverFallbackWarning", "MilpWarmStartWarning", "solve_operational_milp"]

#: ``SolverFactory`` names tried in order by ``solver="auto"`` (Gurobi only when available).
AUTO_SOLVER_CANDIDATES = ("gurobi", "highs")

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
_HIGHS_ERROR_LINE = re.compile(r"^ERROR\b", re.IGNORECASE)
_SOLVED_TERMINATIONS = frozenset({"optimal", "feasible", "locallyoptimal", "globallyoptimal"})
_INFEASIBLE_TERMINATIONS = frozenset({"infeasible", "infeasibleorunbounded", "unbounded"})
_ERROR_TERMINATIONS = frozenset(
    {
        "error",
        "solverfailure",
        "internalsolvererror",
        "licensingproblems",
        "unknown",
        "other",
        "invalidproblem",
        "invalidsolverparameter",
        "resourceinterrupt",
        "userinterrupt",
    }
)
_SEED_FEASIBILITY_TOLERANCE = 1e-6


class MilpWarmStartWarning(UserWarning):
    """Warning emitted when an incumbent cannot be passed to the selected MILP solver.

    Raised (via :func:`warnings.warn`) by :func:`solve_operational_milp` when
    ``incumbent_assignments`` is supplied but the solver interface has no MIP-start support (or the
    APPSI HiGHS interface is unavailable). The solve still runs, just without the warm start.
    """


class MilpSolverFallbackWarning(UserWarning):
    """Warning emitted when ``solver="auto"`` falls back from Gurobi to HiGHS.

    Raised (via :func:`warnings.warn`) by :func:`solve_operational_milp` when the Gurobi solve
    fails (``solver_error``: e.g. a missing or size-limited licence) and the model is solved again
    with HiGHS. The same message is prepended to the result's ``warnings``.
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
    landing_usage: dict[tuple[str, ShiftKey], int]
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
        large ladders), or ``"auto"``: Gurobi when ``SolverFactory("gurobi")`` is available,
        otherwise HiGHS; a Gurobi run that fails (``solver_error``, e.g. a missing or size-limited
        licence) is retried with HiGHS and a :class:`MilpSolverFallbackWarning` is emitted (#139).
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
        The function never raises because a model is infeasible, a limit was hit without an
        incumbent, or the solver failed (#115): exceptions raised by the solver interface (e.g.
        ``gurobipy.GurobiError`` for a missing or size-limited licence, #139) are reported as
        ``outcome="error"`` with ``solver_error`` set. Keys:

        ``objective`` (float | None)
            Objective of the loaded solution; ``None`` without a feasible solution. A solve
            stopped by a limit (time, iterations, objective) that holds a feasible incumbent
            reports that incumbent.
        ``production`` (float)
            Total machine production of the solution (0.0 without one).
        ``assignments`` (DataFrame)
            Columns ``machine_id, block_id, day, shift_id, assigned, production``; one row per
            assigned slot or slot with production > 1e-6. Production is clamped at 0 (no
            ``-0.0`` or solver-noise negatives). Empty (same columns) without a solution.
        ``has_solution`` (bool)
            ``True`` when a feasible solution was loaded into the model.
        ``outcome`` (str)
            ``"optimal"``, ``"feasible"`` (incumbent at a limit), ``"infeasible"``,
            ``"no_solution"`` (limit reached without an incumbent) or ``"error"``.
        ``solver_status``, ``termination_condition`` (str)
            Pyomo solver status and termination condition.
        ``solver_error`` (str | None)
            Set when the solver failed rather than proving infeasibility: HiGHS ``ERROR`` log
            lines (e.g. ``Option 'threads' is set to 1 but global scheduler has already been
            initialized``), a solver exception raised during ``solve``, or an error/unknown
            termination without a solution.
        ``warnings`` (list[str])
            Locks the model had to drop or pin to zero instead of becoming infeasible (see
            :func:`fhops.model.milp.data.resolve_locked_slots`).
        ``warm_start`` (dict)
            Warm-start report (below).
        ``solver`` (str)
            ``SolverFactory`` name that produced the result (the selected candidate for
            ``solver="auto"``).

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
            solvers, or no start passed). When the HiGHS log carries no verdict, acceptance is
            inferred (``True``) if a solution was returned and either its ``x`` values equal the
            seeded ones, or the returned objective is at least the seed objective and the seed
            satisfies every model constraint (checked on the recorded seed values, only when
            needed; tolerance 1e-6).
        ``acceptance`` (str | None)
            ``"log"`` when ``accepted`` comes from the HiGHS log, ``"inferred"`` when it was
            inferred as described above, ``None`` otherwise.
        ``solver_messages`` (list[str])
            HiGHS log lines that mention the MIP start (empty for other solvers).

    Warns
    -----
    MilpWarmStartWarning
        When an incumbent was supplied but the solver interface cannot take a MIP start (the solve
        continues without it).
    MilpSolverFallbackWarning
        When ``solver="auto"`` falls back from a failed Gurobi run to HiGHS.

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

    if solver.strip().lower() == "auto":
        return _solve_auto(
            bundle,
            time_limit=time_limit,
            gap=gap,
            tee=tee,
            solver_options=solver_options,
            incumbent_assignments=incumbent_assignments,
            context=context,
        )

    model = build_operational_model(bundle)
    meta = getattr(model, "_warm_start_meta", None)
    if meta is not None and context is not None:
        meta["operational_problem"] = context
    model_warnings = [str(item) for item in (meta or {}).get("warnings", ())]
    seeded = 0
    if incumbent_assignments is not None:
        seeded = _apply_incumbent_start(model, incumbent_assignments)
    seed_snapshot = _snapshot_seed(model) if seeded > 0 else None

    warm_info: dict[str, Any] = {
        "requested": incumbent_assignments is not None and not incumbent_assignments.empty,
        "seeded_slots": seeded,
        "method": None,
        "solver": None,
        "accepted": None,
        "acceptance": None,
        "solver_messages": [],
    }
    opt, solver_used, method = _create_solver(solver, warm_start=seeded > 0)
    warm_info["method"] = method
    warm_info["solver"] = solver_used
    try:
        if time_limit is not None:
            opt.options["time_limit"] = time_limit
        if gap is not None:
            # Different solvers expect different gap parameter names.
            opt.options["mipgap"] = gap  # Gurobi/CPLEX-style
            if not any(name in solver.lower() for name in ("gurobi", "cplex")):
                opt.options["mip_rel_gap"] = gap  # HiGHS-style
        if solver_options:
            for key, value in solver_options.items():
                opt.options[str(key)] = value
        solve_kwargs: dict[str, object] = {"tee": tee, "load_solutions": False}
        if method is not None:
            solve_kwargs["warmstart"] = True
        run = _run_solver(opt, model, solve_kwargs, appsi=method == "appsi_highs")
    except Exception as exc:  # solver creation/configuration failures are reported, not raised
        run = _SolveRun(
            status="error",
            termination="error",
            has_solution=False,
            log_lines=[],
            error=f"{type(exc).__name__}: {exc}",
        )
    status = run.status
    termination = run.termination
    has_solution = run.has_solution
    solver_error = run.error
    if solver_error is None and not has_solution:
        error_lines = [line for line in run.log_lines if _HIGHS_ERROR_LINE.match(line.strip())]
        if error_lines:
            solver_error = " ".join(line.strip() for line in error_lines)
        elif termination.lower() in _ERROR_TERMINATIONS:
            solver_error = (
                f"solver returned no solution (status={status}, termination={termination})"
            )
    if method == "appsi_highs":
        accepted, messages = _parse_highs_start_log(run.log_lines)
        warm_info["accepted"] = accepted
        warm_info["solver_messages"] = messages
        if accepted is not None:
            warm_info["acceptance"] = "log"
        elif has_solution and seed_snapshot is not None and _seed_accepted(model, seed_snapshot):
            warm_info["accepted"] = True
            warm_info["acceptance"] = "inferred"

    objective_value: float | None = None
    if has_solution:
        assignments = _extract_assignments(model)
        prod = float(sum(max(0.0, pyo.value(model.prod[idx])) for idx in model.prod))
        objective_value = float(pyo.value(model.objective))
    else:
        assignments = pd.DataFrame(columns=ASSIGNMENT_COLUMNS)
        prod = 0.0
    if solver_error is not None:
        outcome = "error"
    elif has_solution:
        outcome = "optimal" if termination.lower() == "optimal" else "feasible"
    elif termination.lower() in _INFEASIBLE_TERMINATIONS:
        outcome = "infeasible"
    else:
        outcome = "no_solution"
    return {
        "objective": objective_value,
        "production": prod,
        "assignments": assignments,
        "has_solution": has_solution,
        "outcome": outcome,
        "solver_status": status,
        "termination_condition": termination,
        "solver_error": solver_error,
        "warnings": model_warnings,
        "warm_start": warm_info,
        "solver": solver,
    }


def _solve_auto(bundle: OperationalMilpBundle, **kwargs: Any) -> dict[str, Any]:
    """Solve with Gurobi when available, falling back to HiGHS on a Gurobi failure.

    Every candidate of :data:`AUTO_SOLVER_CANDIDATES` except HiGHS is skipped when
    ``SolverFactory(name).available()`` is false. A candidate whose result reports
    ``solver_error`` (missing or size-limited licence, solver exception, ...) is followed by the
    next one; the failure is emitted as :class:`MilpSolverFallbackWarning` and prepended to the
    returned ``warnings``. The result's ``solver`` names the solver that produced it.
    """

    candidates = [
        name for name in AUTO_SOLVER_CANDIDATES if name == "highs" or _named_solver_available(name)
    ]
    notes: list[str] = []
    result: dict[str, Any] = {}
    for index, name in enumerate(candidates):
        result = solve_operational_milp(bundle, solver=name, **kwargs)
        if result.get("solver_error") is None or index == len(candidates) - 1:
            break
        message = (
            f"{name} failed ({result['solver_error']}); falling back to "
            f"{candidates[index + 1]} (solver=auto)."
        )
        warnings.warn(message, MilpSolverFallbackWarning, stacklevel=3)
        notes.append(message)
    result["warnings"] = notes + list(result.get("warnings") or [])
    return result


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


def _named_solver_available(name: str) -> bool:
    try:
        return _solver_available(SolverFactory(name))
    except Exception:
        return False


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


@dataclass(slots=True)
class _SolveRun:
    """Outcome of one solver call (see :func:`_run_solver`)."""

    status: str
    termination: str
    has_solution: bool
    log_lines: list[str]
    error: str | None = None


def _run_solver(
    opt: Any, model: pyo.ConcreteModel, solve_kwargs: Mapping[str, object], *, appsi: bool
) -> _SolveRun:
    """Solve ``model`` without automatic solution loading and load a solution only if one exists.

    Every path calls ``opt.solve(..., load_solutions=False)`` so infeasible models, limits without
    an incumbent and solver errors never raise ``NoFeasibleSolutionError`` (or the equivalent
    legacy errors). A solution is loaded when the solver holds one:

    * APPSI HiGHS (``appsi=True``): ``opt.load_vars()`` when ``results.solution`` is non-empty;
    * ``pyomo.contrib.solver`` interfaces wrapped in ``LegacySolverWrapper`` (Pyomo's default
      ``highs``): ``model.solutions.load_from(results)`` when the wrapper reports an incumbent;
    * legacy plugins: ``model.solutions.load_from(results)`` when the termination is optimal /
      feasible, or a limit was hit while a finite incumbent objective is reported.

    The HiGHS log is captured (and still streamed to stdout when ``tee=True``) so callers can
    report ``ERROR`` lines and MIP-start messages. Every exception raised by the solver interface
    during ``solve`` (e.g. :class:`pyomo.common.errors.ApplicationError`, ``RuntimeError``, or
    ``gurobipy.GurobiError`` for a missing or size-limited Gurobi licence) is returned as
    ``error`` (#139).
    """

    if appsi:
        return _solve_appsi_highs(opt, model, solve_kwargs)

    kwargs = dict(solve_kwargs)
    kwargs["load_solutions"] = False
    stream: io.StringIO | None = None
    if _is_contrib_wrapper(opt):
        stream = io.StringIO()
        kwargs["tee"] = [stream, sys.stdout] if solve_kwargs.get("tee") else [stream]
    try:
        result = opt.solve(model, **kwargs)
    except Exception as exc:  # any solver failure (e.g. gurobipy.GurobiError) is reported
        return _SolveRun(
            status="error",
            termination="error",
            has_solution=False,
            log_lines=stream.getvalue().splitlines() if stream is not None else [],
            error=f"{type(exc).__name__}: {exc}",
        )
    log_lines = stream.getvalue().splitlines() if stream is not None else []
    solver_info = getattr(result, "solver", None)
    status = str(getattr(solver_info, "status", "unknown"))
    termination = str(getattr(solver_info, "termination_condition", "unknown"))
    solution = getattr(result, "solution", None)
    try:
        holds_solution = solution is not None and len(solution) > 0
    except TypeError:
        holds_solution = False
    if stream is None and holds_solution:
        # Legacy plugins may attach a solution object for non-feasible terminations.
        status_key, termination_key = status.lower(), termination.lower()
        holds_solution = termination_key in _SOLVED_TERMINATIONS or status_key in {
            "optimal",
            "feasible",
        }
        if not holds_solution and termination_key in _LIMIT_TERMINATIONS:
            holds_solution = _has_incumbent(result, model)
    has_solution = False
    error: str | None = None
    if holds_solution:
        try:
            model.solutions.load_from(result)
            has_solution = True
        except Exception as exc:  # pragma: no cover - defensive: malformed solver output
            error = f"failed to load the solver solution: {type(exc).__name__}: {exc}"
    return _SolveRun(
        status=status,
        termination=termination,
        has_solution=has_solution,
        log_lines=log_lines,
        error=error,
    )


def _is_contrib_wrapper(opt: Any) -> bool:
    try:
        from pyomo.contrib.solver.common.base import LegacySolverWrapper
    except ImportError:  # pragma: no cover - older Pyomo without contrib.solver
        return False
    return isinstance(opt, LegacySolverWrapper)


def _solve_appsi_highs(
    opt: Any, model: pyo.ConcreteModel, solve_kwargs: Mapping[str, object]
) -> _SolveRun:
    """Run a warm-started APPSI HiGHS solve, capturing the HiGHS log.

    Solutions are loaded explicitly (``load_solutions=False`` + ``opt.load_vars()``) because the
    APPSI interface raises when asked to load a solution that does not exist. The HiGHS log is
    routed to a private logger (also streamed to stdout when ``tee=True``) so the caller can tell
    whether the MIP start was accepted and report HiGHS ``ERROR`` lines.
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
    error: str | None = None
    status = termination = "error"
    has_solution = False
    try:
        result = opt.solve(model, **kwargs)
        status = str(result.solver.status)
        termination = str(result.solver.termination_condition)
        solution = getattr(result, "solution", None)
        has_solution = bool(solution is not None and len(solution) > 0)
        if has_solution:
            opt.load_vars()
    except Exception as exc:  # any solver failure (e.g. gurobipy.GurobiError) is reported
        error = f"{type(exc).__name__}: {exc}"
        has_solution = False
    finally:
        highs_logger.removeHandler(collector)
        highs_logger.setLevel(previous_level)
        highs_logger.propagate = previous_propagate
    return _SolveRun(
        status=status,
        termination=termination,
        has_solution=has_solution,
        log_lines=collector.lines,
        error=error,
    )


@dataclass(slots=True)
class _SeedSnapshot:
    """Seeded values recorded before the solve (warm-start acceptance inference).

    Feasibility of the seed is only evaluated when needed (:func:`_seed_accepted`), because a full
    constraint check costs seconds on large models (ka_6: ~10 s).
    """

    values: list[tuple[Any, float | None]]
    x_values: dict[Any, float]
    objective: float | None


def _snapshot_seed(model: pyo.ConcreteModel) -> _SeedSnapshot:
    """Record every seeded variable value, the seeded assignment and its objective."""

    values = [(var, var.value) for var in model.component_data_objects(pyo.Var)]
    x_values = {index: float(var.value or 0.0) for index, var in model.x.items()}
    objective = pyo.value(model.objective, exception=False)
    return _SeedSnapshot(
        values=values,
        x_values=x_values,
        objective=float(objective) if objective is not None else None,
    )


def _seed_is_feasible(model: pyo.ConcreteModel, seed: _SeedSnapshot) -> bool:
    """Evaluate the seed's feasibility, restoring the loaded solution afterwards."""

    current = [(var, var.value) for var, _ in seed.values]
    try:
        for var, value in seed.values:
            var.set_value(value, skip_validation=True)
        return _max_violation(model) <= _SEED_FEASIBILITY_TOLERANCE
    finally:
        for var, value in current:
            var.set_value(value, skip_validation=True)


def _max_violation(model: pyo.ConcreteModel) -> float:
    """Largest absolute bound/integrality violation of the current variable values."""

    worst = 0.0
    for var in model.component_data_objects(pyo.Var, active=True):
        value = var.value
        if value is None:
            return math.inf
        if var.lb is not None and value < var.lb:
            worst = max(worst, var.lb - value)
        if var.ub is not None and value > var.ub:
            worst = max(worst, value - var.ub)
        if var.is_integer():
            worst = max(worst, abs(value - round(value)))
    for con in model.component_data_objects(pyo.Constraint, active=True):
        body = pyo.value(con.body, exception=False)
        if body is None:
            return math.inf
        if con.has_lb():
            worst = max(worst, pyo.value(con.lower) - body)
        if con.has_ub():
            worst = max(worst, body - pyo.value(con.upper))
    return worst


def _seed_accepted(model: pyo.ConcreteModel, seed: _SeedSnapshot) -> bool:
    """Infer MIP-start acceptance when the solver log is silent.

    Returns ``True`` when the returned incumbent assigns exactly the seeded ``x`` values, or when
    the seed satisfied every constraint (so HiGHS could adopt it as its first incumbent) and the
    returned objective is at least the seed objective (relative tolerance 1e-9).
    """

    returned = {index: float(var.value or 0.0) for index, var in model.x.items()}
    if all(abs(returned[index] - value) <= 0.5 for index, value in seed.x_values.items()):
        return True
    if seed.objective is None:
        return False
    objective = pyo.value(model.objective, exception=False)
    if objective is None:
        return False
    tolerance = 1e-9 * max(1.0, abs(seed.objective))
    if float(objective) < seed.objective - tolerance:
        return False
    return _seed_is_feasible(model, seed)


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
        # Clamp solver noise (-0.0, -1e-12) so exported production is never negative zero.
        production_value = max(
            0.0, float(pyo.value(model.prod[machine_id, block_id, (day, shift_id)]))
        )
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
    landing_usage: defaultdict[tuple[str, ShiftKey], int] = defaultdict(int)

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
                landing_usage[(landing_id, (day, shift_id))] += 1

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
    landing_usage: defaultdict[tuple[str, ShiftKey], int] = defaultdict(int)
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
            landing_usage[(landing_id, shift)] += 1

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

    Locked slots take the locked block when the lock is effective and are cleared when the lock
    pins the machine to zero (unavailable slot, contradictory lock), mirroring the
    ``locked_assignment`` constraints (:func:`fhops.model.milp.data.resolve_locked_slots`) so the
    seeded ``x`` values respect locks.
    """

    if not bundle.locked_assignments:
        return
    grid = set(shift_list)
    targets, _ = resolve_locked_slots(bundle)
    for (machine_id, slot), block_id in targets.items():
        if slot not in grid:
            continue
        key = (machine_id, slot)
        if block_id is not None:
            assignment_lookup[key] = block_id
        else:
            assignment_lookup.pop(key, None)


def _seed_moves(
    model: pyo.ConcreteModel, bundle: OperationalMilpBundle, shift_list: tuple[ShiftKey, ...]
) -> None:
    """Seed the position-network variables (``stay``, ``depart``, ``arrive``, ``y``, ``first``,
    ``unplaced``) from the seeded ``x``.

    A machine's position is the block of its last worked slot (or its carried-in block); it moves
    when it works another block, as in
    :func:`fhops.optimization.heuristics.common._recompute_mobilisation_for`.
    """

    if not hasattr(model, "stay"):
        return
    worked: dict[tuple[str, ShiftKey], str] = {}
    for (machine_id, block_id, day, shift_id), var in model.x.items():
        if (var.value or 0.0) > 0.5:
            worked[(machine_id, (int(day), str(shift_id)))] = block_id
    before: dict[tuple[str, ShiftKey], str | None] = {}
    after: dict[tuple[str, ShiftKey], str | None] = {}
    for machine_id in model.M:
        position = bundle.initial_machine_block.get(machine_id)
        for slot in shift_list:
            before[(machine_id, slot)] = position
            block_id = worked.get((machine_id, slot))
            if block_id is not None:
                position = block_id
            after[(machine_id, slot)] = position

    def _moved(machine_id: str, slot: ShiftKey) -> tuple[str | None, str | None]:
        """``(from, to)`` when the machine changes position in ``slot``, else ``(None, None)``."""

        prev_block = before[(machine_id, slot)]
        block_id = worked.get((machine_id, slot))
        if block_id is None or prev_block == block_id:
            return None, None
        return prev_block, block_id

    def _set(var: Any, value: bool) -> None:
        var.set_value(1.0 if value else 0.0)
        var.stale = False

    for (machine_id, block_id, day, shift_id), var in model.stay.items():
        slot = (day, shift_id)
        _set(var, before[(machine_id, slot)] == block_id and _moved(machine_id, slot)[1] is None)
    for (machine_id, block_id, day, shift_id), var in model.depart.items():
        source, target = _moved(machine_id, (day, shift_id))
        _set(var, target is not None and source == block_id)
    for (machine_id, block_id, day, shift_id), var in model.arrive.items():
        source, target = _moved(machine_id, (day, shift_id))
        _set(var, source is not None and target == block_id)
    for (machine_id, prev_blk, block_id, day, shift_id), var in model.y.items():
        _set(var, _moved(machine_id, (day, shift_id)) == (prev_blk, block_id))
    for (machine_id, block_id, day, shift_id), var in model.first.items():
        source, target = _moved(machine_id, (day, shift_id))
        _set(var, source is None and target == block_id)
    for (machine_id, day, shift_id), var in model.unplaced.items():
        _set(var, after[(machine_id, (day, shift_id))] is None)


def _seed_model_from_state(
    model: pyo.ConcreteModel, meta: Mapping[str, Any], state: _IncumbentState
) -> None:
    bundle: OperationalMilpBundle = meta["bundle"]
    assignment_lookup = state.assignment_lookup
    production_lookup = state.production_lookup
    role_prod_lookup = state.role_prod_lookup
    landing_usage = state.landing_usage
    shift_list: tuple[ShiftKey, ...] = meta.get("shift_list") or tuple(model.S)
    inventory_pairs: tuple[tuple[str, str], ...] = tuple(meta.get("inventory_pairs", ()))
    role_upstream: Mapping[tuple[str, str], tuple[str, ...]] = meta.get("role_upstream", {})
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

    _seed_moves(model, bundle, shift_list)

    if hasattr(model, "role_active"):
        role_to_machines: Mapping[str, tuple[str, ...]] = meta.get("role_to_machines", {})
        locked_on_block: frozenset = meta.get("locked_on_block", frozenset())
        for (role, block_id, day, shift_id), var in model.role_active.items():
            shift = _slot_key(day, shift_id)
            key = (role, block_id, shift)
            # Active when the role produces, or when an unlocked machine of the role is assigned
            # (role_active_upper); locked machines may sit idle without activating the role.
            unlocked_assigned = any(
                assignment_lookup.get((mach, shift)) == block_id
                and (mach, block_id, shift) not in locked_on_block
                for mach in role_to_machines.get(role, ())
            )
            produced = role_prod_lookup.get(key, 0.0) > 1e-9
            active = produced or unlocked_assigned
            var.set_value(1.0 if active else 0.0)
            var.stale = False

    cumulative_before: dict[tuple[str, str, ShiftKey], float] = {}
    if hasattr(model, "role_cumulative"):
        cumulative: dict[tuple[str, str], float] = {}
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
    if hasattr(model, "upstream_done"):
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

    if hasattr(model, "landing_surplus") and hasattr(model, "LandingSurplusIndex"):
        # Unit slack pieces: the first (usage - capacity) pieces of a slot are 1.
        for landing_id, day, shift_id, piece in model.LandingSurplusIndex:
            cap = max(int(bundle.landing_capacity.get(landing_id, 0)), 0)
            usage = landing_usage.get((landing_id, _slot_key(day, shift_id)), 0)
            var = model.landing_surplus[landing_id, day, shift_id, piece]
            var.set_value(1.0 if piece <= usage - cap else 0.0)
            var.stale = False

    if hasattr(model, "loader_tail"):
        loader_block_batch: Mapping[str, float] = meta.get("loader_block_batch", {})
        delivered: dict[str, float] = defaultdict(float)
        delivered_before: dict[tuple[str, ShiftKey], float] = {}
        for day, shift_id in shift_list:
            shift = _slot_key(day, shift_id)
            for block_id in bundle.blocks:
                delivered_before[(block_id, shift)] = delivered[block_id]
                delivered[block_id] += sum(
                    role_prod_lookup.get((role, block_id, shift), 0.0)
                    for role in block_terminal_roles.get(block_id, ())
                )
        for (block_id, day, shift_id), var in model.loader_tail.items():
            shift = _slot_key(day, shift_id)
            threshold = bundle.work_required.get(block_id, 0.0) - loader_block_batch.get(
                block_id, 0.0
            )
            reached = delivered_before.get((block_id, shift), 0.0) >= threshold - 1e-9
            var.set_value(1.0 if reached else 0.0)
            var.stale = False

    if inventory_pairs:
        # Staged inventory per upstream role u: output of u minus what its downstream roles used.
        stage_downstream: Mapping[tuple[str, str], tuple[str, ...]] = meta.get(
            "stage_downstream", {}
        )
        initial_start: Mapping[tuple[str, str], float] = meta.get("initial_inventory_start", {})
        inventory_prev: dict[tuple[str, str], float] = {
            pair: float(initial_start.get(pair, 0.0)) for pair in inventory_pairs
        }
        for day, shift_id in shift_list:
            shift = _slot_key(day, shift_id)
            for up_role, block_id in inventory_pairs:
                start_value = inventory_prev[(up_role, block_id)]
                inv_start = model.inventory_start[up_role, block_id, day, shift_id]
                inv_start.set_value(start_value)
                inv_start.stale = False
                staged_output = role_prod_lookup.get((up_role, block_id, shift), 0.0)
                consumed = sum(
                    role_prod_lookup.get((down_role, block_id, shift), 0.0)
                    for down_role in stage_downstream.get((up_role, block_id), ())
                )
                end_value = max(0.0, start_value + staged_output - consumed)
                inv_var = model.inventory[up_role, block_id, day, shift_id]
                inv_var.set_value(end_value)
                inv_var.stale = False
                inventory_prev[(up_role, block_id)] = end_value

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
