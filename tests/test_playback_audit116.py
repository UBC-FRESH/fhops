"""Playback, KPI, and stochastic-event fixes from the 1.0.1 pre-release audit (#116)."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from fhops.cli.main import app
from fhops.evaluation import SamplingConfig, compute_kpis, run_playback, run_stochastic_playback
from fhops.evaluation.playback import (
    DowntimeEvent,
    DowntimeEventConfig,
    LandingShockConfig,
    LandingShockEvent,
    SamplingContext,
    WeatherEvent,
    WeatherEventConfig,
    assignments_to_records,
)
from fhops.evaluation.playback.adapters import multi_shift_days, normalise_shift_ids
from fhops.evaluation.playback.core import shift_hours_resolver
from fhops.optimization.heuristics import solve_sa
from fhops.scenario.contract import Problem
from fhops.scenario.contract.models import ShiftCalendarEntry
from fhops.scenario.io import load_scenario
from fhops.scenario.synthetic import (
    SAMPLING_PRESETS,
    SyntheticDatasetConfig,
    generate_random_dataset,
)
from fhops.scheduling.timeline import ShiftDefinition, TimelineConfig

from .cli import CliRunner

TINY7 = "examples/tiny7/scenario.yaml"
TINY7_ASSIGNMENTS = "tests/fixtures/playback/tiny7_assignments.csv"
SHIFTS = ("S1", "S2", "S3")


def _tiny7() -> tuple[Problem, pd.DataFrame]:
    return Problem.from_scenario(load_scenario(TINY7)), pd.read_csv(TINY7_ASSIGNMENTS)


def _tiny7_shift_calendar() -> Problem:
    """tiny7 with a three-shift shift calendar and no timeline shift definitions."""

    scenario = load_scenario(TINY7)
    calendar = [
        ShiftCalendarEntry(machine_id=m.id, day=d, shift_id=s, available=1)
        for m in scenario.machines
        for d in range(1, scenario.num_days + 1)
        for s in SHIFTS
    ]
    return Problem.from_scenario(scenario.model_copy(update={"shift_calendar": calendar}))


def _tiny7_timeline(names=SHIFTS, hours: float = 8.0) -> Problem:
    scenario = load_scenario(TINY7)
    timeline = TimelineConfig(
        shifts=[ShiftDefinition(name=n, hours=hours, shifts_per_day=len(names)) for n in names]
    )
    return Problem.from_scenario(scenario.model_copy(update={"timeline": timeline}))


def _three_shift_assignments(assignments: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for shift in SHIFTS:
        frame = assignments.drop(columns=["production"]).copy()
        frame["shift_id"] = shift
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _context(problem: Problem, seed: int = 7) -> SamplingContext:
    return SamplingContext(
        problem=problem,
        sample_id=0,
        rng=np.random.default_rng(seed),
        config=SamplingConfig(samples=1),
    )


# --- missing shift_id on multi-shift scenarios ---------------------------------------------


def test_multi_shift_days_detects_timeline_and_shift_calendar() -> None:
    problem, _ = _tiny7()
    assert multi_shift_days(problem) == []
    assert multi_shift_days(_tiny7_timeline()) == list(range(1, 8))
    assert multi_shift_days(_tiny7_shift_calendar()) == list(range(1, 8))
    assert multi_shift_days(_tiny7_timeline(names=("D",))) == []


@pytest.mark.parametrize("factory", [_tiny7_timeline, _tiny7_shift_calendar])
def test_missing_shift_id_raises_on_multi_shift_scenarios(factory) -> None:
    problem = factory()
    _, assignments = _tiny7()
    without_column = assignments.drop(columns=["shift_id"], errors="ignore")
    with pytest.raises(ValueError, match="more than one shift per day"):
        run_playback(problem, without_column)
    with pytest.raises(ValueError, match="no shift_id column"):
        compute_kpis(problem, without_column)
    with pytest.raises(ValueError, match="shift_id"):
        run_stochastic_playback(problem, without_column, sampling_config=SamplingConfig(samples=1))

    partial = assignments.copy()
    partial["shift_id"] = "S1"
    partial.loc[partial.index[0], "shift_id"] = None
    with pytest.raises(ValueError, match="1 row\\(s\\) without shift_id"):
        list(assignments_to_records(problem, partial))


def test_missing_shift_id_on_inactive_rows_is_allowed() -> None:
    problem = _tiny7_timeline()
    _, assignments = _tiny7()
    frame = assignments.copy()
    frame["shift_id"] = "S1"
    frame["assigned"] = 1
    extra = frame.iloc[[0]].copy()
    extra["shift_id"] = None
    extra["assigned"] = 0
    combined = pd.concat([frame, extra], ignore_index=True)
    assert run_playback(problem, combined).delivered_total == pytest.approx(
        run_playback(problem, frame).delivered_total
    )
    # Empty frames never raise.
    assert run_playback(problem, pd.DataFrame()).delivered_total == 0.0


def test_single_shift_scenarios_keep_s1_default() -> None:
    problem, assignments = _tiny7()
    without = assignments.drop(columns=["shift_id"], errors="ignore")
    with_s1 = without.copy()
    with_s1["shift_id"] = "S1"
    assert normalise_shift_ids(problem, without)["shift_id"].eq("S1").all()
    assert compute_kpis(problem, without).to_dict() == compute_kpis(problem, with_s1).to_dict()


def test_heuristic_multi_shift_results_carry_shift_ids() -> None:
    problem = _tiny7_timeline()
    result = solve_sa(problem, iters=20, seed=3)
    assignments = result["assignments"]
    assert assignments["shift_id"].notna().all()
    assert set(assignments["shift_id"]) <= set(SHIFTS)
    compute_kpis(problem, assignments)  # does not raise


# --- duplicate DataFrame index ---------------------------------------------------------------


def _duplicate_index(frame: pd.DataFrame) -> pd.DataFrame:
    half = len(frame) // 2
    dup = pd.concat([frame.iloc[:half], frame.iloc[half:].reset_index(drop=True)])
    assert dup.index.duplicated().any()
    return dup


@pytest.mark.parametrize("event_name", ["downtime", "weather", "landing"])
def test_events_are_index_agnostic(event_name: str) -> None:
    problem, assignments = _tiny7()
    events = {
        "downtime": DowntimeEvent(DowntimeEventConfig(probability=0.5)),
        "weather": WeatherEvent(WeatherEventConfig(day_probability=0.5)),
        "landing": LandingShockEvent(LandingShockConfig(probability=0.5)),
    }
    event = events[event_name]
    base_production = {}
    unique = event.apply(_context(problem), assignments, base_production)
    dup_input = _duplicate_index(assignments)
    dup = event.apply(_context(problem), dup_input, base_production)
    assert dup.index.equals(dup_input.index)
    pd.testing.assert_frame_equal(
        unique.reset_index(drop=True), dup.reset_index(drop=True), check_like=False
    )


def test_stochastic_playback_identical_with_duplicate_index() -> None:
    problem, assignments = _tiny7()
    cfg = SamplingConfig(samples=3, base_seed=5)
    cfg.downtime.probability = 0.5
    cfg.weather.day_probability = 0.5
    cfg.landing.probability = 0.3
    unique = run_stochastic_playback(problem, assignments, sampling_config=cfg)
    dup = run_stochastic_playback(problem, _duplicate_index(assignments), sampling_config=cfg)
    assert [s.result.delivered_total for s in unique.samples] == [
        s.result.delivered_total for s in dup.samples
    ]


# --- shift-hours fallback ------------------------------------------------------------------


def test_shift_hours_resolver_splits_daily_hours_over_shifts() -> None:
    problem, _ = _tiny7()
    hours_for = shift_hours_resolver(problem.scenario)
    assert hours_for("H1", "S1", 1) == (24.0, "machine_daily_hours")

    calendar_problem = _tiny7_shift_calendar()
    hours_for = shift_hours_resolver(calendar_problem.scenario)
    assert hours_for("H1", "S2", 3) == (8.0, "machine_daily_hours")

    timeline_problem = _tiny7_timeline(hours=10.0)
    hours_for = shift_hours_resolver(timeline_problem.scenario)
    assert hours_for("H1", "S2", 3) == (10.0, "shift_definition")


def test_shift_calendar_without_timeline_records_eight_hour_shifts() -> None:
    problem = _tiny7_shift_calendar()
    _, assignments = _tiny7()
    frame = _three_shift_assignments(assignments)
    result = run_playback(problem, frame)
    assert {record.hours_worked for record in result.records} == {8.0}
    per_machine_day: dict[tuple[str, int], float] = {}
    for record in result.records:
        key = (record.machine_id, record.day)
        per_machine_day[key] = per_machine_day.get(key, 0.0) + float(record.hours_worked or 0)
    assert max(per_machine_day.values()) == pytest.approx(24.0)
    assert {summary.available_hours for summary in result.shift_summaries} == {8.0}
    # Matches the explicit 3 x 8 h timeline.
    timeline_kpis = compute_kpis(_tiny7_timeline(), frame).to_dict()
    calendar_kpis = compute_kpis(problem, frame).to_dict()
    for key in ("utilisation_ratio_weighted_day", "utilisation_ratio_mean_shift"):
        assert calendar_kpis[key] == pytest.approx(timeline_kpis[key])


def test_downtime_fraction_uses_split_shift_hours() -> None:
    problem = _tiny7_shift_calendar()
    _, assignments = _tiny7()
    frame = _three_shift_assignments(assignments)
    cfg = SamplingConfig(samples=1, base_seed=3)
    cfg.downtime.probability = 1.0
    cfg.downtime.mean_duration_hours = 4.0
    cfg.downtime.std_duration_hours = 0.0
    cfg.weather.enabled = False
    cfg.landing.enabled = False
    ensemble = run_stochastic_playback(problem, frame, sampling_config=cfg)
    records = ensemble.samples[0].result.records
    assert {record.hours_worked for record in records} == {4.0}
    assert {record.downtime_hours for record in records} == {4.0}


def test_single_shift_hours_unchanged() -> None:
    problem, assignments = _tiny7()
    result = run_playback(problem, assignments)
    assert {record.hours_worked for record in result.records} == {24.0}


# --- record-level loss KPIs ----------------------------------------------------------------


def _unsequenced_tiny7() -> Problem:
    scenario = load_scenario(TINY7)
    # No harvest systems and ample volume: every record delivers its proposed volume uncapped,
    # so the volume an event removes equals the drop in delivered volume.
    blocks = [
        block.model_copy(update={"harvest_system_id": None, "work_required": 1.0e6})
        for block in scenario.blocks
    ]
    return Problem.from_scenario(scenario.model_copy(update={"blocks": blocks}))


def _sample_frame(problem: Problem, assignments: pd.DataFrame, **events) -> pd.DataFrame:
    frame = assignments.copy()
    frame["assigned"] = 1
    frame["production"] = [
        record.production_units for record in run_playback(problem, frame).records
    ]
    for event in events.values():
        frame = event.apply(_context(problem, seed=11), frame, {})
    return frame


def test_downtime_loss_kpi_is_record_level() -> None:
    problem = _unsequenced_tiny7()
    _, assignments = _tiny7()
    # Unsequenced blocks: every record delivers, so the removed volume is the delivered drop.
    base = _sample_frame(problem, assignments)
    event = DowntimeEvent(
        DowntimeEventConfig(probability=0.6, mean_duration_hours=18.0, std_duration_hours=8.0)
    )
    sample = _sample_frame(problem, assignments, downtime=event)
    assert sample["_downtime"].sum() > 0
    assert (sample["assigned"] == 0).any()  # some full-shift losses
    kpis = compute_kpis(problem, sample)
    drop = (
        compute_kpis(problem, base)["total_production"]
        - compute_kpis(problem, sample)["total_production"]
    )
    assert kpis["downtime_production_loss_est"] == pytest.approx(drop, rel=1e-9)
    assert kpis["downtime_production_loss_est"] == pytest.approx(
        float(sample["_downtime_lost"].sum()), rel=1e-12
    )


def test_downtime_loss_fallback_without_lost_column() -> None:
    problem = _unsequenced_tiny7()
    _, assignments = _tiny7()
    event = DowntimeEvent(
        DowntimeEventConfig(probability=1.0, mean_duration_hours=6.0, std_duration_hours=0.0)
    )
    sample = _sample_frame(problem, assignments, downtime=event).drop(columns=["_downtime_lost"])
    rates = {(r.machine_id, r.block_id): r.rate for r in problem.scenario.production_rates}
    expected = sum(
        rates[(row.machine_id, row.block_id)] * 6.0 / 24.0 for row in sample.itertuples()
    )
    assert compute_kpis(problem, sample)["downtime_production_loss_est"] == pytest.approx(expected)


def test_weather_loss_kpis_are_record_level() -> None:
    problem = _unsequenced_tiny7()
    _, assignments = _tiny7()
    base = _sample_frame(problem, assignments)
    event = WeatherEvent(WeatherEventConfig(day_probability=0.6, severity_levels={"x": 0.25}))
    sample = _sample_frame(problem, assignments, weather=event)
    hit = sample["_weather_severity"] > 0
    assert hit.any()
    kpis = compute_kpis(problem, sample)
    drop = (
        compute_kpis(problem, base)["total_production"]
        - compute_kpis(problem, sample)["total_production"]
    )
    assert kpis["weather_production_loss_est"] == pytest.approx(drop, rel=1e-9)
    assert kpis["weather_hours_est"] == pytest.approx(0.25 * 24.0 * int(hit.sum()))


# --- landing-shock calibration ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("probability", "duration"),
    [(0.1, 1), (0.025, 2), (0.035, 3), (0.2, 4)],
)
def test_landing_shock_fraction_matches_formula(probability: float, duration: int) -> None:
    scenario = load_scenario(TINY7).model_copy(update={"num_days": 4000})
    problem = Problem.from_scenario(scenario)
    event = LandingShockEvent(LandingShockConfig(probability=probability, duration_days=duration))
    multipliers = event.sample_multipliers(_context(problem, seed=2024))
    landing_days = len(scenario.landings) * scenario.num_days
    shocked = sum(1 for (_landing, day) in multipliers if day <= scenario.num_days)
    expected = 1 - (1 - probability) ** duration
    assert shocked / landing_days == pytest.approx(expected, abs=0.012)


def test_synthetic_landing_presets_are_calibrated() -> None:
    fractions = {}
    for tier, preset in SAMPLING_PRESETS.items():
        landing = preset["landing"]
        assert isinstance(landing, dict)
        if not landing.get("enabled"):
            continue
        fractions[tier] = 1 - (1 - float(landing["probability"])) ** int(landing["duration_days"])
    assert fractions["medium"] == pytest.approx(0.049375)
    assert fractions["large"] == pytest.approx(1 - 0.965**3)
    assert all(fraction <= 0.15 for fraction in fractions.values())


# --- deprecated fields ---------------------------------------------------------------------


def test_seed_offset_deprecated_and_ignored() -> None:
    with pytest.warns(DeprecationWarning, match="seed_offset"):
        DowntimeEventConfig(seed_offset=3)
    with pytest.warns(DeprecationWarning, match="seed_offset"):
        SamplingConfig.model_validate({"landing": {"seed_offset": 1}})
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        DowntimeEventConfig(seed_offset=0)
        SamplingConfig.model_validate(SamplingConfig().model_dump())

    problem, assignments = _tiny7()
    base_cfg = SamplingConfig(samples=2, base_seed=9)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        offset_cfg = SamplingConfig.model_validate(
            {
                "samples": 2,
                "base_seed": 9,
                "downtime": {"seed_offset": 5},
                "weather": {"seed_offset": 6},
                "landing": {"seed_offset": 7},
            }
        )
    base = run_stochastic_playback(problem, assignments, sampling_config=base_cfg)
    offset = run_stochastic_playback(problem, assignments, sampling_config=offset_cfg)
    assert [s.result.delivered_total for s in base.samples] == [
        s.result.delivered_total for s in offset.samples
    ]


def test_generated_metadata_omits_deprecated_sampling_fields(tmp_path: Path) -> None:
    config = SyntheticDatasetConfig(
        name="meta", tier="medium", num_blocks=4, num_days=5, num_machines=3
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        bundle = generate_random_dataset(config, seed=5)
    bundle.write(tmp_path / "meta")
    metadata = yaml.safe_load((tmp_path / "meta" / "metadata.yaml").read_text(encoding="utf-8"))
    sampling = metadata["sampling_config"]
    assert "correlated_days" not in sampling["weather"]
    for event in ("downtime", "weather", "landing"):
        assert "seed_offset" not in sampling[event]
    assert sampling["landing"]["probability"] == pytest.approx(0.025)


@pytest.mark.parametrize(
    "path",
    [
        "examples/synthetic/metadata.yaml",
        "examples/synthetic/small/metadata.yaml",
        "examples/synthetic/medium/metadata.yaml",
        "examples/synthetic/large/metadata.yaml",
    ],
)
def test_shipped_synthetic_metadata_loads_without_warnings(path: str) -> None:
    metadata = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    configs = []
    if "sampling_config" in metadata:
        configs.append(metadata["sampling_config"])
    for entry in metadata.values():
        if isinstance(entry, dict) and "sampling_config" in entry:
            configs.append(entry["sampling_config"])
    assert configs
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        for payload in configs:
            SamplingConfig.model_validate(payload)


# --- eval-playback CLI ------------------------------------------------------------------------


def test_eval_playback_help_keeps_bracketed_text() -> None:
    result = CliRunner().invoke(app, ["eval-playback", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "landing_multiplier_low" in result.stdout
    assert "landing_multiplier_high" in result.stdout
    assert "between 0 and the shift length" in result.stdout


def test_eval_playback_rejects_missing_shift_id_on_multi_shift(tmp_path: Path) -> None:
    scenario = load_scenario(TINY7)
    timeline = TimelineConfig(
        shifts=[ShiftDefinition(name=n, hours=8.0, shifts_per_day=3) for n in SHIFTS]
    )
    scenario_dir = Path(TINY7).parent
    payload = yaml.safe_load(Path(TINY7).read_text(encoding="utf-8"))
    payload["timeline"] = timeline.model_dump()
    for key, value in list(payload["data"].items()):
        payload["data"][key] = str((scenario_dir / value).resolve())
    for key in ("mobilisation",):
        if key in payload and "distance_csv" in payload[key]:
            payload[key]["distance_csv"] = str(
                (scenario_dir / payload[key]["distance_csv"]).resolve()
            )
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    assert load_scenario(scenario_path).timeline is not None
    assert scenario.num_days == 7
    assignments = pd.read_csv(TINY7_ASSIGNMENTS).drop(columns=["shift_id"], errors="ignore")
    csv_path = tmp_path / "assignments.csv"
    assignments.to_csv(csv_path, index=False)
    result = CliRunner().invoke(
        app, ["eval-playback", str(scenario_path), "--assignments", str(csv_path)]
    )
    assert result.exit_code == 1
    assert "shift_id" in result.stdout
