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

    ordered_days = sorted(pb.days)
    days_up_to = {day: [d for d in ordered_days if d <= day] for day in ordered_days}
    days_before = {day: [d for d in ordered_days if d < day] for day in ordered_days}

    prereq_index = [
        (blk, role, prereq) for (blk, role), prereqs in prereq_roles.items() for prereq in prereqs
    ]
    if prereq_index:
        model.system_sequencing_index = pyo.Set(initialize=prereq_index, dimen=3)

        def sequencing_rule(mdl, blk, role, prereq, day):
            machines_role = machines_by_role.get(role)
            prereq_machines = machines_by_role.get(prereq)
            if not machines_role or not prereq_machines:
                return pyo.Constraint.Skip
            lhs = sum(
                mdl.x[mach, blk, d] for mach in machines_role for d in days_up_to.get(day, [])
            )
            rhs = sum(
                mdl.x[mach, blk, d] for mach in prereq_machines for d in days_before.get(day, [])
            )
            return lhs <= rhs

        model.system_sequencing = pyo.Constraint(
            model.system_sequencing_index, model.D, rule=sequencing_rule
        )


__all__ = ["apply_system_sequencing_constraints"]
