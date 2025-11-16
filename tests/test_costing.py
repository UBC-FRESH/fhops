import pytest

from fhops.costing import compute_unit_cost, estimate_unit_cost_from_stand
from fhops.costing.machine_rates import (
    MachineRate,
    compose_rental_rate,
    get_machine_rate,
    normalize_machine_role,
)
from fhops.productivity import LahrsenModel


def test_compute_unit_cost_basic():
    cost = compute_unit_cost(rental_rate_smh=1000.0, utilisation=0.9, productivity_m3_per_pmh=50.0)
    assert pytest.approx(cost.cost_per_m3, rel=1e-6) == 1000.0 / (0.9 * 50.0)


def test_compute_unit_cost_includes_breakdown():
    breakdown = {"ownership": 120.0, "operating": 80.0, "repair_maintenance": 15.0}
    cost = compute_unit_cost(
        rental_rate_smh=215.0,
        utilisation=0.9,
        productivity_m3_per_pmh=45.0,
        rental_rate_breakdown=breakdown,
    )
    assert cost.rental_rate_breakdown == breakdown


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


def test_compose_rental_rate_with_repair_toggle():
    rate = MachineRate(
        machine_name="Test Yarder",
        role="test_yarder",
        ownership_cost_per_smh=150.0,
        operating_cost_per_smh=180.0,
        default_utilization=0.8,
        move_in_cost=5000.0,
        source="unit-test",
        notes=None,
        repair_maintenance_cost_per_smh=60.0,
        repair_maintenance_reference_hours=10000,
    )
    total, breakdown = compose_rental_rate(rate)
    assert pytest.approx(total) == 390.0
    assert pytest.approx(breakdown["ownership"]) == 150.0
    assert pytest.approx(breakdown["operating"]) == 180.0
    assert pytest.approx(breakdown["repair_maintenance"]) == 60.0

    total_no_repair, breakdown_no = compose_rental_rate(rate, include_repair_maintenance=False)
    assert pytest.approx(total_no_repair) == 330.0
    assert "repair_maintenance" not in breakdown_no


def test_normalize_machine_role_synonyms():
    assert normalize_machine_role("Feller-Buncher") == "feller_buncher"
    assert normalize_machine_role("roadside processor") == "processor"
    assert normalize_machine_role(" Loader-Or-Water ") == "loader"


def test_machine_rate_usage_multipliers_exposed():
    rate = get_machine_rate("grapple_skidder")
    assert rate is not None
    assert rate.repair_maintenance_usage_multipliers is not None
    assert pytest.approx(rate.repair_maintenance_usage_multipliers[5000], rel=1e-4) == 0.6949


def test_compose_rental_rate_scales_repair_with_usage_hours():
    rate = MachineRate(
        machine_name="Test Loader",
        role="loader",
        ownership_cost_per_smh=80.0,
        operating_cost_per_smh=90.0,
        default_utilization=0.8,
        move_in_cost=1000.0,
        source="unit-test",
        notes=None,
        repair_maintenance_cost_per_smh=40.0,
        repair_maintenance_reference_hours=10000,
        repair_maintenance_usage_multipliers={5000: 0.5, 10000: 1.0},
    )
    total_young, breakdown_young = compose_rental_rate(rate, usage_hours=5000)
    assert pytest.approx(breakdown_young["repair_maintenance"]) == 20.0
    assert pytest.approx(total_young) == 80.0 + 90.0 + 20.0

    total_mature, breakdown_mature = compose_rental_rate(rate, usage_hours=10000)
    assert pytest.approx(breakdown_mature["repair_maintenance"]) == 40.0
    assert pytest.approx(total_mature) == 80.0 + 90.0 + 40.0
