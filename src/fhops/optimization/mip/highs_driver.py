"""HiGHS driver for FHOPS MIP."""

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
    """Build and solve the FHOPS MIP with HiGHS (APPSI or exec)."""
    model = build_model(pb)

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

    rows = []
    for machine in model.M:
        for block in model.B:
            for day in model.D:
                assigned = pyo.value(model.x[machine, block, day])
                production = pyo.value(model.prod[machine, block, day])
                if assigned > 0.5 or production > 1e-6:
                    rows.append(
                        {
                            "machine_id": machine,
                            "block_id": block,
                            "day": int(day),
                            "assigned": int(assigned > 0.5),
                            "production": float(production),
                        }
                    )
    assignments = pd.DataFrame(rows).sort_values(["day", "machine_id", "block_id"])
    objective = pyo.value(model.obj)
    return {"objective": objective, "assignments": assignments}
