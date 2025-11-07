from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

from fhops.scenario.contract import Problem


def build_model(pb: Problem) -> pyo.ConcreteModel:
    """
    Builds a Pyomo optimization model based on the given problem instance.

    Args:
        pb (Problem): An instance of the Problem class containing the necessary
                      data and scenario information.

    Returns:
        pyo.ConcreteModel: A Pyomo ConcreteModel representing the optimization
                           problem which aims to maximize total production
                           subject to various constraints such as machine
                           availability, production capacity, block completion,
                           and landing capacity.
    """
    sc = pb.scenario

    M = [m.id for m in sc.machines]
    B = [b.id for b in sc.blocks]
    D = list(pb.days)

    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    work_required = {block.id: block.work_required for block in sc.blocks}
    landing_capacity = {landing.id: landing.daily_capacity for landing in sc.landings}

    # Availability: 1 if machine available on day
    avail = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}

    # Windows: blocks may only be worked between [es, lf]
    windows = {b_id: sc.window_for(b_id) for b_id in sc.block_ids()}

    m = pyo.ConcreteModel()
    m.M = pyo.Set(initialize=M)
    m.B = pyo.Set(initialize=B)
    m.D = pyo.Set(initialize=D)

    def within_window(b, d):
        es, lf = windows[b]
        return 1 if (d >= es and d <= lf) else 0

    # Decision variables
    m.x = pyo.Var(m.M, m.B, m.D, domain=pyo.Binary)  # assign machine to block on day
    m.prod = pyo.Var(m.M, m.B, m.D, domain=pyo.NonNegativeReals)  # work produced that day

    # Objective: maximize total production (bounded by work_required)
    m.obj = pyo.Objective(
        expr=sum(m.prod[mach, blk, day] for mach in m.M for blk in m.B for day in m.D),
        sense=pyo.maximize,
    )

    # Each machine at most one block per day, and respect availability
    def mach_one_block_rule(mdl, mach, day):
        a = avail.get((mach, int(day)), 1)
        return sum(mdl.x[mach, blk, day] for blk in mdl.B) <= a

    m.mach_one_block = pyo.Constraint(m.M, m.D, rule=mach_one_block_rule)

    # Production limited by rate if assigned; zero otherwise or out of window
    def prod_cap_rule(mdl, mach, blk, day):
        r = rate.get((mach, blk), 0.0)
        w = within_window(blk, int(day))
        return mdl.prod[mach, blk, day] <= r * mdl.x[mach, blk, day] * w

    m.prod_cap = pyo.Constraint(m.M, m.B, m.D, rule=prod_cap_rule)

    # Block completion: cumulative production cannot exceed work_required
    def block_cum_rule(mdl, blk):
        return sum(mdl.prod[mach, blk, day] for mach in m.M for day in m.D) <= work_required[blk]

    m.block_cum = pyo.Constraint(m.B, rule=block_cum_rule)

    # Landing capacity per day: sum of active assignments at that landing <= capacity
    blocks_by_landing: dict[str, list[str]] = defaultdict(list)
    for block in sc.blocks:
        blocks_by_landing[block.landing_id].append(block.id)

    def landing_cap_rule(mdl, landing_id, day):
        assignments = sum(
            mdl.x[mach, blk, day] for mach in m.M for blk in blocks_by_landing.get(landing_id, [])
        )
        capacity = landing_capacity.get(landing_id, 0)
        return assignments <= capacity

    m.L = pyo.Set(initialize=list(landing_capacity.keys()))
    m.landing_cap = pyo.Constraint(m.L, m.D, rule=landing_cap_rule)

    return m
