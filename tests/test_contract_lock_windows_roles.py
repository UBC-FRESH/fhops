"""Scenario validation added in 1.0.1 (#118): lock windows/roles and ``role_remaining`` bounds."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
    validate_initial_state,
)
from fhops.scenario.contract.models import ROLE_REMAINING_TOLERANCE
from fhops.scenario.io import load_scenario
from fhops.scheduling.systems import HarvestSystem, SystemJob

SOURCE = Path("examples/tiny7/scenario.yaml")

CHAIN = HarvestSystem(
    system_id="chain",
    jobs=[
        SystemJob("felling", "feller_buncher", []),
        SystemJob("primary_transport", "grapple_skidder", ["felling"]),
    ],
)


def _scenario(**extra: object) -> dict:
    """Two blocks (B1 explicit ``chain`` system, window 2–4; B2 unsequenced), three machines."""

    machines = [
        Machine(id="F1", role="feller_buncher"),
        Machine(id="S1", role="grapple_skidder"),
        Machine(id="P1", role="roadside_processor"),
        Machine(id="X1"),
    ]
    payload = Scenario(
        name="lock-rules",
        num_days=5,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=100.0,
                earliest_start=2,
                latest_finish=4,
                harvest_system_id="chain",
            ),
            Block(id="B2", landing_id="L1", work_required=50.0),
        ],
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=4)],
        calendar=[
            CalendarEntry(machine_id=m.id, day=day, available=1)
            for m in machines
            for day in range(1, 6)
        ],
        production_rates=[
            ProductionRate(machine_id=m.id, block_id=b, rate=20.0)
            for m in machines
            for b in ("B1", "B2")
        ],
        harvest_systems={"chain": CHAIN},
    ).model_dump()
    payload.update(extra)
    return payload


def _lock(machine: str, block: str, day: int, shift: str | None = None) -> dict:
    return {"machine_id": machine, "block_id": block, "day": day, "shift_id": shift}


@pytest.mark.parametrize(
    "locks",
    [
        [_lock("F1", "B1", 2), _lock("S1", "B1", 4)],
        [_lock("F1", "B1", 3, "S1")],
        # Unsequenced blocks (no harvest_system_id) accept any machine, with or without a role.
        [_lock("P1", "B2", 1), _lock("X1", "B2", 5)],
    ],
)
def test_valid_locks_accepted(locks: list[dict]) -> None:
    scenario = Scenario.model_validate(_scenario(locked_assignments=locks))
    assert len(scenario.locked_assignments or []) == len(locks)


@pytest.mark.parametrize(
    ("lock", "message"),
    [
        (_lock("F1", "B1", 1), "on day 1 falls outside block B1 window [2, 4]"),
        (_lock("F1", "B1", 5, "S1"), "on day 5 falls outside block B1 window [2, 4]"),
        (
            _lock("P1", "B1", 3),
            "machine P1 (role processor) on block B1 is incompatible with harvest system chain "
            "(roles: feller_buncher, grapple_skidder)",
        ),
        (_lock("X1", "B1", 3), "machine X1 (no role) on block B1 is incompatible"),
    ],
)
def test_invalid_locks_rejected(lock: dict, message: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Scenario.model_validate(_scenario(locked_assignments=[lock]))
    assert message in str(excinfo.value)


def test_unknown_harvest_system_skips_role_check() -> None:
    payload = _scenario(locked_assignments=[_lock("P1", "B1", 3)])
    payload["blocks"][0]["harvest_system_id"] = "not_registered"
    scenario = Scenario.model_validate(payload)
    assert scenario.locked_assignments is not None


def test_default_registry_system_roles_are_used() -> None:
    payload = _scenario(locked_assignments=[_lock("P1", "B1", 3)], harvest_systems=None)
    payload["blocks"][0]["harvest_system_id"] = "ground_fb_skid"
    assert Scenario.model_validate(payload).locked_assignments is not None
    payload["locked_assignments"] = [_lock("X1", "B1", 3)]
    with pytest.raises(ValidationError, match="incompatible with harvest system ground_fb_skid"):
        Scenario.model_validate(payload)


def _state(remaining: float) -> dict:
    return {"blocks": [{"block_id": "B1", "role_remaining": {"feller_buncher": remaining}}]}


@pytest.mark.parametrize("remaining", [0.0, 60.0, 100.0, 100.0 + 0.5 * ROLE_REMAINING_TOLERANCE])
def test_role_remaining_up_to_work_required_accepted(remaining: float) -> None:
    scenario = Scenario.model_validate(_scenario(initial_state=_state(remaining)))
    validate_initial_state(scenario)


@pytest.mark.parametrize("remaining", [100.0 + 2 * ROLE_REMAINING_TOLERANCE, 150.0])
def test_role_remaining_above_work_required_rejected(remaining: float) -> None:
    with pytest.raises(ValidationError, match=r"role_remaining\['feller_buncher'\]=.* above"):
        Scenario.model_validate(_scenario(initial_state=_state(remaining)))


def _write_tiny7(tmp_path: Path, **updates: object) -> Path:
    meta = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    root = SOURCE.parent.resolve()
    meta["data"] = {key: str(root / value) for key, value in meta["data"].items()}
    meta["mobilisation"]["distance_csv"] = str(root / meta["mobilisation"]["distance_csv"])
    meta.update(updates)
    target = tmp_path / "scenario.yaml"
    target.write_text(yaml.safe_dump(meta), encoding="utf-8")
    return target


def _tiny7_with_window(tmp_path: Path, **updates: object) -> Path:
    blocks = (SOURCE.parent / "data/blocks.csv").read_text(encoding="utf-8")
    narrowed = blocks.replace(
        "B02,L2,ground_fb_skid,2406.789997,1,7", "B02,L2,ground_fb_skid,2406.789997,3,7"
    )
    assert narrowed != blocks
    (tmp_path / "blocks.csv").write_text(narrowed, encoding="utf-8")
    path = _write_tiny7(tmp_path, **updates)
    meta = yaml.safe_load(path.read_text(encoding="utf-8"))
    meta["data"]["blocks"] = str(tmp_path / "blocks.csv")
    path.write_text(yaml.safe_dump(meta), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {"locked_assignments": [{"machine_id": "H1", "block_id": "B02", "day": 2}]},
            "falls outside block B02 window [3, 7]",
        ),
        (
            {"locked_assignments": [{"machine_id": "H7", "block_id": "B01", "day": 2}]},
            None,
        ),
        (
            {
                "initial_state": {
                    "blocks": [{"block_id": "B01", "role_remaining": {"feller_buncher": 2500.0}}]
                }
            },
            "role_remaining['feller_buncher']=2500.0 above the block's work_required",
        ),
    ],
)
def test_yaml_loader_applies_new_rules(tmp_path: Path, updates: dict, message: str | None) -> None:
    path = _tiny7_with_window(tmp_path, **updates)
    if message is None:
        assert load_scenario(path).locked_assignments
        return
    with pytest.raises(ValidationError) as excinfo:
        load_scenario(path)
    assert message in str(excinfo.value)


def test_plan_rolling_fails_at_load_for_out_of_window_lock(tmp_path: Path) -> None:
    path = _tiny7_with_window(
        tmp_path, locked_assignments=[{"machine_id": "H1", "block_id": "B02", "day": 2}]
    )
    result = CliRunner().invoke(
        app,
        [
            "plan",
            "rolling",
            str(path),
            "--master-days",
            "7",
            "--sub-days",
            "7",
            "--lock-days",
            "7",
            "--solver",
            "stub",
        ],
        prog_name="fhops",
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, ValidationError)
    assert "falls outside block B02 window [3, 7]" in str(result.exception)
