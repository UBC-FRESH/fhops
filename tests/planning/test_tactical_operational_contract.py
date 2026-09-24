"""Tests for the Phase 6 tactical–operational contract and CLI validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.planning import (
    TacticalOperationalScenario,
    load_tactical_operational_scenario,
    tactical_scenario_dimensions,
    tactical_scenario_to_dict,
)
from fhops.planning.tactical_operational import four_week_periods, seasonal_periods

TOPM_MINI = (
    Path(__file__).parents[1]
    / "fixtures"
    / "tactical_operational"
    / "topm-mini"
    / "specification.yaml"
)


def test_load_topm_mini_tactical_operational_contract() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)

    assert isinstance(scenario, TacticalOperationalScenario)
    assert scenario.name == "topm-mini"
    assert scenario.planning_level == "tactical_operational"
    assert scenario.schema_version == "0.1.0"

    dimensions = tactical_scenario_dimensions(scenario)
    assert dimensions["periods"] == 2
    assert dimensions["products"] == 2
    assert dimensions["planning_units"] == 3
    assert dimensions["harvest_system_options"] == 4
    assert dimensions["fleet_capacity_records"] == 2
    assert dimensions["facilities"] == 2
    assert dimensions["transport_arcs"] == 3

    round_trip = tactical_scenario_to_dict(scenario)
    replayed = TacticalOperationalScenario.model_validate(round_trip)
    assert tactical_scenario_dimensions(replayed) == dimensions


def test_tactical_operational_cross_reference_validation() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    payload = tactical_scenario_to_dict(scenario)
    payload["facility_demand"][0]["product_id"] = "unknown-product"

    with pytest.raises(ValidationError, match="unknown product"):
        TacticalOperationalScenario.model_validate(payload)


def test_period_templates_and_rollups() -> None:
    four_week = four_week_periods(2027, discount_rate_per_year=0.04)
    seasons = seasonal_periods(2027, discount_rate_per_year=0.04)

    assert len(four_week) == 13
    assert four_week[0].duration_days == 28
    assert four_week[-1].end_date.year == 2027
    assert four_week[0].discount_factor == pytest.approx(1.0)
    assert four_week[-1].discount_factor < 1.0

    assert [period.period_id for period in seasons] == [
        "Y2027-WINTER",
        "Y2027-SPRING",
        "Y2027-SUMMER",
        "Y2027-FALL",
    ]
    assert all(period.duration_days and period.duration_days > 0 for period in seasons)


def test_validate_tactical_operational_cli() -> None:
    result = CliRunner().invoke(
        app,
        ["validate", "tactical-operational", str(TOPM_MINI)],
        prog_name="fhops",
    )

    assert result.exit_code == 0
    assert "Tactical–Operational Scenario" in result.stdout
    assert "topm-mini" in result.stdout
    assert "Harvest System Options" in result.stdout
    assert "Transport Arcs" in result.stdout


def test_validate_operational_cli_compatibility() -> None:
    result = CliRunner().invoke(
        app,
        ["validate", "examples/tiny7/scenario.yaml"],
        prog_name="fhops",
    )

    assert result.exit_code == 0
    assert "Scenario: FHOPS" in result.stdout
    assert "Tiny7" in result.stdout
    assert "Blocks" in result.stdout
