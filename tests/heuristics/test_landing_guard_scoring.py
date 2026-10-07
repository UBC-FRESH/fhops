"""Hard-violation penalty, planned-production scoring and weight-override reporting (#140).

* Audit MINOR-E: a flat 1000 penalty per hard violation let an SA plan that overloads a hard
  landing beat the MILP's hard optimum when one machine-shift is worth more than 1000.
* Audit MINOR-F: ``evaluate_schedule`` proposes full rates, so it charged ``missing_prereq``
  penalties on operational-MILP plans that plan partial or zero production;
  ``evaluate_assignments`` scores a table with its ``production`` column, as playback does.
* Audit 4: ``AUTO_OBJECTIVE_WEIGHT_OVERRIDES`` (Tiny7/Small21) were applied silently.
"""

from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

import fhops.optimization.heuristics.ils as ils_module
from fhops.cli.benchmarks import WEIGHT_COLUMNS, run_benchmark_suite
from fhops.evaluation import compute_kpis
from fhops.model.milp.driver import solve_operational_milp
from fhops.optimization.heuristics import solve_ils, solve_sa, solve_tabu
from fhops.optimization.heuristics.common import (
    AUTO_OBJECTIVE_WEIGHT_OVERRIDES,
    evaluate_assignments,
    evaluate_schedule,
    objective_weight_override_notice,
    objective_weight_override_source,
)
from fhops.optimization.heuristics.ils import _assignments_to_schedule
from fhops.optimization.operational_problem import (
    HARD_VIOLATION_PENALTY_FLOOR,
    build_operational_problem,
    override_objective_weights,
)
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

TINY7 = "examples/tiny7/scenario.yaml"
TOL = 1e-6


def _land_hard_problem() -> Problem:
    """Two 2000 m³/shift machines, one 4000 m³ block, landing capacity 1 (audit land_hard.py)."""

    scenario = Scenario(
        name="land-hard",
        num_days=1,
        blocks=[Block(id="B1", landing_id="L1", work_required=4000.0)],
        machines=[Machine(id="M1"), Machine(id="M2")],
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[CalendarEntry(machine_id=m, day=1, available=1) for m in ("M1", "M2")],
        production_rates=[
            ProductionRate(machine_id=m, block_id="B1", rate=2000.0) for m in ("M1", "M2")
        ],
        objective_weights=ObjectiveWeights(production=1.0, mobilisation=0.0, landing_surplus=0.0),
    )
    return Problem.from_scenario(scenario)


def _landing_overloads(pb: Problem, assignments: pd.DataFrame) -> int:
    landing_of = {block.id: block.landing_id for block in pb.scenario.blocks}
    capacity = {landing.id: landing.daily_capacity for landing in pb.scenario.landings}
    used = Counter(
        (int(row.day), str(row.shift_id), landing_of[row.block_id])
        for row in assignments.itertuples()
    )
    return sum(max(0, count - capacity[key[2]]) for key, count in used.items())


def _tiny7_without_overrides() -> Problem:
    scenario = load_scenario(TINY7)
    return Problem.from_scenario(scenario.model_copy(update={"name": "tiny7-scenario-weights"}))


@pytest.fixture(scope="module")
def tiny7_milp_plan() -> tuple[Problem, dict]:
    pb = _tiny7_without_overrides()
    ctx = build_operational_problem(pb)
    result = solve_operational_milp(ctx.bundle, solver="highs", context=ctx, time_limit=120)
    assert result["outcome"] == "optimal"
    return pb, result


# --- MINOR-E: hard-violation penalty ------------------------------------------------------------


def test_hard_violation_penalty_dominates_one_assignment() -> None:
    pb = _land_hard_problem()
    ctx = build_operational_problem(pb)
    assert ctx.max_production_rate == 2000.0
    assert ctx.max_move_cost == 0.0
    assert ctx.hard_violation_penalty() == pytest.approx(2.0 * 1.0 * 2000.0 + 1.0)
    # Overrides change the penalty with the weights; small rates keep the v1.0.0 floor.
    heavier = override_objective_weights(ctx, {"production": 3.0})
    assert heavier.hard_violation_penalty() == pytest.approx(12001.0)
    tiny = override_objective_weights(ctx, {"production": 0.01})
    assert tiny.hard_violation_penalty() == HARD_VIOLATION_PENALTY_FLOOR


def test_reference_penalties_include_mobilisation_bound() -> None:
    for name in ("tiny7", "med42"):
        pb = Problem.from_scenario(load_scenario(f"examples/{name}/scenario.yaml"))
        ctx = build_operational_problem(pb)
        weights = ctx.bundle.objective_weights
        expected = (
            2.0 * weights.production * ctx.max_production_rate
            + weights.mobilisation * ctx.max_move_cost
            + 1.0
        )
        assert ctx.max_move_cost > 0.0
        assert ctx.hard_violation_penalty() == pytest.approx(max(1000.0, expected))


def test_sa_cannot_beat_the_milp_hard_landing_optimum() -> None:
    pb = _land_hard_problem()
    ctx = build_operational_problem(pb)
    milp = solve_operational_milp(ctx.bundle, solver="highs", context=ctx)
    assert milp["outcome"] == "optimal"
    milp_objective = float(milp["objective"])
    overloaded = pd.DataFrame(
        [
            {"machine_id": m, "block_id": "B1", "day": 1, "shift_id": "S1", "assigned": 1}
            for m in ("M1", "M2")
        ]
    )
    debug: dict[str, object] = {}
    # Scored as planned, the overloaded plan pays more than its extra machine-shift earns.
    # (before #140: 4000 delivered - 1000 = 3000 > 0, the MILP optimum).
    assert evaluate_assignments(pb, overloaded, ctx, debug=debug) < milp_objective
    assert debug["hard_violation_count"] == 1
    for run in (solve_sa, solve_ils, solve_tabu):
        result = run(pb, iters=50, seed=1)
        assert result["objective"] <= milp_objective + TOL
        assert _landing_overloads(pb, result["assignments"]) == 0


# --- MINOR-F: planned-production scoring -----------------------------------------------------


def test_evaluate_assignments_matches_heuristic_scores() -> None:
    pb = Problem.from_scenario(load_scenario("examples/med42/scenario.yaml"))
    result = solve_sa(pb, iters=60, seed=3)
    ctx = build_operational_problem(pb)
    assignments = result["assignments"]
    assert evaluate_assignments(pb, assignments, ctx) == pytest.approx(result["objective"], abs=TOL)
    # The same plan with its replayed production as a planned ``production`` column scores the same.
    kpi_frame = assignments.copy()
    tracker_rows = []
    from fhops.evaluation.playback import run_playback

    playback = run_playback(pb, assignments)
    production = {(r.machine_id, r.day, r.shift_id): r.production_units for r in playback.records}
    for row in kpi_frame.itertuples():
        tracker_rows.append(production[(row.machine_id, int(row.day), str(row.shift_id))])
    kpi_frame["production"] = tracker_rows
    assert evaluate_assignments(pb, kpi_frame, ctx) == pytest.approx(result["objective"], abs=TOL)


def test_proven_optimal_milp_plan_is_not_charged_missing_prereq(tiny7_milp_plan) -> None:
    pb, milp = tiny7_milp_plan
    ctx = build_operational_problem(pb)
    plan = milp["assignments"]
    debug: dict[str, object] = {}
    planned = evaluate_assignments(pb, plan, ctx, debug=debug)
    assert debug["hard_violation_count"] == 0
    assert debug["sequencing_violation_count"] == 0
    # Full-rate scoring (pre-#140 hybrid adoption) charges missing_prereq penalties on the same plan.
    rate_debug: dict[str, object] = {}
    as_is = evaluate_assignments(pb, plan.drop(columns=["production"]), ctx, debug=rate_debug)
    assert rate_debug["sequencing_violation_breakdown"].get("missing_prereq", 0) > 0
    repaired = evaluate_schedule(pb, _assignments_to_schedule(pb, plan), ctx)
    assert planned > max(as_is, repaired) + 1000.0
    # The remaining difference to the MILP objective is the MILP's cheaper idle-gap mobilisation.
    assert milp["objective"] - planned >= -TOL
    assert milp["objective"] - planned <= ctx.bundle.objective_weights.mobilisation * (
        ctx.max_move_cost
    )


def test_ils_hybrid_adopts_milp_plans_scored_as_planned(tiny7_milp_plan, monkeypatch) -> None:
    pb, milp = tiny7_milp_plan
    calls: list[dict] = []

    def _fake_milp(bundle, **kwargs):
        calls.append(kwargs)
        return {
            "outcome": "optimal",
            "objective": milp["objective"],
            "has_solution": True,
            "assignments": milp["assignments"].copy(),
            "warm_start": {"accepted": True, "seeded_slots": 1},
        }

    monkeypatch.setattr(ils_module, "solve_operational_milp", _fake_milp)
    result = solve_ils(pb, iters=3, seed=1, stall_limit=1, hybrid_use_mip=True)
    assert calls
    ctx = build_operational_problem(pb)
    planned = evaluate_assignments(pb, milp["assignments"], ctx)
    record = result["meta"]["hybrid_mip"][0]
    assert record["objective"] == milp["objective"]
    assert record["hybrid_score"] == pytest.approx(planned, abs=TOL)
    assert record["hybrid_rate_score"] < record["hybrid_score"]
    assert record["adopted"] is (planned > record["seed_score"])
    assert record["adopted"]
    # The adopted MILP plan is returned as planned and its score is reproducible.
    assert result["meta"]["hybrid_mip_adopted_final"] is True
    assert "production" in result["assignments"].columns
    assert result["objective"] == pytest.approx(planned, abs=TOL)
    assert evaluate_assignments(pb, result["assignments"], ctx) == pytest.approx(
        result["objective"], abs=TOL
    )
    assert compute_kpis(pb, result["assignments"])["sequencing_violation_count"] == 0


# --- Audit 4: weight-override transparency ----------------------------------------------------


def test_auto_overrides_are_recorded_in_meta() -> None:
    pb = Problem.from_scenario(load_scenario(TINY7))
    assert pb.scenario.name in AUTO_OBJECTIVE_WEIGHT_OVERRIDES
    assert objective_weight_override_source(pb, None) == "auto"
    assert objective_weight_override_source(pb, {"mobilisation": 0.1}) == "explicit"
    assert objective_weight_override_source(_tiny7_without_overrides(), None) is None
    for run in (solve_sa, solve_ils, solve_tabu):
        meta = run(pb, iters=5, seed=1)["meta"]
        assert (
            meta["objective_weight_overrides"] == AUTO_OBJECTIVE_WEIGHT_OVERRIDES[pb.scenario.name]
        )
        assert meta["objective_weight_overrides_source"] == "auto"
        assert meta["scenario_objective_weights"]["mobilisation"] == 0.5
        assert meta["objective_weights"]["landing_surplus"] == 0.05
        notice = objective_weight_override_notice(meta, pb.scenario.name)
        assert notice is not None
        assert "built-in weight overrides for FHOPS Tiny7" in notice
        assert "landing_surplus=0.05" in notice and "scenario weights" in notice
    explicit = solve_sa(pb, iters=5, seed=1, objective_weight_overrides={"mobilisation": 0.1})
    assert explicit["meta"]["objective_weight_overrides_source"] == "explicit"
    assert "user-supplied" in objective_weight_override_notice(explicit["meta"], "x")
    plain = solve_sa(_tiny7_without_overrides(), iters=5, seed=1)["meta"]
    assert "objective_weight_overrides" not in plain
    assert objective_weight_override_notice(plain) is None


def test_bench_suite_adds_scenario_weight_columns_last(tmp_path: Path) -> None:
    summary = run_benchmark_suite(
        [Path(TINY7)],
        tmp_path,
        time_limit=60,
        sa_iters=30,
        include_mip=True,
        include_ils=True,
        ils_iters=3,
        driver="highs",
    )
    columns = list(summary.columns)
    assert columns[-len(WEIGHT_COLUMNS) :] == list(WEIGHT_COLUMNS)
    on_disk = pd.read_csv(tmp_path / "summary.csv")
    assert list(on_disk.columns) == columns
    mip = summary[summary["solver"] == "mip"].iloc[0]
    assert mip["objective_weights_source"] == "scenario"
    assert mip["objective_scenario_weights"] == pytest.approx(mip["objective"])
    assert mip["objective_scenario_weights_vs_mip_gap"] == pytest.approx(0.0)
    pb = Problem.from_scenario(load_scenario(TINY7))
    for solver, csv in (("sa", "sa_assignments.csv"), ("ils", "ils_assignments.csv")):
        row = summary[summary["solver"] == solver].iloc[0]
        assert row["objective_weights_source"] == "auto"
        assert '"landing_surplus": 0.05' in row["objective_weight_overrides"]
        plan = pd.read_csv(tmp_path / "user-1" / csv)
        assert row["objective_scenario_weights"] == pytest.approx(
            evaluate_assignments(pb, plan), abs=TOL
        )
        assert row["objective_scenario_weights_vs_mip_gap"] == pytest.approx(
            mip["objective"] - row["objective_scenario_weights"], abs=TOL
        )
        # The existing gap column keeps comparing the solver's own objective.
        assert row["objective_vs_mip_gap"] == pytest.approx(mip["objective"] - row["objective"])


def test_cli_prints_override_notice_and_scenario_weight_objective(tmp_path: Path) -> None:
    from fhops.cli.main import app
    from tests.cli import CliRunner, cli_text

    out = tmp_path / "sa.csv"
    result = CliRunner().invoke(app, ["solve-heur", TINY7, "--out", str(out), "--iters", "20"])
    text = " ".join(cli_text(result).split())
    assert result.exit_code == 0, text
    assert "Note: Heuristic objective uses built-in weight overrides for FHOPS Tiny7" in text

    result = CliRunner().invoke(
        app,
        ["benchmark", TINY7, "--out-dir", str(tmp_path / "bench"), "--iters", "30"],
    )
    text = " ".join(cli_text(result).split())  # undo Rich line wrapping
    assert result.exit_code == 0, text
    assert "SA obj (override weights)=" in text
    assert "SA obj (scenario weights)=" in text
    pb = Problem.from_scenario(load_scenario(TINY7))
    sa_plan = pd.read_csv(tmp_path / "bench" / "sa_solution.csv")
    assert f"SA obj (scenario weights)={evaluate_assignments(pb, sa_plan):.3f}" in text

    copy_dir = tmp_path / "tiny7_copy"
    shutil.copytree(Path(TINY7).parent, copy_dir, ignore=shutil.ignore_patterns("out"))
    plain = copy_dir / "scenario.yaml"
    plain.write_text(
        plain.read_text(encoding="utf-8").replace("FHOPS Tiny7", "Tiny7 copy"), encoding="utf-8"
    )
    result = CliRunner().invoke(app, ["solve-heur", str(plain), "--out", str(out), "--iters", "20"])
    text = cli_text(result)
    assert result.exit_code == 0, text
    assert "weight overrides" not in text
