"""Operational MILP move accounting (#139): transitions and mobilisation as in the heuristics.

A machine moves when it works a block other than its position, the block of its last *worked*
slot (or the carried-in ``last_block_id``). Staying on a block is never a transition (MAJOR-A),
and idle slots keep the position, so a move across idle slots -- and from the carried-in block
into a later first worked slot -- is charged like ``_recompute_mobilisation_for`` and the KPIs
(MAJOR-B). The loader batching integers of formulation 1.0.1 are gone (MINOR-G).
"""

from __future__ import annotations

import itertools

import pandas as pd
import pyomo.environ as pyo
import pytest

from fhops.evaluation.metrics.kpis import compute_kpis
from fhops.model.milp.driver import _apply_incumbent_start, _max_violation, solve_operational_milp
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    MachineInitialState,
    Problem,
    ProductionRate,
    Scenario,
    ScenarioInitialState,
)
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scenario.io import load_scenario
from fhops.scheduling.mobilisation import BlockDistance, MachineMobilisation, MobilisationConfig


def _scenario(
    *,
    blocks: dict[str, float],
    num_days: int,
    weights: ObjectiveWeights,
    move_cost: float = 1000.0,
    distances: dict[tuple[str, str], float] | None = None,
    unavailable: tuple[int, ...] = (),
    last_block: str | None = None,
    rate: float = 10.0,
) -> Scenario:
    """One machine, one capacity-1 landing per block, no harvest system."""

    mobilisation = MobilisationConfig(
        machine_params=[
            # Without distances every move costs the setup cost (distance 0 is a free walk).
            MachineMobilisation(
                machine_id="M1",
                walk_cost_per_meter=1.0,
                move_cost_flat=move_cost,
                walk_threshold_m=500.0,
                setup_cost=0.0 if distances else move_cost,
            )
        ],
        distances=[
            BlockDistance(from_block=a, to_block=b, distance_m=d)
            for (a, b), d in (distances or {}).items()
        ]
        or None,
    )
    initial_state = None
    if last_block is not None:
        initial_state = ScenarioInitialState(
            machines=[MachineInitialState(machine_id="M1", last_block_id=last_block)]
        )
    return Scenario(
        name="moves",
        num_days=num_days,
        blocks=[
            Block(id=blk, landing_id=f"L{blk}", work_required=volume)
            for blk, volume in blocks.items()
        ],
        machines=[Machine(id="M1")],
        landings=[Landing(id=f"L{blk}", daily_capacity=1) for blk in blocks],
        calendar=[
            CalendarEntry(machine_id="M1", day=day, available=0 if day in unavailable else 1)
            for day in range(1, num_days + 1)
        ],
        production_rates=[
            ProductionRate(machine_id="M1", block_id=blk, rate=rate) for blk in blocks
        ],
        mobilisation=mobilisation,
        objective_weights=weights,
        initial_state=initial_state,
    )


def _solve(scenario: Scenario) -> tuple[Problem, dict]:
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    result = solve_operational_milp(ctx.bundle, solver="highs", context=ctx)
    assert result["outcome"] == "optimal"
    return pb, result


def _worked(result: dict) -> list[tuple[int, str]]:
    frame = result["assignments"]
    frame = frame[frame["assigned"] > 0].sort_values("day")
    return [(int(row.day), str(row.block_id)) for row in frame.itertuples(index=False)]


def test_staying_on_a_block_is_not_a_transition() -> None:
    weights = ObjectiveWeights(production=1.0, mobilisation=0.0, transitions=20.0)
    _, result = _solve(_scenario(blocks={"B1": 100.0}, num_days=10, weights=weights))
    assert result["objective"] == pytest.approx(100.0)
    assert [day for day, _ in _worked(result)] == list(range(1, 11))


def test_idle_slots_do_not_hide_a_move() -> None:
    weights = ObjectiveWeights(production=1.0, mobilisation=1.0, transitions=0.0)
    blocks = {"B01": 30.0, "B02": 30.0}
    # Moving costs 1000 > the 60 a second block is worth: the optimum works one block only
    # (30 delivered, 30 left over). v1.0.1 idled day 4 and moved for free (objective 60).
    _, stay = _solve(_scenario(blocks=blocks, num_days=7, weights=weights))
    assert stay["objective"] == pytest.approx(0.0, abs=1e-9)
    assert len({blk for _, blk in _worked(stay)}) == 1
    # A cheap move across an idle day is taken and charged once, like the KPIs.
    pb, cheap = _solve(
        _scenario(blocks=blocks, num_days=7, weights=weights, move_cost=5.0, unavailable=(4,))
    )
    assert cheap["objective"] == pytest.approx(60.0 - 5.0)
    kpis = compute_kpis(pb, cheap["assignments"])
    assert kpis["mobilisation_cost"] == pytest.approx(5.0)


def test_carried_in_block_charges_the_first_worked_slot() -> None:
    weights = ObjectiveWeights(production=1.0, mobilisation=1.0, transitions=0.5)
    # Day 1 unavailable: the move from the carried-in B01 happens on day 2, not in the first slot.
    scenario = _scenario(
        blocks={"B01": 0.0, "B02": 60.0},
        num_days=7,
        weights=weights,
        move_cost=5.0,
        unavailable=(1,),
        last_block="B01",
    )
    pb, result = _solve(scenario)
    assert _worked(result)[0] == (2, "B02")
    assert result["objective"] == pytest.approx(60.0 - 5.0 - 0.5)
    assert compute_kpis(pb, result["assignments"])["mobilisation_cost"] == pytest.approx(5.0)


def _brute_force(scenario: Scenario) -> float:
    """Best objective over every assignment sequence, with the heuristics' move rule."""

    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    weights = scenario.objective_weights
    params = ctx.mobilisation_params["M1"]
    blocks = [blk.id for blk in scenario.blocks]
    work = {blk.id: blk.work_required for blk in scenario.blocks}
    rate = {(r.machine_id, r.block_id): r.rate for r in scenario.production_rates}
    best = float("-inf")
    for plan in itertools.product([None, *blocks], repeat=scenario.num_days):
        delivered = dict.fromkeys(blocks, 0.0)
        position = ctx.initial_machine_block.get("M1")
        moves = cost = 0.0
        for blk in plan:
            if blk is None:
                continue
            delivered[blk] = min(work[blk], delivered[blk] + rate[("M1", blk)])
            if position is not None and position != blk:
                moves += 1
                distance = ctx.distance_lookup.get((position, blk), 0.0)
                cost += params.setup_cost + (
                    params.walk_cost_per_meter * distance
                    if distance <= params.walk_threshold_m
                    else params.move_cost_flat
                )
            position = blk
        total = sum(delivered.values())
        objective = weights.production * (total - (sum(work.values()) - total))
        objective -= weights.mobilisation * cost + weights.transitions * moves
        best = max(best, objective)
    return best


@pytest.mark.parametrize("last_block", [None, "B2"])
def test_block_specific_move_costs_match_brute_force(last_block: str | None) -> None:
    # Three blocks with distance-dependent move costs (pair arcs y): walk 1/m up to 500 m, else
    # a 50 flat move; working a block for two days is worth 20.
    distances = {("B1", "B2"): 400.0, ("B1", "B3"): 30.0, ("B2", "B3"): 900.0}
    weights = ObjectiveWeights(production=1.0, mobilisation=0.2, transitions=1.0)
    scenario = _scenario(
        blocks={"B1": 20.0, "B2": 20.0, "B3": 20.0},
        num_days=6,
        weights=weights,
        move_cost=50.0,
        distances=distances,
        last_block=last_block,
    )
    _, result = _solve(scenario)
    assert result["objective"] == pytest.approx(_brute_force(scenario), abs=1e-6)


def test_move_network_size_and_no_loader_batching_integers() -> None:
    pb = Problem.from_scenario(load_scenario("examples/tiny7/scenario.yaml"))
    model = build_operational_model(build_operational_problem(pb).bundle)
    assert not hasattr(model, "loads") and not hasattr(model, "loader_partial")
    assert not any(
        var.is_integer() and not var.is_binary() for var in model.component_data_objects(pyo.Var)
    )
    # Two blocks, equal move costs per machine: hub arcs only, no pair arcs.
    assert len(model.y) == 0
    assert len(model.arrive) > 0 and len(model.depart) > 0


def test_seeded_idle_gap_plan_is_feasible_with_its_true_objective() -> None:
    weights = ObjectiveWeights(production=1.0, mobilisation=1.0, transitions=0.5)
    scenario = _scenario(
        blocks={"B01": 30.0, "B02": 30.0}, num_days=7, weights=weights, move_cost=5.0
    )
    pb = Problem.from_scenario(scenario)
    ctx = build_operational_problem(pb)
    model = build_operational_model(ctx.bundle)
    model._warm_start_meta["operational_problem"] = ctx
    plan = pd.DataFrame(
        [
            {"machine_id": "M1", "block_id": blk, "day": day, "shift_id": "S1", "assigned": 1}
            for day, blk in [(1, "B01"), (2, "B01"), (3, "B01"), (5, "B02"), (6, "B02"), (7, "B02")]
        ]
    )
    assert _apply_incumbent_start(model, plan) == 6
    for var in model.component_data_objects(pyo.Var):
        if var.value is None:
            var.set_value(0.0)
    assert _max_violation(model) <= 1e-9
    assert pyo.value(model.objective) == pytest.approx(60.0 - 5.0 - 0.5)
    assert model.depart["M1", "B01", 5, "S1"].value == 1.0
    assert model.stay["M1", "B01", 4, "S1"].value == 1.0
