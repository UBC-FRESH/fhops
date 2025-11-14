import json

import pandas as pd
import pyomo.environ as pyo
import pytest

from fhops.evaluation.metrics.kpis import compute_kpis
from fhops.optimization.mip.builder import build_model
from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)
from fhops.scheduling.mobilisation import (
    BlockDistance,
    MachineMobilisation,
    MobilisationConfig,
)
from fhops.scheduling.systems import HarvestSystem, SystemJob


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


def build_problem() -> Problem:
    scenario = Scenario(
        name="mobilisation-demo",
        num_days=2,
        blocks=[
            Block(id="B1", landing_id="L1", work_required=10.0, earliest_start=1, latest_finish=2),
            Block(id="B2", landing_id="L1", work_required=10.0, earliest_start=1, latest_finish=2),
        ],
        machines=[Machine(id="M1")],
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[
            CalendarEntry(machine_id="M1", day=1, available=1),
            CalendarEntry(machine_id="M1", day=2, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="M1", block_id="B1", rate=10.0),
            ProductionRate(machine_id="M1", block_id="B2", rate=10.0),
        ],
        mobilisation=MobilisationConfig(
            machine_params=[
                MachineMobilisation(
                    machine_id="M1",
                    walk_cost_per_meter=0.0,
                    move_cost_flat=100.0,
                    walk_threshold_m=1000.0,
                    setup_cost=5.0,
                )
            ],
            distances=[
                BlockDistance(from_block="B1", to_block="B2", distance_m=2000.0),
                BlockDistance(from_block="B2", to_block="B1", distance_m=2000.0),
                BlockDistance(from_block="B1", to_block="B1", distance_m=0.0),
                BlockDistance(from_block="B2", to_block="B2", distance_m=0.0),
            ],
        ),
    )
    return Problem.from_scenario(scenario)


def test_build_model_with_mobilisation_config():
    pb = build_problem()
    model = build_model(pb)
    assert model is not None
    assert hasattr(model, "mach_one_shift")


def test_objective_includes_mobilisation_penalty():
    pb = build_problem()
    model = build_model(pb)

    for var in model.x.values():
        var.value = 0
    for var in model.prod.values():
        var.value = 0
    if hasattr(model, "y"):
        for var in model.y.values():
            var.value = 0

    shift1 = _shift_tuple(pb, 1)
    shift2 = _shift_tuple(pb, 2)
    model.x["M1", "B1", shift1].value = 1
    model.x["M1", "B2", shift2].value = 1
    if hasattr(model, "y"):
        model.y["M1", "B1", "B2", shift2].value = 1

    objective_value = pyo.value(model.obj)
    assert objective_value == -105.0


def test_compute_kpis_reports_mobilisation_cost():
    pb = build_problem()
    model = build_model(pb)

    for var in model.x.values():
        var.value = 0
    model.x["M1", "B1", _shift_tuple(pb, 1)].value = 1
    model.x["M1", "B2", _shift_tuple(pb, 2)].value = 1

    assignments = []
    for mach in model.M:
        for blk in model.B:
            for day, shift_id in model.S:
                if pyo.value(model.x[mach, blk, (day, shift_id)]) > 0.5:
                    assignments.append(
                        {
                            "machine_id": mach,
                            "block_id": blk,
                            "day": int(day),
                            "shift_id": shift_id,
                        }
                    )

    df = pd.DataFrame(assignments)
    kpis = compute_kpis(pb, df)
    assert kpis.get("mobilisation_cost") == 105.0
    per_machine = json.loads(kpis.get("mobilisation_cost_by_machine", "{}"))
    assert per_machine == {"M1": 105.0}
    per_landing = json.loads(kpis.get("mobilisation_cost_by_landing", "{}"))
    assert per_landing == {"L1": 105.0}
    assert kpis.get("makespan_day") == 2
    assert kpis.get("makespan_shift") == "S1"
    assert pytest.approx(kpis.get("utilisation_ratio_mean_shift", 0.0)) == 1.0
    assert pytest.approx(kpis.get("utilisation_ratio_weighted_shift", 0.0)) == 1.0
    assert kpis.get("downtime_hours_total", 0.0) == 0.0


def test_compute_kpis_reports_sequencing_metrics():
    system = HarvestSystem(
        system_id="ground_sequence",
        jobs=[
            SystemJob(name="felling", machine_role="feller", prerequisites=[]),
            SystemJob(name="processing", machine_role="processor", prerequisites=["felling"]),
        ],
    )
    scenario = Scenario(
        name="seq-metrics",
        num_days=1,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=5.0,
                earliest_start=1,
                latest_finish=1,
                harvest_system_id="ground_sequence",
            )
        ],
        machines=[
            Machine(id="F1", role="feller"),
            Machine(id="P1", role="processor"),
        ],
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[
            CalendarEntry(machine_id="F1", day=1, available=1),
            CalendarEntry(machine_id="P1", day=1, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="F1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="P1", block_id="B1", rate=5.0),
        ],
        mobilisation=None,
        harvest_systems={"ground_sequence": system},
    )
    pb = Problem.from_scenario(scenario)
    assignments = pd.DataFrame([{"machine_id": "P1", "block_id": "B1", "day": 1}])
    kpis = compute_kpis(pb, assignments)
    assert kpis.get("sequencing_violation_count") == 1
    assert kpis.get("sequencing_violation_blocks") == 1
    assert kpis.get("sequencing_violation_days") == 1
    assert kpis.get("sequencing_clean_blocks") == 0
    assert str(kpis.get("sequencing_violation_breakdown")).startswith("missing_prereq=1")
