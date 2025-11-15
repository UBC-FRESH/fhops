import pytest

from fhops.costing import compute_unit_cost, estimate_unit_cost_from_stand
from fhops.productivity import LahrsenModel


def test_compute_unit_cost_basic():
    cost = compute_unit_cost(rental_rate_smh=1000.0, utilisation=0.9, productivity_m3_per_pmh=50.0)
    assert pytest.approx(cost.cost_per_m3, rel=1e-6) == 1000.0 / (0.9 * 50.0)


def test_estimate_unit_cost_from_stand():
    cost, prod = estimate_unit_cost_from_stand(
        rental_rate_smh=1200.0,
        utilisation=0.85,
        avg_stem_size=0.4,
        volume_per_ha=300.0,
        stem_density=900.0,
        ground_slope=15.0,
        model=LahrsenModel.DAILY,
    )
    assert cost.cost_per_m3 > 0
    assert prod.predicted_m3_per_pmh > 0
