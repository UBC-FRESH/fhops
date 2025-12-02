"""Operational MILP driver (solve + watch wrappers)."""

from __future__ import annotations

from collections.abc import Mapping
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
    solver_options: Mapping[str, object] | None = None,
    incumbent_assignments: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Solve the operational MILP given a prepared bundle."""

    model = build_operational_model(bundle)
    if incumbent_assignments is not None:
        _apply_incumbent_start(model, incumbent_assignments)

    opt = SolverFactory(solver)
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


def _apply_incumbent_start(
    model: pyo.ConcreteModel, assignments: pd.DataFrame | None
) -> int:
    """Populate variable starting values from an incumbent assignment matrix."""

    if assignments is None or assignments.empty:
        return 0

    required = {"machine_id", "block_id", "day", "shift_id"}
    missing = required - set(assignments.columns)
    if missing:
        raise ValueError(
            "Incumbent assignments missing required columns: "
            + ", ".join(sorted(missing))
        )

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
        index = (machine_id, block_id, day, shift_id)
        if index not in model.x:
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

        model.x[index].set_value(1.0)
        model.x[index].stale = False
        seeded += 1

        if has_production:
            prod_raw = getattr(row, "production")
            if pd.notna(prod_raw):
                try:
                    prod_val = float(prod_raw)
                except (TypeError, ValueError):
                    continue
                prod_index = (machine_id, block_id, day, shift_id)
                if prod_index in model.prod:
                    model.prod[prod_index].set_value(prod_val)
                    model.prod[prod_index].stale = False

    return seeded
