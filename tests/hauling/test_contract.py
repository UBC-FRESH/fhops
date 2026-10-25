"""Contract tests for the optional hauling extension."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from fhops.hauling import (
    Contractor,
    ContractorBlock,
    Depot,
    DepotLeg,
    DriverPolicy,
    HaulArc,
    HaulingConfig,
    HaulingDemand,
    HaulingSupply,
    LoaderLocation,
    LoaderLocationKind,
    LogSort,
    SortYard,
    Truck,
    TruckType,
)
from fhops.scenario.contract.models import (
    SUPPORTED_SCHEMA_VERSIONS,
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)
from fhops.scenario.io import load_scenario


def _core_scenario(**updates: object) -> Scenario:
    payload: dict[str, object] = {
        "name": "hauling-contract",
        "num_days": 5,
        "schema_version": "1.1.0",
        "blocks": [
            Block(id="b1", landing_id="l1", work_required=100.0),
            Block(id="b2", landing_id="l1", work_required=100.0),
        ],
        "machines": [
            Machine(id="loader_b1", role="loader"),
            Machine(id="loader_y1", role="loader"),
        ],
        "landings": [Landing(id="l1", daily_capacity=2)],
        "calendar": [
            CalendarEntry(machine_id="loader_b1", day=day, available=1) for day in range(1, 6)
        ]
        + [CalendarEntry(machine_id="loader_y1", day=day, available=1) for day in range(1, 6)],
        "production_rates": [ProductionRate(machine_id="loader_b1", block_id="b1", rate=100.0)],
    }
    payload.update(updates)
    return Scenario(**payload)


def _config(**updates: object) -> HaulingConfig:
    payload: dict[str, object] = {
        "planning_horizon_days": 5,
        "start_day": 1,
        "log_sorts": [LogSort(id="saw", sorted=True)],
        "contractors": [Contractor(id="c1", preferred_daily_truckloads=2)],
        "truck_types": [
            TruckType(
                id="highway",
                capacity_m3=45.0,
                fixed_cost=100.0,
                variable_cost_per_minute=1.0,
                overtime_cost_per_minute=2.0,
            )
        ],
        "trucks": [Truck(id="c1_h1", contractor_id="c1", truck_type_id="highway")],
        "depots": [Depot(id="depot")],
        "sort_yards": [
            SortYard(
                id="y1",
                unsorted_storage_m3=1000.0,
                sorted_processing_m3_per_day=500.0,
                unsorted_processing_m3_per_day=300.0,
                total_processing_m3_per_day=600.0,
            )
        ],
        "depot_legs": [
            DepotLeg(
                depot_id="depot",
                location_id="b1",
                truck_type_id="highway",
                travel_minutes=20.0,
            ),
            DepotLeg(
                depot_id="depot",
                location_id="y1",
                truck_type_id="highway",
                travel_minutes=20.0,
            ),
        ],
        "loader_locations": [
            LoaderLocation(
                loader_id="loader_b1",
                location_id="b1",
                location_kind=LoaderLocationKind.PICKUP,
            ),
            LoaderLocation(
                loader_id="loader_y1",
                location_id="y1",
                location_kind=LoaderLocationKind.DELIVERY,
            ),
        ],
        "supply": [HaulingSupply(block_id="b1", log_sort_id="saw", sorted_m3=100.0)],
        "demand": [HaulingDemand(yard_id="y1", log_sort_id="saw", day=1, volume_m3=20.0)],
        "haul_arcs": [
            HaulArc(
                block_id="b1",
                yard_id="y1",
                truck_type_id="highway",
                travel_minutes=150.0,
            )
        ],
        "contractor_blocks": [ContractorBlock(contractor_id="c1", block_id="b1")],
        "driver_policy": DriverPolicy(
            regular_minutes=510.0,
            max_overtime_minutes=150.0,
        ),
    }
    payload.update(updates)
    return HaulingConfig(**payload)


def test_supported_schema_versions_include_the_hauling_bump() -> None:
    assert SUPPORTED_SCHEMA_VERSIONS == frozenset({"1.0.0", "1.1.0"})


def test_valid_hauling_scenario_builds() -> None:
    scenario = _core_scenario(hauling=_config())
    assert scenario.hauling is not None
    assert scenario.hauling.log_sort_ids() == {"saw"}
    assert scenario.hauling.trucks_for("c1", "highway")[0].id == "c1_h1"
    assert scenario.hauling.contractor_can_serve_block("c1", "b1")
    assert not scenario.hauling.contractor_can_serve_block("c1", "b2")


def test_hauling_requires_schema_1_1_0() -> None:
    with pytest.raises(ValidationError, match="requires schema_version=1.1.0"):
        _core_scenario(schema_version="1.0.0", hauling=_config())


def test_legacy_scenario_still_loads_without_hauling() -> None:
    scenario = load_scenario(Path("tests/data/minimal/scenario.yaml"))
    assert scenario.schema_version == "1.0.0"
    assert scenario.hauling is None


def test_hauling_round_trips_through_the_loader(tmp_path: Path) -> None:
    source = Path("tests/data/minimal")
    for name in (
        "blocks.csv",
        "machines.csv",
        "landings.csv",
        "calendar.csv",
        "production_rates.csv",
    ):
        (tmp_path / name).write_text((source / name).read_text())
    scenario_payload = yaml.safe_load((source / "scenario.yaml").read_text())
    scenario_payload["schema_version"] = "1.1.0"
    scenario_payload["num_days"] = 5
    (tmp_path / "scenario.yaml").write_text(yaml.safe_dump(scenario_payload))
    # The minimal bundle uses one block and one machine; extend the CSVs to match the helper.
    (tmp_path / "blocks.csv").write_text("id,landing_id,work_required\nb1,l1,100\nb2,l1,100\n")
    (tmp_path / "machines.csv").write_text("id,role\nloader_b1,loader\nloader_y1,loader\n")
    (tmp_path / "landings.csv").write_text("id,daily_capacity\nl1,2\n")
    (tmp_path / "calendar.csv").write_text(
        "machine_id,day,available\n"
        + "".join(
            f"{machine},{day},1\n" for machine in ("loader_b1", "loader_y1") for day in range(1, 6)
        )
    )
    (tmp_path / "production_rates.csv").write_text("machine_id,block_id,rate\nloader_b1,b1,100\n")
    payload = yaml.safe_load((tmp_path / "scenario.yaml").read_text())
    payload["hauling"] = _config().model_dump(mode="json")
    (tmp_path / "scenario.yaml").write_text(yaml.safe_dump(payload))

    scenario = load_scenario(tmp_path / "scenario.yaml")
    assert scenario.schema_version == "1.1.0"
    assert scenario.hauling is not None
    assert scenario.hauling.yard_ids() == {"y1"}


def test_unknown_supply_block_rejected_by_scenario() -> None:
    with pytest.raises(ValidationError, match="unknown block_id=missing"):
        _core_scenario(
            hauling=_config(
                supply=[HaulingSupply(block_id="missing", log_sort_id="saw", sorted_m3=10.0)]
            )
        )


def test_unknown_truck_contractor_is_rejected() -> None:
    with pytest.raises(ValidationError, match="references unknown contractor_id=missing"):
        _config(trucks=[Truck(id="t1", contractor_id="missing", truck_type_id="highway")])


def test_unknown_loader_machine_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown machine_id=missing"):
        _core_scenario(
            hauling=_config(
                loader_locations=[
                    LoaderLocation(
                        loader_id="missing",
                        location_id="b1",
                        location_kind=LoaderLocationKind.PICKUP,
                    )
                ]
            )
        )


def test_horizon_must_fit_the_parent_scenario() -> None:
    with pytest.raises(ValidationError, match="exceeds scenario num_days=5"):
        _core_scenario(hauling=_config(start_day=2, planning_horizon_days=5))


def test_duplicate_log_sort_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Duplicate log sort id=saw"):
        _config(log_sorts=[LogSort(id="saw"), LogSort(id="saw")])


def test_truck_type_must_carry_something() -> None:
    with pytest.raises(ValidationError, match="must be able to carry sorted or unsorted"):
        TruckType(
            id="bad",
            capacity_m3=10.0,
            can_carry_sorted=False,
            can_carry_unsorted=False,
        )


def test_total_processing_capacity_covers_components() -> None:
    with pytest.raises(ValidationError, match="must be >= each component capacity"):
        SortYard(
            id="y1",
            sorted_processing_m3_per_day=500.0,
            unsorted_processing_m3_per_day=300.0,
            total_processing_m3_per_day=400.0,
        )


def test_delivery_loader_must_point_at_a_yard() -> None:
    with pytest.raises(ValidationError, match="points at unknown yard"):
        _config(
            loader_locations=[
                LoaderLocation(
                    loader_id="loader_b1",
                    location_id="b1",
                    location_kind=LoaderLocationKind.DELIVERY,
                )
            ]
        )


def test_hauling_requires_a_truck_depot_and_arc() -> None:
    with pytest.raises(ValidationError, match="requires at least one truck"):
        _config(trucks=[])
    with pytest.raises(ValidationError, match="requires at least one depot"):
        _config(depots=[])
    with pytest.raises(ValidationError, match="requires at least one haul arc"):
        _config(haul_arcs=[])


def test_contractor_allowlist_is_optional() -> None:
    config = _config(contractor_blocks=[])
    assert config.contractor_can_serve_block("c1", "b2")


def test_demand_day_must_fit_the_hauling_horizon() -> None:
    with pytest.raises(ValidationError, match="exceeds planning_horizon_days=5"):
        _config(demand=[HaulingDemand(yard_id="y1", log_sort_id="saw", day=6, volume_m3=10.0)])


def test_hauling_can_be_a_separate_yaml_file(tmp_path: Path) -> None:
    source = Path("tests/data/minimal")
    for name in (
        "blocks.csv",
        "machines.csv",
        "landings.csv",
        "calendar.csv",
        "production_rates.csv",
    ):
        (tmp_path / name).write_text((source / name).read_text())
    (tmp_path / "blocks.csv").write_text("id,landing_id,work_required\nb1,l1,100\nb2,l1,100\n")
    (tmp_path / "machines.csv").write_text("id,role\nloader_b1,loader\nloader_y1,loader\n")
    (tmp_path / "landings.csv").write_text("id,daily_capacity\nl1,2\n")
    (tmp_path / "calendar.csv").write_text(
        "machine_id,day,available\n"
        + "".join(
            f"{machine},{day},1\n" for machine in ("loader_b1", "loader_y1") for day in range(1, 6)
        )
    )
    (tmp_path / "production_rates.csv").write_text("machine_id,block_id,rate\nloader_b1,b1,100\n")
    payload = yaml.safe_load((source / "scenario.yaml").read_text())
    payload["schema_version"] = "1.1.0"
    payload["num_days"] = 5
    payload["data"]["hauling"] = "hauling.yaml"
    (tmp_path / "scenario.yaml").write_text(yaml.safe_dump(payload))
    (tmp_path / "hauling.yaml").write_text(yaml.safe_dump(_config().model_dump(mode="json")))

    scenario = load_scenario(tmp_path / "scenario.yaml")
    assert scenario.hauling is not None
    assert scenario.hauling.planning_horizon_days == 5


def test_haul_arc_empty_return_defaults_to_loaded_time() -> None:
    arc = HaulArc(
        block_id="b1",
        yard_id="y1",
        truck_type_id="highway",
        travel_minutes=120.0,
    )
    assert arc.empty_travel_minutes() == 120.0
    faster_empty = arc.model_copy(update={"return_travel_minutes": 90.0})
    assert faster_empty.empty_travel_minutes() == 90.0
