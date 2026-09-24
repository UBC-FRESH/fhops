"""Tests for tactical scenario overlays, diffs, batch manifests, and reports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from fhops.model.milp.tactical_operational import (
    build_tactical_operational_bundle,
    solve_tactical_operational_milp,
)
from fhops.planning.tactical_operational.io import load_tactical_operational_scenario
from fhops.planning.tactical_operational.scenario import (
    diff_tactical_scenarios,
    load_tactical_overlay_scenario,
    solve_tactical_batch_manifest,
    write_tactical_report,
    write_tactical_scenario_yaml,
)

TOPM_MINI = (
    Path(__file__).parents[1]
    / "fixtures"
    / "tactical_operational"
    / "topm-mini"
    / "specification.yaml"
)


def _write_overlay(path: Path) -> Path:
    payload = {
        "overlay_id": "lower-sawlog-demand",
        "description": "Reduce Y1-P1 sawlog target from 780 to 700 m3.",
        "facility_demand": [
            {
                "facility_id": "mill_saw",
                "product_id": "sawlog",
                "period_id": "Y1-P1",
                "target_m3": 700.0,
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_overlay_write_and_diff(tmp_path: Path) -> None:
    overlay = _write_overlay(tmp_path / "lower-demand.yaml")
    scenario = load_tactical_overlay_scenario(TOPM_MINI, overlay)

    assert scenario.parent == "topm-mini"
    assert scenario.overlay_id == "lower-sawlog-demand"
    assert scenario.source_hash
    demand = next(
        row
        for row in scenario.facility_demand
        if (row.facility_id, row.product_id, row.period_id) == ("mill_saw", "sawlog", "Y1-P1")
    )
    assert demand.target_m3 == pytest.approx(700.0)
    assert demand.minimum_m3 == pytest.approx(700.0)  # inherited through row merge

    merged_path = tmp_path / "merged.yaml"
    write_tactical_scenario_yaml(scenario, merged_path)
    replayed = load_tactical_operational_scenario(merged_path)
    assert replayed.dimension_summary() == scenario.dimension_summary()

    diff = diff_tactical_scenarios(
        load_tactical_operational_scenario(TOPM_MINI),
        scenario,
    )
    assert not diff.empty
    assert any("target_m3" in value for value in diff["field"].astype(str))


def test_batch_manifest_and_report(tmp_path: Path) -> None:
    overlay = _write_overlay(tmp_path / "lower-demand.yaml")
    manifest = tmp_path / "batch.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "cases": [
                    {"case_id": "base", "scenario": str(TOPM_MINI)},
                    {
                        "case_id": "lower-demand",
                        "scenario": str(TOPM_MINI),
                        "overlay": str(overlay),
                    },
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "batch"
    summary = solve_tactical_batch_manifest(manifest, out_dir=out_dir)

    assert set(summary["case_id"]) == {"base", "lower-demand"}
    assert (out_dir / "comparison.csv").exists()
    assert (out_dir / "comparison.md").exists()
    assert (out_dir / "base" / "summary.md").exists()
    assert (out_dir / "lower-demand" / "summary.md").exists()


def test_write_tactical_report_formats(tmp_path: Path) -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    result = solve_tactical_operational_milp(
        build_tactical_operational_bundle(scenario), solver="highs", time_limit=30
    )
    out_dir = tmp_path / "report"
    written = write_tactical_report(result, out_dir, formats="csv,markdown,parquet")

    assert (out_dir / "summary.md").exists()
    assert (out_dir / "harvest_decisions.csv").exists()
    assert (out_dir / "harvest_decisions.parquet").exists()
    assert "summary_md" in written

    # JSON round-trip from CLI output remains reportable.
    payload = json.loads(json.dumps(result, default=lambda value: value.to_dict("records")))
    rewritten = write_tactical_report(payload, tmp_path / "report-json")
    assert "summary_md" in rewritten
