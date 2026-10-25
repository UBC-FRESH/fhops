"""Tests for operational/tactical hauling integration."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from fhops.hauling.integration import (
    residual_report,
    scenario_from_operational_plan,
    scenario_from_tactical_plan,
)
from fhops.planning.tactical_operational import (
    Facility,
    FacilityDemand,
    HarvestSystemOption,
    PeriodLevel,
    PlanningPeriod,
    PlanningUnit,
    Product,
    TacticalOperationalScenario,
    TransportArc,
)
from fhops.scenario.io import load_scenario


def _example_scenario():
    return load_scenario("examples/hauling/scenario.yaml")


def test_operational_assignments_become_supply() -> None:
    scenario = _example_scenario()
    assignments = pd.DataFrame(
        {
            "block_id": ["b1", "b2", "b3"],
            "production": [300.0, 250.0, 250.0],
        }
    )
    result = scenario_from_operational_plan(
        scenario,
        assignments,
        sort_shares={"fir_saw": 0.5, "hemlock_pulp": 0.3, "mixed_unsorted": 0.2},
    )
    assert result.warnings == []
    assert result.scenario.hauling is not None
    supply = result.scenario.hauling.supply
    assert len(supply) == 9
    b1 = {
        row.log_sort_id: (row.sorted_m3, row.unsorted_m3) for row in supply if row.block_id == "b1"
    }
    assert b1["fir_saw"] == (150.0, 0.0)
    assert b1["hemlock_pulp"] == (90.0, 0.0)
    assert b1["mixed_unsorted"] == (0.0, 60.0)
    assert result.residuals["supply_m3"].sum() == pytest.approx(800.0)


def test_equal_share_default_is_warned() -> None:
    scenario = _example_scenario()
    assignments = pd.DataFrame({"block_id": ["b1"], "production": [300.0]})
    result = scenario_from_operational_plan(scenario, assignments)
    assert any("equal shares" in warning for warning in result.warnings)
    assert result.scenario.hauling is not None
    assert sum(
        row.sorted_m3 + row.unsorted_m3 for row in result.scenario.hauling.supply
    ) == pytest.approx(300.0)


def test_invalid_sort_shares_are_rejected() -> None:
    scenario = _example_scenario()
    assignments = pd.DataFrame({"block_id": ["b1"], "production": [300.0]})
    with pytest.raises(ValueError, match="must sum to 1.0"):
        scenario_from_operational_plan(
            scenario,
            assignments,
            sort_shares={"fir_saw": 0.2, "hemlock_pulp": 0.2, "mixed_unsorted": 0.2},
        )


def _tactical() -> TacticalOperationalScenario:
    return TacticalOperationalScenario(
        name="hauling-tactical",
        periods=[
            PlanningPeriod(
                period_id="p1",
                level=PeriodLevel.FOUR_WEEK,
                sequence=1,
                start_date=date(2026, 11, 2),
                end_date=date(2026, 11, 29),
            )
        ],
        products=[
            Product(product_id="fir_saw"),
            Product(product_id="hemlock_pulp"),
            Product(product_id="mixed_unsorted"),
        ],
        planning_units=[
            PlanningUnit(
                block_id="b1",
                gross_area_ha=10.0,
                operable_area_ha=10.0,
                product_yields_m3_per_ha={"fir_saw": 30.0},
            ),
            PlanningUnit(
                block_id="b2",
                gross_area_ha=10.0,
                operable_area_ha=10.0,
                product_yields_m3_per_ha={"hemlock_pulp": 25.0},
            ),
            PlanningUnit(
                block_id="b3",
                gross_area_ha=10.0,
                operable_area_ha=10.0,
                product_yields_m3_per_ha={"mixed_unsorted": 25.0},
            ),
        ],
        harvest_system_options=[
            HarvestSystemOption(
                option_id="b1-ground",
                block_id="b1",
                system_id="ground",
                period_id="p1",
                max_area_ha=10.0,
            )
        ],
        facilities=[
            Facility(
                facility_id="mill_a",
                accepted_products=["fir_saw", "hemlock_pulp", "mixed_unsorted"],
            )
        ],
        transport_arcs=[
            TransportArc(
                arc_id="b1-mill-fir",
                origin_id="b1",
                destination_id="mill_a",
                product_id="fir_saw",
                period_id="p1",
                distance_km=100.0,
            )
        ],
        facility_demand=[
            FacilityDemand(
                facility_id="mill_a", product_id="fir_saw", period_id="p1", target_m3=300.0
            ),
            FacilityDemand(
                facility_id="mill_a", product_id="hemlock_pulp", period_id="p1", target_m3=250.0
            ),
            FacilityDemand(
                facility_id="mill_a", product_id="mixed_unsorted", period_id="p1", target_m3=250.0
            ),
        ],
    )


def test_tactical_production_and_demand_become_hauling_inputs() -> None:
    scenario = _example_scenario()
    production = pd.DataFrame(
        {
            "block_id": ["b1", "b2", "b3"],
            "product_id": ["fir_saw", "hemlock_pulp", "mixed_unsorted"],
            "period_id": ["p1", "p1", "p1"],
            "volume_m3": [300.0, 250.0, 250.0],
        }
    )
    result = scenario_from_tactical_plan(
        scenario,
        _tactical(),
        period_id="p1",
        production=production,
    )
    assert result.scenario.hauling is not None
    supply_total = sum(row.sorted_m3 + row.unsorted_m3 for row in result.scenario.hauling.supply)
    demand_total = sum(row.volume_m3 for row in result.scenario.hauling.demand)
    assert supply_total == pytest.approx(800.0)
    assert demand_total == pytest.approx(800.0)
    assert len(result.scenario.hauling.demand) == 15
    assert any("spread evenly" in warning for warning in result.warnings)
    assert result.residuals["residual_m3"].abs().max() == pytest.approx(0.0)


def test_residual_report_flags_missing_supply() -> None:
    scenario = _example_scenario()
    assert scenario.hauling is not None
    config = scenario.hauling.model_copy(
        update={"supply": [row for row in scenario.hauling.supply if row.block_id != "b1"]}
    )
    reduced = scenario.model_copy(update={"hauling": config})
    residuals = residual_report(reduced)
    fir = residuals[residuals["log_sort_id"] == "fir_saw"].iloc[0]
    assert fir["residual_m3"] > 0
