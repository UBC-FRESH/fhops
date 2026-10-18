#!/usr/bin/env python3
"""Regenerate the pinned 1.0.1 SA baselines after a deliberate search change.

The SA random stream is part of the pinned result. When the search changes on purpose (for
example, the bounded cross-exchange sampling in 1.1.0b2), the ``*_v101.csv`` assignment tables and
the ``sa_objective_v101`` / ``kpis_v101`` entries in ``tests/fixtures/v100_regression/baseline.json``
must be refreshed. The v1.0.0 baseline (``v100_fresh_objective``, ``sa_objective``, ``kpis``) is
left unchanged.

Usage
-----
    python scripts/regenerate_sa_baselines.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics import solve_sa
from fhops.optimization.heuristics.common import (
    evaluate_schedule,
    resolve_objective_weight_overrides,
)
from fhops.optimization.heuristics.ils import _assignments_to_schedule
from fhops.optimization.operational_problem import (
    build_operational_problem,
    override_objective_weights,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v100_regression"
CASES = [
    ("tiny7", 300, 123, "tiny7_sa_seed123_iters300_v101.csv"),
    ("med42", 150, 7, "med42_sa_seed7_iters150_v101.csv"),
]
COLUMNS = ["machine_id", "block_id", "day", "shift_id", "assigned"]


def _fresh_objective(pb: Problem, assignments: pd.DataFrame) -> float:
    ctx = build_operational_problem(pb)
    overrides = resolve_objective_weight_overrides(pb, None)
    if overrides:
        ctx = override_objective_weights(ctx, overrides)
    return float(evaluate_schedule(pb, _assignments_to_schedule(pb, assignments), ctx))


def main() -> int:
    """Rewrite the SA fixtures and print the new pinned values.

    Returns
    -------
    int
        0 on success.
    """
    baseline = json.loads((FIXTURES / "baseline.json").read_text(encoding="utf-8"))
    for name, iters, seed, fixture in CASES:
        pb = Problem.from_scenario(load_scenario(str(ROOT / "examples" / name / "scenario.yaml")))
        result = solve_sa(pb, iters=iters, seed=seed)
        assignments = (
            result["assignments"]
            .sort_values(["machine_id", "day", "shift_id"])
            .reset_index(drop=True)
        )
        assignments[COLUMNS].to_csv(FIXTURES / fixture, index=False)
        kpis = {key: value for key, value in compute_kpis(pb, result["assignments"]).items()}
        entry = baseline[f"{name}_sa"]
        entry["sa_objective_v101"] = float(_fresh_objective(pb, result["assignments"]))
        entry["kpis_v101"] = json.loads(json.dumps(kpis, default=str))
        print(f"{name}: sa_objective_v101={entry['sa_objective_v101']}")
    (FIXTURES / "baseline.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
