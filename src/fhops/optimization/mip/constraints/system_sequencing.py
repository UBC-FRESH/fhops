"""Harvest system sequencing constraints."""

from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

from fhops.scenario.contract import Problem


def apply_system_sequencing_constraints(model: pyo.ConcreteModel, pb: Problem) -> None:
    """Attach role filters and precedence constraints derived from harvest systems."""

    scenario = pb.scenario
    systems = scenario.harvest_systems or {}
    if not systems:
        return

    allowed_roles: dict[str, set[str] | None] = {}
    prereq_roles: dict[tuple[str, str], set[str]] = {}

    for block in scenario.blocks:
        system = systems.get(block.harvest_system_id) if block.harvest_system_id else None
        if not system:
            allowed_roles[block.id] = None
            continue
        job_roles = {job.name: job.machine_role for job in system.jobs}
        allowed_roles[block.id] = {job.machine_role for job in system.jobs}
        for job in system.jobs:
            prereq = {job_roles[name] for name in job.prerequisites if name in job_roles}
            prereq_roles[(block.id, job.machine_role)] = prereq

    machine_roles = {machine.id: getattr(machine, "role", None) for machine in scenario.machines}
    machines_by_role: dict[str, list[str]] = defaultdict(list)
    for machine_id, role in machine_roles.items():
        if role is not None:
            machines_by_role[role].append(machine_id)

    if not machines_by_role:
        return

    if not hasattr(model, "R"):
        model.R = pyo.Set(initialize=list(machines_by_role.keys()))

    def role_constraint_rule(mdl, mach, blk, day):
        allowed = allowed_roles.get(blk)
        role = machine_roles.get(mach)
        if allowed is None or role in allowed:
            return pyo.Constraint.Skip
        return mdl.x[mach, blk, day] == 0

    model.role_filter = pyo.Constraint(model.M, model.B, model.D, rule=role_constraint_rule)

    cumulative_days = sorted(pb.days)

    def sequencing_rule(mdl, blk, role, day):
        prereqs = prereq_roles.get((blk, role))
        if not prereqs:
            return pyo.Constraint.Skip
        machines_role = machines_by_role.get(role)
        if not machines_role:
            return pyo.Constraint.Skip
        machines_prereq = [machines_by_role.get(pr, []) for pr in prereqs]
        if not any(machines_prereq):
            return pyo.Constraint.Skip
        lhs = sum(
            mdl.x[mach, blk, d] for mach in machines_role for d in cumulative_days if d <= day
        )
        rhs = sum(
            mdl.x[mach, blk, d]
            for machine_list in machines_prereq
            for mach in machine_list
            for d in cumulative_days
            if d <= day
        )
        return lhs <= rhs

    model.system_sequencing = pyo.Constraint(model.B, model.R, model.D, rule=sequencing_rule)


__all__ = ["apply_system_sequencing_constraints"]
