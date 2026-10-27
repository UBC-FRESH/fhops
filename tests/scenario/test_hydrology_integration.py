"""End-to-end hydrology consumer integration tests (P15.6)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from test_hydrology_mapping import (
    SCENARIO,
    _rows,
    _scenario,
    _write_crosswalk,
    _write_metadata,
)
from test_hydrology_screen import _exposure, _schedule
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.hydrology_registration import register_femic_hydrology_bundle

runner = CliRunner()
BUNDLE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "response"


def test_end_to_end_cli_path(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    mapping = tmp_path / "mapping"
    screen = tmp_path / "screen"
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule)
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", _rows(scenario))
    metadata = _write_metadata(
        tmp_path / "crosswalk.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
    )

    validated = runner.invoke(
        app,
        ["scenario", "hydrology", "validate", str(BUNDLE)],
        prog_name="fhops",
    )
    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.output)["is_valid"] is True

    registered = runner.invoke(
        app,
        ["scenario", "hydrology", "register", str(scenario), str(BUNDLE)],
        prog_name="fhops",
    )
    assert registered.exit_code == 0, registered.output
    assert json.loads(registered.output)["readiness_status"] == "ready"

    mapped = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "map",
            str(scenario),
            str(BUNDLE),
            str(crosswalk),
            "--metadata",
            str(metadata),
            "--out",
            str(mapping),
        ],
        prog_name="fhops",
    )
    assert mapped.exit_code == 0, mapped.output
    assert (mapping / "hydrology_mapping.json").is_file()

    checked = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "exposure",
            str(exposure),
            "--schedule",
            str(schedule),
        ],
        prog_name="fhops",
    )
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["is_valid"] is True

    screened = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "screen",
            str(scenario),
            str(BUNDLE),
            str(mapping),
            str(schedule),
            str(exposure),
            "--out",
            str(screen),
        ],
        prog_name="fhops",
    )
    assert screened.exit_code == 0, screened.output
    payload = json.loads(screened.output)
    assert payload["row_count"] == 2
    assert payload["refusal_count"] == 0
    assert (screen / "hydrology_screen.csv").is_file()
    assert (screen / "hydrology_screen.json").is_file()


def _map_cli(
    scenario: Path,
    crosswalk: Path,
    metadata: Path,
    out: Path,
    *extra: str,
    bundle: Path = BUNDLE,
) -> Path:
    result = runner.invoke(
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
            str(out),
            *extra,
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    return out


def _blocked_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "blocked-bundle"
    shutil.copytree(BUNDLE, bundle)
    card_path = bundle / "artifacts" / "model_card" / "model_card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["validation_summary"]["tail_check_failures"] = {"fixture-station": ["tail"]}
    card_path.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        if artifact["role"] == "model_card":
            artifact["size_bytes"] = card_path.stat().st_size
            artifact["sha256"] = hashlib.sha256(card_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return bundle


def _blocked_scenario(tmp_path: Path, bundle: Path) -> Path:
    root = tmp_path / "blocked-scenario"
    root.mkdir()
    shutil.copytree(SCENARIO.parent, root / "lidar_tfl6")
    scenario = root / "lidar_tfl6" / "scenario.yaml"
    register_femic_hydrology_bundle(scenario, bundle)
    return scenario


def test_end_to_end_rejects_blocked_readiness(tmp_path: Path) -> None:
    bundle = _blocked_bundle(tmp_path)
    scenario = _blocked_scenario(tmp_path, bundle)
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", _rows(scenario))
    metadata = _write_metadata(
        tmp_path / "crosswalk.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
    )
    mapping = _map_cli(scenario, crosswalk, metadata, tmp_path / "mapping", bundle=bundle)
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule)

    result = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "screen",
            str(scenario),
            str(bundle),
            str(mapping),
            str(schedule),
            str(exposure),
            "--policy",
            "allow_provisional",
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "Tail-check" in result.output


def test_end_to_end_rejects_unreviewed_crosswalk(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", _rows(scenario))
    metadata = _write_metadata(
        tmp_path / "crosswalk.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
        review_status="not_reviewed",
        reviewed_by=None,
    )
    mapping = _map_cli(scenario, crosswalk, metadata, tmp_path / "mapping")
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule)

    result = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "screen",
            str(scenario),
            str(BUNDLE),
            str(mapping),
            str(schedule),
            str(exposure),
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "not reviewed" in result.output


def test_end_to_end_rejects_partial_mapping(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    crosswalk = _write_crosswalk(tmp_path / "partial.csv", [_rows(scenario)[0]])
    metadata = _write_metadata(
        tmp_path / "partial.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
    )
    mapping = _map_cli(scenario, crosswalk, metadata, tmp_path / "mapping", "--allow-partial")
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule)

    result = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "screen",
            str(scenario),
            str(BUNDLE),
            str(mapping),
            str(schedule),
            str(exposure),
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "no hydraulic mapping" in result.output


def test_end_to_end_rejects_missing_exposure_file(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", _rows(scenario))
    metadata = _write_metadata(
        tmp_path / "crosswalk.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
    )
    mapping = _map_cli(scenario, crosswalk, metadata, tmp_path / "mapping")
    schedule = _schedule(tmp_path)

    result = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "screen",
            str(scenario),
            str(BUNDLE),
            str(mapping),
            str(schedule),
            str(tmp_path / "missing-exposure.json"),
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "Unable to read exposure" in result.output


def test_end_to_end_rejects_tampered_bundle(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLE, bundle)
    artifact = bundle / "artifacts" / "response_surface" / "response_surface.json"
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["scenario", "hydrology", "register", str(scenario), str(bundle)],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "checksum mismatch" in result.output


def test_end_to_end_rejects_schedule_mismatch(tmp_path: Path) -> None:
    scenario = _scenario(tmp_path)
    schedule = _schedule(tmp_path)
    exposure = _exposure(tmp_path, schedule, schedule_sha256="b" * 64)
    crosswalk = _write_crosswalk(tmp_path / "crosswalk.csv", _rows(scenario))
    metadata = _write_metadata(
        tmp_path / "crosswalk.meta.json",
        crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
    )
    mapping = tmp_path / "mapping"
    mapped = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "map",
            str(scenario),
            str(BUNDLE),
            str(crosswalk),
            "--metadata",
            str(metadata),
            "--out",
            str(mapping),
        ],
        prog_name="fhops",
    )
    assert mapped.exit_code == 0, mapped.output

    result = runner.invoke(
        app,
        [
            "scenario",
            "hydrology",
            "screen",
            str(scenario),
            str(BUNDLE),
            str(mapping),
            str(schedule),
            str(exposure),
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "schedule hash" in result.output
