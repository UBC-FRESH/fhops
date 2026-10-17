"""Traceability checks for the canonical operational MILP formulation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md"
TEX = SOURCE.with_suffix(".tex")
RST = ROOT / "docs/includes/softwarex/fhops_operational_formulation.rst"
CODE = ROOT / "src/fhops/model/milp/operational.py"
HOWTO = ROOT / "docs/howto/optimization_formulation.rst"

EXPECTED_COMPONENTS = [
    "model.activation_prod",
    "model.arrive",
    "model.block_balance",
    "model.block_windows",
    "model.depart",
    "model.first",
    "model.head_start",
    "model.hub_balance",
    "model.inventory",
    "model.inventory_balance",
    "model.inventory_guard",
    "model.inventory_start",
    "model.inventory_start_eq",
    "model.landing_capacity",
    "model.landing_surplus",
    "model.leftover",
    "model.loader_tail",
    "model.loader_tail_monotone",
    "model.loader_tail_reached",
    "model.loader_threshold",
    "model.loader_threshold_tail",
    "model.locked_assignment",
    "model.machine_capacity",
    "model.move_requires_work",
    "model.objective",
    "model.position_balance",
    "model.prod",
    "model.production_cap",
    "model.role_active",
    "model.role_active_lower",
    "model.role_active_upper",
    "model.role_compatibility",
    "model.role_cumulative",
    "model.role_cumulative_eq",
    "model.role_prod",
    "model.role_prod_balance",
    "model.role_remaining_cap",
    "model.role_slot_remaining",
    "model.stay",
    "model.unplaced",
    "model.unplaced_balance",
    "model.upstream_done",
    "model.upstream_done_link",
    "model.work_sets_position",
    "model.x",
    "model.y",
]


def test_operational_formulation_traceability_components_exist() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    code = CODE.read_text(encoding="utf-8")

    assert "Implementation mapping (equation blocks to code)" in source
    assert "build_operational_bundle(...)" in source
    for component in EXPECTED_COMPONENTS:
        assert component in source
        assert component in code


def test_generated_operational_formulation_outputs_include_mapping() -> None:
    tex = TEX.read_text(encoding="utf-8")
    rst = RST.read_text(encoding="utf-8")

    assert "AUTO-GENERATED from fhops_operational_formulation.md" in tex
    assert "AUTO-GENERATED from fhops_operational_formulation.md" in rst
    assert "model.machine\\_capacity" in tex
    assert "model.machine_capacity" in rst
    assert "model.objective" in tex
    assert "model.objective" in rst
    assert "Implementation mapping" in rst
    assert "Pyomo objects and rules" in rst
    assert "fhops_operational_formulation.rst" in HOWTO.read_text(encoding="utf-8")
