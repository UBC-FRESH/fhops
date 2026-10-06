"""YAML ``locked_assignments`` are cross-validated by ``load_scenario`` (#100)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from fhops.scenario.contract import Scenario
from fhops.scenario.io import load_scenario

SOURCE = Path("examples/tiny7/scenario.yaml")
TWO_SHIFTS = {
    "shifts": [
        {"name": "S1", "hours": 10.0, "shifts_per_day": 1},
        {"name": "S2", "hours": 10.0, "shifts_per_day": 1},
    ],
    "blackouts": [{"start_day": 6, "end_day": 6, "reason": "holiday"}],
}


def _write(tmp_path: Path, locks: list[dict], *, timeline: dict | None = None) -> Path:
    meta = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    root = SOURCE.parent.resolve()
    meta["data"] = {key: str(root / value) for key, value in meta["data"].items()}
    meta["mobilisation"]["distance_csv"] = str(root / meta["mobilisation"]["distance_csv"])
    meta["locked_assignments"] = locks
    if timeline is not None:
        meta["timeline"] = timeline
    target = tmp_path / "scenario.yaml"
    target.write_text(yaml.safe_dump(meta), encoding="utf-8")
    return target


def test_valid_yaml_locks_load(tmp_path: Path) -> None:
    locks = [
        {"machine_id": "H1", "block_id": "B01", "day": 1},
        {"machine_id": "H2", "block_id": "B02", "day": 2, "shift_id": "S2"},
        {"machine_id": "H2", "block_id": "B01", "day": 2, "shift_id": "S1"},
    ]
    scenario = load_scenario(_write(tmp_path, locks, timeline=TWO_SHIFTS))
    assert [(lk.machine_id, lk.day, lk.shift_id) for lk in scenario.locked_assignments or []] == [
        ("H1", 1, None),
        ("H2", 2, "S2"),
        ("H2", 2, "S1"),
    ]
    # Same result as constructing the scenario in Python.
    rebuilt = Scenario.model_validate(scenario.model_dump())
    assert rebuilt.locked_assignments == scenario.locked_assignments


@pytest.mark.parametrize(
    ("locks", "timeline", "message"),
    [
        ([{"machine_id": "HX", "block_id": "B01", "day": 1}], None, "unknown machine_id=HX"),
        ([{"machine_id": "H1", "block_id": "BX", "day": 1}], None, "unknown block_id=BX"),
        ([{"machine_id": "H1", "block_id": "B01", "day": 0}], None, "outside scenario horizon"),
        ([{"machine_id": "H1", "block_id": "B01", "day": 8}], None, "outside scenario horizon"),
        # Day-indexed scenario: only the synthetic S1 shift exists.
        (
            [{"machine_id": "H1", "block_id": "B01", "day": 1, "shift_id": "S2"}],
            None,
            "unknown shift_id=S2",
        ),
        (
            [{"machine_id": "H1", "block_id": "B01", "day": 1, "shift_id": "NIGHT"}],
            TWO_SHIFTS,
            "unknown shift_id=NIGHT",
        ),
        (
            [
                {"machine_id": "H1", "block_id": "B01", "day": 1},
                {"machine_id": "H1", "block_id": "B02", "day": 1},
            ],
            None,
            "Multiple locked assignments",
        ),
        (
            [
                {"machine_id": "H1", "block_id": "B01", "day": 1, "shift_id": "S1"},
                {"machine_id": "H1", "block_id": "B02", "day": 1, "shift_id": "S1"},
            ],
            TWO_SHIFTS,
            "Multiple locked assignments",
        ),
        (
            [
                {"machine_id": "H1", "block_id": "B01", "day": 1},
                {"machine_id": "H1", "block_id": "B02", "day": 1, "shift_id": "S2"},
            ],
            TWO_SHIFTS,
            "Multiple locked assignments",
        ),
        (
            [{"machine_id": "H1", "block_id": "B01", "day": 6}],
            TWO_SHIFTS,
            "falls within blackout",
        ),
    ],
)
def test_invalid_yaml_locks_rejected(
    tmp_path: Path, locks: list[dict], timeline: dict | None, message: str
) -> None:
    path = _write(tmp_path, locks, timeline=timeline)
    with pytest.raises(ValidationError, match=message):
        load_scenario(path)

    # Model-constructed locks are rejected with the same rule.
    valid = load_scenario(_write(tmp_path, [], timeline=timeline))
    payload = valid.model_dump()
    payload["locked_assignments"] = locks
    with pytest.raises(ValidationError, match=message):
        Scenario.model_validate(payload)


def test_malformed_yaml_lock_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, [{"machine_id": "H1", "block_id": "B01", "day": 1, "shift_id": " "}])
    with pytest.raises(ValidationError, match="non-empty"):
        load_scenario(path)
