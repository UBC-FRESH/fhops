"""Validation for the redistributable practitioner-scale tactical case."""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.model.milp.tactical_operational import (
    build_tactical_operational_bundle,
    solve_tactical_operational_milp,
)
from fhops.planning.tactical_operational.io import load_tactical_operational_scenario
from fhops.planning.tactical_operational.practitioner import (
    generate_tactical_practitioner_case,
)

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "tactical_operational"
    / "practitioner-case"
    / "scenario.yaml"
)


def test_practitioner_case_generator_and_fixture_round_trip() -> None:
    generated = generate_tactical_practitioner_case()
    loaded = load_tactical_operational_scenario(FIXTURE)

    assert generated.dimension_summary() == loaded.dimension_summary()
    assert loaded.dimension_summary()["planning_units"] == 24
    assert loaded.dimension_summary()["periods"] == 8
    assert loaded.dimension_summary()["harvest_system_options"] == 240
    assert loaded.dimension_summary()["road_projects"] == 3
    assert loaded.dimension_summary()["silviculture_transitions"] == 18
    assert loaded.dimension_summary()["fleet_options"] == 1


def test_practitioner_case_solves_with_all_modules() -> None:
    scenario = load_tactical_operational_scenario(FIXTURE)
    result = solve_tactical_operational_milp(
        build_tactical_operational_bundle(
            scenario,
            enable_roads=True,
            enable_silviculture=True,
            enable_fleet_investment=True,
        ),
        solver="highs",
        time_limit=120,
        gap=0.01,
    )

    assert result["termination_condition"].lower() == "optimal"
    assert result["objective"] is not None
    assert result["objective_components"]["total_cost"] > 0

    options = {option.option_id: option for option in scenario.harvest_system_options}
    for row in result["harvest_decisions"].itertuples(index=False):
        if row.harvested_area_ha > 0:
            assert row.harvested_area_ha + 1e-6 >= options[row.option_id].min_area_ha

    # Inventory balances must close for every facility/product/period.
    flows = result["flows"]
    purchases = result["purchases"]
    inventory = result["inventory"]
    consumption = result["consumption"]
    inventory_map = {
        (row.facility_id, row.product_id, row.period_id): float(row.closing_m3)
        for row in inventory.itertuples(index=False)
    }
    periods = sorted(scenario.periods, key=lambda period: period.sequence)
    for facility in scenario.facilities:
        for product_id in facility.accepted_products:
            opening = next(
                (
                    row.opening_m3
                    for row in scenario.initial_inventory
                    if row.facility_id == facility.facility_id and row.product_id == product_id
                ),
                0.0,
            )
            for period in periods:
                key = (facility.facility_id, product_id, period.period_id)
                deliveries = flows.loc[
                    (flows["destination_id"] == facility.facility_id)
                    & (flows["product_id"] == product_id)
                    & (flows["period_id"] == period.period_id),
                    "volume_m3",
                ].sum()
                bought = purchases.loc[
                    (purchases["destination_id"] == facility.facility_id)
                    & (purchases["product_id"] == product_id)
                    & (purchases["period_id"] == period.period_id),
                    "volume_m3",
                ].sum()
                used = consumption.loc[
                    (consumption["facility_id"] == facility.facility_id)
                    & (consumption["product_id"] == product_id)
                    & (consumption["period_id"] == period.period_id),
                    "consumption_m3",
                ].sum()
                closing = inventory_map.get(key, 0.0)
                assert closing == pytest.approx(opening + deliveries + bought - used)
                opening = closing


def test_practitioner_case_cli_generator(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from fhops.cli.main import app

    out = tmp_path / "practitioner.yaml"
    result = CliRunner().invoke(
        app,
        ["synth", "tactical-practitioner", "--out", str(out)],
        prog_name="fhops",
    )

    assert result.exit_code == 0
    assert load_tactical_operational_scenario(out).dimension_summary()["planning_units"] == 24
