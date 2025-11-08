from pathlib import Path

import pytest

from fhops.scenario.io import load_scenario

DATA_ROOT = Path("tests/data")


def test_minimal_fixture_loads():
    scenario = load_scenario(DATA_ROOT / "minimal" / "scenario.yaml")
    assert scenario.num_days == 1
    assert len(scenario.blocks) == 1
    assert scenario.production_rates[0].rate == 1.0


def test_typical_fixture_loads_with_mobilisation_hooks():
    scenario = load_scenario(DATA_ROOT / "typical" / "scenario.yaml")
    assert scenario.num_days == 5
    assert len(scenario.blocks) == 2
    assert scenario.blocks[0].harvest_system_id is not None
    assert scenario.timeline is not None
    assert scenario.timeline.shifts[0].hours > 0
    assert scenario.crew_assignments is not None
    assert len(scenario.crew_assignments) == 2
    assert scenario.geo is not None
    assert scenario.geo.block_geojson.endswith("blocks.geojson")


def test_invalid_fixture_raises_validation_error():
    with pytest.raises(Exception) as excinfo:
        load_scenario(DATA_ROOT / "invalid" / "scenario.yaml")
    msg = str(excinfo.value)
    assert "unknown landing_id" in msg or "ValidationError" in msg
