from __future__ import annotations

import subprocess
from pathlib import Path


def test_run_tuning_benchmarks_minimal(tmp_path: Path):
    out_dir = tmp_path / "results"
    cmd = [
        "python",
        "scripts/run_tuning_benchmarks.py",
        "--bundle",
        "minitoy",
        "--out-dir",
        str(out_dir),
        "--random-runs",
        "1",
        "--random-iters",
        "10",
        "--grid-iters",
        "10",
        "--grid-batch-size",
        "1",
        "--grid-preset",
        "balanced",
        "--bayes-trials",
        "1",
        "--bayes-iters",
        "10",
    ]
    subprocess.run(cmd, check=True, text=True)

    telemetry_log = out_dir / "telemetry" / "runs.jsonl"
    report_csv = out_dir / "tuner_report.csv"
    summary_csv = out_dir / "tuner_summary.csv"
    summary_md = out_dir / "tuner_summary.md"
    comparison_csv = out_dir / "tuner_comparison.csv"
    comparison_md = out_dir / "tuner_comparison.md"
    leaderboard_csv = out_dir / "tuner_leaderboard.csv"
    leaderboard_md = out_dir / "tuner_leaderboard.md"

    assert telemetry_log.exists()
    assert report_csv.exists()
    assert summary_csv.exists()
    assert summary_md.exists()
    assert comparison_csv.exists()
    assert comparison_md.exists()
    assert leaderboard_csv.exists()
    assert leaderboard_md.exists()

    # Ensure summary mentions the minitoy scenario
    summary_text = summary_md.read_text(encoding="utf-8")
    assert "Minitoy" in summary_text or "MiniToy" in summary_text

    comparison_text = comparison_md.read_text(encoding="utf-8")
    assert "scenario" in comparison_text.lower()
    leaderboard_text = leaderboard_md.read_text(encoding="utf-8")
    assert "algorithm" in leaderboard_text.lower()
