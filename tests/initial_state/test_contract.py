"""Contract validation for ``Scenario.initial_state`` and ``ScheduleLock.shift_id`` (#91)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from fhops.model.milp.data import build_operational_bundle, bundle_from_dict, bundle_to_dict
from fhops.scenario.contract import (
    BlockInitialState,
    MachineInitialState,
    Problem,
    Scenario,
    ScenarioInitialState,
    ScheduleLock,
)
from fhops.scenario.io import load_scenario

from ._scenarios import chain_scenario, solo_two_shift_scenario


def _with_state(state: dict) -> Scenario:
    base = chain_scenario()
    return Scenario.model_validate({**base.model_dump(), "initial_state": state})


def test_default_initial_state_is_none() -> None:
    scenario = chain_scenario()
    assert scenario.initial_state is None
    bundle = build_operational_bundle(Problem.from_scenario(scenario))
    assert not bundle.has_initial_state()
    assert bundle.locked_assignments == ()
    payload = bundle_to_dict(bundle)
    assert "initial_state" not in payload
    assert "locked_assignments" not in payload


def test_valid_initial_state_normalises_roles() -> None:
    scenario = _with_state(
        {
            "blocks": [
                {
                    "block_id": "B1",
                    "role_remaining": {"Feller-Buncher": 10.0},
                    "staged_inventory": {"feller_buncher": 30.0},
                    "role_shift_counts": {"grapple skidder": 2},
                }
            ],
            "machines": [{"machine_id": "S1", "last_block_id": "B2"}],
        }
    )
    state = scenario.initial_state
    assert state is not None
    block_state = state.block_state("B1")
    assert block_state is not None
    assert block_state.role_remaining == {"feller_buncher": 10.0}
    assert block_state.role_shift_counts == {"grapple_skidder": 2}
    assert state.last_block_by_machine() == {"S1": "B2"}
    assert state.block_state("B2") is None


@pytest.mark.parametrize(
    ("state", "message"),
    [
        ({"blocks": [{"block_id": "BX"}]}, "unknown block_id=BX"),
        ({"machines": [{"machine_id": "MX"}]}, "unknown machine_id=MX"),
        (
            {"machines": [{"machine_id": "F1", "last_block_id": "BX"}]},
            "unknown last_block_id=BX",
        ),
        (
            {"blocks": [{"block_id": "B1", "staged_inventory": {"feller_buncher": -1.0}}]},
            "must be non-negative",
        ),
        (
            {"blocks": [{"block_id": "B1", "role_shift_counts": {"feller_buncher": -2}}]},
            "must be non-negative",
        ),
        (
            {"blocks": [{"block_id": "B1", "role_remaining": {"loader": 5.0}}]},
            "not roles of harvest system chain",
        ),
        (
            {"blocks": [{"block_id": "B1"}, {"block_id": "B1"}]},
            "more than once",
        ),
        (
            {"machines": [{"machine_id": "F1"}, {"machine_id": "F1"}]},
            "more than once",
        ),
        (
            {
                "blocks": [
                    {
                        "block_id": "B1",
                        "staged_inventory": {"feller_buncher": 1.0, "Feller Buncher": 2.0},
                    }
                ]
            },
            "more than once",
        ),
    ],
)
def test_invalid_initial_state_rejected(state: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _with_state(state)


def test_role_state_requires_harvest_system() -> None:
    base = chain_scenario()
    payload = base.model_dump()
    payload["blocks"][0]["harvest_system_id"] = None
    payload["initial_state"] = {
        "blocks": [{"block_id": "B1", "staged_inventory": {"feller_buncher": 1.0}}]
    }
    with pytest.raises(ValidationError, match="has no harvest_system_id"):
        Scenario.model_validate(payload)
    # Role-free entries are fine for blocks without a harvest system.
    payload["initial_state"] = {"blocks": [{"block_id": "B1"}]}
    assert Scenario.model_validate(payload).initial_state is not None


def test_schedule_lock_shift_validation() -> None:
    base = solo_two_shift_scenario()
    payload = base.model_dump()

    payload["locked_assignments"] = [
        {"machine_id": "F1", "block_id": "B2", "day": 1, "shift_id": "S2"},
        {"machine_id": "F1", "block_id": "B1", "day": 1, "shift_id": "S1"},
    ]
    scenario = Scenario.model_validate(payload)
    assert [lock.shift_id for lock in scenario.locked_assignments or []] == ["S2", "S1"]

    payload["locked_assignments"] = [
        {"machine_id": "F1", "block_id": "B2", "day": 1, "shift_id": "NIGHT"}
    ]
    with pytest.raises(ValidationError, match="unknown shift_id=NIGHT"):
        Scenario.model_validate(payload)

    payload["locked_assignments"] = [
        {"machine_id": "F1", "block_id": "B2", "day": 1, "shift_id": "S2"},
        {"machine_id": "F1", "block_id": "B1", "day": 1, "shift_id": "S2"},
    ]
    with pytest.raises(ValidationError, match="Multiple locked assignments"):
        Scenario.model_validate(payload)

    payload["locked_assignments"] = [
        {"machine_id": "F1", "block_id": "B2", "day": 1},
        {"machine_id": "F1", "block_id": "B1", "day": 1, "shift_id": "S1"},
    ]
    with pytest.raises(ValidationError, match="Multiple locked assignments"):
        Scenario.model_validate(payload)

    with pytest.raises(ValidationError, match="non-empty"):
        ScheduleLock(machine_id="F1", block_id="B1", day=1, shift_id="  ")
    assert ScheduleLock(machine_id="F1", block_id="B1", day=1).shift_id is None


def test_bundle_round_trip_with_state_and_locks() -> None:
    scenario = chain_scenario(
        locked_assignments=[ScheduleLock(machine_id="F1", block_id="B1", day=1)],
        initial_state=ScenarioInitialState(
            blocks=[
                BlockInitialState(
                    block_id="B1",
                    role_remaining={"feller_buncher": 5.0},
                    staged_inventory={"feller_buncher": 30.0},
                    role_shift_counts={"feller_buncher": 3},
                )
            ],
            machines=[MachineInitialState(machine_id="S1", last_block_id="B2")],
        ),
    )
    bundle = build_operational_bundle(Problem.from_scenario(scenario))
    assert bundle.locked_assignments == (("F1", "B1", 1, None),)
    assert bundle.initial_staged_inventory == {("B1", "feller_buncher"): 30.0}
    assert bundle.initial_role_remaining == {("B1", "feller_buncher"): 5.0}
    assert bundle.initial_role_shift_counts == {("B1", "feller_buncher"): 3}
    assert bundle.initial_machine_block == {"S1": "B2"}
    assert bundle_from_dict(bundle_to_dict(bundle)) == bundle


def test_loader_accepts_inline_initial_state(tmp_path: Path) -> None:
    source = Path("examples/tiny7/scenario.yaml")
    meta = yaml.safe_load(source.read_text(encoding="utf-8"))
    root = source.parent.resolve()
    meta["data"] = {key: str(root / value) for key, value in meta["data"].items()}
    meta["mobilisation"]["distance_csv"] = str(root / meta["mobilisation"]["distance_csv"])
    meta["initial_state"] = {
        "blocks": [
            {
                "block_id": "B01",
                "role_remaining": {"feller_buncher": 0.0},
                "staged_inventory": {"feller_buncher": 150.0},
            }
        ],
        "machines": [{"machine_id": "H3", "last_block_id": "B02"}],
    }
    target = tmp_path / "scenario.yaml"
    target.write_text(yaml.safe_dump(meta), encoding="utf-8")
    scenario = load_scenario(target)
    assert scenario.initial_state is not None
    assert scenario.initial_state.last_block_by_machine() == {"H3": "B02"}

    meta["initial_state"]["blocks"][0]["staged_inventory"] = {"helicopter": 1.0}
    target.write_text(yaml.safe_dump(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="not roles of harvest system"):
        load_scenario(target)
