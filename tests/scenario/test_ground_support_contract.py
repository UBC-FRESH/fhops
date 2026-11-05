"""Scenario-level FEMIC ground-support reference tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from fhops.scenario.contract import GroundSupportRef
from fhops.scenario.io import load_scenario

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "examples/lidar_tfl6"
TINY = REPO / "examples/tiny7"


def test_example_scenario_has_ground_support() -> None:
    """The public TFL6 fixture pins the seven-block ground summary."""
    scenario = load_scenario(FIXTURE / "scenario.yaml")
    reference = scenario.ground_support
    assert reference is not None
    assert reference.schema_version == "femic.ground-summary.v1"
    assert reference.summary_path == "ground_summary.csv"
    assert reference.summary_sha256 == (
        "c1755a444a11f0ee8aba1db49dcba2b9900d6ed4c157acd0ee4cc205d6541b6b"
    )
    assert reference.id_field == "polygon_id"
    assert reference.producer == "FEMIC"
    assert reference.caveats


def test_ground_support_is_optional() -> None:
    """Scenarios without ground evidence remain valid."""
    scenario = load_scenario(TINY / "scenario.yaml")
    assert scenario.ground_support is None


def test_ground_support_rejects_bad_checksum() -> None:
    """The summary checksum must be a SHA-256 digest."""
    with pytest.raises(ValidationError, match="SHA-256"):
        GroundSupportRef(summary_path="summary.csv", summary_sha256="not-a-checksum")


def test_ground_support_rejects_unknown_schema() -> None:
    """Only the supported FEMIC summary schema is accepted."""
    with pytest.raises(ValidationError, match="femic.ground-summary.v1"):
        GroundSupportRef(
            schema_version="femic.ground-summary.v2",
            summary_path="summary.csv",
            summary_sha256="a" * 64,
        )


def test_ground_support_rejects_blank_path() -> None:
    """A blank summary path is invalid."""
    with pytest.raises(ValidationError, match="non-empty"):
        GroundSupportRef(summary_path="   ", summary_sha256="a" * 64)
