from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pandas as pd

from fhops.scenario.contract import Problem


@dataclass
class Schedule:
    """
    Represents a schedule for machine assignments.

    Attributes:
    plan (dict[str, dict[int, str | None]]):
            A dictionary where the key is a machine ID (str) and the value is another dictionary.
            The nested dictionary's key is a day (int) and the value is a block_id (str) that machine is assigned to on that day, or None if no assignment is made.
    """

    plan: dict[str, dict[int, str | None]]


def _init_greedy(pb: Problem) -> Schedule:
    """
    Initializes a schedule using a greedy algorithm.

    The algorithm assigns blocks to machines for each day based on availability,
    production rates, remaining work, and the specified scheduling windows. It
    prioritizes assignments to the block with the highest production rate that
    still requires work, ensuring that the assignments are within the permissible
    scheduling window.

    Args:
        pb (Problem): The problem instance containing the scenario with blocks,
                      machines, production rates, and scheduling constraints.

    Returns:
        Schedule: A Schedule object representing the machine assignment plan
                  for the given problem instance.
    """
    sc = pb.scenario
    # remaining work per block
    remaining = {b.id: b.work_required for b in sc.blocks}
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    avail = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    windows = {b_id: sc.window_for(b_id) for b_id in sc.block_ids()}

    plan: dict[str, dict[int, str | None]] = {
        machine.id: {day: None for day in pb.days} for machine in sc.machines
    }
    for d in pb.days:
        for m in sc.machines:
            if avail.get((m.id, d), 1) == 0:
                continue
            # pick best block by highest rate with remaining work and within window
            cands: list[tuple[float, str]] = []
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
    """
    Evaluates the current scheduling solution by calculating a score based on
    the given problem instance and schedule.

    The evaluation process considers the landing capacity constraints, scheduling
    windows for blocks, and the production rates. Assignments that violate
    these constraints receive penalties, while valid assignments contribute
    positively to the score.

    Args:
        pb (Problem): The problem instance containing scenario details such as blocks,
                      machines, production rates, schedules, landings, and capacity constraints.
        sched (Schedule): The current scheduling solution, mapping machines to block assignments.

    Returns:
        float: The score representing the quality of the schedule, where a higher score
               indicates a better schedule with fewer or no constraint violations.
    """
    sc = pb.scenario
    remaining = {b.id: b.work_required for b in sc.blocks}
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    windows = {b_id: sc.window_for(b_id) for b_id in sc.block_ids()}
    landing_of = {b.id: b.landing_id for b in sc.blocks}
    landing_cap = {landing.id: landing.daily_capacity for landing in sc.landings}

    score = 0.0
    for d in pb.days:
        # landing capacity check: penalize violations heavily
        used = {landing.id: 0 for landing in sc.landings}
        for m in sc.machines:
            blk = sched.plan[m.id][d]
            if blk is None:
                continue
            es, lf = windows[blk]
            if d < es or d > lf:
                continue  # assignment illegal -> contributes nothing
            if remaining[blk] <= 1e-9:
                continue
            landing_id = landing_of[blk]
            used[landing_id] += 1
            if used[landing_id] > landing_cap[landing_id]:
                score -= 1000.0  # violation
                continue
            r = rate.get((m.id, blk), 0.0)
            prod = min(r, remaining[blk])
            remaining[blk] -= prod
            score += prod
    return score


def _neighbors(pb: Problem, sched: Schedule):
    """
    Generates neighboring schedule solutions for the given problem and current schedule.

    The function explores the solution space by generating new schedules through
    small modifications to the current schedule. Two types of modifications are
    performed:
    1. Swapping assignments for two machines on the same day.
    2. Moving a job to a different day for one machine.

    Args:
        pb (Problem): The problem instance containing scenario details such as blocks,
                      machines, production rates, schedules, landings, and capacity constraints.
        sched (Schedule): The current scheduling solution, mapping machines to block assignments.

    Yields:
        Schedule: A neighboring schedule with a slight modification from the current one.
    """
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
    """
    Solves the scheduling problem using a simulated annealing approach.

    The function iteratively improves the schedule by exploring neighboring
    solutions, accepting changes based on a probabilistic criterion related
    to temperature, which gradually decreases over iterations. The goal is
    to find a schedule with the best possible score according to the given
    evaluation function.

    Args:
        pb (Problem): The problem instance containing the scenario with blocks,
                      machines, production rates, schedules, landings, and constraints.
        iters (int): The number of iterations to perform in the annealing process.
                     Default is 2000.
        seed (int): A seed for the random number generator to ensure reproducibility
                    of results. Default is 42.

    Returns:
        Dict[str, Any]: A dictionary containing the objective score ('objective')
                        and a DataFrame ('assignments') detailing the machine
                        assignments with columns for machine ID, block ID, day,
                        and assignment status.
    """
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
        T = T0 * 0.995**k
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
    df = pd.DataFrame(rows).sort_values(["day", "machine_id", "block_id"])
    return {"objective": float(best_score), "assignments": df}
