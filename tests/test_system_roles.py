import pyomo.environ as pyo

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
from fhops.scheduling.systems import HarvestSystem, SystemJob


def test_role_constraints_restrict_assignments():
    system = HarvestSystem(
        system_id="forward_only",
        jobs=[SystemJob(name="forward", machine_role="forwarder", prerequisites=[])],
    )
    scenario = Scenario(
        name="role-test",
        num_days=1,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=5.0,
                earliest_start=1,
                latest_finish=1,
                harvest_system_id="forward_only",
            )
        ],
        machines=[
            Machine(id="M1", role="forwarder"),
            Machine(id="M2", role="helicopter"),
        ],
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[
            CalendarEntry(machine_id="M1", day=1, available=1),
            CalendarEntry(machine_id="M2", day=1, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="M1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="M2", block_id="B1", rate=5.0),
        ],
        harvest_systems={"forward_only": system},
    )
    model = build_model(Problem.from_scenario(scenario))
    assert ("M2", "B1", 1) in model.role_filter
    con = model.role_filter["M2", "B1", 1]
    # Constraint should be x[M2,B1,1] == 0
    assert con.lower == 0
    assert con.upper == 0
    assert con.body == model.x["M2", "B1", 1]


def test_sequencing_enforces_prerequisites():
    system = HarvestSystem(
        system_id="ground_sequence",
        jobs=[
            SystemJob(name="felling", machine_role="feller", prerequisites=[]),
            SystemJob(name="processing", machine_role="processor", prerequisites=["felling"]),
        ],
    )
    scenario = Scenario(
        name="seq-test",
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
            Machine(id="M1", role="feller"),
            Machine(id="M2", role="processor"),
        ],
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[
            CalendarEntry(machine_id="M1", day=1, available=1),
            CalendarEntry(machine_id="M2", day=1, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="M1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="M2", block_id="B1", rate=5.0),
        ],
        harvest_systems={"ground_sequence": system},
    )
    model = build_model(Problem.from_scenario(scenario))
    # Activate processor without feller to see constraint reaction
    model.x["M1", "B1", 1].value = 0
    model.x["M2", "B1", 1].value = 1
    assert "processor" in list(model.R)
    expr = model.system_sequencing["B1", "processor", 1].body
    assert pyo.value(expr) > 0
