from __future__ import annotations
from pathlib import Path
import pandas as pd
import pyomo.environ as pyo

from fhops.core.types import Problem
from fhops.model.pyomo_builder import build_model

def _try_appsi_highs():
    try:
        from pyomo.contrib.appsi.solvers.highs import Highs
        return Highs()
    except Exception:
        return None

def _try_exec_highs():
    try:
        opt = pyo.SolverFactory("highs")
        ok = opt.available()
        return opt if ok else None
    except Exception:
        return None

def solve_mip(pb: Problem, time_limit: int = 60):
    model = build_model(pb)
    solver = _try_appsi_highs()
    if solver is not None:
        solver.options["time_limit"] = time_limit
        res = solver.solve(model)
    else:
        opt = _try_exec_highs()
        if opt is None:
            raise RuntimeError("HiGHS solver not available (neither appsi.highs nor highs executable).")
        res = opt.solve(model, tee=False, timelimit=time_limit)

    # Extract solution
    rows = []
    for m in model.M:
        for b in model.B:
            for d in model.D:
                x = pyo.value(model.x[m, b, d])
                prod = pyo.value(model.prod[m, b, d])
                if x > 0.5 or prod > 1e-6:
                    rows.append({"machine_id": m, "block_id": b, "day": int(d), "assigned": int(x > 0.5), "production": float(prod)})
    df = pd.DataFrame(rows).sort_values(["day","machine_id","block_id"])
    obj = pyo.value(model.obj)
    return {"objective": obj, "assignments": df}
