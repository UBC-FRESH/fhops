"""CLI coverage for tactical scenario overlays, diffs, batches, and reports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from fhops.cli.main import app

TOPM_MINI = Path("tests/fixtures/tactical_operational/topm-mini/specification.yaml").resolve()


def _overlay(path: Path) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "overlay_id": "lower-demand",
                "facility_demand": [
                    {
                        "facility_id": "mill_saw",
                        "product_id": "sawlog",
                        "period_id": "Y1-P1",
                        "target_m3": 700.0,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_tactical_scenario_overlay_diff_batch_and_report_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    overlay = _overlay(tmp_path / "overlay.yaml")
    merged = tmp_path / "merged.yaml"

    result = runner.invoke(
        app,
        ["scenario", "overlay", str(TOPM_MINI), str(overlay), "--out", str(merged)],
        prog_name="fhops",
    )
    assert result.exit_code == 0
    assert merged.exists()

    diff_path = tmp_path / "diff.csv"
    result = runner.invoke(
        app,
        ["scenario", "diff", str(TOPM_MINI), str(merged), "--out", str(diff_path)],
        prog_name="fhops",
    )
    assert result.exit_code == 0
    assert not pd.read_csv(diff_path).empty

    manifest = tmp_path / "batch.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "cases": [
                    {"case_id": "base", "scenario": str(TOPM_MINI)},
                    {
                        "case_id": "overlay",
                        "scenario": str(TOPM_MINI),
                        "overlay": str(overlay),
                    },
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    batch_dir = tmp_path / "batch"
    result = runner.invoke(
        app,
        ["scenario", "batch", str(manifest), "--out-dir", str(batch_dir)],
        prog_name="fhops",
    )
    assert result.exit_code == 0
    comparison = pd.read_csv(batch_dir / "comparison.csv")
    assert set(comparison["case_id"]) == {"base", "overlay"}

    result_json = batch_dir / "base" / "result.json"
    assert result_json.exists()
    report_dir = tmp_path / "report"
    result = runner.invoke(
        app,
        ["report", "tactical", str(result_json), "--out-dir", str(report_dir)],
        prog_name="fhops",
    )
    assert result.exit_code == 0
    assert (report_dir / "summary.md").exists()
