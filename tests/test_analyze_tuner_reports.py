from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd

try:
    import altair  # noqa: F401
except ImportError:  # pragma: no cover - optional dependency
    ALTAIR_AVAILABLE = False
else:
    ALTAIR_AVAILABLE = True


def _write_report(path: Path, algorithm: str, scenario: str, best: float, mean: float, runs: int) -> None:
    df = pd.DataFrame(
        [
            {
                "algorithm": algorithm,
                "scenario": scenario,
                "best_objective": best,
                "mean_objective": mean,
                "runs": runs,
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


def test_analyze_tuner_reports_history(tmp_path: Path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    _write_report(history_dir / "2024-11-01.csv", "random", "MiniToy", 7.0, 6.5, 2)
    _write_report(history_dir / "2024-11-02.csv", "random", "MiniToy", 7.5, 7.1, 2)

    history_csv = tmp_path / "history.csv"
    history_md = tmp_path / "history.md"

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
    ]
    subprocess.run(cmd, text=True, capture_output=True, check=True)

    assert history_csv.exists()
    assert history_md.exists()
    df = pd.read_csv(history_csv)
    assert set(df.columns) == {"algorithm", "scenario", "best_objective", "mean_objective", "runs", "snapshot"}
    assert len(df) == 2
    assert "2024-11-02" in df["snapshot"].tolist()
