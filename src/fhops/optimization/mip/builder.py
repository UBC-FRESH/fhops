"""Pyomo builder for FHOPS MIP."""

from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

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

    systems = sc.harvest_systems or {}
    allowed_roles: dict[str, set[str] | None] = {}
    block_prereq_roles: dict[tuple[str, str], set[str]] = {}
    for block in sc.blocks:
        system = systems.get(block.harvest_system_id) if block.harvest_system_id else None
        if system:
            job_role = {job.name: job.machine_role for job in system.jobs}
            allowed = {job.machine_role for job in system.jobs}
            allowed_roles[block.id] = allowed
            for job in system.jobs:
                prereq_roles = {job_role[name] for name in job.prerequisites if name in job_role}
                block_prereq_roles[(block.id, job.machine_role)] = prereq_roles
        else:
            allowed_roles[block.id] = None
    machine_roles = {machine.id: getattr(machine, "role", None) for machine in sc.machines}
    machines_by_role: dict[str, list[str]] = defaultdict(list)
    for machine_id, role in machine_roles.items():
        if role is not None:
            machines_by_role[role].append(machine_id)

    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    windows = {block_id: sc.window_for(block_id) for block_id in sc.block_ids()}

    model = pyo.ConcreteModel()
    model.M = pyo.Set(initialize=machines)
    model.B = pyo.Set(initialize=blocks)
    model.D = pyo.Set(initialize=days)
    model.R = pyo.Set(initialize=list(machines_by_role.keys()))

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

    model.obj = pyo.Objective(expr=production_expr - mobil_cost_expr, sense=pyo.maximize)

    def role_constraint_rule(mdl, mach, blk, day):
        allowed = allowed_roles.get(blk)
        role = machine_roles.get(mach)
        if allowed is None or role in allowed:
            return pyo.Constraint.Skip
        return mdl.x[mach, blk, day] == 0

    model.role_filter = pyo.Constraint(model.M, model.B, model.D, rule=role_constraint_rule)

    cumulative_days = sorted(days)

    def sequencing_rule(mdl, blk, role, day):
        prereq_roles = block_prereq_roles.get((blk, role))
        if not prereq_roles:
            return pyo.Constraint.Skip
        machines_role = machines_by_role.get(role)
        if not machines_role:
            return pyo.Constraint.Skip
        machines_prereq = [
            (prereq_role, machines_by_role.get(prereq_role, [])) for prereq_role in prereq_roles
        ]
        if not any(m_list for _, m_list in machines_prereq):
            return pyo.Constraint.Skip
        lhs = sum(
            mdl.x[mach, blk, d] for mach in machines_role for d in cumulative_days if d <= day
        )
        rhs = sum(
            mdl.x[mach, blk, d]
            for prereq_role, machine_list in machines_prereq
            for mach in machine_list
            for d in cumulative_days
            if d <= day
        )
        return lhs <= rhs

    model.system_sequencing = pyo.Constraint(model.B, model.R, model.D, rule=sequencing_rule)

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
