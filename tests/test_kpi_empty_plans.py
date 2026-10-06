"""KPIs for empty and partial assignment plans never look complete (#108)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from fhops.evaluation import (
    SamplingConfig,
    assignments_to_records,
    compute_kpis,
    day_dataframe_from_ensemble,
    run_playback,
    run_stochastic_playback,
    shift_dataframe_from_ensemble,
)
from fhops.planning import (
    RollingPlanResult,
    comparison_dataframe,
    compute_rolling_kpis,
    evaluate_rolling_plan,
)
from fhops.scenario.contract import (
    BlockInitialState,
    Problem,
    ScenarioInitialState,
    ScheduleLock,
)
from fhops.scenario.io import load_scenario

from .initial_state._scenarios import chain_scenario

PLAYBACK_FIXTURES = Path("tests/fixtures/playback")
PRE108_SNAPSHOT = json.loads(
    Path("tests/fixtures/kpi/pre108_snapshot.json").read_text(encoding="utf-8")
)
ASSIGNMENT_COLUMNS = ["machine_id", "block_id", "day", "shift_id", "assigned"]

ABSENT_FOR_EMPTY = {
    "mobilisation_cost",
    "mobilisation_cost_by_machine",
    "mobilisation_cost_by_landing",
    "utilisation_ratio_mean_shift",
    "utilisation_ratio_weighted_shift",
    "utilisation_ratio_by_machine",
    "utilisation_ratio_by_role",
    "downtime_hours_total",
    "downtime_production_loss_est",
    "downtime_hours_by_machine",
    "downtime_event_count",
    "weather_severity_total",
    "weather_hours_est",
    "weather_production_loss_est",
    "weather_severity_by_machine",
}


def _problem(name: str) -> Problem:
    return Problem.from_scenario(load_scenario(f"examples/{name}/scenario.yaml"))


def _total_required(pb: Problem) -> float:
    return float(sum(block.work_required for block in pb.scenario.blocks))


def _fixture_assignments(name: str) -> pd.DataFrame:
    return pd.read_csv(PLAYBACK_FIXTURES / f"{name}_assignments.csv")


def _empty_plans(pb: Problem) -> dict[str, pd.DataFrame | None]:
    machine = pb.scenario.machines[0].id
    block = pb.scenario.blocks[0].id
    unassigned = pd.DataFrame(
        [
            {"machine_id": machine, "block_id": block, "day": 1, "shift_id": "S1", "assigned": 0},
            {"machine_id": machine, "block_id": block, "day": 2, "shift_id": "S1", "assigned": 0},
        ]
    )
    return {
        "none": None,
        "no_columns": pd.DataFrame(),
        "columns_only": pd.DataFrame(columns=ASSIGNMENT_COLUMNS),
        "all_unassigned": unassigned,
    }


def _assert_zero_delivery(kpis: dict, pb: Problem) -> None:
    total = _total_required(pb)
    assert kpis["total_production"] == 0.0
    assert kpis["remaining_work_total"] == pytest.approx(total, abs=1e-9)
    assert kpis["staged_production"] == pytest.approx(total, abs=1e-9)
    assert kpis["completed_blocks"] == 0.0
    assert kpis["makespan_day"] == 0
    assert kpis["makespan_shift"] == "N/A"
    assert kpis["utilisation_ratio_mean_day"] == 0.0
    assert kpis["utilisation_ratio_weighted_day"] == 0.0
    assert not ABSENT_FOR_EMPTY & set(kpis)
    system_blocks = {block.id for block in pb.scenario.blocks if block.harvest_system_id}
    if system_blocks:
        assert kpis["sequencing_violation_count"] == 0
        assert kpis["sequencing_violation_blocks"] == 0
        assert kpis["sequencing_violation_days"] == 0
        assert kpis["sequencing_violation_breakdown"] == "none"
        assert kpis["sequencing_clean_blocks"] == len(system_blocks)


@pytest.mark.parametrize("name", ["tiny7", "med42"])
@pytest.mark.parametrize("case", ["none", "no_columns", "columns_only", "all_unassigned"])
def test_empty_plan_reports_zero_delivery(name: str, case: str) -> None:
    pb = _problem(name)
    plan = _empty_plans(pb)[case]

    result = run_playback(pb, plan)  # type: ignore[arg-type]
    assert result.records == ()
    assert result.shift_summaries == ()
    assert result.delivered_total == 0.0
    assert result.remaining_work_total == pytest.approx(_total_required(pb), abs=1e-9)
    assert result.sequencing_debug is not None
    assert result.sequencing_debug["completed_blocks"] == 0
    assert result.sequencing_debug["delivered_total"] == 0.0
    assert len(result.day_summaries) == pb.scenario.num_days

    kpis = compute_kpis(pb, plan)  # type: ignore[arg-type]
    _assert_zero_delivery(kpis.to_dict(), pb)
    assert kpis.shift_calendar is not None and kpis.shift_calendar.empty


def test_empty_assignments_still_expose_tracker() -> None:
    pb = _problem("tiny7")
    records = assignments_to_records(pb, pd.DataFrame())
    tracker = records.sequencing_tracker  # type: ignore[attr-defined]
    assert list(records) == []
    assert sum(tracker.remaining_work.values()) == pytest.approx(_total_required(pb))
    assert tracker.delivered_total == 0.0


@pytest.mark.parametrize("name", ["tiny7", "med42"])
def test_partial_plans_report_consistent_volumes(name: str) -> None:
    pb = _problem(name)
    total = _total_required(pb)
    full = _fixture_assignments(name)
    previous = -1.0
    for last_day in range(0, pb.scenario.num_days + 1, max(1, pb.scenario.num_days // 6)):
        plan = full[full["day"] <= last_day]
        result = run_playback(pb, plan)
        kpis = compute_kpis(pb, plan)
        delivered = float(kpis["total_production"])
        assert delivered == pytest.approx(result.delivered_total, abs=1e-6)
        assert delivered + float(kpis["remaining_work_total"]) == pytest.approx(total, abs=1e-6)
        assert delivered >= previous - 1e-9
        assert delivered <= total + 1e-9
        previous = delivered
        if plan.empty:
            assert delivered == 0.0
    full_kpis = compute_kpis(pb, full)
    assert float(full_kpis["total_production"]) >= previous - 1e-9


def test_upstream_only_plan_delivers_nothing() -> None:
    pb = Problem.from_scenario(chain_scenario(num_days=2))
    plan = pd.DataFrame(
        [
            {"machine_id": "F1", "block_id": "B1", "day": 1, "shift_id": "S1", "assigned": 1},
            {"machine_id": "F1", "block_id": "B1", "day": 2, "shift_id": "S1", "assigned": 1},
        ]
    )
    kpis = compute_kpis(pb, plan)
    assert kpis["total_production"] == 0.0
    assert kpis["remaining_work_total"] == pytest.approx(40.0)
    assert kpis["completed_blocks"] == 0.0
    # The feller outputs all 40 m³ on day 1 (role cap), so day 2 is unproductive.
    assert kpis["makespan_day"] == 1


def test_empty_plan_respects_initial_state_and_reduced_work() -> None:
    state = ScenarioInitialState(
        blocks=[BlockInitialState(block_id="B1", staged_inventory={"feller_buncher": 40.0})]
    )
    pb = Problem.from_scenario(chain_scenario(work_b1=25.0, work_b2=5.0, initial_state=state))

    kpis = compute_kpis(pb, pd.DataFrame(columns=ASSIGNMENT_COLUMNS))
    _assert_zero_delivery(kpis.to_dict(), pb)
    assert kpis["remaining_work_total"] == pytest.approx(30.0)

    # A skidder-only plan delivers from the carried-in staged inventory.
    skid = pd.DataFrame(
        [{"machine_id": "S1", "block_id": "B1", "day": 1, "shift_id": "S1", "assigned": 1}]
    )
    partial = compute_kpis(pb, skid)
    assert partial["total_production"] == pytest.approx(25.0)
    assert partial["remaining_work_total"] == pytest.approx(5.0)
    assert partial["completed_blocks"] == 1.0


def test_stochastic_playback_with_empty_plan() -> None:
    pb = _problem("med42")
    cfg = SamplingConfig(samples=3, base_seed=7)
    cfg.downtime.enabled = True
    cfg.downtime.probability = 0.9
    cfg.weather.enabled = True
    cfg.weather.day_probability = 0.9
    cfg.landing.enabled = True
    cfg.landing.probability = 0.9

    for plan in (pd.DataFrame(), pd.DataFrame(columns=ASSIGNMENT_COLUMNS)):
        ensemble = run_stochastic_playback(pb, plan, sampling_config=cfg)
        results = [ensemble.base_result] + [sample.result for sample in ensemble.samples]
        assert len(results) == 4
        for result in results:
            assert result.records == ()
            assert result.delivered_total == 0.0
            assert result.remaining_work_total == pytest.approx(_total_required(pb))
        shift_df = shift_dataframe_from_ensemble(ensemble)
        day_df = day_dataframe_from_ensemble(ensemble)
        assert shift_df.empty
        assert float(day_df["production_units"].sum()) == 0.0


def _tiny7_locks() -> list[ScheduleLock]:
    frame = _fixture_assignments("tiny7")
    return [
        ScheduleLock(
            machine_id=str(row.machine_id),
            block_id=str(row.block_id),
            day=int(row.day),
            shift_id=str(row.shift_id),
        )
        for row in frame.itertuples()
    ]


@pytest.mark.parametrize(
    "empty_result",
    [
        RollingPlanResult(locked_assignments=[], iteration_summaries=[], metadata={}),
        pd.DataFrame(),
        pd.DataFrame(columns=ASSIGNMENT_COLUMNS),
        [],
    ],
    ids=["rolling_result", "frame_no_columns", "frame_columns_only", "lock_list"],
)
def test_compute_rolling_kpis_rejects_empty_rolling_plan(empty_result: object) -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    with pytest.raises(ValueError, match="no locked assignments"):
        compute_rolling_kpis(scenario, empty_result)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "empty_baseline",
    [pd.DataFrame(), pd.DataFrame(columns=ASSIGNMENT_COLUMNS), []],
    ids=["frame_no_columns", "frame_columns_only", "lock_list"],
)
def test_empty_baseline_scores_as_zero_delivery(empty_baseline: object) -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    pb = Problem.from_scenario(scenario)
    total = _total_required(pb)

    comparison = compute_rolling_kpis(
        scenario,
        _tiny7_locks(),
        baseline_assignments=empty_baseline,  # type: ignore[arg-type]
    )
    assert comparison.baseline_kpis is not None
    assert comparison.baseline_assignments is not None and comparison.baseline_assignments.empty
    _assert_zero_delivery(comparison.baseline_kpis.to_dict(), pb)
    rolling_total = float(comparison.rolling_kpis["total_production"])
    assert rolling_total == pytest.approx(total)
    assert comparison.delta_totals is not None
    assert comparison.delta_totals["total_production_delta"] == pytest.approx(rolling_total)
    assert comparison.delta_totals["remaining_work_total_delta"] == pytest.approx(-total)
    assert "total_production_pct_delta" not in comparison.delta_totals


def test_evaluate_rolling_plan_with_empty_baseline() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    result = RollingPlanResult(
        locked_assignments=_tiny7_locks(), iteration_summaries=[], metadata={}
    )
    comparison = evaluate_rolling_plan(
        result,
        scenario,
        baseline_assignments=pd.DataFrame(columns=ASSIGNMENT_COLUMNS),
        baseline_label="failed_mip",
    )
    assert comparison.baseline_kpis is not None
    assert comparison.baseline_kpis["total_production"] == 0.0
    assert comparison.metadata["baseline_label"] == "failed_mip"
    assert comparison.metadata["baseline_assignment_count"] == 0

    frame = comparison_dataframe(comparison, metrics=["total_production"]).iloc[0]
    assert frame["baseline"] == 0.0
    assert frame["rolling"] == pytest.approx(_total_required(Problem.from_scenario(scenario)))
    assert pd.isna(frame["pct_delta"])


def test_omitted_baseline_still_skips_comparison() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    comparison = compute_rolling_kpis(scenario, _tiny7_locks(), baseline_assignments=None)
    assert comparison.baseline_kpis is None
    assert comparison.delta_totals is None


@pytest.mark.parametrize("name", ["tiny7", "med42", "large84"])
def test_full_plan_kpis_unchanged_from_pre108(name: str) -> None:
    """Non-empty plans keep the exact KPI values computed before the #108 fix (ac6d203)."""

    expected = PRE108_SNAPSHOT[name]
    pb = _problem(name)
    assignments = _fixture_assignments(name)
    result = run_playback(pb, assignments)
    assert result.delivered_total == expected["delivered_total"]
    assert result.remaining_work_total == expected["remaining_work_total"]
    assert compute_kpis(pb, assignments).to_dict() == expected["kpis"]
