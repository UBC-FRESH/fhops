"""FEMIC hydrology bundle contract tests (P15.1)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.hydrology import (
    FemicHydrologyError,
    assess_femic_hydrology_readiness,
    bundle_pin,
    load_femic_hydrology_bundle,
    validate_femic_hydrology_bundle,
)

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hydrology" / "response"


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "bundle"
    shutil.copytree(FIXTURE, target)
    return target


def _manifest(path: Path) -> dict[str, object]:
    payload = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    (path / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _artifact(path: Path, role: str) -> Path:
    return path / "artifacts" / role / f"{role}.json"


def _refresh_artifact(path: Path, role: str) -> None:
    artifact_path = _artifact(path, role)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    artifact_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = _manifest(path)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    for item in artifacts:
        assert isinstance(item, dict)
        if item.get("role") == role:
            item["size_bytes"] = artifact_path.stat().st_size
            item["sha256"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            break
    else:
        raise AssertionError(f"role {role!r} is not in the manifest")
    _write_manifest(path, manifest)


def _drop_optional_evidence(path: Path) -> None:
    manifest = _manifest(path)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    manifest["artifacts"] = [
        item
        for item in artifacts
        if isinstance(item, dict) and item.get("role") not in {"validation_report", "model_card"}
    ]
    _write_manifest(path, manifest)


def test_load_and_pin_bundle() -> None:
    bundle = load_femic_hydrology_bundle(
        FIXTURE,
        expected_bundle_id="hydro-response-test00000001",
        expected_bundle_version="2026.10.0",
    )

    assert bundle.bundle_id == "hydro-response-test00000001"
    assert bundle.domain_id == "fixture-domain"
    assert bundle.ledger_id == "fixture-ledger"
    assert bundle.response_surface_id == "fixture-surface"
    assert set(bundle.artifacts) == {
        "response_surface",
        "flood_risk",
        "domain",
        "disturbance_ledger",
        "validation_report",
        "model_card",
    }
    assert bundle.total_bytes > 0
    pin = bundle_pin(bundle)
    assert pin["bundle_id"] == bundle.bundle_id
    assert pin["manifest_sha256"] == bundle.manifest_sha256
    artifacts = pin["artifacts"]
    assert isinstance(artifacts, dict)
    assert artifacts["response_surface"]["sha256"] == bundle.artifacts["response_surface"].sha256
    assert "not a regulatory flood map" in bundle.caveats[0]

    readiness = assess_femic_hydrology_readiness(bundle)
    assert readiness.status == "ready"
    assert readiness.review_status == "reviewed"
    assert readiness.hydrologist_review_recorded is True
    assert readiness.tail_check_failures == {}
    assert readiness.evidence_sha256.startswith("hydro-evidence-")
    assert readiness.to_dict()["status"] == "ready"


def test_validation_rejects_tampered_artifact(tmp_path: Path) -> None:
    bundle = _copy_fixture(tmp_path)
    artifact = _artifact(bundle, "response_surface")
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = validate_femic_hydrology_bundle(bundle)

    assert report.is_valid is False
    assert any("checksum mismatch" in error for error in report.errors)
    with pytest.raises(FemicHydrologyError, match="checksum mismatch"):
        load_femic_hydrology_bundle(bundle)


def test_validation_rejects_missing_required_role(tmp_path: Path) -> None:
    bundle = _copy_fixture(tmp_path)
    manifest = _manifest(bundle)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    manifest["artifacts"] = [
        item for item in artifacts if isinstance(item, dict) and item.get("role") != "flood_risk"
    ]
    _write_manifest(bundle, manifest)

    report = validate_femic_hydrology_bundle(bundle)

    assert report.is_valid is False
    assert any("Missing required artifact roles" in error for error in report.errors)


def test_validation_rejects_path_escape_and_absolute_path(tmp_path: Path) -> None:
    bundle = _copy_fixture(tmp_path)
    manifest = _manifest(bundle)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    first = artifacts[0]
    assert isinstance(first, dict)
    first["relative_path"] = "../escape.json"
    _write_manifest(bundle, manifest)

    report = validate_femic_hydrology_bundle(bundle)
    assert any("must not traverse" in error for error in report.errors)

    bundle = _copy_fixture(tmp_path / "absolute")
    manifest = _manifest(bundle)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    first = artifacts[0]
    assert isinstance(first, dict)
    first["relative_path"] = "/tmp/absolute.json"
    _write_manifest(bundle, manifest)
    report = validate_femic_hydrology_bundle(bundle)
    assert any("must be relative" in error for error in report.errors)


def test_validation_rejects_id_mismatch(tmp_path: Path) -> None:
    bundle = _copy_fixture(tmp_path)
    artifact = _artifact(bundle, "response_surface")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload["surface_id"] = "other-surface"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _refresh_artifact(bundle, "response_surface")

    report = validate_femic_hydrology_bundle(bundle)

    assert report.is_valid is False
    assert any("Response-surface artifact ID" in error for error in report.errors)


def test_validation_rejects_wrong_role_schema(tmp_path: Path) -> None:
    bundle = _copy_fixture(tmp_path)
    manifest = _manifest(bundle)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    surface = next(
        item
        for item in artifacts
        if isinstance(item, dict) and item.get("role") == "response_surface"
    )
    surface["schema_version"] = "femic.hydrology.wrong.v1"
    _write_manifest(bundle, manifest)

    report = validate_femic_hydrology_bundle(bundle)

    assert report.is_valid is False
    assert any("does not match" in error for error in report.errors)


def test_expected_id_and_version_mismatch(tmp_path: Path) -> None:
    with pytest.raises(FemicHydrologyError, match="does not match expected"):
        load_femic_hydrology_bundle(FIXTURE, expected_bundle_id="other")
    with pytest.raises(FemicHydrologyError, match="does not match expected"):
        load_femic_hydrology_bundle(FIXTURE, expected_bundle_version="other")


def test_readiness_not_available_and_blocked(tmp_path: Path) -> None:
    bundle = _copy_fixture(tmp_path / "missing")
    _drop_optional_evidence(bundle)
    loaded = load_femic_hydrology_bundle(bundle)
    readiness = assess_femic_hydrology_readiness(loaded)
    assert readiness.status == "not_available"
    assert any("No validation_report" in warning for warning in readiness.warnings)
    assert any("No model_card" in warning for warning in readiness.warnings)

    bundle = _copy_fixture(tmp_path / "blocked")
    for role in ("validation_report", "model_card"):
        artifact = _artifact(bundle, role)
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        summary_key = "summary" if role == "validation_report" else "validation_summary"
        summary = payload[summary_key]
        assert isinstance(summary, dict)
        summary["tail_check_failures"] = {"fixture-station": ["shape outside bounds"]}
        artifact.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _refresh_artifact(bundle, role)
    loaded = load_femic_hydrology_bundle(bundle)
    readiness = assess_femic_hydrology_readiness(loaded)
    assert readiness.status == "blocked"
    assert readiness.tail_check_failures


def test_readiness_provisional_and_conditionally_ready(tmp_path: Path) -> None:
    bundle = _copy_fixture(tmp_path / "provisional")
    artifact = _artifact(bundle, "model_card")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload["review_status"] = "not_reviewed"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _refresh_artifact(bundle, "model_card")
    readiness = assess_femic_hydrology_readiness(load_femic_hydrology_bundle(bundle))
    assert readiness.status == "provisional"

    bundle = _copy_fixture(tmp_path / "conditional")
    artifact = _artifact(bundle, "model_card")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload["review_status"] = "reviewed_with_conditions"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _refresh_artifact(bundle, "model_card")
    readiness = assess_femic_hydrology_readiness(load_femic_hydrology_bundle(bundle))
    assert readiness.status == "conditionally_ready"


def test_validation_accepts_manifest_path_and_missing_manifest(tmp_path: Path) -> None:
    report = validate_femic_hydrology_bundle(FIXTURE / "manifest.json")
    assert report.is_valid is True

    missing = tmp_path / "missing"
    missing.mkdir()
    report = validate_femic_hydrology_bundle(missing)
    assert report.is_valid is False
    assert any("Manifest is missing" in error for error in report.errors)


def test_cli_validate_returns_json_and_exit_code(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["scenario", "hydrology", "validate", str(FIXTURE)],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["is_valid"] is True
    assert payload["artifact_count"] == 6

    bundle = _copy_fixture(tmp_path)
    artifact = _artifact(bundle, "response_surface")
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    invalid = runner.invoke(
        app,
        ["scenario", "hydrology", "validate", str(bundle)],
        prog_name="fhops",
    )
    assert invalid.exit_code == 1
    invalid_payload = json.loads(invalid.output)
    assert invalid_payload["is_valid"] is False
    assert any("checksum mismatch" in error for error in invalid_payload["errors"])
