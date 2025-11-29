from fhops.optimization.heuristics import common
from fhops.optimization.heuristics.common import Schedule
from fhops.optimization.operational_problem import build_operational_problem
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


def _build_problem() -> Problem:
    system = HarvestSystem(
        system_id="ground_seq",
        jobs=[
            SystemJob("fell", "feller_buncher", []),
            SystemJob("process", "roadside_processor", ["fell"]),
            SystemJob("load", "loader", ["process"]),
        ],
        role_headstart_shifts={"roadside_processor": 1.0, "loader": 1.0},
    )
    scenario = Scenario(
        name="repair-test",
        num_days=3,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=90.0,
                earliest_start=1,
                latest_finish=3,
                harvest_system_id="ground_seq",
            )
        ],
        machines=[
            Machine(id="F1", role="feller_buncher"),
            Machine(id="P1", role="roadside_processor"),
            Machine(id="L1", role="loader"),
        ],
        landings=[Landing(id="L1", daily_capacity=3)],
        calendar=[
            CalendarEntry(machine_id=machine_id, day=day, available=1)
            for machine_id in ("F1", "P1", "L1")
            for day in (1, 2, 3)
        ],
        production_rates=[
            ProductionRate(machine_id="F1", block_id="B1", rate=30.0),
            ProductionRate(machine_id="P1", block_id="B1", rate=30.0),
            ProductionRate(machine_id="L1", block_id="B1", rate=30.0),
        ],
        harvest_systems={"ground_seq": system},
    )
    return Problem.from_scenario(scenario)


def test_repair_defers_downstream_roles_until_prereqs_completed():
    pb = _build_problem()
    ctx = build_operational_problem(pb)
    shift_keys = [(shift.day, shift.shift_id) for shift in pb.shifts]
    plan = {
        machine.id: {key: None for key in shift_keys}
        for machine in pb.scenario.machines
    }
    schedule = Schedule(plan=plan)

    common._repair_schedule_cover_blocks(pb, schedule, ctx)

    shift_id = pb.shifts[0].shift_id
    assert schedule.plan["F1"][(1, shift_id)] == "B1"
    assert schedule.plan["P1"][(1, shift_id)] is None
    assert schedule.plan["P1"][(2, shift_id)] == "B1"
    assert schedule.plan["L1"][(2, shift_id)] is None
    assert schedule.plan["L1"][(3, shift_id)] == "B1"
