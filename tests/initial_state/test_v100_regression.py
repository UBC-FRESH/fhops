"""Regression: without ``initial_state`` or locks, results match FHOPS v1.0.0 exactly (#91).

Baselines in ``tests/fixtures/v100_regression`` were captured on the unmodified ``v1.0.0`` code
(branch ``feature/phase8-v101-maintenance`` before #91) with:

* ``solve_sa(tiny7, iters=300, seed=123)`` and ``solve_sa(med42, iters=150, seed=7)``;
* ``solve_operational_milp(tiny7 bundle, solver="highs")`` (optimal);
* ``compute_kpis`` on the saved SA and MILP assignment tables.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from fhops.evaluation import compute_kpis
from fhops.model.milp.driver import solve_operational_milp
from fhops.optimization.heuristics import solve_sa
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

FIXTURES = Path("tests/fixtures/v100_regression")
BASELINE = json.loads((FIXTURES / "baseline.json").read_text(encoding="utf-8"))


def _problem(name: str) -> Problem:
    scenario = load_scenario(f"examples/{name}/scenario.yaml")
    assert scenario.initial_state is None
    assert not scenario.locked_assignments
    return Problem.from_scenario(scenario)


def _sorted(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["machine_id", "day", "shift_id"]).reset_index(drop=True)


def _assert_kpis_equal(actual: dict, expected: dict) -> None:
    assert set(actual) == set(expected)
    for key, value in expected.items():
        if isinstance(value, float):
            assert math.isclose(float(actual[key]), value, rel_tol=0.0, abs_tol=1e-9), key
        else:
            assert actual[key] == value, key


@pytest.mark.parametrize(
    ("name", "iters", "seed", "fixture"),
    [
        ("tiny7", 300, 123, "tiny7_sa_seed123_iters300.csv"),
        ("med42", 150, 7, "med42_sa_seed7_iters150.csv"),
    ],
)
def test_sa_matches_v100(name: str, iters: int, seed: int, fixture: str) -> None:
    baseline = BASELINE[f"{name}_sa"]
    result = solve_sa(_problem(name), iters=iters, seed=seed)
    assert result["objective"] == baseline["sa_objective"]
    expected = pd.read_csv(FIXTURES / fixture)
    actual = _sorted(result["assignments"])[list(expected.columns)]
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)


def test_operational_milp_matches_v100() -> None:
    pb = _problem("tiny7")
    ctx = build_operational_problem(pb)
    assert not ctx.bundle.has_initial_state()
    result = solve_operational_milp(ctx.bundle, solver="highs", context=ctx)
    assert result["termination_condition"].lower() == "optimal"
    assert result["objective"] == pytest.approx(BASELINE["tiny7_milp"]["milp_objective"], abs=1e-6)


@pytest.mark.parametrize(
    ("name", "fixture", "key"),
    [
        ("tiny7", "tiny7_sa_seed123_iters300.csv", ("tiny7_sa", "kpis")),
        ("med42", "med42_sa_seed7_iters150.csv", ("med42_sa", "kpis")),
        ("tiny7", "tiny7_milp_highs.csv", ("tiny7_milp", "playback_kpis")),
    ],
)
def test_playback_kpis_match_v100(name: str, fixture: str, key: tuple[str, str]) -> None:
    assignments = pd.read_csv(FIXTURES / fixture)
    actual = compute_kpis(_problem(name), assignments).to_dict()
    _assert_kpis_equal(actual, BASELINE[key[0]][key[1]])
