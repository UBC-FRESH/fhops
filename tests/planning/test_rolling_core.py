from fhops.planning.rolling import (
    RollingHorizonConfig,
    build_iteration_plan,
    slice_scenario_for_window,
)
from fhops.scenario.io import load_scenario


def test_iteration_plan_respects_master_horizon():
    scenario = load_scenario("examples/med42/scenario.yaml")
    config = RollingHorizonConfig(
        scenario=scenario, master_days=28, subproblem_days=14, lock_days=7
    )
    iterations = build_iteration_plan(config)
    assert len(iterations) == 4
    assert iterations[0].start_day == 1
    assert iterations[-1].end_day == config.start_day + config.master_days - 1
    assert sum(iter.lock_days for iter in iterations) == 28


def test_slice_scenario_rebases_calendars_and_locks():
    scenario = load_scenario("examples/med42/scenario.yaml")
    config = RollingHorizonConfig(
        scenario=scenario, master_days=28, subproblem_days=14, lock_days=7
    )
    plan = build_iteration_plan(config)[0]
    sliced = slice_scenario_for_window(scenario, plan)

    assert sliced.num_days == 14
    assert all(1 <= entry.day <= 14 for entry in sliced.calendar)
    assert all(rate.block_id in {b.id for b in sliced.blocks} for rate in sliced.production_rates)
