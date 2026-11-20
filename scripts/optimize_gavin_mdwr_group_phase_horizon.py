#!/usr/bin/env python3
"""Horizon-aware per-block phase screen for the Gavin MDWR group cohort.

Every shifted cut must remain before year 300; event volumes are fixed.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
FLOOR = 10316.89
CEILING = 30950.67
PERIODS = 30


def vectors(events: pd.DataFrame, phases: dict[int, int]) -> dict[int, np.ndarray]:
    out: dict[int, np.ndarray] = defaultdict(lambda: np.zeros(PERIODS))
    for row in events.itertuples(index=False):
        period = (int(row.entry_year) + phases.get(int(row.block_id), 0)) // 10
        if 0 <= period < PERIODS:
            out[int(row.block_id)][period] += float(row.volume_m3)
    return out


def score(total: np.ndarray) -> float:
    return float((np.maximum(0.0, FLOOR - total) ** 2 + np.maximum(0.0, total - CEILING) ** 2).sum())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cuts", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_cuts_legal_s40.csv")
    parser.add_argument("--phases-out", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_horizon.csv")
    parser.add_argument("--summary-out", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_horizon.json")
    args = parser.parse_args()
    events = pd.read_csv(args.cuts)
    events = events.loc[events["ba_ok"]].copy()
    events["block_id"] = events["block_id"].astype(int)
    events["entry_year"] = events["entry_year"].astype(int)
    blocks = sorted(events.block_id.unique())
    max_year = events.groupby("block_id")["entry_year"].max().to_dict()
    phases = {b: 0 for b in blocks}
    vectors_by_block = vectors(events, phases)
    total = sum(vectors_by_block.values(), np.zeros(PERIODS))
    best = score(total)
    candidates = {b: tuple(range(0, min(119, 299 - int(max_year[b])) + 1)) for b in blocks}
    for _ in range(4):
        changed = False
        for block in blocks:
            old = phases[block]
            base = total - vectors_by_block[block]
            local_best = best
            local_phase = old
            for phase in candidates[block]:
                trial = dict(phases)
                trial[block] = phase
                block_vec = vectors(events[events.block_id == block], trial)[block]
                candidate = base + block_vec
                candidate_score = score(candidate)
                if candidate_score < local_best - 1e-9:
                    local_best = candidate_score
                    local_phase = phase
            if local_phase != old:
                phases[block] = local_phase
                vectors_by_block[block] = vectors(events[events.block_id == block], phases)[block]
                total = base + vectors_by_block[block]
                best = local_best
                changed = True
        if not changed:
            break
    frame = pd.DataFrame({"block_id": blocks, "phase_years": [phases[b] for b in blocks], "max_phase_years": [max(candidates[b]) if candidates[b] else 0 for b in blocks]})
    frame.to_csv(args.phases_out, index=False)
    summary = {
        "events": int(len(events)),
        "blocks": int(len(blocks)),
        "total_volume_m3": round(float(total.sum()), 3),
        "mean_10y_volume_m3": round(float(total.mean()), 3),
        "min_10y_volume_m3": round(float(total.min()), 3),
        "max_10y_volume_m3": round(float(total.max()), 3),
        "periods_in_band": int(((total >= FLOOR) & (total <= CEILING)).sum()),
        "objective": round(float(score(total)), 3),
        "horizon_years": 300,
        "caveat": "Horizon-aware cut-year shift only; event volumes fixed.",
    }
    args.summary_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
