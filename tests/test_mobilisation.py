from fhops.optimization.mip.builder import build_model
from fhops.scheduling.mobilisation import MachineMobilisation, MobilisationConfig
from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)


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
                    move_cost_flat=5.0,
                    walk_threshold_m=0.0,
                    setup_cost=0.0,
                )
            ],
            distances=[],
        ),
    )
    return Problem.from_scenario(scenario)


def test_build_model_with_mobilisation_config():
    pb = build_problem()
    model = build_model(pb)
    assert model is not None
    assert hasattr(model, "mach_one_block")
