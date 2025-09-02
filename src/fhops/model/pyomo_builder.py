from __future__ import annotations
from typing import Dict, Tuple
from collections import defaultdict

import pyomo.environ as pyo
from fhops.core.types import Problem

def build_model(pb: Problem) -> pyo.ConcreteModel:
    sc = pb.scenario

    M = [m.id for m in sc.machines]
    B = [b.id for b in sc.blocks]
    D = list(pb.days)

    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    work_required = {b.id: b.work_required for b in sc.blocks}
    landing_of = {b.id: b.landing_id for b in sc.blocks}
    landing_capacity = {l.id: l.daily_capacity for l in sc.landings}

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
    blocks_by_landing = defaultdict(list)
    for b in sc.blocks:
        blocks_by_landing[b.landing_id].append(b.id)
    def landing_cap_rule(mdl, landing, day):
        return sum(mdl.x[mach, blk, day] for mach in m.M for blk in blocks_by_landing[landing]) <= landing_capacity[landing]
    m.landing_cap = pyo.Constraint(list(blocks_by_landing.keys()), m.D, rule=landing_cap_rule)

    return m
