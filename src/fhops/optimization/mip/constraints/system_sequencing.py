"""Harvest system sequencing constraints."""

from __future__ import annotations

from collections import defaultdict

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
    sequencing_enabled: bool = True,
) -> None:
    """Attach role filters and precedence constraints derived from harvest systems."""

    if not sequencing_enabled:
        return

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

    ordered_shifts = list(getattr(ctx, "shift_keys", ()))
    if not ordered_shifts:
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
    landing_for_block = ctx.bundle.landing_for_block
    loader_index = [
        (blk, role, prereq)
        for (blk, role), prereqs in prereq_roles.items()
        if (blk, role) in loader_roles
        for prereq in prereqs
    ]
    if loader_index:
        model.system_loader_index = pyo.Set(initialize=loader_index, dimen=3)

        def loader_buffer_rule(mdl, blk, role, prereq, day, shift_id):
            machines_role = machines_by_role.get(role)
            prereq_machines = machines_by_role.get(prereq)
            if not machines_role or not prereq_machines:
                return pyo.Constraint.Skip
            shift_key = (day, shift_id)
            lhs = sum(
                mdl.prod[mach, blk, s]
                for mach in machines_role
                for s in shifts_up_to.get(shift_key, [])
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

    headstart_buffers = {key: value for key, value in ctx.role_headstarts.items() if value > 0.0}
    activation_roles = set(loader_roles) | set(headstart_buffers.keys())

    role_active_defined = False
    if activation_roles:
        activation_index = [
            (blk, role, day, shift_id)
            for blk, role in activation_roles
            for day, shift_id in ordered_shifts
        ]
        model.role_activation_index = pyo.Set(initialize=activation_index, dimen=4)
        model.role_active = pyo.Var(model.role_activation_index, domain=pyo.Binary, initialize=0)
        role_active_defined = True

        lb_index = [
            (blk, role, mach, day, shift_id)
            for blk, role in activation_roles
            for mach in machines_by_role.get(role, [])
            for day, shift_id in ordered_shifts
        ]
        if lb_index:
            model.role_activation_lb_index = pyo.Set(initialize=lb_index, dimen=5)

            def role_activation_lb_rule(mdl, blk, role, mach, day, shift_id):
                return mdl.role_active[blk, role, day, shift_id] >= mdl.x[mach, blk, (day, shift_id)]

            model.role_activation_lb = pyo.Constraint(
                model.role_activation_lb_index, rule=role_activation_lb_rule
            )

        def role_activation_ub_rule(mdl, blk, role, day, shift_id):
            machines_role = machines_by_role.get(role)
            if not machines_role:
                return pyo.Constraint.Skip
            return mdl.role_active[blk, role, day, shift_id] <= sum(
                mdl.x[mach, blk, (day, shift_id)] for mach in machines_role
            )

        model.role_activation_ub = pyo.Constraint(
            model.role_activation_index, rule=role_activation_ub_rule
        )

    headstart_index = [
        (blk, role, prereq)
        for (blk, role), buffer in headstart_buffers.items()
        if buffer > 0.0
        for prereq in prereq_roles.get((blk, role), ())
    ]
    if headstart_index:
        model.system_headstart_index = pyo.Set(initialize=headstart_index, dimen=3)

        def headstart_rule(mdl, blk, role, prereq, day, shift_id):
            machines_role = machines_by_role.get(role)
            prereq_machines = machines_by_role.get(prereq)
            if not machines_role or not prereq_machines:
                return pyo.Constraint.Skip
            shift_key = (day, shift_id)
            buffer = headstart_buffers.get((blk, role), 0.0)
            if buffer <= 0.0:
                return pyo.Constraint.Skip
            before = shifts_before.get(shift_key, [])
            if not before:
                return sum(mdl.x[mach, blk, (day, shift_id)] for mach in machines_role) == 0
            lhs = sum(
                mdl.x[mach, blk, s]
                for mach in machines_role
                for s in before
            )
            rhs = sum(
                mdl.x[mach, blk, s]
                for mach in prereq_machines
                for s in before
            )
            return lhs + buffer <= rhs

        model.system_headstart = pyo.Constraint(
            model.system_headstart_index, model.S, rule=headstart_rule
        )

    if role_active_defined and loader_roles:
        loader_activation_index = [
            (blk, role, day, shift_id)
            for blk, role in loader_roles
            for day, shift_id in ordered_shifts
        ]
        model.loader_activation_index = pyo.Set(initialize=loader_activation_index, dimen=4)

        def loader_batch_rule(mdl, blk, role, day, shift_id):
            buffer = loader_batches.get(blk, 0.0)
            if buffer <= 0.0:
                return pyo.Constraint.Skip
            prereq_set = prereq_roles.get((blk, role))
            if not prereq_set:
                return pyo.Constraint.Skip
            shift_key = (day, shift_id)
            before = shifts_before.get(shift_key, [])
            if not before:
                return mdl.role_active[blk, role, day, shift_id] == 0
            rhs = sum(
                mdl.prod[mach, blk, s]
                for prereq_role in prereq_set
                for mach in machines_by_role.get(prereq_role, [])
                for s in before
            )
            return buffer * mdl.role_active[blk, role, day, shift_id] <= rhs

        model.loader_batch_activation = pyo.Constraint(
            model.loader_activation_index, rule=loader_batch_rule
        )

    landing_blocks: dict[str, list[str]] = defaultdict(list)
    for blk, landing_id in landing_for_block.items():
        if landing_id is not None:
            landing_blocks[landing_id].append(blk)

    landing_loader_prereqs: dict[tuple[str, str], set[str]] = {}
    for blk, role in loader_roles:
        landing_id = landing_for_block.get(blk)
        if not landing_id:
            continue
        prereqs = prereq_roles.get((blk, role))
        if not prereqs:
            continue
        key = (landing_id, role)
        landing_loader_prereqs.setdefault(key, set()).update(prereqs)

    landing_loader_index = [
        (landing_id, role, prereq)
        for (landing_id, role), prereqs in landing_loader_prereqs.items()
        for prereq in prereqs
    ]
    if landing_loader_index:
        model.landing_loader_index = pyo.Set(initialize=landing_loader_index, dimen=3)

        def landing_loader_rule(mdl, landing_id, role, prereq, day, shift_id):
            loader_blocks = landing_blocks.get(landing_id, [])
            if not loader_blocks:
                return pyo.Constraint.Skip
            loader_machines = machines_by_role.get(role)
            prereq_machines = machines_by_role.get(prereq)
            if not loader_machines or not prereq_machines:
                return pyo.Constraint.Skip
            shift_key = (day, shift_id)
            lhs = sum(
                mdl.prod[mach, blk, s]
                for blk in loader_blocks
                for mach in loader_machines
                for s in shifts_up_to.get(shift_key, [])
            )
            rhs = sum(
                mdl.prod[mach, blk, s]
                for blk in loader_blocks
                for mach in prereq_machines
                for s in shifts_before.get(shift_key, [])
            )
            return lhs <= rhs

        model.landing_loader_sequencing = pyo.Constraint(
            model.landing_loader_index, model.S, rule=landing_loader_rule
        )


__all__ = ["apply_system_sequencing_constraints"]
