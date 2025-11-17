from __future__ import annotations

import pytest

from fhops.productivity import ALPACASlopeClass
from fhops.productivity.forwarder_bc import (
    ForwarderBCModel,
    estimate_forwarder_productivity_bc,
)


@pytest.mark.parametrize(
    ("model", "distance_m", "expected"),
    [
        (ForwarderBCModel.GHAFFARIYAN_SMALL, 100.0, 31.8),
        (ForwarderBCModel.GHAFFARIYAN_LARGE, 100.0, 49.1),
        (ForwarderBCModel.GHAFFARIYAN_SMALL, 400.0, 28.1),
        (ForwarderBCModel.GHAFFARIYAN_LARGE, 400.0, 41.2),
    ],
)
def test_forwarder_bc_ghaffariyan_matches_tables(
    model: ForwarderBCModel, distance_m: float, expected: float
) -> None:
    result = estimate_forwarder_productivity_bc(
        model=model,
        extraction_distance_m=distance_m,
        slope_class=ALPACASlopeClass.FLAT,
    )
    assert result.predicted_m3_per_pmh == pytest.approx(expected, rel=5e-3)


def test_forwarder_bc_kellogg_matches_table8() -> None:
    result = estimate_forwarder_productivity_bc(
        model=ForwarderBCModel.KELLOGG_MIXED,
        volume_per_load_m3=9.3,
        distance_out_m=274.0,
        travel_in_unit_m=76.0,
        distance_in_m=259.0,
    )
    assert result.predicted_m3_per_pmh == pytest.approx(13.4, rel=1e-2)
