from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path

import pandas as pd
import pandas.testing as pdt


def _run_benchmarks(out_dir: Path, *, max_workers: int | None = None) -> None:
    cmd = [
        "python",
        "scripts/run_tuning_benchmarks.py",
        "--plan",
        "baseline-smoke",
        "--tuner",
        "random",
        "--tuner",
        "grid",
        "--tuner",
        "bayes",
        "--tuner",
        "ils",
        "--tuner",
        "tabu",
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
        "--ils-runs",
        "1",
        "--ils-iters",
        "10",
        "--tabu-runs",
        "1",
        "--tabu-iters",
        "10",
    ]
    if max_workers is not None:
        cmd.extend(["--max-workers", str(max_workers)])
    subprocess.run(cmd, check=True, text=True)


def _normalise(df: pd.DataFrame, *, drop_bundle: bool = True) -> pd.DataFrame:
    result = df.copy()
    if "scenario" in result.columns:
        result["scenario"] = result["scenario"].apply(
            lambda value: value.split(":", 1)[1]
            if isinstance(value, str) and ":" in value
            else value
        )
    if drop_bundle and "bundle" in result.columns:
        result = result.drop(columns=["bundle"])
    result = result.sort_values(list(result.columns)).reset_index(drop=True)
    return result.drop_duplicates().reset_index(drop=True)


def test_run_tuning_benchmarks_minimal(tmp_path: Path):
    out_dir = tmp_path / "results"
    _run_benchmarks(out_dir)

    telemetry_log = out_dir / "telemetry" / "runs.jsonl"
    report_csv = out_dir / "tuner_report.csv"
    summary_csv = out_dir / "tuner_summary.csv"
    summary_md = out_dir / "tuner_summary.md"
    comparison_csv = out_dir / "tuner_comparison.csv"
    comparison_md = out_dir / "tuner_comparison.md"
    leaderboard_csv = out_dir / "tuner_leaderboard.csv"
    leaderboard_md = out_dir / "tuner_leaderboard.md"
    difficulty_csv = out_dir / "tuner_difficulty.csv"
    difficulty_md = out_dir / "tuner_difficulty.md"
    baseline_comp_csv = out_dir / "tuner_comparison_baseline.csv"
    baseline_leader_csv = out_dir / "tuner_leaderboard_baseline.csv"
    baseline_diff_csv = out_dir / "tuner_difficulty_baseline.csv"

    assert telemetry_log.exists()
    assert report_csv.exists()
    assert summary_csv.exists()
    assert summary_md.exists()
    assert comparison_csv.exists()
    assert comparison_md.exists()
    assert leaderboard_csv.exists()
    assert leaderboard_md.exists()
    assert difficulty_csv.exists()
    assert difficulty_md.exists()
    assert baseline_comp_csv.exists()
    assert baseline_leader_csv.exists()
    assert baseline_diff_csv.exists()

    summary_text = summary_md.read_text(encoding="utf-8")
    assert "Minitoy" in summary_text or "MiniToy" in summary_text

    comparison_text = comparison_md.read_text(encoding="utf-8")
    assert "scenario" in comparison_text.lower()
    leaderboard_text = leaderboard_md.read_text(encoding="utf-8")
    assert "algorithm" in leaderboard_text.lower()
    difficulty_text = difficulty_md.read_text(encoding="utf-8")
    assert "mip_gap" in difficulty_text.lower()

    meta_summary_csv = out_dir / "tuner_meta_summary.csv"
    meta_summary_md = out_dir / "tuner_meta_summary.md"
    subprocess.run(
        [
            "python",
            "scripts/summarize_tuner_meta.py",
            str(telemetry_log.with_suffix(".sqlite")),
            "--out-csv",
            str(meta_summary_csv),
            "--out-markdown",
            str(meta_summary_md),
        ],
        check=True,
        text=True,
    )
    assert meta_summary_csv.exists()
    assert meta_summary_md.exists()
    meta_text = meta_summary_md.read_text(encoding="utf-8")
    assert "algorithm" in meta_text.lower()

    convergence_runs_csv = out_dir / "convergence_runs.csv"
    convergence_summary_csv = out_dir / "convergence_summary.csv"
    convergence_summary_md = out_dir / "convergence_summary.md"
    subprocess.run(
        [
            "python",
            "scripts/analyze_tuner_reports.py",
            "--report",
            str(out_dir / "tuner_report.csv"),
            "--telemetry-log",
            str(telemetry_log),
            "--out-convergence-csv",
            str(convergence_runs_csv),
            "--out-convergence-summary-csv",
            str(convergence_summary_csv),
            "--out-convergence-summary-markdown",
            str(convergence_summary_md),
        ],
        check=True,
        text=True,
    )
    assert convergence_runs_csv.exists()
    assert convergence_summary_csv.exists()
    assert convergence_summary_md.exists()


def test_run_tuning_benchmarks_parallel_matches_serial(tmp_path: Path):
    serial_dir = tmp_path / "serial"
    parallel_dir = tmp_path / "parallel"

    _run_benchmarks(serial_dir)
    _run_benchmarks(parallel_dir, max_workers=2)

    serial_summary = pd.read_csv(serial_dir / "tuner_summary.csv")
    parallel_summary = pd.read_csv(parallel_dir / "tuner_summary.csv")

    serial_summary_sorted = _normalise(serial_summary, drop_bundle=False)
    parallel_summary_sorted = _normalise(parallel_summary, drop_bundle=False)
    pdt.assert_frame_equal(
        serial_summary_sorted, parallel_summary_sorted, check_dtype=False, atol=1e-9
    )

    def signature(df: pd.DataFrame) -> Counter[tuple[str, float, float, float]]:
        keys = []
        for row in df.itertuples(index=False):
            keys.append(
                (
                    getattr(row, "algorithm"),
                    round(float(getattr(row, "best_objective")), 6),
                    round(float(getattr(row, "mean_objective")), 6),
                    round(float(getattr(row, "delta_vs_best")), 6),
                )
            )
        return Counter(keys)

    serial_comparison_signature = signature(pd.read_csv(serial_dir / "tuner_comparison.csv"))
    parallel_comparison_signature = signature(pd.read_csv(parallel_dir / "tuner_comparison.csv"))
    assert serial_comparison_signature == parallel_comparison_signature

    serial_log = serial_dir / "telemetry" / "runs.jsonl"
    parallel_log = parallel_dir / "telemetry" / "runs.jsonl"
    assert serial_log.exists()
    assert parallel_log.exists()

    with serial_log.open("r", encoding="utf-8") as src:
        serial_lines = sum(1 for _ in src)
    with parallel_log.open("r", encoding="utf-8") as src:
        parallel_lines = sum(1 for _ in src)
    assert serial_lines == parallel_lines
