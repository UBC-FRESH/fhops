#!/usr/bin/env python3
"""Anneal per-block phase shifts for the Gavin MDWR group cohort.

Event volumes are held fixed; only cut years move within a 0-39 year delay.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
FLOOR = 10316.89
CEILING = 30950.67
PERIODS = 30
PHASES = range(40)


def precompute(events: pd.DataFrame) -> dict[int, np.ndarray]:
    by_block: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for row in events.itertuples(index=False):
        by_block[int(row.block_id)].append((int(row.entry_year), float(row.volume_m3)))
    table: dict[int, np.ndarray] = {}
    for block, values in by_block.items():
        matrix = np.zeros((len(PHASES), PERIODS))
        for phase in PHASES:
            for year, volume in values:
                matrix[phase, min(PERIODS - 1, (year + phase) // 10)] += volume
        table[block] = matrix
    return table


def score(total: np.ndarray) -> float:
    below = np.maximum(0.0, FLOOR - total)
    above = np.maximum(0.0, total - CEILING)
    return float((below**2 + above**2).sum())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cuts", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_cuts_legal_s40.csv")
    parser.add_argument("--phases-out", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_anneal.csv")
    parser.add_argument("--summary-out", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_anneal.json")
    parser.add_argument("--iterations", type=int, default=60000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    events = pd.read_csv(args.cuts)
    events = events.loc[events["ba_ok"]].copy()
    events["block_id"] = events["block_id"].astype(int)
    events["entry_year"] = events["entry_year"].astype(int)
    table = precompute(events)
    blocks = sorted(table)
    rng = random.Random(args.seed)
    phases = {block: rng.randrange(40) for block in blocks}
    total = sum((table[block][phases[block]] for block in blocks), np.zeros(PERIODS))
    current = score(total)
    best_total = total.copy()
    best_score = current
    best_phases = dict(phases)
    temperature = 5e9
    for iteration in range(args.iterations):
        block = rng.choice(blocks)
        old = phases[block]
        new = rng.randrange(40)
        if new == old:
            continue
        trial_total = total - table[block][old] + table[block][new]
        trial = score(trial_total)
        delta = trial - current
        if delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9)):
            phases[block] = new
            total = trial_total
            current = trial
            if current < best_score:
                best_score = current
                best_total = total.copy()
                best_phases = dict(phases)
        temperature *= 0.99985
    # coordinate descent polish
    changed = True
    while changed:
        changed = False
        for block in blocks:
            old = best_phases[block]
            base = best_total - table[block][old]
            local = best_score
            local_phase = old
            for phase in PHASES:
                candidate = base + table[block][phase]
                candidate_score = score(candidate)
                if candidate_score < local - 1e-9:
                    local = candidate_score
                    local_phase = phase
            if local_phase != old:
                best_phases[block] = local_phase
                best_total = base + table[block][local_phase]
                best_score = local
                changed = True
    frame = pd.DataFrame({"block_id": blocks, "phase_years": [best_phases[b] for b in blocks]})
    frame.to_csv(args.phases_out, index=False)
    summary = {
        "events": int(len(events)),
        "blocks": int(len(blocks)),
        "total_volume_m3": round(float(best_total.sum()), 3),
        "mean_10y_volume_m3": round(float(best_total.mean()), 3),
        "min_10y_volume_m3": round(float(best_total.min()), 3),
        "max_10y_volume_m3": round(float(best_total.max()), 3),
        "periods_in_band": int(((best_total >= FLOOR) & (best_total <= CEILING)).sum()),
        "objective": round(float(best_score), 3),
        "iterations": args.iterations,
        "seed": args.seed,
        "caveat": "Cut-year shift only; event volumes and final state fixed.",
    }
    args.summary_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
