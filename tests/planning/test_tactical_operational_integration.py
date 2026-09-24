"""Tests for tactical→operational handoff and rolling-state helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.model.milp.tactical_operational import (
    build_tactical_operational_bundle,
    solve_tactical_operational_milp,
)
from fhops.planning.tactical_operational.integration import (
    apply_operational_realization,
    build_tactical_rolling_state,
    commitments_from_result,
    compile_business_window_scenario,
    write_operational_scenario_bundle,
)
from fhops.planning.tactical_operational.io import load_tactical_operational_scenario
from fhops.scenario.io import load_scenario

TOPM_MINI = Path("tests/fixtures/tactical_operational/topm-mini/specification.yaml")
TINY7 = Path("examples/tiny7/scenario.yaml")


def _solve_topm() -> dict:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    return solve_tactical_operational_milp(
        build_tactical_operational_bundle(scenario), solver="highs", time_limit=30
    )


def test_commitments_and_rolling_state() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    result = _solve_topm()
    commitments = commitments_from_result(result)
    state = build_tactical_rolling_state(scenario, result)

    assert {item.block_id for item in commitments} == {"B1", "B2"}
    assert state.remaining_area_ha["B1"] == pytest.approx(4.0)
    assert state.remaining_area_ha["B2"] == pytest.approx(3.2222222222)
    assert state.facility_inventory_m3[("mill_saw", "sawlog")] == pytest.approx(0.0)
    assert state.cumulative_costs["total_cost"] == pytest.approx(24130.0)


def test_compile_tactical_commitments_to_tiny7_bundle(tmp_path: Path) -> None:
    result = _solve_topm()
    commitments = commitments_from_result(result)
    base = load_scenario(TINY7)
    compiled = compile_business_window_scenario(
        base,
        commitments,
        block_map={"B1": "B01", "B2": "B02"},
        start_day=1,
        horizon_days=7,
    )

    assert [block.id for block in compiled.blocks] == ["B01", "B02"]
    assert all(block.harvest_system_id == "ground_fb_skid" for block in compiled.blocks)
    assert {rate.block_id for rate in compiled.production_rates} == {"B01", "B02"}

    bundle_path = write_operational_scenario_bundle(compiled, tmp_path / "compiled")
    loaded = load_scenario(bundle_path)
    assert [block.id for block in loaded.blocks] == ["B01", "B02"]


def test_apply_operational_realization_updates_remaining_state() -> None:
    scenario = load_tactical_operational_scenario(TOPM_MINI)
    state = build_tactical_rolling_state(scenario, _solve_topm())
    assignments = pd.DataFrame(
        [{"machine_id": "H1", "block_id": "B01", "day": 1, "production": 100.0}]
    )
    apply_operational_realization(
        state,
        assignments,
        yield_per_ha={"B01": 100.0},
        block_map={"B01": "B1"},
    )

    assert state.remaining_area_ha["B1"] == pytest.approx(3.0)
    assert state.remaining_product_volume_m3[("B1", "sawlog")] == pytest.approx(240.0)
    assert state.remaining_product_volume_m3[("B1", "pulp")] == pytest.approx(60.0)


def test_compile_tactical_cli(tmp_path: Path) -> None:
    result = _solve_topm()
    serializable = dict(result)
    for key, value in list(serializable.items()):
        if isinstance(value, pd.DataFrame):
            serializable[key] = value.to_dict("records")
    result_path = tmp_path / "tactical-result.json"
    result_path.write_text(json.dumps(serializable), encoding="utf-8")
    out_dir = tmp_path / "compiled"

    cli_result = CliRunner().invoke(
        app,
        [
            "plan",
            "compile-tactical",
            str(result_path),
            str(TINY7),
            "--block-map",
            "B1=B01",
            "--block-map",
            "B2=B02",
            "--horizon-days",
            "7",
            "--out-dir",
            str(out_dir),
        ],
        prog_name="fhops",
    )

    assert cli_result.exit_code == 0
    loaded = load_scenario(out_dir / "scenario.yaml")
    assert [block.id for block in loaded.blocks] == ["B01", "B02"]
