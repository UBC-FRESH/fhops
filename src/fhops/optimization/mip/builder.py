"""Pyomo builder for FHOPS MIP."""

from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

from fhops.optimization.mip.constraints.system_sequencing import apply_system_sequencing_constraints
from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import MachineMobilisation, build_distance_lookup

__all__ = ["build_model"]


def build_model(pb: Problem) -> pyo.ConcreteModel:
    """Build the core FHOPS MIP model (shift-indexed)."""

    sc = pb.scenario

    machines = [machine.id for machine in sc.machines]
    blocks = [block.id for block in sc.blocks]
    shift_list = pb.shifts
    shift_tuples = [(shift.day, shift.shift_id) for shift in shift_list]
    ordered_days = sorted({day for day, _ in shift_tuples})

    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    work_required = {block.id: block.work_required for block in sc.blocks}
    landing_capacity = {landing.id: landing.daily_capacity for landing in sc.landings}

    mobilisation = sc.mobilisation
    mobil_params: dict[str, MachineMobilisation] = {}
    if mobilisation is not None:
        mobil_params = {param.machine_id: param for param in mobilisation.machine_params}
    distance_lookup = build_distance_lookup(mobilisation)

    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    shift_availability = (
        {(c.machine_id, c.day, c.shift_id): int(c.available) for c in sc.shift_calendar}
        if sc.shift_calendar
        else {}
    )

    calendar_blackouts: set[tuple[str, int, str]] = set()
    if sc.timeline and sc.timeline.blackouts:
        for blackout in sc.timeline.blackouts:
            for day, shift_id in shift_tuples:
                if blackout.start_day <= day <= blackout.end_day:
                    for machine in sc.machines:
                        calendar_blackouts.add((machine.id, day, shift_id))

    locked_assignments = sc.locked_assignments or []
    locked_lookup = {(lock.machine_id, lock.day): lock.block_id for lock in locked_assignments}
    windows = {block_id: sc.window_for(block_id) for block_id in sc.block_ids()}

    model = pyo.ConcreteModel()
    model.M = pyo.Set(initialize=machines)
    model.B = pyo.Set(initialize=blocks)
    model.D = pyo.Set(initialize=ordered_days)
    model.S = pyo.Set(initialize=shift_tuples, dimen=2)

    def within_window(block_id: str, day: int) -> int:
        earliest, latest = windows[block_id]
        return 1 if earliest <= day <= latest else 0

    model.x = pyo.Var(model.M, model.B, model.S, domain=pyo.Binary)
    model.prod = pyo.Var(model.M, model.B, model.S, domain=pyo.NonNegativeReals)

    production_expr = sum(
        model.prod[mach, blk, (day, shift_id)]
        for mach in model.M
        for blk in model.B
        for day, shift_id in model.S
    )

    mobil_cost_expr = 0
    transition_expr = 0
    landing_slack_expr = 0

    transition_weight = 0.0
    landing_slack_weight = 0.0
    prod_weight = 1.0
    mobil_weight = 1.0
    if sc.objective_weights is not None:
        prod_weight = sc.objective_weights.production
        mobil_weight = sc.objective_weights.mobilisation
        transition_weight = sc.objective_weights.transitions
        landing_slack_weight = sc.objective_weights.landing_slack
    needs_transitions = bool(mobil_params) or transition_weight > 0.0
    enable_landing_slack = landing_slack_weight > 0.0

    prev_shift_map: dict[tuple[int, str], tuple[int, str]] = {}
    for idx in range(1, len(shift_tuples)):
        prev_shift_map[shift_tuples[idx]] = shift_tuples[idx - 1]

    if needs_transitions:
        model.S_transition = pyo.Set(initialize=list(prev_shift_map.keys()), dimen=2)

        model.y = pyo.Var(model.M, model.B, model.B, model.S_transition, domain=pyo.Binary)

        def _prev_match_rule(mdl, mach, prev_blk, curr_blk, day, shift_id):
            prev_index = prev_shift_map.get((day, shift_id))
            if prev_index is None:
                return pyo.Constraint.Skip
            prev_day, prev_shift = prev_index
            return mdl.y[mach, prev_blk, curr_blk, (day, shift_id)] <= mdl.x[
                mach, prev_blk, (prev_day, prev_shift)
            ]

        def _curr_match_rule(mdl, mach, prev_blk, curr_blk, day, shift_id):
            return mdl.y[mach, prev_blk, curr_blk, (day, shift_id)] <= mdl.x[
                mach, curr_blk, (day, shift_id)
            ]

        def _link_rule(mdl, mach, prev_blk, curr_blk, day, shift_id):
            prev_index = prev_shift_map.get((day, shift_id))
            if prev_index is None:
                return pyo.Constraint.Skip
            prev_day, prev_shift = prev_index
            return mdl.y[mach, prev_blk, curr_blk, (day, shift_id)] >= (
                mdl.x[mach, prev_blk, (prev_day, prev_shift)]
                + mdl.x[mach, curr_blk, (day, shift_id)]
                - 1
            )

        model.transition_prev = pyo.Constraint(
            model.M, model.B, model.B, model.S_transition, rule=_prev_match_rule
        )
        model.transition_curr = pyo.Constraint(
            model.M, model.B, model.B, model.S_transition, rule=_curr_match_rule
        )
        model.transition_link = pyo.Constraint(
            model.M, model.B, model.B, model.S_transition, rule=_link_rule
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
            _mobil_cost(mach, prev_blk, curr_blk) * model.y[mach, prev_blk, curr_blk, (day, shift_id)]
            for mach in model.M
            for prev_blk in model.B
            for curr_blk in model.B
            for day, shift_id in model.S_transition
        )

        transition_expr = sum(
            model.y[mach, prev_blk, curr_blk, (day, shift_id)]
            for mach in model.M
            for prev_blk in model.B
            for curr_blk in model.B
            for day, shift_id in model.S_transition
        )

    def mach_one_shift_rule(mdl, mach, day, shift_id):
        if (mach, day, shift_id) in calendar_blackouts:
            return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) == 0
        if (mach, day) in locked_lookup:
            return pyo.Constraint.Skip
        available = shift_availability.get((mach, day, shift_id))
        if available is not None:
            return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) <= available
        availability_flag = availability.get((mach, day), 1)
        return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) <= availability_flag

    model.mach_one_shift = pyo.Constraint(model.M, model.S, rule=mach_one_shift_rule)

    def prod_cap_rule(mdl, mach, blk, day, shift_id):
        r = rate.get((mach, blk), 0.0)
        w = within_window(blk, day)
        return mdl.prod[mach, blk, (day, shift_id)] <= r * mdl.x[mach, blk, (day, shift_id)] * w

    model.prod_cap = pyo.Constraint(model.M, model.B, model.S, rule=prod_cap_rule)

    def block_cum_rule(mdl, blk):
        return (
            sum(mdl.prod[mach, blk, (day, shift_id)] for mach in model.M for day, shift_id in model.S)
            <= work_required[blk]
        )

    model.block_cum = pyo.Constraint(model.B, rule=block_cum_rule)

    blocks_by_landing: dict[str, list[str]] = defaultdict(list)
    for block in sc.blocks:
        blocks_by_landing[block.landing_id].append(block.id)

    model.L = pyo.Set(initialize=list(landing_capacity.keys()))

    if enable_landing_slack:
        model.landing_slack = pyo.Var(model.L, model.S, domain=pyo.NonNegativeReals)

        def landing_cap_rule(mdl, landing_id, day, shift_id):
            assignments = sum(
                mdl.x[mach, blk, (day, shift_id)]
                for mach in model.M
                for blk in blocks_by_landing.get(landing_id, [])
            )
            capacity = landing_capacity.get(landing_id, 0)
            return assignments <= capacity + mdl.landing_slack[landing_id, (day, shift_id)]

        landing_slack_expr = sum(
            model.landing_slack[landing_id, (day, shift_id)]
            for landing_id in model.L
            for day, shift_id in model.S
        )
    else:

        def landing_cap_rule(mdl, landing_id, day, shift_id):
            assignments = sum(
                mdl.x[mach, blk, (day, shift_id)]
                for mach in model.M
                for blk in blocks_by_landing.get(landing_id, [])
            )
            capacity = landing_capacity.get(landing_id, 0)
            return assignments <= capacity

    model.landing_cap = pyo.Constraint(model.L, model.S, rule=landing_cap_rule)

    obj_expr = prod_weight * production_expr
    if mobil_params:
        obj_expr -= mobil_weight * mobil_cost_expr
    if needs_transitions and transition_weight > 0.0:
        obj_expr -= transition_weight * transition_expr
    if enable_landing_slack and landing_slack_weight > 0.0:
        obj_expr -= landing_slack_weight * landing_slack_expr
    model.obj = pyo.Objective(expr=obj_expr, sense=pyo.maximize)

    apply_system_sequencing_constraints(model, pb, shift_tuples)

    for lock in locked_assignments:
        for day, shift_id in model.S:
            if day == lock.day:
                allowed = shift_availability.get((lock.machine_id, day, shift_id), 1)
                model.x[lock.machine_id, lock.block_id, (day, shift_id)].fix(1 if allowed else 0)
        for other_blk in blocks:
            if other_blk != lock.block_id:
                for day, shift_id in model.S:
                    if day == lock.day:
                        model.x[lock.machine_id, other_blk, (day, shift_id)].fix(0)

    return model
