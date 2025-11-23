from __future__ import annotations

import pytest

from fhops.reference import estimate_tr28_road_cost, load_tr28_machines


def _get_machine(slug: str):
    return next(machine for machine in load_tr28_machines() if machine.slug == slug)


def test_estimate_tr28_road_cost_totals() -> None:
    machine = _get_machine("caterpillar_235_hydraulic_backhoe")
    estimate = estimate_tr28_road_cost(machine, road_length_m=100.0)
    assert pytest.approx(estimate.total_cost_base_cad, rel=1e-6) == (
        machine.unit_cost_cad_per_meter * 100.0
    )
    assert estimate.mobilisation_cost_base_cad == pytest.approx(
        machine.movement_total_cost_cad or 0.0
    )
    assert estimate.mobilisation_included


def test_estimate_tr28_road_cost_excluding_mobilisation() -> None:
    machine = _get_machine("caterpillar_235_hydraulic_backhoe")
    estimate = estimate_tr28_road_cost(
        machine,
        road_length_m=50.0,
        include_mobilisation=False,
    )
    assert estimate.mobilisation_cost_base_cad == 0.0
    assert estimate.total_with_mobilisation_base_cad == estimate.total_cost_base_cad
