"""Scenario validation of ``Block.harvest_system_id`` against the harvest-system registry (#129)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)
from fhops.scenario.io import load_scenario
from fhops.scheduling.systems import HarvestSystem, SystemJob

REGRESSION_DIR = Path("tests/fixtures/regression")
CUSTOM = HarvestSystem(
    system_id="custom_chain",
    jobs=[
        SystemJob("felling", "feller", []),
        SystemJob("processing", "processor", ["felling"]),
    ],
)


def _scenario(system_id: str | None, harvest_systems: dict | None = None, **extra: object):
    return Scenario(
        name="systems",
        num_days=3,
        blocks=[
            Block(id="B1", landing_id="L1", work_required=10.0),
            Block(id="B2", landing_id="L1", work_required=10.0, harvest_system_id=system_id),
        ],
        machines=[Machine(id="F1", role="feller"), Machine(id="P1", role="processor")],
        landings=[Landing(id="L1", daily_capacity=2)],
        calendar=[
            CalendarEntry(machine_id=m, day=day, available=1)
            for m in ("F1", "P1")
            for day in range(1, 4)
        ],
        production_rates=[
            ProductionRate(machine_id=m, block_id=b, rate=5.0)
            for m in ("F1", "P1")
            for b in ("B1", "B2")
        ],
        harvest_systems=harvest_systems,
        **extra,
    )


@pytest.mark.parametrize("harvest_systems", [None, {}, {"custom_chain": CUSTOM}])
def test_unknown_system_rejected(harvest_systems: dict | None) -> None:
    with pytest.raises(
        ValidationError,
        match=r"Block B2 references unknown harvest_system_id=mystery; define it under "
        r"harvest_systems",
    ):
        _scenario("mystery", harvest_systems)


@pytest.mark.parametrize(
    ("system_id", "harvest_systems"),
    [
        (None, None),
        ("ground_fb_skid", None),
        ("custom_chain", {"custom_chain": CUSTOM}),
        # Custom systems are overlaid on the default registry (as in the solvers), so a default
        # system stays valid when the scenario also defines its own systems.
        ("ground_fb_skid", {"custom_chain": CUSTOM}),
    ],
)
def test_registered_or_missing_system_accepted(
    system_id: str | None, harvest_systems: dict | None
) -> None:
    scenario = _scenario(system_id, harvest_systems)
    assert scenario.blocks[1].harvest_system_id == system_id


def test_check_runs_after_all_fields_are_set() -> None:
    # Pre-#129 the check was a ``blocks`` field validator; ``harvest_systems`` is declared after
    # ``blocks``, so it never saw the systems and never fired. ``model_validate`` follows the same
    # path as the YAML loader.
    payload = _scenario("custom_chain", {"custom_chain": CUSTOM}).model_dump()
    payload["harvest_systems"] = {}
    with pytest.raises(ValidationError, match="unknown harvest_system_id=custom_chain"):
        Scenario.model_validate(payload)


def _copy_regression(tmp_path: Path) -> Path:
    target = tmp_path / "regression"
    shutil.copytree(REGRESSION_DIR, target)
    return target / "regression.yaml"


def test_yaml_unknown_system_rejected(tmp_path: Path) -> None:
    path = _copy_regression(tmp_path)
    meta = yaml.safe_load(path.read_text(encoding="utf-8"))
    del meta["harvest_systems"]
    path.write_text(yaml.safe_dump(meta), encoding="utf-8")
    with pytest.raises(ValidationError, match="unknown harvest_system_id=ground_sequence"):
        load_scenario(path)


def test_yaml_system_file_in_data_section(tmp_path: Path) -> None:
    path = _copy_regression(tmp_path)
    meta = yaml.safe_load(path.read_text(encoding="utf-8"))
    systems = meta.pop("harvest_systems")
    (path.parent / "systems.yaml").write_text(yaml.safe_dump(systems), encoding="utf-8")
    meta["data"]["harvest_systems"] = "systems.yaml"
    path.write_text(yaml.safe_dump(meta), encoding="utf-8")
    scenario = load_scenario(path)
    assert scenario.harvest_systems is not None
    assert set(scenario.harvest_systems) == {"ground_sequence"}


def test_regression_fixture_registers_its_system() -> None:
    scenario = load_scenario(REGRESSION_DIR / "regression.yaml")
    assert {block.harvest_system_id for block in scenario.blocks} == {"ground_sequence"}
    assert scenario.harvest_systems is not None
    system = scenario.harvest_systems["ground_sequence"]
    assert [(job.name, job.machine_role, list(job.prerequisites)) for job in system.jobs] == [
        ("felling", "feller", []),
        ("processing", "processor", ["felling"]),
    ]
