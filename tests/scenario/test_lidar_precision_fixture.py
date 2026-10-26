"""P14.5 synthetic precision-forestry fixture tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.io import load_scenario
from fhops.scenario.lidar import load_femic_lidar_bundle
from fhops.scenario.lidar_operability import assess_scenario_operability

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "examples/lidar_precision_forestry"


def test_fixture_pin_support_and_bundle() -> None:
    scenario = load_scenario(FIXTURE / "scenario.yaml")
    assert scenario.lidar_products is not None
    pin = scenario.lidar_products[0]
    assert pin.bundle_id == "lidarbc-p14-precision-fixture"
    assert pin.aoi_bbox is not None
    assert pin.products is not None
    assert scenario.lidar_support is not None
    assert len(scenario.lidar_support) == 10
    bundle = load_femic_lidar_bundle(FIXTURE / "femic_bundle")
    assert bundle.bundle_version == "2026.10.0-synthetic"
    assert set(bundle.products) == {"slope", "chm"}


def test_fixture_aoi_provenance() -> None:
    payload = json.loads((FIXTURE / "aoi_provenance.json").read_text(encoding="utf-8"))
    assert payload["source_repository"] == "https://github.com/UBC-FRESH/femic-gnn-instance"
    assert "Proposed Statement of Intent" in payload["caveat"]
    assert "synthetic" in payload["caveat"].lower()
    assert (FIXTURE / "aoi_demo.geojson").is_file()


def test_fixture_operability_is_explicit() -> None:
    scenario = load_scenario(FIXTURE / "scenario.yaml")
    rows = {row.block_id: row for row in assess_scenario_operability(scenario)}
    assert rows["B01"].terrain_class == "cable"
    assert rows["B01"].current_system_compatible is False
    assert rows["B02"].terrain_class == "ground"
    assert rows["B02"].current_system_compatible is True


def test_fixture_validates_and_solves(tmp_path: Path) -> None:
    runner = CliRunner()
    validate = runner.invoke(app, ["validate", str(FIXTURE / "scenario.yaml")], prog_name="fhops")
    assert validate.exit_code == 0, validate.output
    out = tmp_path / "assignments.csv"
    solve = runner.invoke(
        app,
        [
            "solve-heur",
            str(FIXTURE / "scenario.yaml"),
            "--iters",
            "5",
            "--seed",
            "7",
            "--out",
            str(out),
        ],
        prog_name="fhops",
    )
    assert solve.exit_code == 0, solve.output
    assert out.is_file()
    assert out.stat().st_size > 0
