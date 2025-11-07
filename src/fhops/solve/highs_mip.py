from __future__ import annotations

import pandas as pd
import pyomo.environ as pyo

from fhops.model.pyomo_builder import build_model
from fhops.scenario.contract import Problem

try:
    from rich.console import Console
except Exception:  # pragma: no cover - rich optional

    class Console:  # type: ignore[no-redef]
        """Fallback console with a no-op print."""

        def print(self, *args, **kwargs) -> None:  # noqa: D401 - simple shim
            return None


console = Console()


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
        opt = pyo.SolverFactory("highs")
        return opt if opt and opt.available() else None
    except Exception:
        return None


def _set_appsi_controls(solver, time_limit: int, debug: bool) -> bool:
    """
    Configures the solver settings for APPSI Highs solver in a way
    that is compatible with multiple versions.

    Parameters
    ----------
    solver : object
        The APPSI Highs solver instance to configure.
    time_limit : int
        The maximum time (in seconds) the solver is allowed to run.
    debug : bool
        If True, enables streaming of solver logs.

    Returns
    -------
    bool
        True if any settings were successfully applied, False otherwise.
    """
    # Newer APPSI: solver.config
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

    # Fallback (older style): solver.options
    try:
        if hasattr(solver, "options"):
            solver.options["time_limit"] = time_limit  # may not exist; best effort
            return True
    except Exception:
        pass

    return False


def solve_mip(pb: Problem, time_limit: int = 60, driver: str = "auto", debug: bool = False):
    """
    Build and solve the FHOPS MIP with HiGHS (APPSI or exec).

    Parameters
    ----------
    pb : Problem
        Validated FHOPS Problem.
    time_limit : int
        Seconds.
    driver : {"auto","appsi","exec"}
        Prefer APPSI (Python) or the 'highs' executable; "auto" picks APPSI if present.
    debug : bool
        If True, stream solver logs where supported.
    """
    model = build_model(pb)

    # Decide which HiGHS driver to use
    use_appsi: bool | None = None
    if driver == "appsi":
        use_appsi = True
    elif driver == "exec":
        use_appsi = False
    if use_appsi is None:
        use_appsi = _try_appsi_highs() is not None

    if use_appsi:
        solver = _try_appsi_highs()
        if solver is None:
            raise RuntimeError("Requested driver=appsi, but appsi.highs is unavailable.")
        _set_appsi_controls(solver, time_limit=time_limit, debug=debug)
        if debug:
            console.print("[bold cyan]FHOPS[/]: using [bold]appsi.highs[/] driver.")
        solver.solve(model)
    else:
        opt = _try_exec_highs()
        if opt is None:
            raise RuntimeError("HiGHS solver not available (no 'highs' executable found).")
        # Prefer solver.options; fall back to timelimit kw
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

    # Extract solution
    rows = []
    for m in model.M:
        for b in model.B:
            for d in model.D:
                x = pyo.value(model.x[m, b, d])
                prod = pyo.value(model.prod[m, b, d])
                if x > 0.5 or prod > 1e-6:
                    rows.append(
                        {
                            "machine_id": m,
                            "block_id": b,
                            "day": int(d),
                            "assigned": int(x > 0.5),
                            "production": float(prod),
                        }
                    )
    df = pd.DataFrame(rows).sort_values(["day", "machine_id", "block_id"])
    obj = pyo.value(model.obj)
    return {"objective": obj, "assignments": df}
