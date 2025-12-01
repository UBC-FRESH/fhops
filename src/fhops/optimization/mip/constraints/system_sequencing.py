"""Harvest system sequencing constraints."""

from __future__ import annotations

import pyomo.environ as pyo

from fhops.optimization.operational_problem import (
    OperationalProblem,
    build_operational_problem,
)
from fhops.scenario.contract import Problem


def apply_system_sequencing_constraints(
    model: pyo.ConcreteModel,
    pb: Problem,
    shift_sequence: list[tuple[int, str]],
    system_ctx: OperationalProblem | None = None,
) -> None:
    """Attach role filters and precedence constraints derived from harvest systems."""

    scenario = pb.scenario
    systems = scenario.harvest_systems or {}
    if not systems:
        return

    ctx = system_ctx or build_operational_problem(pb)

    allowed_roles = ctx.allowed_roles
    prereq_roles = ctx.prereq_roles
    machine_roles = ctx.bundle.machine_roles
    machines_by_role = {
        role: list(machine_ids)
        for role, machine_ids in ctx.machines_by_role.items()
        if role and machine_ids
    }
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
    if not prereq_index:
        return

    model.system_sequencing_index = pyo.Set(initialize=prereq_index, dimen=3)

    def sequencing_rule(mdl, blk, role, prereq, day, shift_id):
        machines_role = machines_by_role.get(role)
        prereq_machines = machines_by_role.get(prereq)
        if not machines_role or not prereq_machines:
            return pyo.Constraint.Skip
        shift_key = (day, shift_id)
        lhs = sum(
            mdl.prod[mach, blk, s] for mach in machines_role for s in shifts_up_to.get(shift_key, [])
        )
        rhs = sum(
            mdl.prod[mach, blk, s]
            for mach in prereq_machines
            for s in shifts_before.get(shift_key, [])
        )
        return lhs <= rhs

    model.system_sequencing = pyo.Constraint(
        model.system_sequencing_index, model.S, rule=sequencing_rule
    )

    loader_roles = ctx.loader_roles
    loader_batches = ctx.loader_batch_volume
    loader_index = [
        (blk, role, prereq)
        for (blk, role), prereqs in prereq_roles.items()
        if (blk, role) in loader_roles
        for prereq in prereqs
    ]
    if not loader_index:
        return

    model.system_loader_index = pyo.Set(initialize=loader_index, dimen=3)

    def loader_buffer_rule(mdl, blk, role, prereq, day, shift_id):
        machines_role = machines_by_role.get(role)
        prereq_machines = machines_by_role.get(prereq)
        if not machines_role or not prereq_machines:
            return pyo.Constraint.Skip
        shift_key = (day, shift_id)
        lhs = sum(
            mdl.prod[mach, blk, s] for mach in machines_role for s in shifts_up_to.get(shift_key, [])
        )
        rhs = sum(
            mdl.prod[mach, blk, s]
            for mach in prereq_machines
            for s in shifts_before.get(shift_key, [])
        )
        buffer = loader_batches.get(blk, 0.0)
        return lhs <= rhs - buffer

    model.system_loader_buffer = pyo.Constraint(
        model.system_loader_index, model.S, rule=loader_buffer_rule
    )


__all__ = ["apply_system_sequencing_constraints"]
