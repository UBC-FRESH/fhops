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
    "model.machine_capacity",
    "model.role_compatibility",
    "model.production_cap",
    "model.block_windows",
    "model.role_prod_balance",
    "model.transition_prev",
    "model.transition_curr",
    "model.transition_link",
    "model.inventory_start_eq",
    "model.inventory_balance",
    "model.inventory_guard",
    "model.activation_prod",
    "model.head_start",
    "model.role_active_upper",
    "model.role_active_lower",
    "model.loader_batch",
    "model.loader_partial_cap",
    "model.block_balance",
    "model.leftover",
    "model.landing_capacity",
    "model.landing_surplus",
    "model.objective",
]


def test_operational_formulation_traceability_components_exist() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    code = CODE.read_text(encoding="utf-8")

    assert "Equation/constraint block | Pyomo component" in source
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
    assert "fhops_operational_formulation.rst" in HOWTO.read_text(encoding="utf-8")
