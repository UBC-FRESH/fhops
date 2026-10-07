"""Regression: without ``initial_state`` or locks, results match FHOPS v1.0.0 (#91) or 1.0.1 pins.

Baselines in ``tests/fixtures/v100_regression`` were captured on the unmodified ``v1.0.0`` code
(branch ``feature/phase8-v101-maintenance`` before #91) with:

* ``solve_sa(tiny7, iters=300, seed=123)`` and ``solve_sa(med42, iters=150, seed=7)``;
* ``solve_operational_milp(tiny7 bundle, solver="highs")`` (optimal; since #125 reproduced only
  with non-binding landing capacities);
* ``compute_kpis`` on the saved SA and MILP assignment tables.

Since #131 (exact heuristic objective) the SA runs no longer reproduce v1.0.0: they are pinned to
the 1.0.1 results (``*_v101.csv``, ``sa_objective_v101``, ``kpis_v101``), while the v1.0.0 SA
tables remain KPI fixtures and document the overstated v1.0.0 objective. The med42 pins were
regenerated in #140 (hard landing guard on single-shift days: the plan no longer overloads
landings, objective -35524.91 -> 18572.27; 21239.54 once the repair reserves landing places for
downstream roles whose input is staged).
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

FIXTURES = Path("tests/fixtures/v100_regression")
BASELINE = json.loads((FIXTURES / "baseline.json").read_text(encoding="utf-8"))


def _problem(name: str) -> Problem:
    scenario = load_scenario(f"examples/{name}/scenario.yaml")
    assert scenario.initial_state is None
    assert not scenario.locked_assignments
    return Problem.from_scenario(scenario)


def _sorted(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["machine_id", "day", "shift_id"]).reset_index(drop=True)


def _fresh_objective(pb: Problem, assignments: pd.DataFrame) -> float:
    ctx = build_operational_problem(pb)
    overrides = resolve_objective_weight_overrides(pb, None)
    if overrides:
        ctx = override_objective_weights(ctx, overrides)
    return evaluate_schedule(pb, _assignments_to_schedule(pb, assignments), ctx)


def _assert_kpis_equal(actual: dict, expected: dict) -> None:
    assert set(actual) == set(expected)
    for key, value in expected.items():
        if isinstance(value, float):
            assert math.isclose(float(actual[key]), value, rel_tol=0.0, abs_tol=1e-6), key
        else:
            assert actual[key] == value, key


@pytest.mark.parametrize(
    ("name", "iters", "seed", "fixture"),
    [
        ("tiny7", 300, 123, "tiny7_sa_seed123_iters300_v101.csv"),
        ("med42", 150, 7, "med42_sa_seed7_iters150_v101.csv"),
    ],
)
def test_sa_matches_pinned_baseline(name: str, iters: int, seed: int, fixture: str) -> None:
    """Pinned 1.0.1 SA results (``*_v101.csv``, ``sa_objective_v101``).

    Until #131 these runs reproduced v1.0.0 exactly. The v1.0.0 search scored candidates with a
    mobilisation cache that could omit machines, so it optimised (and reported) an overstated
    objective; with the exact objective the SA trajectory and result differ from v1.0.0 (see
    :func:`test_v100_sa_objective_was_overstated`). The reported objective is a fresh evaluation
    of the exported schedule.
    """

    baseline = BASELINE[f"{name}_sa"]
    pb = _problem(name)
    result = solve_sa(pb, iters=iters, seed=seed)
    # Objective to 1e-6 (last-bit float differences across platforms); assignments exactly.
    assert result["objective"] == pytest.approx(baseline["sa_objective_v101"], rel=0, abs=1e-6)
    assert result["objective"] == _fresh_objective(pb, result["assignments"])
    assert result["objective"] > baseline["v100_fresh_objective"]
    expected = pd.read_csv(FIXTURES / fixture)
    actual = _sorted(result["assignments"])[list(expected.columns)]
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)


def test_operational_milp_matches_v100_without_binding_landings() -> None:
    """v1.0.0 objective once landing capacity cannot bind, less one uncharged idle-gap move.

    Since #125 the MILP limits machines per landing and shift slot, hard at
    ``landing_surplus = 0`` (v1.0.0: machine-shifts per day with a slack that was free at weight
    0, i.e. no limit). tiny7's capacity-1 landings therefore bind (objective 279.796036, see
    ``tests/model/test_milp_driver_robustness.py``). With capacities no plan can exceed, the
    v1.0.0 optimum 4388.082752 charged moves only between consecutive slots; since #139 a move
    across idle slots is charged as in the heuristics and KPIs, and the optimum (HiGHS and Gurobi)
    is 4361.462752 = 4388.082752 − 0.5·(50 + 0.02·162): full delivery with two moves instead of
    the one v1.0.0 charged.
    """

    pb = _problem("tiny7")
    scenario = pb.scenario
    landings = [
        landing.model_copy(update={"daily_capacity": len(scenario.machines)})
        for landing in scenario.landings
    ]
    pb = Problem.from_scenario(scenario.model_copy(update={"landings": landings}))
    ctx = build_operational_problem(pb)
    assert not ctx.bundle.has_initial_state()
    result = solve_operational_milp(ctx.bundle, solver="highs", context=ctx)
    assert result["termination_condition"].lower() == "optimal"
    idle_gap_move = 0.5 * (50.0 + 0.02 * 162.0)
    assert result["objective"] == pytest.approx(
        BASELINE["tiny7_milp"]["milp_objective"] - idle_gap_move, abs=1e-6
    )
    assert result["objective"] == pytest.approx(4361.462752, abs=1e-6)


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


@pytest.mark.parametrize(("name", "fixture"), [("tiny7", "tiny7_sa_seed123_iters300.csv")])
def test_v100_sa_objective_was_overstated(name: str, fixture: str) -> None:
    """v1.0.0 reported more than a fresh evaluation of its own SA schedule (#131).

    med42 is no longer checked: since #140 the fresh evaluation repairs the 1.0.0 schedule's
    single-shift landing overloads (hard landing guard on every day), so it no longer isolates the
    #131 mobilisation-cache overstatement (``v100_fresh_objective`` pins the repaired score).
    """

    baseline = BASELINE[f"{name}_sa"]
    fresh = _fresh_objective(_problem(name), pd.read_csv(FIXTURES / fixture))
    assert fresh == pytest.approx(baseline["v100_fresh_objective"], rel=0, abs=1e-6)
    assert baseline["sa_objective"] - fresh > 10.0


@pytest.mark.parametrize("name", ["tiny7", "med42"])
def test_pinned_sa_kpis(name: str) -> None:
    fixture = {
        "tiny7": "tiny7_sa_seed123_iters300_v101.csv",
        "med42": "med42_sa_seed7_iters150_v101.csv",
    }
    assignments = pd.read_csv(FIXTURES / fixture[name])
    actual = compute_kpis(_problem(name), assignments).to_dict()
    _assert_kpis_equal(actual, BASELINE[f"{name}_sa"]["kpis_v101"])
