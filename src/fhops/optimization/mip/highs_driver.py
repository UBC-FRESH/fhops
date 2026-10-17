"""Deprecated ``solve_mip`` entry point (delegates to the operational MILP since 1.0.1, #127).

This module backs :func:`solve_mip` and the ``fhops solve-mip`` / ``fhops benchmark`` CLI
commands. Since FHOPS 1.0.1 (#127) they solve the operational MILP
(:func:`fhops.model.milp.driver.solve_operational_milp`, the formulation documented in the
SoftwareX paper) through :func:`solve_with_operational_milp`; the legacy ``--driver`` names are
mapped to operational solver names by :func:`operational_solver_for_driver`.

The legacy day-level MIP (:func:`fhops.optimization.mip.builder.build_model`) is infeasible for
every scenario with a loader role (see :mod:`fhops.optimization.mip.deprecation`). Its 1.0.1 (#124)
solve path is kept as the private ``_solve_legacy_mip`` to reproduce that finding; no public entry
point uses it.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Mapping
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyomo.environ as pyo

from fhops.optimization.mip.builder import build_model
from fhops.optimization.mip.deprecation import LEGACY_SOLVE_MIP_MESSAGE, LegacyMipDeprecationWarning
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem

if TYPE_CHECKING:
    from fhops.model.milp.driver import _SolveRun

__all__ = [
    "ASSIGNMENT_COLUMNS",
    "SolverUnavailable",
    "operational_solver_for_driver",
    "solve_mip",
    "solve_with_operational_milp",
]

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
# Legacy ``--driver`` value -> operational MILP solver name (``auto`` is handled separately).
_OPERATIONAL_SOLVER_BY_DRIVER = {
    "highs": "highs",
    "appsi": "highs",
    "highs-appsi": "highs",
    "exec": "highs",
    "highs-exec": "highs",
    "gurobi": "gurobi",
    "gurobi-appsi": "appsi_gurobi",
    "gurobi-direct": "gurobi_direct",
}


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


def operational_solver_for_driver(driver: str) -> tuple[str, ...]:
    """Map a legacy MIP ``driver`` name to the operational MILP solver name(s) to try.

    Parameters
    ----------
    driver :
        Legacy driver name (case-insensitive): ``auto``, ``highs``, ``appsi``, ``highs-appsi``,
        ``exec``, ``highs-exec``, ``gurobi``, ``gurobi-appsi`` or ``gurobi-direct``.

    Returns
    -------
    tuple[str, ...]
        ``SolverFactory`` names in the order they are tried: ``("gurobi", "highs")`` for ``auto``
        (Gurobi when installed, otherwise or after a Gurobi failure HiGHS — the 1.0.0 ``auto``
        rule); ``("highs",)`` for every HiGHS driver (seeded solves still go through
        ``appsi_highs``, see :func:`fhops.model.milp.driver.solve_operational_milp`);
        ``("gurobi",)``, ``("appsi_gurobi",)`` or ``("gurobi_direct",)`` for the Gurobi drivers.

    Raises
    ------
    ValueError
        For an unknown driver name.
    """

    key = driver.strip().lower()
    if key == "auto":
        return ("gurobi", "highs")
    if key not in _OPERATIONAL_SOLVER_BY_DRIVER:
        raise ValueError(
            f"Unknown MIP driver '{driver}'. "
            "Supported values: auto, highs, highs-appsi, highs-exec, gurobi, gurobi-appsi, "
            "gurobi-direct."
        )
    return (_OPERATIONAL_SOLVER_BY_DRIVER[key],)


def _operational_solver_available(name: str) -> bool:
    """Return ``True`` when ``SolverFactory(name)`` reports an available solver."""

    try:
        return bool(pyo.SolverFactory(name).available(exception_flag=False))
    except Exception:
        return False


def solve_with_operational_milp(
    pb: Problem, time_limit: int | None = 60, driver: str = "auto", debug: bool = False
) -> dict[str, Any]:
    """Solve the operational MILP for ``pb`` using a legacy ``driver`` name (no deprecation).

    This is the implementation behind :func:`solve_mip`, ``fhops solve-mip`` and the MIP step of
    ``fhops benchmark``. It builds the operational problem
    (:func:`fhops.optimization.operational_problem.build_operational_problem`) and calls
    :func:`fhops.model.milp.driver.solve_operational_milp` with ``solver`` from
    :func:`operational_solver_for_driver`, ``time_limit``, ``tee=debug`` and the operational
    context. Equivalent to ``fhops solve-mip-operational SCENARIO --solver <solver>
    --time-limit <time_limit>``.

    Parameters
    ----------
    pb :
        :class:`fhops.scenario.contract.Problem` built with ``Problem.from_scenario``.
    time_limit :
        Solver wall-clock limit in seconds (default 60; ``None`` leaves the solver default).
    driver :
        Legacy driver name (see :func:`operational_solver_for_driver`).
    debug :
        Stream the solver log to stdout and print the selected solver.

    Returns
    -------
    dict
        The :func:`fhops.model.milp.driver.solve_operational_milp` result (``objective``,
        ``production``, ``assignments``, ``has_solution``, ``outcome``, ``solver_status``,
        ``termination_condition``, ``solver_error``, ``warnings``, ``warm_start``) plus
        ``solver`` (the ``SolverFactory`` name that produced it). Under ``driver="auto"`` a Gurobi
        run that reports ``solver_error`` is retried with HiGHS and the failure is prepended to
        ``warnings``.

    Raises
    ------
    SolverUnavailable
        When no candidate solver is available.
    ValueError
        For an unknown ``driver`` name (raised before the model is built).
    """

    candidates = operational_solver_for_driver(driver)
    available = [name for name in candidates if _operational_solver_available(name)]
    if not available:
        raise SolverUnavailable(
            f"No operational MILP solver available for driver={driver!r} "
            f"(tried: {', '.join(candidates)})."
        )
    ctx = build_operational_problem(pb)
    solve_operational_milp = _milp_driver().solve_operational_milp
    notes: list[str] = []
    result: dict[str, Any] = {}
    for index, name in enumerate(available):
        if debug:
            console.print(f"[bold cyan]FHOPS[/]: operational MILP solver [bold]{name}[/].")
        result = dict(
            solve_operational_milp(
                ctx.bundle, solver=name, time_limit=time_limit, tee=bool(debug), context=ctx
            )
        )
        result["solver"] = name
        if result.get("solver_error") is None or index == len(available) - 1:
            break
        notes.append(
            f"{name} failed ({result['solver_error']}); falling back to {available[index + 1]} "
            f"(driver={driver})."
        )
    result["warnings"] = notes + list(result.get("warnings") or [])
    return result


def solve_mip(
    pb: Problem, time_limit: int = 60, driver: str = "auto", debug: bool = False
) -> Mapping[str, object]:
    """Solve ``pb`` with the operational MILP (deprecated legacy entry point).

    .. deprecated:: 1.0.1
       Emits :class:`fhops.optimization.mip.deprecation.LegacyMipDeprecationWarning` and delegates
       to :func:`solve_with_operational_milp` (i.e.
       :func:`fhops.model.milp.driver.solve_operational_milp`). Until 1.0.1 this function solved the
       legacy day-level MIP, which is infeasible for every scenario with a loader role (#124,
       #127). Call :func:`fhops.model.milp.driver.solve_operational_milp` directly.

    Parameters
    ----------
    pb :
        :class:`fhops.scenario.contract.Problem` built with ``Problem.from_scenario``.
    time_limit :
        Solver wall-clock limit in seconds (default 60).
    driver :
        Legacy driver name, mapped by :func:`operational_solver_for_driver`: ``"auto"`` (Gurobi
        when installed, otherwise — or after a Gurobi solver error — HiGHS), ``"highs"`` /
        ``"highs-appsi"`` / ``"appsi"`` / ``"highs-exec"`` / ``"exec"`` (HiGHS), ``"gurobi"``,
        ``"gurobi-appsi"`` (``appsi_gurobi``) or ``"gurobi-direct"`` (``gurobi_direct``).
    debug :
        Stream the solver log to stdout and print the selected solver.

    Returns
    -------
    dict
        Same contract as in 1.0.1 (#124); the function never raises because a model is
        infeasible, a limit was reached without an incumbent, or an available solver failed.
        Keys:

        ``objective`` (float | None)
            Operational MILP objective of the loaded solution (not comparable with 1.0.0 legacy
            objectives); ``None`` without a feasible solution. A solve stopped by a limit that
            holds a feasible incumbent reports that incumbent.
        ``assignments`` (DataFrame)
            Columns ``machine_id, block_id, day, shift_id, assigned, production``; one row per
            assigned slot or slot with production > 1e-6. Empty (same columns) without a
            solution.
        ``has_solution`` (bool)
            ``True`` when a feasible solution was loaded into the model.
        ``outcome`` (str)
            ``"optimal"``, ``"feasible"`` (incumbent at a limit), ``"infeasible"``,
            ``"no_solution"`` (limit reached without an incumbent) or ``"error"``.
        ``solver_status``, ``termination_condition`` (str)
            Pyomo solver status and termination condition.
        ``solver_error`` (str | None)
            Set when the solver failed rather than proving infeasibility.
        ``warnings`` (list[str])
            Driver notes (e.g. a Gurobi failure under ``driver="auto"`` before the HiGHS retry)
            followed by the operational driver's lock warnings.
        ``production`` (float), ``warm_start`` (dict), ``solver`` (str)
            Added by the delegation (see :func:`solve_with_operational_milp`).

    Raises
    ------
    SolverUnavailable
        When the requested solver is not installed (or, for ``driver="auto"``, neither Gurobi
        nor HiGHS is available).
    ValueError
        For an unknown ``driver`` name.

    Warns
    -----
    LegacyMipDeprecationWarning
        On every call.

    Examples
    --------
    >>> res = solve_mip(pb, time_limit=60)  # doctest: +SKIP
    >>> # preferred:
    >>> from fhops.model.milp.driver import solve_operational_milp  # doctest: +SKIP
    >>> from fhops.optimization.operational_problem import build_operational_problem  # doctest: +SKIP
    >>> ctx = build_operational_problem(pb)  # doctest: +SKIP
    >>> res = solve_operational_milp(ctx.bundle, time_limit=60, context=ctx)  # doctest: +SKIP
    """

    warnings.warn(LEGACY_SOLVE_MIP_MESSAGE, LegacyMipDeprecationWarning, stacklevel=2)
    return solve_with_operational_milp(pb, time_limit=time_limit, driver=driver, debug=debug)


def _solve_legacy_mip(
    pb: Problem, time_limit: int = 60, driver: str = "auto", debug: bool = False
) -> dict[str, Any]:
    """Build and solve the legacy day-level MIP (private; kept to reproduce the #124 finding).

    This is the FHOPS 1.0.0 – 1.0.1 (#124) implementation of ``solve_mip``. It returns the result
    mapping documented in :func:`solve_mip` (without ``production``/``warm_start``), raises
    :class:`SolverUnavailable` for a missing solver and ``ValueError`` for an unknown ``driver``.
    The legacy model is infeasible for scenarios with loader roles (see
    :mod:`fhops.optimization.mip.deprecation`); no public entry point calls this function.
    """
    driver_clean = driver.lower()
    if driver_clean not in _KNOWN_DRIVERS:
        raise ValueError(
            f"Unknown MIP driver '{driver}'. "
            "Supported values: auto, highs, highs-appsi, highs-exec, gurobi, gurobi-appsi, "
            "gurobi-direct."
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", LegacyMipDeprecationWarning)
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
    reported. Every solver exception (``ApplicationError``, ``RuntimeError``,
    ``gurobipy.GurobiError``, ...) is returned as ``error``.
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
    except Exception as exc:  # any solver failure (e.g. gurobipy.GurobiError) is reported
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
