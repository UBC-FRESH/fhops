import pytest

from fhops.validation.ranges import validate_block_ranges


def test_validate_block_ranges_flags_outliers():
    warnings = validate_block_ranges(
        block_id="B1",
        stem_size=2.0,
        volume_per_ha=1000.0,
        stem_density=4000.0,
        ground_slope=60.0,
    )
    assert len(warnings) == 4


def test_validate_block_ranges_ok_within_bounds():
    warnings = validate_block_ranges(
        block_id="B1",
        stem_size=0.5,
        volume_per_ha=300.0,
        stem_density=800.0,
        ground_slope=20.0,
    )
    assert warnings == []
