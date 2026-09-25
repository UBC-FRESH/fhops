"""Traceability checks for the canonical tactical–operational MILP formulation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "docs/softwarex/manuscript/sections/includes/fhops_tactical_operational_formulation.md"
)
TEX = SOURCE.with_suffix(".tex")
RST = ROOT / "docs/includes/softwarex/fhops_tactical_operational_formulation.rst"
CODE = ROOT / "src/fhops/model/milp/tactical_operational.py"
HOWTO = ROOT / "docs/howto/tactical_operational.rst"

EXPECTED_COMPONENTS = [
    "model.harvest_upper",
    "model.harvest_lower",
    "model.whole_block",
    "model.productivity_cap",
    "model.product_conversion",
    "model.block_area",
    "model.fleet_capacity",
    "model.fleet_units",
    "model.fleet_option_upper",
    "model.flow_supply",
    "model.arc_capacity",
    "model.purchase_lower",
    "model.purchase_upper",
    "model.consumption_lower",
    "model.consumption_target",
    "model.consumption_upper",
    "model.inventory_balance",
    "model.road_build",
    "model.road_available",
    "model.road_build_timing",
    "model.road_availability",
    "model.road_build_once",
    "model.road_dependencies",
    "model.road_access",
    "model.road_capacity",
    "model.silviculture_area",
    "model.silviculture_fulfillment",
    "model.objective",
]


def test_tactical_formulation_traceability_components_exist() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    code = CODE.read_text(encoding="utf-8")

    assert "Equation/constraint block | Pyomo component" in source
    assert "TacticalOperationalScenario" in source
    assert "TOPM-inspired" in source
    for component in EXPECTED_COMPONENTS:
        assert component in source
        assert component in code


def test_generated_tactical_formulation_outputs_include_mapping() -> None:
    tex = TEX.read_text(encoding="utf-8")
    rst = RST.read_text(encoding="utf-8")

    assert "AUTO-GENERATED from fhops_tactical_operational_formulation.md" in tex
    assert "AUTO-GENERATED from fhops_tactical_operational_formulation.md" in rst
    assert "model.harvest\\_upper" in tex
    assert "model.inventory\\_balance" in tex
    assert "Implementation mapping" in rst
    assert "Pyomo component" in rst
    assert "fhops_tactical_operational_formulation.rst" in HOWTO.read_text(encoding="utf-8")
