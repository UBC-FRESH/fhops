"""MIP solver driver plumbing (HiGHS by default, optional Gurobi)."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import pyomo.environ as pyo

from fhops.optimization.mip.builder import build_model
from fhops.scenario.contract import Problem

__all__ = ["solve_mip"]


try:
    from rich.console import Console
except Exception:  # pragma: no cover - rich optional

    class Console:  # type: ignore[no-redef]
        """Fallback console with a no-op print."""

        def print(self, *args, **kwargs) -> None:
            return None


console = Console()


class SolverUnavailable(RuntimeError):
    """Raised when a requested solver backend is not available."""


def _try_appsi_highs():
    """Return APPSI Highs solver if available, else None."""
    try:
        from pyomo.contrib.appsi.solvers.highs import Highs

        return Highs()
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
    """Build and solve the FHOPS MIP."""
    driver_clean = driver.lower()
    model = build_model(pb)

    if driver_clean == "auto":
        try:
            return _solve_with_gurobi(model, time_limit, driver_hint="auto", debug=debug)
        except SolverUnavailable:
            return _solve_with_highs(model, time_limit, driver_hint="auto", debug=debug)

    if driver_clean in {"gurobi", "gurobi-appsi", "gurobi-direct"}:
        return _solve_with_gurobi(model, time_limit, driver_hint=driver_clean, debug=debug)

    if driver_clean in {"highs", "appsi", "highs-appsi", "exec", "highs-exec"}:
        return _solve_with_highs(model, time_limit, driver_hint=driver_clean, debug=debug)

    raise ValueError(
        f"Unknown MIP driver '{driver}'. "
        "Supported values: auto, highs, highs-appsi, highs-exec, gurobi, gurobi-appsi, gurobi-direct."
    )


def _solve_with_highs(model: pyo.ConcreteModel, time_limit: int, driver_hint: str, *, debug: bool):
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
        solver.solve(model)
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
        solve_kwargs: dict[str, object] = {"tee": bool(debug)}
        if timelimit_kw is not None:
            solve_kwargs["timelimit"] = timelimit_kw
        opt.solve(model, **solve_kwargs)
    return _extract_results(model)


def _solve_with_gurobi(
    model: pyo.ConcreteModel, time_limit: int, driver_hint: str, *, debug: bool
) -> Mapping[str, object]:
    solver = None
    if driver_hint in {"auto", "gurobi", "gurobi-appsi"}:
        solver = _try_appsi_gurobi()
        if solver:
            _set_appsi_gurobi_controls(solver, time_limit=time_limit, debug=debug)
            if debug:
                console.print("[bold cyan]FHOPS[/]: using [bold]appsi.gurobi[/] driver.")
            try:
                solver.solve(model)
                return _extract_results(model)
            except Exception:
                if driver_hint in {"gurobi-appsi"}:
                    raise
                solver = None  # fall through to exec attempt
        if driver_hint == "gurobi-appsi":
            raise SolverUnavailable("Requested driver=gurobi-appsi, but appsi.gurobi is unavailable.")

    if driver_hint in {"auto", "gurobi", "gurobi-direct"}:
        opt = _try_exec_gurobi()
        if opt:
            _configure_exec_gurobi(opt, time_limit=time_limit, debug=debug)
            if debug:
                console.print("[bold cyan]FHOPS[/]: using [bold]gurobi (exec)[/] driver.")
            try:
                opt.solve(model, tee=bool(debug))
                return _extract_results(model)
            except Exception:
                if driver_hint == "gurobi-direct":
                    raise
                opt = None
        if driver_hint == "gurobi-direct":
            raise SolverUnavailable("Requested driver=gurobi-direct, but Gurobi interface is unavailable.")

    raise SolverUnavailable(
        "Gurobi solver unavailable (install gurobipy and ensure the license is configured)."
    )


def _extract_results(model: pyo.ConcreteModel) -> Mapping[str, object]:
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
    assignments = pd.DataFrame(rows).sort_values(["day", "shift_id", "machine_id", "block_id"])
    objective = pyo.value(model.obj)
    return {"objective": objective, "assignments": assignments}


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
