"""FEMIC hydrology registration and scenario-pin tests (P15.2)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.hydrology_registration import (
    FemicHydrologyRegistrationError,
    register_femic_hydrology_bundle,
)
from fhops.scenario.io import load_scenario

runner = CliRunner()
REPO = Path(__file__).resolve().parents[2]
BUNDLE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "response"


def _scenario(tmp_path: Path) -> Path:
    target = tmp_path / "hauling"
    shutil.copytree(REPO / "examples" / "hauling", target)
    return target / "scenario.yaml"


def test_register_pins_bundle_with_readiness_and_artifacts(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    result = register_femic_hydrology_bundle(scenario_path, BUNDLE)

    assert result.written is True
    assert result.bundle_id == "hydro-response-test00000001"
    assert result.readiness_status == "ready"
    assert result.pin.readiness_status == "ready"
    assert result.pin.readiness_evidence_sha256 is not None
    assert len(result.pin.artifacts) == 6
    assert result.pin.artifacts[0].role == "disturbance_ledger"
    assert all(artifact.sha256 == artifact.sha256.lower() for artifact in result.pin.artifacts)

    loaded = load_scenario(scenario_path)
    assert loaded.hydrology_products is not None
    pin = loaded.hydrology_products[0]
    assert pin.bundle_version == "2026.10.0"
    assert pin.domain_id == "fixture-domain"
    assert pin.ledger_id == "fixture-ledger"
    assert pin.response_surface_id == "fixture-surface"
    assert pin.readiness_status == "ready"
    assert pin.caveats
    assert len(pin.artifacts) == 6


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    before = scenario_path.read_text(encoding="utf-8")
    result = register_femic_hydrology_bundle(scenario_path, BUNDLE, dry_run=True)
    assert result.written is False
    assert scenario_path.read_text(encoding="utf-8") == before


def test_register_is_idempotent(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    register_femic_hydrology_bundle(scenario_path, BUNDLE)
    register_femic_hydrology_bundle(scenario_path, BUNDLE)
    loaded = load_scenario(scenario_path)
    assert loaded.hydrology_products is not None
    assert len(loaded.hydrology_products) == 1
    assert scenario_path.read_text(encoding="utf-8").count("\nhydrology_products:") == 1


def test_changed_manifest_is_rejected_on_reregistration(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLE, bundle)
    register_femic_hydrology_bundle(scenario_path, bundle)
    manifest = bundle / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(FemicHydrologyRegistrationError, match="different manifest checksum"):
        register_femic_hydrology_bundle(scenario_path, bundle)


def test_duplicate_pins_are_rejected_by_the_scenario_contract(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    register_femic_hydrology_bundle(scenario_path, BUNDLE)
    payload = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    pins = payload["hydrology_products"]
    assert isinstance(pins, list)
    payload["hydrology_products"] = [pins[0], pins[0]]
    duplicate_path = scenario_path.parent / "duplicate.yaml"
    duplicate_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValidationError, match="Duplicate HydrologyBundleRef pin"):
        load_scenario(duplicate_path)


def test_cli_register_writes_pin(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    result = runner.invoke(
        app,
        ["scenario", "hydrology", "register", str(scenario_path), str(BUNDLE)],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["written"] is True
    assert payload["readiness_status"] == "ready"
    assert load_scenario(scenario_path).hydrology_products is not None


def test_cli_register_rejects_tampered_bundle(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLE, bundle)
    artifact = bundle / "artifacts" / "response_surface" / "response_surface.json"
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["scenario", "hydrology", "register", str(scenario_path), str(bundle)],
        prog_name="fhops",
    )
    assert result.exit_code == 1
    assert "checksum mismatch" in result.output


def test_scenario_without_hydrology_remains_valid(tmp_path: Path) -> None:
    scenario_path = _scenario(tmp_path)
    loaded = load_scenario(scenario_path)
    assert loaded.hydrology_products is None
