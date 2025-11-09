"""Harvest system sequencing constraints."""

from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

from fhops.scenario.contract import Problem


def apply_system_sequencing_constraints(
    model: pyo.ConcreteModel, pb: Problem, shift_sequence: list[tuple[int, str]]
) -> None:
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

    def role_constraint_rule(mdl, mach, blk, day, shift_id):
        allowed = allowed_roles.get(blk)
        role = machine_roles.get(mach)
        if allowed is None or role in allowed:
            return pyo.Constraint.Skip
        return mdl.x[mach, blk, (day, shift_id)] == 0

    model.role_filter = pyo.Constraint(model.M, model.B, model.S, rule=role_constraint_rule)

    ordered_shifts = list(shift_sequence)
    if not ordered_shifts:
        return

    shifts_up_to: dict[tuple[int, str], list[tuple[int, str]]] = {}
    shifts_before: dict[tuple[int, str], list[tuple[int, str]]] = {}
    for idx, shift in enumerate(ordered_shifts):
        shifts_up_to[shift] = ordered_shifts[: idx + 1]
        shifts_before[shift] = ordered_shifts[:idx]

    prereq_index = [
        (blk, role, prereq) for (blk, role), prereqs in prereq_roles.items() for prereq in prereqs
    ]
    if prereq_index:
        model.system_sequencing_index = pyo.Set(initialize=prereq_index, dimen=3)

        def sequencing_rule(mdl, blk, role, prereq, day, shift_id):
            machines_role = machines_by_role.get(role)
            prereq_machines = machines_by_role.get(prereq)
            if not machines_role or not prereq_machines:
                return pyo.Constraint.Skip
            shift_key = (day, shift_id)
            lhs = sum(
                mdl.x[mach, blk, s]
                for mach in machines_role
                for s in shifts_up_to.get(shift_key, [])
            )
            rhs = sum(
                mdl.x[mach, blk, s]
                for mach in prereq_machines
                for s in shifts_before.get(shift_key, [])
            )
            return lhs <= rhs

        model.system_sequencing = pyo.Constraint(
            model.system_sequencing_index, model.S, rule=sequencing_rule
        )


__all__ = ["apply_system_sequencing_constraints"]
