from pathlib import Path

import pyomo.environ as pyo
import pytest
import yaml

from fhops.evaluation.metrics.kpis import compute_kpis
from fhops.optimization.heuristics import solve_sa
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

REFERENCE_ASSIGNMENTS = {
    (entry["machine_id"], entry["block_id"], int(entry["day"])): entry.get("assigned", 1)
    for entry in BASELINE["reference_assignments"]
}


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
        update={"mobilisation": mobilisation, "harvest_systems": {"ground_sequence": harvest_system}}
    )
    return Problem.from_scenario(scenario)


def test_regression_sa_mobilisation_and_sequencing():
    """Simulated annealing should yield a mobilisation-aware, sequence-feasible schedule."""
    pb = regression_problem()
    res = solve_sa(pb, iters=2000, seed=123)
    assignments = res["assignments"]
    kpis = compute_kpis(pb, assignments)

    assert kpis["sequencing_violation_count"] == 0
    assert kpis["sequencing_violation_breakdown"] == "none"
    assert kpis["mobilisation_cost"] == pytest.approx(BASELINE["sa_expected"]["mobilisation_cost"])
    assert res["objective"] == pytest.approx(BASELINE["sa_expected"]["objective"])
    assert kpis["total_production"] == pytest.approx(BASELINE["sa_expected"]["total_production"])


def test_regression_mip_sequencing_constraints_accept_reference_plan():
    """Reference assignments should satisfy role filters and sequencing constraints."""
    pb = regression_problem()
    model = build_model(pb)

    for var in model.x.values():
        var.value = 0

    for key, value in REFERENCE_ASSIGNMENTS.items():
        model.x[key].value = value

    if hasattr(model, "system_sequencing_index"):
        for idx in model.system_sequencing_index:
            blk, role, prereq = idx
            for day in model.D:
                key = idx + (day,)
                if key not in model.system_sequencing:
                    continue
                con = model.system_sequencing[key]
                body = pyo.value(con.body)
                upper = con.upper if con.upper is not None else float("inf")
                assert body <= upper + 1e-6, f"Constraint violated for {(blk, role, prereq, day)}"

    for key in REFERENCE_ASSIGNMENTS:
        if key in model.role_filter:
            con = model.role_filter[key]
            assert pyo.value(con.body) == 0
