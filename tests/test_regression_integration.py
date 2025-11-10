from pathlib import Path

import pyomo.environ as pyo
import pytest
import yaml

from fhops.cli._utils import resolve_operator_presets
from fhops.evaluation.metrics.kpis import compute_kpis
from fhops.optimization.heuristics import solve_sa, solve_tabu
from fhops.optimization.mip.builder import build_model
from fhops.scenario.contract.models import Problem
from fhops.scenario.io import load_scenario
from fhops.scheduling.mobilisation import (
    BlockDistance,
    MachineMobilisation,
    MobilisationConfig,
)
from fhops.scheduling.systems import HarvestSystem, SystemJob

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "regression"
SCENARIO_PATH = FIXTURE_DIR / "regression.yaml"
BASELINE_PATH = FIXTURE_DIR / "baseline.yaml"

with BASELINE_PATH.open("r", encoding="utf-8") as handle:
    BASELINE = yaml.safe_load(handle)

REFERENCE_ASSIGNMENTS = [
    {
        "machine_id": entry["machine_id"],
        "block_id": entry["block_id"],
        "day": int(entry["day"]),
        "shift_id": entry.get("shift_id"),
        "assigned": entry.get("assigned", 1),
    }
    for entry in BASELINE["reference_assignments"]
]


def _shift_tuple(pb: Problem, day: int, shift_id: str | None = None) -> tuple[int, str]:
    candidates = [shift for shift in pb.shifts if shift.day == day]
    if not candidates:
        raise KeyError(f"No shift defined for day={day}")
    if shift_id is None:
        return (candidates[0].day, candidates[0].shift_id)
    for shift in candidates:
        if shift.shift_id == shift_id:
            return (shift.day, shift.shift_id)
    raise KeyError(f"Shift {shift_id!r} not found for day={day}")


def regression_problem() -> Problem:
    scenario = load_scenario(SCENARIO_PATH)
    mobilisation = MobilisationConfig(
        machine_params=[
            MachineMobilisation(
                machine_id="F1",
                walk_cost_per_meter=0.01,
                move_cost_flat=5.0,
                walk_threshold_m=100.0,
                setup_cost=1.0,
            ),
            MachineMobilisation(
                machine_id="P1",
                walk_cost_per_meter=0.02,
                move_cost_flat=6.0,
                walk_threshold_m=100.0,
                setup_cost=1.5,
            ),
        ],
        distances=[
            BlockDistance(from_block="B1", to_block="B1", distance_m=0.0),
            BlockDistance(from_block="B2", to_block="B2", distance_m=0.0),
            BlockDistance(from_block="B1", to_block="B2", distance_m=500.0),
            BlockDistance(from_block="B2", to_block="B1", distance_m=500.0),
        ],
    )
    harvest_system = HarvestSystem(
        system_id="ground_sequence",
        jobs=[
            SystemJob(name="felling", machine_role="feller", prerequisites=[]),
            SystemJob(name="processing", machine_role="processor", prerequisites=["felling"]),
        ],
    )
    scenario = scenario.model_copy(
        update={
            "mobilisation": mobilisation,
            "harvest_systems": {"ground_sequence": harvest_system},
        }
    )
    return Problem.from_scenario(scenario)


def test_regression_sa_mobilisation_and_sequencing():
    """Simulated annealing should yield a mobilisation-aware, sequence-feasible schedule."""
    pb = regression_problem()
    res = solve_sa(pb, iters=2000, seed=123)
    assignments = res["assignments"]
    assert "shift_id" in assignments.columns
    assert not assignments["shift_id"].isna().any()
    assert "operators_stats" in res.get("meta", {})
    kpis = compute_kpis(pb, assignments)

    assert kpis["sequencing_violation_count"] == 0
    assert kpis["sequencing_violation_breakdown"] == "none"
    assert kpis["mobilisation_cost"] == pytest.approx(BASELINE["sa_expected"]["mobilisation_cost"])
    assert res["objective"] == pytest.approx(BASELINE["sa_expected"]["objective"])
    assert kpis["total_production"] == pytest.approx(BASELINE["sa_expected"]["total_production"])


@pytest.mark.parametrize("preset", ["explore", "mobilisation", "stabilise"])
def test_regression_sa_presets_preserve_objective(preset: str):
    """Advanced presets should not worsen the regression objective."""
    pb = regression_problem()
    _, preset_weights = resolve_operator_presets([preset])
    res = solve_sa(pb, iters=2000, seed=123, operator_weights=preset_weights)
    assert "operators_stats" in res.get("meta", {})
    baseline_obj = BASELINE["sa_expected"]["objective"]
    assert res["objective"] >= baseline_obj - 1e-9


def test_regression_tabu_scenario_feasible():
    """Tabu Search should produce a feasible schedule for the regression scenario."""
    pb = regression_problem()
    res = solve_tabu(pb, iters=500, seed=42, stall_limit=200)
    assignments = res["assignments"]
    assert not assignments.empty
    kpis = compute_kpis(pb, assignments)
    assert kpis["sequencing_violation_count"] == 0
    assert "mobilisation_cost" in kpis
    assert pytest.approx(BASELINE["sa_expected"]["objective"], abs=1e-2) == res["objective"]


def test_regression_mip_sequencing_constraints_accept_reference_plan():
    """Reference assignments should satisfy role filters and sequencing constraints."""
    pb = regression_problem()
    model = build_model(pb)

    for var in model.x.values():
        var.value = 0

    for entry in REFERENCE_ASSIGNMENTS:
        machine = entry["machine_id"]
        block = entry["block_id"]
        day = entry["day"]
        shift_id = entry.get("shift_id")
        assigned = entry["assigned"]
        shift_key = _shift_tuple(pb, day, shift_id)
        model.x[machine, block, shift_key].value = assigned

    if hasattr(model, "system_sequencing_index"):
        for key, con in model.system_sequencing.items():
            if not con.active:
                continue
            body = pyo.value(con.body)
            upper = con.upper if con.upper is not None else float("inf")
            assert body <= upper + 1e-6, f"Constraint violated for {key}"

    for entry in REFERENCE_ASSIGNMENTS:
        machine = entry["machine_id"]
        block = entry["block_id"]
        day = entry["day"]
        shift_id = entry.get("shift_id")
        shift_key = _shift_tuple(pb, day, shift_id)
        con_key = (machine, block) + shift_key
        if con_key in model.role_filter:
            con = model.role_filter[con_key]
            assert pyo.value(con.body) == 0
