from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from fhops.cli.main import app


runner = CliRunner()


def test_synth_preview(tmp_path: Path):
    out_dir = tmp_path / "preview_bundle"
    result = runner.invoke(
        app,
        [
            "synth",
            "generate",
            str(out_dir),
            "--tier",
            "small",
            "--seed",
            "555",
            "--preview",
        ],
    )

    assert result.exit_code == 0
    assert not out_dir.exists()
    assert "Seed: 555" in result.stdout


def test_synth_generate_bundle(tmp_path: Path):
    out_dir = tmp_path / "bundle"
    result = runner.invoke(
        app,
        [
            "synth",
            "generate",
            str(out_dir),
            "--tier",
            "medium",
            "--seed",
            "777",
            "--blocks",
            "10:12",
            "--overwrite",
        ],
    )

    assert result.exit_code == 0
    scenario_path = out_dir / "scenario.yaml"
    metadata_path = out_dir / "metadata.yaml"
    assert scenario_path.exists()
    assert metadata_path.exists()

    scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    data_section = scenario["data"]
    assert "crew_assignments" in data_section

    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    assert metadata["seed"] == 777
    assert metadata["counts"]["blocks"] >= 10
