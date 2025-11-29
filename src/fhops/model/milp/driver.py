"""Operational MILP driver (solve + watch wrappers)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory

from fhops.model.milp.data import OperationalMilpBundle
from fhops.model.milp.operational import build_operational_model

ASSIGNMENT_COLUMNS = [
    "machine_id",
    "block_id",
    "day",
    "shift_id",
    "assigned",
    "production",
]

__all__ = ["solve_operational_milp"]


def solve_operational_milp(
    bundle: OperationalMilpBundle,
    solver: str = "highs",
    time_limit: int | None = None,
    gap: float | None = None,
    tee: bool = False,
) -> dict[str, Any]:
    """Solve the operational MILP given a prepared bundle."""

    model = build_operational_model(bundle)
    opt = SolverFactory(solver)
    if time_limit is not None:
        opt.options["time_limit"] = time_limit
    if gap is not None:
        # Different solvers expect different gap parameter names; set the common ones
        opt.options["mipgap"] = gap  # Gurobi/CPLEX-style
        opt.options["mip_rel_gap"] = gap  # HiGHS-style
    result = opt.solve(model, tee=tee, load_solutions=True)
    status = str(result.solver.status).lower()
    termination = str(result.solver.termination_condition).lower()
    solved = termination in {"optimal", "feasible"} or status in {"optimal", "feasible"}
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
    }


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
