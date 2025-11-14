from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd
import pytest

from fhops.telemetry.sqlite_store import persist_run

try:
    import altair  # noqa: F401
except ImportError:  # pragma: no cover - optional dependency
    ALTAIR_AVAILABLE = False
else:
    ALTAIR_AVAILABLE = True


def _write_report(
    path: Path,
    algorithm: str,
    scenario: str,
    best: float,
    mean: float,
    runs: int,
    *,
    best_run_id: str | None = None,
) -> None:
    df = pd.DataFrame(
        [
            {
                "algorithm": algorithm,
                "scenario": scenario,
                "best_objective": best,
                "mean_objective": mean,
                "runs": runs,
                **({"best_run_id": best_run_id} if best_run_id else {}),
            }
        ]
    )
    df.to_csv(path, index=False)


def test_analyze_tuner_reports_cli(tmp_path: Path):
    report_a = tmp_path / "baseline.csv"
    report_b = tmp_path / "experiment.csv"
    _write_report(report_a, "random", "FHOPS MiniToy", 7.5, 7.0, 2)
    _write_report(report_b, "random", "FHOPS MiniToy", 8.0, 7.6, 3)

    markdown_out = tmp_path / "comparison.md"
    csv_out = tmp_path / "comparison.csv"
    chart_out = tmp_path / "comparison.html"
    summary_csv = tmp_path / "summary.csv"
    summary_md = tmp_path / "summary.md"

    cmd = [
        "python",
        "scripts/analyze_tuner_reports.py",
        "--report",
        f"baseline={report_a}",
        "--report",
        f"experiment={report_b}",
        "--out-markdown",
        str(markdown_out),
        "--out-csv",
        str(csv_out),
        "--out-summary-csv",
        str(summary_csv),
        "--out-summary-markdown",
        str(summary_md),
    ]
    if ALTAIR_AVAILABLE:
        cmd.extend(["--out-chart", str(chart_out)])

    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.returncode == 0
    assert markdown_out.exists()
    assert csv_out.exists()
    assert summary_csv.exists()
    assert summary_md.exists()
    if ALTAIR_AVAILABLE:
        assert chart_out.exists()

    content = markdown_out.read_text(encoding="utf-8")
    assert "| Algorithm | Scenario |" in content
    assert "baseline" in content
    assert "experiment" in content
    combined = pd.read_csv(csv_out)
    assert combined.loc[0, "best_baseline"] == 7.5
    assert combined.loc[0, "best_experiment"] == 8.0
    assert combined.loc[0, "best_delta_experiment"] == 0.5
    summary_df = pd.read_csv(summary_csv)
    expected_columns = {
        "scenario",
        "best_algorithm_baseline",
        "best_value_baseline",
        "best_algorithm_experiment",
        "best_value_experiment",
        "best_delta_experiment",
    }
    assert expected_columns.issubset(set(summary_df.columns))
    assert summary_df.loc[0, "best_algorithm_baseline"] == "random"
    assert summary_df.loc[0, "best_value_baseline"] == pytest.approx(7.5)
    assert summary_df.loc[0, "best_algorithm_experiment"] == "random"
    assert summary_df.loc[0, "best_value_experiment"] == pytest.approx(8.0)
    assert summary_df.loc[0, "best_delta_experiment"] == pytest.approx(0.5)
    summary_md_text = summary_md.read_text(encoding="utf-8")
    assert "Best Algo (baseline)" in summary_md_text
    assert "Best Obj (experiment)" in summary_md_text


def test_analyze_tuner_reports_history(tmp_path: Path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    def _persist_history_snapshot(
        stem: str,
        *,
        best: float,
        mean: float,
        runs: int,
        run_id: str,
        total_prod: float,
        downtime_hours: float,
        downtime_events: int,
    ) -> None:
        csv_path = history_dir / f"{stem}.csv"
        sqlite_path = csv_path.with_suffix(".sqlite")
        _write_report(csv_path, "random", "MiniToy", best, mean, runs, best_run_id=run_id)
        record = {
            "run_id": run_id,
            "schema_version": "1.1",
            "solver": "sa",
            "scenario": "MiniToy",
            "scenario_path": "examples/minitoy/scenario.yaml",
            "seed": 42,
            "status": "ok",
            "started_at": f"{stem}T00:00:00+00:00",
            "finished_at": f"{stem}T00:00:30+00:00",
            "duration_seconds": 30.0,
            "config": {"iters": 50},
            "context": {"source": "cli.tune-random", "algorithm": "random"},
            "extra": {},
            "artifacts": [],
            "error": None,
        }
        metrics = {
            "objective": best,
            "total_production": total_prod,
            "mobilisation_cost": 0.0,
            "utilisation_ratio_mean_shift": 0.75,
            "utilisation_ratio_mean_day": 0.72,
            "downtime_hours_total": downtime_hours,
            "downtime_event_count": downtime_events,
            "weather_severity_total": 0.0,
        }
        persist_run(sqlite_path, record=record, metrics=metrics, kpis={})

    _persist_history_snapshot(
        "2024-11-01",
        best=7.0,
        mean=6.5,
        runs=2,
        run_id="run_20241101",
        total_prod=100.0,
        downtime_hours=2.0,
        downtime_events=1,
    )
    _persist_history_snapshot(
        "2024-11-02",
        best=7.5,
        mean=7.1,
        runs=2,
        run_id="run_20241102",
        total_prod=110.0,
        downtime_hours=1.5,
        downtime_events=3,
    )

    history_csv = tmp_path / "history.csv"
    history_md = tmp_path / "history.md"
    delta_csv = tmp_path / "history_delta.csv"
    delta_md = tmp_path / "history_delta.md"

    cmd = [
        "python",
        "scripts/analyze_tuner_reports.py",
        "--report",
        f"baseline={history_dir / '2024-11-02.csv'}",
        "--history-dir",
        str(history_dir),
        "--out-history-csv",
        str(history_csv),
        "--out-history-markdown",
        str(history_md),
        "--out-history-delta-csv",
        str(delta_csv),
        "--out-history-delta-markdown",
        str(delta_md),
    ]
    subprocess.run(cmd, text=True, capture_output=True, check=True)

    assert history_csv.exists()
    assert history_md.exists()
    assert delta_csv.exists()
    assert delta_md.exists()
    df = pd.read_csv(history_csv)
    expected_columns = {
        "algorithm",
        "scenario",
        "best_objective",
        "mean_objective",
        "runs",
        "snapshot",
        "best_total_production",
        "best_mobilisation_cost",
        "best_utilisation_ratio_shift",
        "best_utilisation_ratio_day",
        "best_downtime_hours",
        "best_downtime_events",
        "best_weather_severity",
    }
    assert expected_columns.issubset(set(df.columns))
    assert len(df) == 2
    assert "2024-11-02" in df["snapshot"].tolist()
    delta_df = pd.read_csv(delta_csv)
    assert "best_objective_delta" in delta_df.columns
    assert delta_df.loc[0, "best_objective_delta"] == 0.5
    assert "best_objective_delta_pct" in delta_df.columns
    assert delta_df.loc[0, "best_objective_delta_pct"] == pytest.approx(0.5 / 7.0)
    assert "best_downtime_hours_delta" in delta_df.columns
    assert delta_df.loc[0, "best_downtime_hours_delta"] == pytest.approx(-0.5)
    assert "best_downtime_hours_delta_pct" in delta_df.columns
    assert delta_df.loc[0, "best_downtime_hours_delta_pct"] == pytest.approx(-0.5 / 2.0)
    assert "best_downtime_events_delta" in delta_df.columns
    assert delta_df.loc[0, "best_downtime_events_delta"] == pytest.approx(2.0)

    delta_md_text = delta_md.read_text(encoding="utf-8")
    assert "Δ% Best Objective" in delta_md_text
