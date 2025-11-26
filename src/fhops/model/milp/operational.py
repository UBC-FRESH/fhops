"""Operational MILP builder (day × shift grid)."""

from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

from fhops.model.milp.data import OperationalMilpBundle

__all__ = ["build_operational_model"]


def build_operational_model(bundle: OperationalMilpBundle) -> pyo.ConcreteModel:
    """Construct a Pyomo model from an :class:`OperationalMilpBundle`."""

    model = pyo.ConcreteModel()

    machines = bundle.machines
    blocks = bundle.blocks
    shifts = bundle.shifts
    days = bundle.days

    model.M = pyo.Set(initialize=machines)
    model.B = pyo.Set(initialize=blocks)
    model.D = pyo.Set(initialize=days)
    model.S = pyo.Set(initialize=shifts, dimen=2)

    shift_list = list(shifts)
    prev_shift_map: dict[tuple[int, str], tuple[int, str] | None] = {}
    for idx, slot in enumerate(shift_list):
        prev_shift_map[slot] = shift_list[idx - 1] if idx > 0 else None

    machine_roles = bundle.machine_roles
    role_to_machines: dict[str, list[str]] = defaultdict(list)
    for machine_id, role in machine_roles.items():
        if role:
            role_to_machines[role].append(machine_id)

    block_system = bundle.block_system
    system_configs = bundle.systems
    block_roles: dict[str, tuple[str, ...]] = {}
    role_block_pairs: list[tuple[str, str]] = []
    inventory_pairs: list[tuple[str, str]] = []
    activation_pairs: list[tuple[str, str]] = []
    loader_pairs: list[tuple[str, str]] = []
    role_upstream: dict[tuple[str, str], tuple[str, ...]] = {}
    role_buffer_volume: dict[tuple[str, str], float] = {}
    role_capacity: dict[tuple[str, str], float] = {}
    loader_batch_volume: dict[tuple[str, str], float] = {}

    for block in blocks:
        system_id = block_system[block]
        system_cfg = system_configs[system_id]
        roles_for_block: list[str] = []
        for role_cfg in system_cfg.roles:
            role_name = role_cfg.role
            pair = (role_name, block)
            role_block_pairs.append(pair)
            role_upstream[pair] = role_cfg.upstream_roles
            roles_for_block.append(role_name)

            cap = sum(
                bundle.production_rates.get((machine_id, block), 0.0)
                for machine_id in role_to_machines.get(role_name, [])
            )
            if cap <= 0:
                cap = 1.0
            role_capacity[pair] = cap
            buffer_volume = role_cfg.buffer_shifts * cap
            role_buffer_volume[pair] = buffer_volume

            if role_cfg.upstream_roles:
                inventory_pairs.append(pair)
            if buffer_volume > 0:
                activation_pairs.append(pair)
            if role_cfg.is_loader:
                loader_pairs.append(pair)
                loader_batch_volume[pair] = system_cfg.loader_batch_volume_m3
            else:
                loader_batch_volume[pair] = system_cfg.loader_batch_volume_m3

        block_roles[block] = tuple(roles_for_block)

    window_lookup = bundle.windows
    availability_day = bundle.availability_day
    availability_shift = bundle.availability_shift

    def _within_window(block_id: str, day: int) -> bool:
        earliest, latest = window_lookup[block_id]
        return earliest <= day <= latest

    def _is_available(machine_id: str, day: int, shift_id: str) -> bool:
        if (machine_id, day, shift_id) in availability_shift:
            return availability_shift[(machine_id, day, shift_id)] == 1
        return availability_day.get((machine_id, day), 1) == 1

    model.x = pyo.Var(model.M, model.B, model.S, domain=pyo.Binary)
    model.prod = pyo.Var(model.M, model.B, model.S, domain=pyo.NonNegativeReals)

    # Machine capacity & compatibility
    def machine_capacity_rule(mdl, mach, day, shift_id):
        if not _is_available(mach, day, shift_id):
            return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) == 0
        return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) <= 1

    model.machine_capacity = pyo.Constraint(model.M, model.S, rule=machine_capacity_rule)

    def role_compatibility_rule(mdl, mach, blk, day, shift_id):
        role = machine_roles.get(mach)
        if role and role in block_roles.get(blk, ()):  # allowed
            return pyo.Constraint.Skip
        # machine not compatible with block/system role
        return mdl.x[mach, blk, (day, shift_id)] == 0

    model.role_compatibility = pyo.Constraint(model.M, model.B, model.S, rule=role_compatibility_rule)

    # Production capacity per assignment
    def prod_cap_rule(mdl, mach, blk, day, shift_id):
        rate = bundle.production_rates.get((mach, blk), 0.0)
        return mdl.prod[mach, blk, (day, shift_id)] <= rate * mdl.x[mach, blk, (day, shift_id)]

    model.production_cap = pyo.Constraint(model.M, model.B, model.S, rule=prod_cap_rule)

    # Window feasibility
    def window_rule(mdl, mach, blk, day, shift_id):
        if _within_window(blk, day):
            return pyo.Constraint.Skip
        return mdl.x[mach, blk, (day, shift_id)] == 0

    model.block_windows = pyo.Constraint(model.M, model.B, model.S, rule=window_rule)

    # Role-level production aggregation
    model.RB = pyo.Set(initialize=role_block_pairs, dimen=2)
    model.role_prod = pyo.Var(model.RB, model.S, domain=pyo.NonNegativeReals)

    def role_prod_balance_rule(mdl, role, blk, day, shift_id):
        machines_for_role = role_to_machines.get(role, [])
        if not machines_for_role:
            return mdl.role_prod[role, blk, (day, shift_id)] == 0
        return mdl.role_prod[role, blk, (day, shift_id)] == sum(
            mdl.prod[mach, blk, (day, shift_id)] for mach in machines_for_role
        )

    model.role_prod_balance = pyo.Constraint(model.RB, model.S, rule=role_prod_balance_rule)

    # Inventory tracking (only for roles with upstream requirements)
    model.InventoryPairs = pyo.Set(initialize=inventory_pairs, dimen=2)
    model.inventory = pyo.Var(model.InventoryPairs, model.S, domain=pyo.NonNegativeReals)

    def inventory_balance_rule(mdl, role, blk, day, shift_id):
        slot = (day, shift_id)
        prev_slot = prev_shift_map[slot]
        prev_inventory = mdl.inventory[role, blk, prev_slot] if prev_slot else 0.0
        upstream_roles = role_upstream[(role, blk)]
        upstream_sum = sum(mdl.role_prod[up_role, blk, slot] for up_role in upstream_roles)
        return mdl.inventory[role, blk, slot] == prev_inventory + upstream_sum - mdl.role_prod[role, blk, slot]

    if inventory_pairs:
        model.inventory_balance = pyo.Constraint(
            model.InventoryPairs, model.S, rule=inventory_balance_rule
        )

    # Head-start buffers via activation binaries (only when buffer > 0)
    model.ActivationPairs = pyo.Set(initialize=activation_pairs, dimen=2)
    if activation_pairs:
        model.role_active = pyo.Var(model.ActivationPairs, model.S, domain=pyo.Binary)

        def activation_prod_rule(mdl, role, blk, day, shift_id):
            return mdl.role_prod[role, blk, (day, shift_id)] <= cap * mdl.role_active[role, blk, (day, shift_id)]

        def head_start_rule(mdl, role, blk, day, shift_id):
            slot = (day, shift_id)
            prev_slot = prev_shift_map[slot]
            prev_inventory = mdl.inventory[role, blk, prev_slot] if prev_slot else 0.0
            upstream_roles = role_upstream[(role, blk)]
            upstream_sum = sum(mdl.role_prod[up_role, blk, slot] for up_role in upstream_roles)
            buffer_volume = role_buffer_volume[(role, blk)]
            if buffer_volume <= 0:
                return pyo.Constraint.Skip
            return prev_inventory + upstream_sum + buffer_volume * (1 - mdl.role_active[role, blk, slot]) >= buffer_volume

        model.activation_prod = pyo.Constraint(
            model.ActivationPairs, model.S, rule=activation_prod_rule
        )
        model.head_start = pyo.Constraint(
            model.ActivationPairs, model.S, rule=head_start_rule
        )

    # Loader batching constraints
    model.LoaderPairs = pyo.Set(initialize=loader_pairs, dimen=2)
    if loader_pairs:
        model.loads = pyo.Var(model.LoaderPairs, model.S, domain=pyo.NonNegativeIntegers)

        def loader_batch_rule(mdl, role, blk, day, shift_id):
            batch = loader_batch_volume[(role, blk)]
            return mdl.role_prod[role, blk, (day, shift_id)] == batch * mdl.loads[role, blk, (day, shift_id)]

        model.loader_batch = pyo.Constraint(model.LoaderPairs, model.S, rule=loader_batch_rule)

    # Block balance ensures required work is met (with leftover slack)
    model.leftover = pyo.Var(model.B, domain=pyo.NonNegativeReals)

    def block_balance_rule(mdl, blk):
        total_prod = sum(mdl.prod[mach, blk, slot] for mach in mdl.M for slot in model.S)
        return total_prod + mdl.leftover[blk] == bundle.work_required[blk]

    model.block_balance = pyo.Constraint(model.B, rule=block_balance_rule)

    # Landing capacity with slack
    landing_ids = list(bundle.landing_capacity.keys())
    model.Landing = pyo.Set(initialize=landing_ids)
    model.landing_slack = pyo.Var(model.Landing, model.D, domain=pyo.NonNegativeReals)

    def landing_capacity_rule(mdl, landing_id, day):
        capacity = bundle.landing_capacity.get(landing_id)
        if capacity is None:
            return pyo.Constraint.Skip
        related_blocks = [
            blk for blk, landing in bundle.landing_for_block.items() if landing == landing_id
        ]
        if not related_blocks:
            return pyo.Constraint.Skip
        expr = 0
        for blk in related_blocks:
            for mach in mdl.M:
                for shift_day, shift_label in model.S:
                    if shift_day == day:
                        expr += mdl.x[mach, blk, (shift_day, shift_label)]
        return expr <= capacity + mdl.landing_slack[landing_id, day]

    model.landing_capacity = pyo.Constraint(model.Landing, model.D, rule=landing_capacity_rule)

    prod_weight = bundle.objective_weights.production
    leftover_penalty = bundle.objective_weights.transitions
    landing_weight = bundle.objective_weights.landing_slack

    obj_expr = prod_weight * sum(
        model.prod[mach, blk, slot] for mach in model.M for blk in model.B for slot in model.S
    )
    if leftover_penalty:
        obj_expr -= leftover_penalty * sum(model.leftover[blk] for blk in model.B)
    if landing_weight:
        obj_expr -= landing_weight * sum(
            model.landing_slack[landing_id, day] for landing_id in model.Landing for day in model.D
        )

    model.objective = pyo.Objective(expr=obj_expr, sense=pyo.maximize)

    return model
