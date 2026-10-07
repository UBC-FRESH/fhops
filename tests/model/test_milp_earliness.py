"""Lexicographic earliness tie-break of the operational MILP (#141).

Stage 1 solves the base objective (OBJ); stage 2 maximises the production-weighted earliness
``E = Σ_s w_s Σ_{m,b} p[m,b,s]`` subject to ``OBJ ≥ z1 − τ``. The reported objective is always
OBJ, and the tie-break never trades OBJ for earliness.
"""

from __future__ import annotations

import pytest

import fhops.model.milp.driver as driver
from fhops.model.milp.driver import EARLINESS_OBJECTIVE_TOLERANCE, solve_operational_milp
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scenario.io import load_scenario


def _defer_scenario(num_days: int = 6) -> Scenario:
    """One machine, one 300 m³ block, rate 100: three working days, any three of the horizon."""

    return Scenario(
        name="defer",
        num_days=num_days,
        blocks=[Block(id="B1", landing_id="L1", work_required=300)],
        machines=[Machine(id="F1", role="feller_buncher")],
        landings=[Landing(id="L1", daily_capacity=2)],
        calendar=[
            CalendarEntry(machine_id="F1", day=day, available=1) for day in range(1, num_days + 1)
        ],
        production_rates=[ProductionRate(machine_id="F1", block_id="B1", rate=100)],
    )


def _solve(scenario: Scenario, **kwargs: object) -> dict:
    ctx = build_operational_problem(Problem.from_scenario(scenario))
    return solve_operational_milp(ctx.bundle, solver="highs", time_limit=60, context=ctx, **kwargs)


def _worked_days(result: dict) -> list[int]:
    frame = result["assignments"]
    return sorted(int(day) for day in frame.loc[frame["production"] > 1e-6, "day"])


def test_earliness_moves_tied_production_to_the_first_slots() -> None:
    plain = _solve(_defer_scenario())
    early = _solve(_defer_scenario(), earliness=True)

    assert plain["earliness"] is None
    assert plain["outcome"] == early["outcome"] == "optimal"
    assert early["objective"] == pytest.approx(plain["objective"], abs=1e-6)
    assert early["objective"] == pytest.approx(300.0)
    assert _worked_days(early) == [1, 2, 3]
    info = early["earliness"]
    assert info["status"] == "applied"
    assert info["stage1_objective"] == pytest.approx(300.0)
    assert info["objective_floor"] == pytest.approx(300.0 - EARLINESS_OBJECTIVE_TOLERANCE * 300.0)
    # E = 100 · (6 + 5 + 4) / 6 for days 1-3 of a 6-slot horizon.
    assert info["value"] == pytest.approx(250.0)
    assert info["value"] >= info["stage1_value"] - 1e-9
    assert info["runtime_s"] is not None


def test_earliness_never_trades_the_base_objective() -> None:
    """A weighted ``OBJ + ε·E`` picks the early, worse plan here for every ε > 0 (δ < 25ε).

    Block A is open on day 1 only (rate 100, 100 m³), block B on day 2 only (rate 100 + δ,
    100 + δ m³), and a move costs 1000, so the machine works one block. OBJ: A only −δ, B only
    +δ; E (weights 1 and 1/2): A only 100, B only 50 + δ/2. The lexicographic tie-break keeps the
    OBJ-optimal plan (B).
    """

    delta = 1e-3
    scenario = Scenario(
        name="no-trade",
        num_days=2,
        blocks=[
            Block(id="A", landing_id="L1", work_required=100, earliest_start=1, latest_finish=1),
            Block(
                id="B",
                landing_id="L1",
                work_required=100 + delta,
                earliest_start=2,
                latest_finish=2,
            ),
        ],
        machines=[Machine(id="M1")],
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[CalendarEntry(machine_id="M1", day=day, available=1) for day in (1, 2)],
        production_rates=[
            ProductionRate(machine_id="M1", block_id="A", rate=100),
            ProductionRate(machine_id="M1", block_id="B", rate=100 + delta),
        ],
        objective_weights=ObjectiveWeights(transitions=1000.0),
    )
    early = _solve(scenario, earliness=True)

    assert early["objective"] == pytest.approx(delta, abs=1e-7)
    assert set(early["assignments"]["block_id"]) == {"B"}
    assert early["earliness"]["status"] == "applied"
    assert early["earliness"]["value"] == pytest.approx(50 + delta / 2)


def test_tiny7_objective_unchanged_with_earliness() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    plain = _solve(scenario)
    early = _solve(scenario, earliness=True)

    assert early["outcome"] == "optimal"
    assert early["objective"] == pytest.approx(plain["objective"], rel=2e-6)
    assert early["earliness"]["status"] == "applied"
    assert early["earliness"]["value"] >= early["earliness"]["stage1_value"] - 1e-6


def test_failed_earliness_stage_keeps_the_stage1_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    real = driver._run_solver
    calls = {"n": 0}

    def flaky(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:
            return driver._SolveRun("error", "error", False, [], "RuntimeError: boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(driver, "_run_solver", flaky)
    plain = _solve(_defer_scenario())
    calls["n"] = 0
    result = _solve(_defer_scenario(), earliness=True)

    assert calls["n"] == 2
    assert result["outcome"] == "optimal"
    assert result["solver_error"] is None
    assert result["objective"] == pytest.approx(plain["objective"])
    assert _worked_days(result) == _worked_days(plain)
    info = result["earliness"]
    assert info["status"] == "kept_stage1"
    assert info["solver_error"] == "RuntimeError: boom"
    assert info["value"] == info["stage1_value"]


def test_earliness_skipped_without_a_stage1_solution() -> None:
    ctx = build_operational_problem(Problem.from_scenario(_defer_scenario()))
    failed = solve_operational_milp(ctx.bundle, solver="nosuchsolver", context=ctx, earliness=True)
    assert failed["outcome"] == "error"
    assert failed["earliness"] == {"status": "skipped"}


def test_solve_mip_operational_earliness_flag(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from fhops.cli.main import app
    from tests.cli import CliRunner, cli_text

    out = tmp_path / "plan.csv"
    args = ["solve-mip-operational", "examples/tiny7/scenario.yaml", "--out", str(out)]
    plain = CliRunner().invoke(app, args)
    early = CliRunner().invoke(app, [*args, "--earliness"])

    assert plain.exit_code == 0 and early.exit_code == 0, cli_text(early)
    assert "Earliness tie-break" not in cli_text(plain)
    text = cli_text(early)
    assert "Earliness tie-break: status=applied" in text
    assert "objective=279.79603" in text
