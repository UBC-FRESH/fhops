"""Legacy day-level MIP solver driver (HiGHS by default, optional Gurobi).

This module backs :func:`solve_mip` and the ``fhops solve-mip`` / ``fhops benchmark`` CLI
commands. It builds the legacy MIP (:func:`fhops.optimization.mip.builder.build_model`), dispatches
it to HiGHS (APPSI or Pyomo's ``highs`` interface) or Gurobi, and converts the solution into an
assignment table.

Since FHOPS 1.0.1 (#124) the driver follows the same result policy as the operational MILP driver
(:func:`fhops.model.milp.driver.solve_operational_milp`, #115): infeasible models, limits reached
without an incumbent and solver failures are reported in the result instead of raising.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyomo.environ as pyo
from pyomo.common.errors import ApplicationError

from fhops.optimization.mip.builder import build_model
from fhops.scenario.contract import Problem

if TYPE_CHECKING:
    from fhops.model.milp.driver import _SolveRun

__all__ = ["ASSIGNMENT_COLUMNS", "SolverUnavailable", "solve_mip"]

ASSIGNMENT_COLUMNS = ["machine_id", "block_id", "day", "shift_id", "assigned", "production"]
_APPSI_LOGGER_NAME = "fhops.optimization.mip.highs_driver.appsi"
_KNOWN_DRIVERS = frozenset(
    {
        "auto",
        "highs",
        "appsi",
        "highs-appsi",
        "exec",
        "highs-exec",
        "gurobi",
        "gurobi-appsi",
        "gurobi-direct",
    }
)


try:
    from rich.console import Console
except Exception:  # pragma: no cover - rich optional

    class Console:  # type: ignore[no-redef]
        """Fallback console with a no-op print."""

        def print(self, *args, **kwargs) -> None:
            return None


console = Console()


def _milp_driver() -> ModuleType:
    """Return :mod:`fhops.model.milp.driver` (imported lazily to avoid an import cycle).

    The legacy driver shares the operational driver's solve/load helpers and status vocabulary so
    both report missing solutions and solver errors identically (#115, #124).
    """

    from fhops.model.milp import driver

    return driver


class SolverUnavailable(RuntimeError):
    """Raised when a requested solver backend is not installed or cannot be created.

    This is the only solver-related exception :func:`solve_mip` raises; failures of an available
    solver are reported through the result's ``solver_error`` instead.
    """


def _try_appsi_highs():
    """Return APPSI Highs solver if available, else None."""
    try:
        from pyomo.contrib.appsi.solvers.highs import Highs

        solver = Highs()
        if not solver.available():
            return None
        return solver
    except Exception:
        return None


def _try_exec_highs():
    """Return Pyomo 'highs' executable interface if available, else None."""
    try:
        solver = pyo.SolverFactory("highs")
        return solver if solver and solver.available() else None
    except Exception:
        return None


def _set_appsi_controls(solver, time_limit: int, debug: bool) -> bool:
    """Configure APPSI solver with best-effort options."""
    try:
        cfg = getattr(solver, "config", None)
        if cfg is not None:
            if hasattr(cfg, "time_limit"):
                cfg.time_limit = time_limit
            if hasattr(cfg, "stream_solver"):
                cfg.stream_solver = bool(debug)
            return True
    except Exception:
        pass

    try:
        if hasattr(solver, "options"):
            solver.options["time_limit"] = time_limit
            return True
    except Exception:
        pass

    return False


def solve_mip(
    pb: Problem, time_limit: int = 60, driver: str = "auto", debug: bool = False
) -> Mapping[str, object]:
    """Build and solve the legacy FHOPS MIP.

    Parameters
    ----------
    pb :
        :class:`fhops.scenario.contract.Problem` built with ``Problem.from_scenario``.
    time_limit :
        Solver wall-clock limit in seconds (default 60).
    driver :
        ``"auto"`` (Gurobi when installed and licensed, otherwise HiGHS), ``"highs"`` /
        ``"highs-appsi"`` / ``"appsi"`` (HiGHS through Pyomo's APPSI interface, falling back to
        the ``highs`` interface for ``"highs"`` when APPSI is missing), ``"highs-exec"`` /
        ``"exec"`` (Pyomo's ``highs`` interface), ``"gurobi"``, ``"gurobi-appsi"`` or
        ``"gurobi-direct"``.
    debug :
        Stream the solver log to stdout and print the selected driver.

    Returns
    -------
    dict
        The function never raises because a model is infeasible, a limit was reached without an
        incumbent, or an available solver failed (#124, same policy as
        :func:`fhops.model.milp.driver.solve_operational_milp`). Keys:

        ``objective`` (float | None)
            Objective of the loaded solution; ``None`` without a feasible solution. A solve
            stopped by a limit that holds a feasible incumbent reports that incumbent.
        ``assignments`` (DataFrame)
            Columns ``machine_id, block_id, day, shift_id, assigned, production``; one row per
            assigned slot or slot with production > 1e-6, sorted by ``day, shift_id, machine_id,
            block_id``. Empty (same columns) without a solution.
        ``has_solution`` (bool)
            ``True`` when a feasible solution was loaded into the model.
        ``outcome`` (str)
            ``"optimal"``, ``"feasible"`` (incumbent at a limit), ``"infeasible"``,
            ``"no_solution"`` (limit reached without an incumbent) or ``"error"``.
        ``solver_status``, ``termination_condition`` (str)
            Solver status and termination condition (APPSI interfaces report ``"ok"`` /
            ``"error"`` as status and the APPSI termination name, e.g. ``"maxTimeLimit"``).
        ``solver_error`` (str | None)
            Set when the solver failed rather than proving infeasibility: HiGHS ``ERROR`` log
            lines (only when no solution was returned), a solver exception raised during
            ``solve``, or an error/unknown termination without a solution.
        ``warnings`` (list[str])
            Driver notes, e.g. a Gurobi interface that failed under ``driver="auto"`` before the
            driver fell back to the next interface or to HiGHS.

    Raises
    ------
    SolverUnavailable
        When the requested solver is not installed (or, for ``driver="auto"``, neither Gurobi
        nor HiGHS is available).
    ValueError
        For an unknown ``driver`` name.

    Notes
    -----
    Every interface is called without automatic solution loading (APPSI
    ``config.load_solution = False``; ``solve(..., load_solutions=False)`` otherwise), and a
    solution is loaded only when the solver holds one. The legacy MIP does not model
    ``Scenario.initial_state`` (see :func:`fhops.optimization.mip.builder.build_model`).

    Examples
    --------
    >>> res = solve_mip(pb, time_limit=60)  # doctest: +SKIP
    >>> if res["has_solution"]:  # doctest: +SKIP
    ...     print(res["outcome"], res["objective"], len(res["assignments"]))
    ... elif res["solver_error"]:
    ...     print("solver failed:", res["solver_error"])
    """
    driver_clean = driver.lower()
    if driver_clean not in _KNOWN_DRIVERS:
        raise ValueError(
            f"Unknown MIP driver '{driver}'. "
            "Supported values: auto, highs, highs-appsi, highs-exec, gurobi, gurobi-appsi, "
            "gurobi-direct."
        )
    model = build_model(pb)

    if driver_clean == "auto":
        notes: list[str] = []
        try:
            result = _solve_with_gurobi(model, time_limit, driver_hint="auto", debug=debug)
        except SolverUnavailable:
            result = None
        if result is not None and result["solver_error"] is not None:
            notes.extend(result["warnings"])
            notes.append(
                f"Gurobi failed ({result['solver_error']}); falling back to HiGHS (driver=auto)."
            )
            result = None
        if result is None:
            result = _solve_with_highs(model, time_limit, driver_hint="auto", debug=debug)
            result["warnings"] = notes + list(result["warnings"])
        return result

    if driver_clean in {"gurobi", "gurobi-appsi", "gurobi-direct"}:
        return _solve_with_gurobi(model, time_limit, driver_hint=driver_clean, debug=debug)

    return _solve_with_highs(model, time_limit, driver_hint=driver_clean, debug=debug)


def _solve_with_highs(
    model: pyo.ConcreteModel, time_limit: int, driver_hint: str, *, debug: bool
) -> dict[str, Any]:
    use_appsi: bool | None
    if driver_hint in {"appsi", "highs-appsi"}:
        use_appsi = True
    elif driver_hint in {"exec", "highs-exec"}:
        use_appsi = False
    else:
        use_appsi = _try_appsi_highs() is not None

    if use_appsi:
        solver = _try_appsi_highs()
        if solver is None:
            raise SolverUnavailable("Requested driver=appsi, but appsi.highs is unavailable.")
        _set_appsi_controls(solver, time_limit=time_limit, debug=debug)
        if debug:
            console.print("[bold cyan]FHOPS[/]: using [bold]appsi.highs[/] driver.")
        run = _run_appsi(solver, model)
    else:
        opt = _try_exec_highs()
        if opt is None:
            raise SolverUnavailable("HiGHS solver not available (no 'highs' executable found).")
        timelimit_kw: int | None = None
        options = getattr(opt, "options", None)
        if isinstance(options, dict):
            try:
                options["time_limit"] = time_limit
            except Exception:
                timelimit_kw = time_limit
        else:
            timelimit_kw = time_limit
        if debug:
            console.print("[bold cyan]FHOPS[/]: using [bold]highs (exec)[/] driver.")
        solve_kwargs: dict[str, object] = {"tee": bool(debug), "load_solutions": False}
        if timelimit_kw is not None:
            solve_kwargs["timelimit"] = timelimit_kw
        run = _milp_driver()._run_solver(opt, model, solve_kwargs, appsi=False)
    return _build_result(model, run)


def _solve_with_gurobi(
    model: pyo.ConcreteModel, time_limit: int, driver_hint: str, *, debug: bool
) -> dict[str, Any]:
    """Solve with Gurobi (APPSI first, then Pyomo's ``gurobi`` plugin).

    For ``driver_hint`` ``"auto"``/``"gurobi"`` an APPSI run that fails (``solver_error``) is
    retried with the ``gurobi`` plugin (noted in ``warnings``); when that plugin is missing the
    APPSI failure is returned. :class:`SolverUnavailable` is raised only when no requested Gurobi
    interface is available.
    """

    appsi_failure: dict[str, Any] | None = None
    if driver_hint in {"auto", "gurobi", "gurobi-appsi"}:
        solver = _try_appsi_gurobi()
        if solver:
            _set_appsi_gurobi_controls(solver, time_limit=time_limit, debug=debug)
            if debug:
                console.print("[bold cyan]FHOPS[/]: using [bold]appsi.gurobi[/] driver.")
            result = _build_result(model, _run_appsi(solver, model))
            if result["solver_error"] is None or driver_hint == "gurobi-appsi":
                return result
            appsi_failure = result
        elif driver_hint == "gurobi-appsi":
            raise SolverUnavailable(
                "Requested driver=gurobi-appsi, but appsi.gurobi is unavailable."
            )

    if driver_hint in {"auto", "gurobi", "gurobi-direct"}:
        opt = _try_exec_gurobi()
        if opt:
            _configure_exec_gurobi(opt, time_limit=time_limit, debug=debug)
            if debug:
                console.print("[bold cyan]FHOPS[/]: using [bold]gurobi (exec)[/] driver.")
            solve_kwargs = {"tee": bool(debug), "load_solutions": False}
            run = _milp_driver()._run_solver(opt, model, solve_kwargs, appsi=False)
            result = _build_result(model, run)
            if appsi_failure is not None:
                result["warnings"].insert(
                    0,
                    f"appsi.gurobi failed ({appsi_failure['solver_error']}); "
                    "used gurobi (exec) instead.",
                )
            return result
        if driver_hint == "gurobi-direct":
            raise SolverUnavailable(
                "Requested driver=gurobi-direct, but Gurobi interface is unavailable."
            )

    if appsi_failure is not None:
        return appsi_failure
    raise SolverUnavailable(
        "Gurobi solver unavailable (install gurobipy and ensure the license is configured)."
    )


def _run_appsi(solver: Any, model: pyo.ConcreteModel) -> _SolveRun:
    """Solve with a native APPSI solver (HiGHS or Gurobi) without automatic solution loading.

    ``config.load_solution`` is disabled so APPSI never raises for a missing solution; the solution
    is loaded with ``solver.load_vars()`` only when ``best_feasible_objective`` is set (optimal, or
    a limit with a valid incumbent). The solver log is routed to a private logger (and still
    streamed to stdout when ``config.stream_solver`` is set) so HiGHS ``ERROR`` lines can be
    reported. Solver exceptions (``ApplicationError``, ``RuntimeError``) are returned as ``error``.
    """

    milp_driver = _milp_driver()
    collector = milp_driver._LineCollector()
    solver_logger = logging.getLogger(_APPSI_LOGGER_NAME)
    previous_level = solver_logger.level
    previous_propagate = solver_logger.propagate
    solver_logger.addHandler(collector)
    solver_logger.setLevel(logging.DEBUG)
    solver_logger.propagate = False
    config = getattr(solver, "config", None)
    if config is not None:
        for name, value in (
            ("load_solution", False),
            ("solver_output_logger", solver_logger),
            ("log_level", logging.DEBUG),
        ):
            try:
                setattr(config, name, value)
            except (AttributeError, ValueError):
                pass
    status = termination = "error"
    has_solution = False
    error: str | None = None
    try:
        results = solver.solve(model)
        condition = getattr(results, "termination_condition", None)
        termination = str(getattr(condition, "name", condition))
        status = "error" if termination.lower() in milp_driver._ERROR_TERMINATIONS else "ok"
        if getattr(results, "best_feasible_objective", None) is not None:
            solver.load_vars()
            has_solution = True
    except (ApplicationError, RuntimeError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        status = termination = "error"
        has_solution = False
    finally:
        solver_logger.removeHandler(collector)
        solver_logger.setLevel(previous_level)
        solver_logger.propagate = previous_propagate
    return milp_driver._SolveRun(
        status=status,
        termination=termination,
        has_solution=has_solution,
        log_lines=collector.lines,
        error=error,
    )


def _build_result(model: pyo.ConcreteModel, run: _SolveRun) -> dict[str, Any]:
    """Convert a solver run into the result mapping documented in :func:`solve_mip`."""

    milp_driver = _milp_driver()
    solver_error = run.error
    termination = run.termination
    if solver_error is None and not run.has_solution:
        error_lines = [
            line for line in run.log_lines if milp_driver._HIGHS_ERROR_LINE.match(line.strip())
        ]
        if error_lines:
            solver_error = " ".join(line.strip() for line in error_lines)
        elif termination.lower() in milp_driver._ERROR_TERMINATIONS:
            solver_error = (
                f"solver returned no solution (status={run.status}, termination={termination})"
            )
    if run.has_solution:
        objective: float | None = float(pyo.value(model.obj))
        assignments = _extract_assignments(model)
    else:
        objective = None
        assignments = pd.DataFrame(columns=ASSIGNMENT_COLUMNS)
    if solver_error is not None:
        outcome = "error"
    elif run.has_solution:
        outcome = "optimal" if termination.lower() == "optimal" else "feasible"
    elif termination.lower() in milp_driver._INFEASIBLE_TERMINATIONS:
        outcome = "infeasible"
    else:
        outcome = "no_solution"
    return {
        "objective": objective,
        "assignments": assignments,
        "has_solution": run.has_solution,
        "outcome": outcome,
        "solver_status": run.status,
        "termination_condition": termination,
        "solver_error": solver_error,
        "warnings": [],
    }


def _extract_assignments(model: pyo.ConcreteModel) -> pd.DataFrame:
    rows = []
    for machine in model.M:
        for block in model.B:
            for day, shift_id in model.S:
                assigned = pyo.value(model.x[machine, block, (day, shift_id)])
                production = pyo.value(model.prod[machine, block, (day, shift_id)])
                if assigned > 0.5 or production > 1e-6:
                    rows.append(
                        {
                            "machine_id": machine,
                            "block_id": block,
                            "day": int(day),
                            "shift_id": shift_id,
                            "assigned": int(assigned > 0.5),
                            "production": float(production),
                        }
                    )
    if rows:
        return pd.DataFrame(rows).sort_values(["day", "shift_id", "machine_id", "block_id"])
    return pd.DataFrame(columns=ASSIGNMENT_COLUMNS)


def _try_appsi_gurobi():
    try:
        from pyomo.contrib.appsi.solvers.gurobi import Gurobi

        solver = Gurobi()
        try:
            available = solver.available()
        except TypeError:
            available = solver.available
        if not available:
            return None
        return solver
    except Exception:
        return None


def _try_exec_gurobi():
    try:
        solver = pyo.SolverFactory("gurobi")
        if solver is not None and solver.available(exception_flag=False):
            return solver
    except Exception:
        return None
    return None


def _set_appsi_gurobi_controls(solver, time_limit: int, debug: bool) -> bool:
    try:
        cfg = getattr(solver, "config", None)
        if cfg is not None:
            if hasattr(cfg, "time_limit"):
                cfg.time_limit = time_limit
            if hasattr(cfg, "verbosity"):
                cfg.verbosity = 10 if debug else 0
            return True
    except Exception:
        pass

    try:
        if hasattr(solver, "options"):
            solver.options["TimeLimit"] = time_limit
            return True
    except Exception:
        pass
    return False


def _configure_exec_gurobi(opt, *, time_limit: int, debug: bool) -> None:
    options = getattr(opt, "options", None)
    if not isinstance(options, dict):
        opt.options = {}
        options = opt.options
    options["TimeLimit"] = time_limit
    options["timelimit"] = time_limit
    if not debug:
        options.setdefault("OutputFlag", 0)
