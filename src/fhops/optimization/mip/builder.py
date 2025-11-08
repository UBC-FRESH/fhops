"""Pyomo builder for FHOPS MIP."""

from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

from fhops.optimization.mip.constraints.system_sequencing import apply_system_sequencing_constraints
from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import MachineMobilisation, build_distance_lookup

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

    mobilisation = sc.mobilisation
    mobil_params: dict[str, MachineMobilisation] = {}
    if mobilisation is not None:
        mobil_params = {param.machine_id: param for param in mobilisation.machine_params}
    distance_lookup = build_distance_lookup(mobilisation)

    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    calendar_blackouts: set[tuple[str, int]] = set()
    if sc.timeline and sc.timeline.blackouts:
        for blackout in sc.timeline.blackouts:
            for day in range(blackout.start_day, blackout.end_day + 1):
                for machine in sc.machines:
                    calendar_blackouts.add((machine.id, day))
    locked_assignments = sc.locked_assignments or []
    locked_lookup = {(lock.machine_id, lock.day): lock.block_id for lock in locked_assignments}
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

    production_expr = sum(
        model.prod[mach, blk, day] for mach in model.M for blk in model.B for day in model.D
    )

    mobil_cost_expr = 0

    if mobil_params:
        transition_days = [day for day in days if day > min(days)]
        model.D_transition = pyo.Set(initialize=transition_days)

        model.y = pyo.Var(model.M, model.B, model.B, model.D_transition, domain=pyo.Binary)

        def _prev_match_rule(mdl, mach, prev_blk, curr_blk, day):
            prev_day = day - 1
            return mdl.y[mach, prev_blk, curr_blk, day] <= mdl.x[mach, prev_blk, prev_day]

        def _curr_match_rule(mdl, mach, prev_blk, curr_blk, day):
            return mdl.y[mach, prev_blk, curr_blk, day] <= mdl.x[mach, curr_blk, day]

        def _link_rule(mdl, mach, prev_blk, curr_blk, day):
            prev_day = day - 1
            return mdl.y[mach, prev_blk, curr_blk, day] >= (
                mdl.x[mach, prev_blk, prev_day] + mdl.x[mach, curr_blk, day] - 1
            )

        model.transition_prev = pyo.Constraint(
            model.M, model.B, model.B, model.D_transition, rule=_prev_match_rule
        )
        model.transition_curr = pyo.Constraint(
            model.M, model.B, model.B, model.D_transition, rule=_curr_match_rule
        )
        model.transition_link = pyo.Constraint(
            model.M, model.B, model.B, model.D_transition, rule=_link_rule
        )

        def _mobil_cost(mach: str, prev_blk: str, curr_blk: str) -> float:
            params = mobil_params.get(mach)
            if params is None or prev_blk == curr_blk:
                return 0.0
            distance = distance_lookup.get((prev_blk, curr_blk), 0.0)
            threshold = params.walk_threshold_m
            cost = params.setup_cost
            if distance <= threshold:
                cost += params.walk_cost_per_meter * distance
            else:
                cost += params.move_cost_flat
            return cost

        mobil_cost_expr = sum(
            _mobil_cost(mach, prev_blk, curr_blk) * model.y[mach, prev_blk, curr_blk, day]
            for mach in model.M
            for prev_blk in model.B
            for curr_blk in model.B
            for day in model.D_transition
        )

    prod_weight = 1.0
    mobil_weight = 1.0
    if sc.objective_weights is not None:
        prod_weight = sc.objective_weights.production
        mobil_weight = sc.objective_weights.mobilisation
    obj_expr = prod_weight * production_expr
    if mobil_params:
        obj_expr -= mobil_weight * mobil_cost_expr
    model.obj = pyo.Objective(expr=obj_expr, sense=pyo.maximize)

    def mach_one_block_rule(mdl, mach, day):
        day_int = int(day)
        if (mach, day_int) in calendar_blackouts:
            return sum(mdl.x[mach, blk, day] for blk in mdl.B) == 0
        if (mach, day_int) in locked_lookup:
            return pyo.Constraint.Skip
        availability_flag = availability.get((mach, day_int), 1)
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

    apply_system_sequencing_constraints(model, pb)

    for lock in locked_assignments:
        model.x[lock.machine_id, lock.block_id, lock.day].fix(1)
        for other_blk in blocks:
            if other_blk != lock.block_id:
                model.x[lock.machine_id, other_blk, lock.day].fix(0)

    return model
