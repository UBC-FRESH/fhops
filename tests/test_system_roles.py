import pyomo.environ as pyo

from fhops.optimization.heuristics.common import Schedule, evaluate_schedule
from fhops.optimization.mip.builder import build_model
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


def _shift_key(pb: Problem, day: int, shift_id: str | None = None) -> tuple[int, str]:
    matches = [shift for shift in pb.shifts if shift.day == day]
    if not matches:
        raise KeyError(f"No shift found for day={day}")
    if shift_id is None:
        selected = matches[0]
        return (selected.day, selected.shift_id)
    for shift in matches:
        if shift.shift_id == shift_id:
            return (shift.day, shift.shift_id)
    raise KeyError(f"Shift {shift_id!r} not found for day={day}")


def _plan_from_days(pb: Problem, mapping: dict[str, dict[int, str | None]]) -> dict:
    return {
        machine: {_shift_key(pb, day): block for day, block in day_map.items()}
        for machine, day_map in mapping.items()
    }


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
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)
    shift_key = _shift_key(pb, 1)
    assert ("M2", "B1") + shift_key in model.role_filter
    con = model.role_filter["M2", "B1", *shift_key]
    # Constraint should be x[M2,B1,1] == 0
    assert con.lower == 0
    assert con.upper == 0
    assert con.body == model.x["M2", "B1", shift_key]


def test_role_normalisation_matches_machine_and_job():
    system = HarvestSystem(
        system_id="fb_system",
        jobs=[SystemJob(name="felling", machine_role="feller-buncher", prerequisites=[])],
    )
    scenario = Scenario(
        name="role-normalise",
        num_days=1,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=5.0,
                earliest_start=1,
                latest_finish=1,
                harvest_system_id="fb_system",
            )
        ],
        machines=[Machine(id="M1", role="feller_buncher")],
        landings=[Landing(id="L1", daily_capacity=1)],
        calendar=[CalendarEntry(machine_id="M1", day=1, available=1)],
        production_rates=[ProductionRate(machine_id="M1", block_id="B1", rate=5.0)],
        harvest_systems={"fb_system": system},
    )
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)
    shift_key = _shift_key(pb, 1)
    assert ("M1", "B1", *shift_key) not in model.role_filter


def test_sequencing_blocks_without_prior_work():
    system = HarvestSystem(
        system_id="ground_sequence",
        jobs=[
            SystemJob(name="felling", machine_role="feller", prerequisites=[]),
            SystemJob(name="processing", machine_role="processor", prerequisites=["felling"]),
        ],
    )
    scenario = Scenario(
        name="seq-test-blocking",
        num_days=2,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=10.0,
                earliest_start=1,
                latest_finish=2,
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
            CalendarEntry(machine_id="M1", day=2, available=1),
            CalendarEntry(machine_id="M2", day=2, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="M1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="M2", block_id="B1", rate=5.0),
        ],
        harvest_systems={"ground_sequence": system},
    )
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)
    shift_key = _shift_key(pb, 1)
    for var in model.x.values():
        var.value = 0
    model.x["M2", "B1", shift_key].value = 1
    con = model.system_sequencing["B1", "processor", "feller", *shift_key]
    lhs = pyo.value(con.body)
    rhs = pyo.value(con.upper)
    assert lhs > rhs


def test_sequencing_allows_roles_after_prereqs_complete():
    system = HarvestSystem(
        system_id="ground_sequence",
        jobs=[
            SystemJob(name="felling", machine_role="feller", prerequisites=[]),
            SystemJob(name="processing", machine_role="processor", prerequisites=["felling"]),
        ],
    )
    scenario = Scenario(
        name="seq-test-allow",
        num_days=2,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=10.0,
                earliest_start=1,
                latest_finish=2,
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
            CalendarEntry(machine_id="M2", day=2, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="M1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="M2", block_id="B1", rate=5.0),
        ],
        harvest_systems={"ground_sequence": system},
    )
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)
    fel_shift = _shift_key(pb, 1)
    proc_shift = _shift_key(pb, 2)
    for var in model.x.values():
        var.value = 0
    model.x["M1", "B1", fel_shift].value = 1
    model.x["M2", "B1", proc_shift].value = 1
    con = model.system_sequencing["B1", "processor", "feller", *proc_shift]
    lhs = pyo.value(con.body)
    rhs = pyo.value(con.upper)
    assert lhs <= rhs


def test_sa_evaluator_penalises_out_of_order_assignments():
    system = HarvestSystem(
        system_id="ground_sequence",
        jobs=[
            SystemJob(name="felling", machine_role="feller", prerequisites=[]),
            SystemJob(name="processing", machine_role="processor", prerequisites=["felling"]),
        ],
    )
    scenario = Scenario(
        name="heuristic-seq",
        num_days=2,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=10.0,
                earliest_start=1,
                latest_finish=2,
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
            CalendarEntry(machine_id="F1", day=2, available=1),
            CalendarEntry(machine_id="P1", day=2, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="F1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="P1", block_id="B1", rate=5.0),
        ],
        harvest_systems={"ground_sequence": system},
    )
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)

    bad_plan = Schedule(
        plan=_plan_from_days(
            pb,
            {
                "F1": {1: None, 2: "B1"},
                "P1": {1: "B1", 2: None},
            },
        )
    )
    good_plan = Schedule(
        plan=_plan_from_days(
            pb,
            {
                "F1": {1: "B1", 2: None},
                "P1": {1: None, 2: "B1"},
            },
        )
    )
    bad_score = evaluate_schedule(pb, bad_plan, ctx)
    good_score = evaluate_schedule(pb, good_plan, ctx)
    assert bad_score < good_score


def test_cable_system_enforces_multi_stage_sequence():
    system = HarvestSystem(
        system_id="cable_sequence",
        jobs=[
            SystemJob(name="falling", machine_role="faller", prerequisites=[]),
            SystemJob(name="yarding", machine_role="yarder", prerequisites=["falling"]),
            SystemJob(name="processing", machine_role="processor", prerequisites=["yarding"]),
        ],
    )
    scenario = Scenario(
        name="cable-seq",
        num_days=3,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=15.0,
                earliest_start=1,
                latest_finish=3,
                harvest_system_id="cable_sequence",
            )
        ],
        machines=[
            Machine(id="F1", role="faller"),
            Machine(id="Y1", role="yarder"),
            Machine(id="P1", role="processor"),
        ],
        landings=[Landing(id="L1", daily_capacity=2)],
        calendar=[
            CalendarEntry(machine_id="F1", day=1, available=1),
            CalendarEntry(machine_id="Y1", day=1, available=1),
            CalendarEntry(machine_id="P1", day=1, available=1),
            CalendarEntry(machine_id="F1", day=2, available=1),
            CalendarEntry(machine_id="Y1", day=2, available=1),
            CalendarEntry(machine_id="P1", day=2, available=1),
            CalendarEntry(machine_id="F1", day=3, available=1),
            CalendarEntry(machine_id="Y1", day=3, available=1),
            CalendarEntry(machine_id="P1", day=3, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="F1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="Y1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="P1", block_id="B1", rate=5.0),
        ],
        harvest_systems={"cable_sequence": system},
    )
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)
    for var in model.x.values():
        var.value = 0
    shift1 = _shift_key(pb, 1)
    shift2 = _shift_key(pb, 2)
    shift3 = _shift_key(pb, 3)
    model.x["Y1", "B1", shift1].value = 1
    con = model.system_sequencing["B1", "yarder", "faller", *shift1]
    assert pyo.value(con.body) > pyo.value(con.upper)

    for var in model.x.values():
        var.value = 0
    model.x["F1", "B1", shift1].value = 1
    model.x["Y1", "B1", shift2].value = 1
    con = model.system_sequencing["B1", "yarder", "faller", *shift2]
    assert pyo.value(con.body) <= pyo.value(con.upper)
    model.x["P1", "B1", shift3].value = 1
    con = model.system_sequencing["B1", "processor", "yarder", *shift3]
    assert pyo.value(con.body) <= pyo.value(con.upper)


def test_helicopter_system_requires_all_prerequisites():
    system = HarvestSystem(
        system_id="heli_sequence",
        jobs=[
            SystemJob(name="falling", machine_role="faller", prerequisites=[]),
            SystemJob(name="hook_tending", machine_role="hook_tender", prerequisites=[]),
            SystemJob(
                name="helicopter_lift",
                machine_role="helicopter",
                prerequisites=["falling", "hook_tending"],
            ),
        ],
    )
    scenario = Scenario(
        name="heli-seq",
        num_days=2,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=10.0,
                earliest_start=1,
                latest_finish=2,
                harvest_system_id="heli_sequence",
            )
        ],
        machines=[
            Machine(id="F1", role="faller"),
            Machine(id="H1", role="hook_tender"),
            Machine(id="C1", role="helicopter"),
        ],
        landings=[Landing(id="L1", daily_capacity=2)],
        calendar=[
            CalendarEntry(machine_id="F1", day=1, available=1),
            CalendarEntry(machine_id="H1", day=1, available=1),
            CalendarEntry(machine_id="C1", day=1, available=1),
            CalendarEntry(machine_id="F1", day=2, available=1),
            CalendarEntry(machine_id="H1", day=2, available=1),
            CalendarEntry(machine_id="C1", day=2, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="F1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="H1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="C1", block_id="B1", rate=5.0),
        ],
        harvest_systems={"heli_sequence": system},
    )
    pb = Problem.from_scenario(scenario)
    model = build_model(pb)

    for var in model.x.values():
        var.value = 0
    shift1 = _shift_key(pb, 1)
    shift2 = _shift_key(pb, 2)
    model.x["F1", "B1", shift1].value = 1
    model.x["C1", "B1", shift2].value = 1
    con_faller = model.system_sequencing["B1", "helicopter", "faller", *shift2]
    con_hook = model.system_sequencing["B1", "helicopter", "hook_tender", *shift2]
    assert pyo.value(con_faller.body) <= pyo.value(con_faller.upper)
    assert pyo.value(con_hook.body) > pyo.value(con_hook.upper)

    for var in model.x.values():
        var.value = 0
    model.x["F1", "B1", shift1].value = 1
    model.x["H1", "B1", shift1].value = 1
    model.x["C1", "B1", shift2].value = 1
    con_faller = model.system_sequencing["B1", "helicopter", "faller", *shift2]
    con_hook = model.system_sequencing["B1", "helicopter", "hook_tender", *shift2]
    assert pyo.value(con_faller.body) <= pyo.value(con_faller.upper)
    assert pyo.value(con_hook.body) <= pyo.value(con_hook.upper)


def test_sa_evaluator_requires_all_prereqs_before_helicopter():
    system = HarvestSystem(
        system_id="heli_sequence",
        jobs=[
            SystemJob(name="falling", machine_role="faller", prerequisites=[]),
            SystemJob(name="hook_tending", machine_role="hook_tender", prerequisites=[]),
            SystemJob(
                name="helicopter_lift",
                machine_role="helicopter",
                prerequisites=["falling", "hook_tending"],
            ),
        ],
    )
    scenario = Scenario(
        name="heli-sa",
        num_days=2,
        blocks=[
            Block(
                id="B1",
                landing_id="L1",
                work_required=10.0,
                earliest_start=1,
                latest_finish=2,
                harvest_system_id="heli_sequence",
            )
        ],
        machines=[
            Machine(id="F1", role="faller"),
            Machine(id="H1", role="hook_tender"),
            Machine(id="C1", role="helicopter"),
        ],
        landings=[Landing(id="L1", daily_capacity=3)],
        calendar=[
            CalendarEntry(machine_id="F1", day=1, available=1),
            CalendarEntry(machine_id="H1", day=1, available=1),
            CalendarEntry(machine_id="C1", day=1, available=1),
            CalendarEntry(machine_id="F1", day=2, available=1),
            CalendarEntry(machine_id="H1", day=2, available=1),
            CalendarEntry(machine_id="C1", day=2, available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="F1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="H1", block_id="B1", rate=5.0),
            ProductionRate(machine_id="C1", block_id="B1", rate=5.0),
        ],
        harvest_systems={"heli_sequence": system},
    )
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)

    incomplete_prereq_plan = Schedule(
        plan=_plan_from_days(
            pb,
            {
                "F1": {1: "B1", 2: None},
                "H1": {1: None, 2: None},
                "C1": {1: None, 2: "B1"},
            },
        )
    )
    complete_prereq_plan = Schedule(
        plan=_plan_from_days(
            pb,
            {
                "F1": {1: "B1", 2: None},
                "H1": {1: "B1", 2: None},
                "C1": {1: None, 2: "B1"},
            },
        )
    )
    bad_score = evaluate_schedule(pb, incomplete_prereq_plan, ctx)
    good_score = evaluate_schedule(pb, complete_prereq_plan, ctx)
    assert bad_score < good_score
