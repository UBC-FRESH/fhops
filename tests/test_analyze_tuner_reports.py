from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd


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

    result = subprocess.run(
        [
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
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.returncode == 0
    assert markdown_out.exists()
    assert csv_out.exists()

    content = markdown_out.read_text(encoding="utf-8")
    assert "| Algorithm | Scenario |" in content
    assert "baseline" in content
    assert "experiment" in content
    combined = pd.read_csv(csv_out)
    assert combined.loc[0, "best_baseline"] == 7.5
    assert combined.loc[0, "best_experiment"] == 8.0
    assert combined.loc[0, "best_delta_experiment"] == 0.5
