from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import math
import pandas as pd

from fhops.core.types import Problem

@dataclass
class Schedule:
    # schedule[machine][day] = block_id or None
    plan: Dict[str, Dict[int, Optional[str]]]

def _init_greedy(pb: Problem) -> Schedule:
    sc = pb.scenario
    # remaining work per block
    remaining = {b.id: b.work_required for b in sc.blocks}
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    avail = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    windows = {b.id: sc.window_for(b.id) for b in sc.block_ids()}

    plan = {m.id: {d: None for d in pb.days} for m in sc.machines}
    for d in pb.days:
        for m in sc.machines:
            if avail.get((m.id, d), 1) == 0:
                continue
            # pick best block by highest rate with remaining work and within window
            cands = []
            for b in sc.blocks:
                es, lf = windows[b.id]
                if d < es or d > lf or remaining[b.id] <= 1e-9:
                    continue
                r = rate.get((m.id, b.id), 0.0)
                if r > 0:
                    cands.append((r, b.id))
            if cands:
                cands.sort(reverse=True)
                _, blk = cands[0]
                plan[m.id][d] = blk
                remaining[blk] = max(0.0, remaining[blk] - rate.get((m.id, blk), 0.0))
    return Schedule(plan=plan)

def _evaluate(pb: Problem, sched: Schedule) -> float:
    sc = pb.scenario
    remaining = {b.id: b.work_required for b in sc.blocks}
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    windows = {b.id: sc.window_for(b.id) for b in sc.block_ids()}
    landing_of = {b.id: b.landing_id for b in sc.blocks}
    landing_cap = {l.id: l.daily_capacity for l in sc.landings}

    score = 0.0
    for d in pb.days:
        # landing capacity check: penalize violations heavily
        used = {l.id: 0 for l in sc.landings}
        for m in sc.machines:
            blk = sched.plan[m.id][d]
            if blk is None:
                continue
            es, lf = windows[blk]
            if d < es or d > lf:
                continue  # assignment illegal -> contributes nothing
            if remaining[blk] <= 1e-9:
                continue
            l = landing_of[blk]
            used[l] += 1
            if used[l] > landing_cap[l]:
                score -= 1000.0  # violation
                continue
            r = rate.get((m.id, blk), 0.0)
            prod = min(r, remaining[blk])
            remaining[blk] -= prod
            score += prod
    return score

def _neighbors(pb: Problem, sched: Schedule):
    sc = pb.scenario
    machines = [m.id for m in sc.machines]
    days = list(pb.days)
    # swap two assignments
    m1, m2 = random.sample(machines, k=2) if len(machines) >= 2 else (machines[0], machines[0])
    d = random.choice(days)
    n = Schedule(plan={m: plan.copy() for m, plan in sched.plan.items()})
    n.plan[m1][d], n.plan[m2][d] = n.plan[m2][d], n.plan[m1][d]
    yield n
    # move a job to a different day for one machine
    m = random.choice(machines)
    d1, d2 = random.sample(days, k=2) if len(days) >= 2 else (days[0], days[0])
    n2 = Schedule(plan={m_: plan.copy() for m_, plan in sched.plan.items()})
    n2.plan[m][d2] = n2.plan[m][d1]
    n2.plan[m][d1] = None
    yield n2

def solve_sa(pb: Problem, iters: int = 2000, seed: int = 42):
    random.seed(seed)
    cur = _init_greedy(pb)
    cur_score = _evaluate(pb, cur)
    best = cur
    best_score = cur_score

    T0 = max(1.0, best_score / 10.0)
    T = T0
    for k in range(1, iters + 1):
        accepted = False
        for n in _neighbors(pb, cur):
            ns = _evaluate(pb, n)
            delta = ns - cur_score
            if delta >= 0 or random.random() < math.exp(delta / max(1e-6, T)):
                cur, cur_score = n, ns
                accepted = True
                break
        if cur_score > best_score:
            best, best_score = cur, cur_score
        T = T0 * 0.995 ** k
        if not accepted and k % 100 == 0:
            # random restart
            cur = _init_greedy(pb)
            cur_score = _evaluate(pb, cur)

    # Convert to DataFrame
    rows = []
    for m, plan in best.plan.items():
        for d, b in plan.items():
            if b is not None:
                rows.append({"machine_id": m, "block_id": b, "day": int(d), "assigned": 1})
    df = pd.DataFrame(rows).sort_values(["day","machine_id","block_id"])
    return {"objective": float(best_score), "assignments": df}
