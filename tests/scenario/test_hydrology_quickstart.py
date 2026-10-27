"""Cross-repo hydrology quickstart generator tests (P18.2)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app  # type: ignore[import-untyped]
from scripts.build_hydrology_quickstart import build_quickstart

runner = CliRunner()


def test_build_quickstart_workspace(tmp_path: Path) -> None:
    out = tmp_path / "quickstart"
    manifest = build_quickstart(out)
    expected = manifest["expected"]
    assert isinstance(expected, dict)

    assert expected["ws4_screen_rows"] == 2
    assert expected["fhops_screen_rows"] == 2
    assert expected["fhops_constraint_events"] == 3
    assert (out / "bundle" / "manifest.json").is_file()
    assert (out / "ws4" / "dataset" / "fragments.parquet").is_file()
    assert (out / "ws4" / "crosswalk.csv").is_file()
    assert (out / "ws4" / "exposure.json").is_file()
    assert (out / "fhops" / "scenario" / "scenario.yaml").is_file()
    assert (out / "fhops" / "crosswalk.csv").is_file()
    assert (out / "fhops" / "hazard.json").is_file()
    assert (out / "fhops" / "assets.json").is_file()
    quickstart = json.loads((out / "quickstart.json").read_text(encoding="utf-8"))
    assert quickstart["fhops_version"]


def test_generated_fhops_path_runs(tmp_path: Path) -> None:
    out = tmp_path / "quickstart"
    build_quickstart(out)
    scenario = out / "fhops" / "scenario" / "scenario.yaml"
    bundle = out / "bundle"
    crosswalk = out / "fhops" / "crosswalk.csv"
    metadata = out / "fhops" / "crosswalk.meta.json"
    screen_schedule = out / "fhops" / "screen_schedule.csv"
    hazard_schedule = out / "fhops" / "hazard_schedule.csv"
    exposure = out / "fhops" / "exposure.json"
    hazard = out / "fhops" / "hazard.json"
    assets = out / "fhops" / "assets.json"
    mapping = out / "fhops" / "mapping"
    screen = out / "fhops" / "screen"

    registered = runner.invoke(
        app,
        ["scenario", "hydrology", "register", str(scenario), str(bundle)],
        prog_name="fhops",
    )
    assert registered.exit_code == 0, registered.output

    mapped = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "map",
            str(scenario),
            str(bundle),
            str(crosswalk),
            "--metadata",
            str(metadata),
            "--out",
            str(mapping),
        ],
        prog_name="fhops",
    )
    assert mapped.exit_code == 0, mapped.output

    screened = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "screen",
            str(scenario),
            str(bundle),
            str(mapping),
            str(screen_schedule),
            str(exposure),
            "--out",
            str(screen),
        ],
        prog_name="fhops",
    )
    assert screened.exit_code == 0, screened.output
    screen_payload = json.loads(screened.output)
    assert screen_payload["row_count"] == 2

    checked = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "constraint-check",
            str(scenario),
            str(mapping),
            str(hazard_schedule),
            str(hazard),
            "--assets",
            str(assets),
            "--no-fail-on-closure",
        ],
        prog_name="fhops",
    )
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["coverage"]["closure_events"] == 1
