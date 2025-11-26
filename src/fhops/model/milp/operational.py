"""Operational MILP builder (day × shift grid)."""

from __future__ import annotations

import pyomo.environ as pyo

from fhops.model.milp.data import OperationalMilpBundle

__all__ = ["build_operational_model"]


def build_operational_model(bundle: OperationalMilpBundle) -> pyo.ConcreteModel:
    """Construct a Pyomo model from an :class:`OperationalMilpBundle`."""

    model = pyo.ConcreteModel()

    model.M = pyo.Set(initialize=bundle.machines)
    model.B = pyo.Set(initialize=bundle.blocks)
    model.D = pyo.Set(initialize=bundle.days)
    model.S = pyo.Set(initialize=bundle.shifts, dimen=2)

    window_lookup = bundle.windows
    availability_day = bundle.availability_day
    availability_shift = bundle.availability_shift

    def _within_window(block_id: str, day: int) -> bool:
        earliest, latest = window_lookup[block_id]
        return earliest <= day <= latest

    def _is_available(machine_id: str, day: int, shift_id: str) -> bool:
        key = (machine_id, day, shift_id)
        if key in availability_shift:
            return availability_shift[key] == 1
        return availability_day.get((machine_id, day), 1) == 1

    model.x = pyo.Var(model.M, model.B, model.S, domain=pyo.Binary)
    model.prod = pyo.Var(model.M, model.B, model.S, domain=pyo.NonNegativeReals)

    # Production limited by assignment & per-block productivity
    def prod_cap_rule(mdl, mach, blk, day, shift_id):
        rate = bundle.production_rates.get((mach, blk), 0.0)
        return mdl.prod[mach, blk, (day, shift_id)] <= rate * mdl.x[mach, blk, (day, shift_id)]

    model.production_cap = pyo.Constraint(model.M, model.B, model.S, rule=prod_cap_rule)

    # Machine works on at most one block per slot and only when available
    def machine_capacity_rule(mdl, mach, day, shift_id):
        if not _is_available(mach, day, shift_id):
            return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) == 0
        return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) <= 1

    model.machine_capacity = pyo.Constraint(model.M, model.S, rule=machine_capacity_rule)

    # Window feasibility: zero assignments outside block window
    def window_rule(mdl, mach, blk, day, shift_id):
        if _within_window(blk, day):
            return pyo.Constraint.Skip
        return mdl.x[mach, blk, (day, shift_id)] == 0

    model.block_windows = pyo.Constraint(model.M, model.B, model.S, rule=window_rule)

    # Block balance ensures we meet required work (leftover ignored for now)
    def block_balance_rule(mdl, blk):
        total_prod = sum(mdl.prod[mach, blk, slot] for mach in mdl.M for slot in model.S)
        return total_prod >= bundle.work_required[blk]

    model.block_balance = pyo.Constraint(model.B, rule=block_balance_rule)

    # Landing capacity (per day) optional constraint
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
                for shift_day, shift_id in mdl.S:
                    if shift_day == day:
                        expr += mdl.x[mach, blk, (shift_day, shift_id)]
        return expr <= capacity * len(bundle.machines)

    model.landing_capacity = pyo.Constraint(
        bundle.landing_capacity.keys(), model.D, rule=landing_capacity_rule
    )

    prod_weight = bundle.objective_weights.production
    model.objective = pyo.Objective(
        expr=prod_weight
        * sum(
            model.prod[mach, blk, slot] for mach in model.M for blk in model.B for slot in model.S
        ),
        sense=pyo.maximize,
    )

    return model
