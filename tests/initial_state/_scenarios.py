"""Small hand-built scenarios used by the initial-state (#91) tests."""

from __future__ import annotations

from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)
from fhops.scenario.contract.models import ObjectiveWeights, ShiftCalendarEntry
from fhops.scheduling.mobilisation import BlockDistance, MachineMobilisation, MobilisationConfig
from fhops.scheduling.systems import HarvestSystem, SystemJob

CHAIN_SYSTEM = HarvestSystem(
    system_id="chain",
    jobs=[
        SystemJob("felling", "feller_buncher", []),
        SystemJob("primary_transport", "grapple_skidder", ["felling"]),
    ],
)

SOLO_SYSTEM = HarvestSystem(
    system_id="solo",
    jobs=[SystemJob("felling", "feller_buncher", [])],
)


def chain_scenario(
    *,
    num_days: int = 1,
    work_b1: float = 40.0,
    work_b2: float = 0.0,
    feller_rate: float = 50.0,
    skidder_rate: float = 40.0,
    mobilisation: bool = False,
    objective_weights: ObjectiveWeights | None = None,
    **extra: object,
) -> Scenario:
    """Two-role (feller → skidder) scenario with one machine per role.

    Machines: ``F1`` (feller_buncher), ``S1`` (grapple_skidder). Blocks ``B1``/``B2`` on landing
    ``L1`` (capacity 4). When ``mobilisation`` is set, both machines pay ``setup 10 + 0.1 $/m``
    for the 200 m B1↔B2 walk (30 per move).
    """

    blocks = [
        Block(id="B1", landing_id="L1", work_required=work_b1, harvest_system_id="chain"),
        Block(id="B2", landing_id="L1", work_required=work_b2, harvest_system_id="chain"),
    ]
    machines = [
        Machine(id="F1", role="feller_buncher", operating_cost=1.0),
        Machine(id="S1", role="grapple_skidder", operating_cost=1.0),
    ]
    calendar = [
        CalendarEntry(machine_id=m.id, day=day, available=1)
        for m in machines
        for day in range(1, num_days + 1)
    ]
    rates = [
        ProductionRate(machine_id="F1", block_id="B1", rate=feller_rate),
        ProductionRate(machine_id="F1", block_id="B2", rate=feller_rate),
        ProductionRate(machine_id="S1", block_id="B1", rate=skidder_rate),
        ProductionRate(machine_id="S1", block_id="B2", rate=skidder_rate),
    ]
    mobilisation_cfg = None
    if mobilisation:
        mobilisation_cfg = MobilisationConfig(
            machine_params=[
                MachineMobilisation(
                    machine_id=machine_id,
                    walk_cost_per_meter=0.1,
                    move_cost_flat=500.0,
                    walk_threshold_m=1000.0,
                    setup_cost=10.0,
                )
                for machine_id in ("F1", "S1")
            ],
            distances=[
                BlockDistance(from_block="B1", to_block="B2", distance_m=200.0),
                BlockDistance(from_block="B2", to_block="B1", distance_m=200.0),
            ],
        )
    return Scenario(
        name="initial-state-chain",
        num_days=num_days,
        blocks=blocks,
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=4)],
        calendar=calendar,
        production_rates=rates,
        harvest_systems={"chain": CHAIN_SYSTEM},
        mobilisation=mobilisation_cfg,
        objective_weights=objective_weights,
        **extra,  # type: ignore[arg-type]
    )


def solo_two_shift_scenario(**extra: object) -> Scenario:
    """Single-role scenario on one day with two shifts (``S1``, ``S2``).

    Machine ``F1`` fells B1 at 60 m³/shift and B2 at 40 m³/shift; both blocks need 100 m³, so the
    unlocked optimum works B1 in both shifts and a lock on ``S2`` moves only that shift.
    """

    blocks = [
        Block(id="B1", landing_id="L1", work_required=100.0, harvest_system_id="solo"),
        Block(id="B2", landing_id="L1", work_required=100.0, harvest_system_id="solo"),
    ]
    machines = [Machine(id="F1", role="feller_buncher", operating_cost=1.0)]
    return Scenario(
        name="initial-state-solo",
        num_days=1,
        blocks=blocks,
        machines=machines,
        landings=[Landing(id="L1", daily_capacity=4)],
        calendar=[CalendarEntry(machine_id="F1", day=1, available=1)],
        shift_calendar=[
            ShiftCalendarEntry(machine_id="F1", day=1, shift_id="S1", available=1),
            ShiftCalendarEntry(machine_id="F1", day=1, shift_id="S2", available=1),
        ],
        production_rates=[
            ProductionRate(machine_id="F1", block_id="B1", rate=60.0),
            ProductionRate(machine_id="F1", block_id="B2", rate=40.0),
        ],
        harvest_systems={"solo": SOLO_SYSTEM},
        **extra,  # type: ignore[arg-type]
    )
