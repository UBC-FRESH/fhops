from __future__ import annotations

from pathlib import Path

import yaml

from fhops.cli.main import app
from fhops.cli.synthetic import (
    _refresh_aggregate_metadata,
)

from .cli import CliRunner

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


def test_refresh_aggregate_metadata(tmp_path: Path):
    base = tmp_path / "synthetic"
    small_dir = base / "small"
    medium_dir = base / "medium"
    small_dir.mkdir(parents=True)
    medium_dir.mkdir(parents=True)

    (small_dir / "metadata.yaml").write_text(
        "name: synthetic-small\nterrain_counts:\n  gentle: 3\n", encoding="utf-8"
    )
    (small_dir / "scenario.yaml").write_text("num_days: 6\n", encoding="utf-8")

    (medium_dir / "metadata.yaml").write_text(
        "name: synthetic-medium\nterrain_counts:\n  mixed: 5\n", encoding="utf-8"
    )
    (medium_dir / "scenario.yaml").write_text("num_days: 12\n", encoding="utf-8")

    _refresh_aggregate_metadata(base)

    aggregate_path = base / "metadata.yaml"
    assert aggregate_path.exists()
    aggregate = yaml.safe_load(aggregate_path.read_text(encoding="utf-8"))
    assert aggregate["small"]["num_days"] == 6
    assert aggregate["medium"]["terrain_counts"]["mixed"] == 5


def test_synth_batch_generates_multiple(tmp_path: Path):
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        """
        - tier: small
          output_dir: "{tmp}/bundle_small"
          seed: 501
        - tier: custom
          output_dir: "{tmp}/bundle_custom"
          config: "{tmp}/config.yaml"
          overrides:
            name: synthetic-custom
            num_blocks: [5, 5]
          flags:
            blocks: "5:5"
          seed: 777
        """.replace("{tmp}", str(tmp_path)),
        encoding="utf-8",
    )

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
        num_days: 6
        num_machines: 2
        num_landings: 1
        """,
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "synth",
            "batch",
            str(plan),
            "--overwrite",
        ],
    )
    assert result.exit_code == 0
    assert (tmp_path / "bundle_small" / "scenario.yaml").exists()
    assert (tmp_path / "bundle_custom" / "scenario.yaml").exists()
    small_meta = yaml.safe_load(
        (tmp_path / "bundle_small" / "metadata.yaml").read_text(encoding="utf-8")
    )
    assert small_meta["seed"] == 501
