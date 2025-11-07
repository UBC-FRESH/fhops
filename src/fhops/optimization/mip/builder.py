"""Pyomo builder for FHOPS MIP."""

from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

from fhops.scenario.contract import Problem

__all__ = ["build_model"]


def build_model(pb: Problem) -> pyo.ConcreteModel:
    """Build the core FHOPS MIP model."""
    sc = pb.scenario

    machines = [machine.id for machine in sc.machines]
    blocks = [block.id for block in sc.blocks]
    days = list(pb.days)

    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    work_required = {block.id: block.work_required for block in sc.blocks}
    landing_capacity = {landing.id: landing.daily_capacity for landing in sc.landings}

    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    windows = {block_id: sc.window_for(block_id) for block_id in sc.block_ids()}

    model = pyo.ConcreteModel()
    model.M = pyo.Set(initialize=machines)
    model.B = pyo.Set(initialize=blocks)
    model.D = pyo.Set(initialize=days)

    def within_window(block_id: str, day: int) -> int:
        earliest, latest = windows[block_id]
        return 1 if earliest <= day <= latest else 0

    model.x = pyo.Var(model.M, model.B, model.D, domain=pyo.Binary)
    model.prod = pyo.Var(model.M, model.B, model.D, domain=pyo.NonNegativeReals)

    model.obj = pyo.Objective(
        expr=sum(
            model.prod[mach, blk, day] for mach in model.M for blk in model.B for day in model.D
        ),
        sense=pyo.maximize,
    )

    def mach_one_block_rule(mdl, mach, day):
        availability_flag = availability.get((mach, int(day)), 1)
        return sum(mdl.x[mach, blk, day] for blk in mdl.B) <= availability_flag

    model.mach_one_block = pyo.Constraint(model.M, model.D, rule=mach_one_block_rule)

    def prod_cap_rule(mdl, mach, blk, day):
        r = rate.get((mach, blk), 0.0)
        w = within_window(blk, int(day))
        return mdl.prod[mach, blk, day] <= r * mdl.x[mach, blk, day] * w

    model.prod_cap = pyo.Constraint(model.M, model.B, model.D, rule=prod_cap_rule)

    def block_cum_rule(mdl, blk):
        return (
            sum(mdl.prod[mach, blk, day] for mach in model.M for day in model.D)
            <= work_required[blk]
        )

    model.block_cum = pyo.Constraint(model.B, rule=block_cum_rule)

    blocks_by_landing: dict[str, list[str]] = defaultdict(list)
    for block in sc.blocks:
        blocks_by_landing[block.landing_id].append(block.id)

    model.L = pyo.Set(initialize=list(landing_capacity.keys()))

    def landing_cap_rule(mdl, landing_id, day):
        assignments = sum(
            mdl.x[mach, blk, day]
            for mach in model.M
            for blk in blocks_by_landing.get(landing_id, [])
        )
        capacity = landing_capacity.get(landing_id, 0)
        return assignments <= capacity

    model.landing_cap = pyo.Constraint(model.L, model.D, rule=landing_cap_rule)

    return model
