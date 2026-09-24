"""Structural checks for the TOPM-inspired tactical–operational mini fixture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

SPEC_PATH = (
    Path(__file__).parent / "fixtures" / "tactical_operational" / "topm-mini" / "specification.yaml"
)


def _load_spec() -> dict[str, Any]:
    with SPEC_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    assert isinstance(payload, dict)
    return payload


def _index(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    values = [row[key] for row in rows]
    assert len(values) == len(set(values))
    return {row[key]: row for row in rows}


def test_topm_mini_specification_structure() -> None:
    spec = _load_spec()
    assert spec["specification_version"] == "0.1.0"
    assert spec["fixture_id"] == "topm-mini"
    assert spec["issue"] == 37
    assert spec["units"]["area"] == "ha"
    assert spec["units"]["volume"] == "m3"

    for section in (
        "periods",
        "products",
        "planning_units",
        "harvest_system_options",
        "hand_calculated_cases",
        "facilities",
        "facility_demand",
        "initial_inventory",
        "transport_arcs",
        "flow_inventory_expectations",
    ):
        assert section in spec
        assert isinstance(spec[section], list)
        assert spec[section]

    _index(spec["periods"], "period_id")
    _index(spec["products"], "product_id")
    _index(spec["planning_units"], "block_id")
    _index(spec["harvest_system_options"], "option_id")
    _index(spec["hand_calculated_cases"], "case_id")
    _index(spec["facilities"], "facility_id")


def test_topm_mini_references_resolve() -> None:
    spec = _load_spec()
    periods = _index(spec["periods"], "period_id")
    products = _index(spec["products"], "product_id")
    blocks = _index(spec["planning_units"], "block_id")
    options = _index(spec["harvest_system_options"], "option_id")
    facilities = _index(spec["facilities"], "facility_id")

    for option in spec["harvest_system_options"]:
        assert option["block_id"] in blocks
        assert option["period_id"] in periods
        assert 0 < option["min_area_ha"] <= option["max_area_ha"]
        assert option["max_area_ha"] <= blocks[option["block_id"]]["operable_area_ha"]

    for demand in spec["facility_demand"]:
        assert demand["facility_id"] in facilities
        assert demand["product_id"] in products
        assert demand["period_id"] in periods
        assert demand["minimum_m3"] <= demand["target_m3"] <= demand["maximum_m3"]

    for arc in spec["transport_arcs"]:
        assert arc["origin_id"] in blocks
        assert arc["destination_id"] in facilities
        assert arc["product_id"] in products
        assert arc["period_id"] in periods

    for case in spec["hand_calculated_cases"]:
        if "option_id" in case:
            assert case["option_id"] in options


def test_topm_mini_hand_calculated_harvest_modes() -> None:
    spec = _load_spec()
    blocks = _index(spec["planning_units"], "block_id")
    options = _index(spec["harvest_system_options"], "option_id")

    for case in spec["hand_calculated_cases"]:
        if case["case_id"] == "economic_dispatch":
            continue
        option = options[case["option_id"]]
        block = blocks[option["block_id"]]
        mode = case["mode"]
        requested = case["requested_area_ha"]
        expected = case["expected"]

        if mode == "whole_block":
            area = block["operable_area_ha"]
            activation = 1
        elif mode == "semi_continuous" and requested < option["min_area_ha"]:
            area = 0.0
            activation = 0
        else:
            area = requested
            activation = 1

        assert activation == expected["activation"]
        assert area == pytest.approx(expected["harvested_area_ha"])
        yields = block["product_yields_m3_per_ha"]
        assert area * yields["sawlog"] == pytest.approx(expected["sawlog_volume_m3"])
        assert area * yields["pulp"] == pytest.approx(expected["pulp_volume_m3"])


def test_topm_mini_economic_dispatch_case() -> None:
    spec = _load_spec()
    blocks = _index(spec["planning_units"], "block_id")
    options = _index(spec["harvest_system_options"], "option_id")
    case = next(
        item for item in spec["hand_calculated_cases"] if item["case_id"] == "economic_dispatch"
    )

    sawlog = 0.0
    fixed = 0.0
    variable = 0.0
    for harvested in case["expected"]["harvested"]:
        option = options[harvested["option_id"]]
        block = blocks[option["block_id"]]
        area = harvested["area_ha"]
        assert option["min_area_ha"] <= area <= option["max_area_ha"]
        total_volume = area * sum(block["product_yields_m3_per_ha"].values())
        sawlog += area * block["product_yields_m3_per_ha"]["sawlog"]
        fixed += option["fixed_cost"]
        variable += total_volume * option["variable_cost_per_m3"]
        sawlog_volume = area * block["product_yields_m3_per_ha"]["sawlog"]
        assert sawlog_volume == pytest.approx(harvested["sawlog_volume_m3"])

    assert sawlog == pytest.approx(case["required_sawlog_m3"])
    assert fixed == pytest.approx(case["expected"]["total_fixed_cost"])
    assert variable == pytest.approx(case["expected"]["total_variable_cost"])
    assert fixed + variable == pytest.approx(case["expected"]["total_cost"])


def test_topm_mini_inventory_balances() -> None:
    spec = _load_spec()
    for expectation in spec["flow_inventory_expectations"]:
        closing = (
            expectation["opening_m3"]
            + expectation["deliveries_m3"]
            + expectation["purchases_m3"]
            - expectation["consumption_m3"]
        )
        assert closing == pytest.approx(expectation["expected_closing_m3"])
