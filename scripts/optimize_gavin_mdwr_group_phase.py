#!/usr/bin/env python3
"""Greedy per-block phase shift for the Gavin MDWR group cohort.

This is a scheduling screen, not a volume regrowth model. It shifts each
block's cohort cut years later by 0-35 years, keeps the event volumes fixed,
and minimises the squared distance outside the interim even-flow band.
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


def block_vectors(events: pd.DataFrame, phases: dict[int, int]) -> dict[int, np.ndarray]:
    vectors: dict[int, np.ndarray] = defaultdict(lambda: np.zeros(PERIODS))
    for row in events.itertuples(index=False):
        period = min(PERIODS - 1, max(0, (int(row.entry_year) + phases.get(int(row.block_id), 0)) // 10))
        vectors[int(row.block_id)][period] += float(row.volume_m3)
    return vectors


def score(vector: np.ndarray) -> float:
    below = np.maximum(0.0, FLOOR - vector)
    above = np.maximum(0.0, vector - CEILING)
    return float((below**2 + above**2).sum())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cuts", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_cuts_legal_s40.csv")
    parser.add_argument("--phases-out", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase.csv")
    parser.add_argument("--summary-out", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_summary.json")
    args = parser.parse_args()

    events = pd.read_csv(args.cuts)
    events = events.loc[events["ba_ok"]].copy()
    events["block_id"] = events["block_id"].astype(int)
    events["entry_year"] = events["entry_year"].astype(int)
    blocks = sorted(events["block_id"].unique())
    phases = {block: 0 for block in blocks}
    vectors = block_vectors(events, phases)
    total = sum(vectors.values())
    best = score(total)

    candidates = tuple(range(0, 40))
    for _ in range(4):
        changed = False
        for block in blocks:
            current_phase = phases[block]
            base = total - vectors[block]
            best_phase = current_phase
            best_local = best
            for phase in candidates:
                trial = dict(phases)
                trial[block] = phase
                block_vec = block_vectors(events[events.block_id == block], trial)[block]
                candidate_total = base + block_vec
                candidate_score = score(candidate_total)
                if candidate_score < best_local - 1e-9:
                    best_local = candidate_score
                    best_phase = phase
            if best_phase != current_phase:
                phases[block] = best_phase
                vectors[block] = block_vectors(events[events.block_id == block], phases)[block]
                total = base + vectors[block]
                best = best_local
                changed = True
        if not changed:
            break

    phase_frame = pd.DataFrame({"block_id": blocks, "phase_years": [phases[b] for b in blocks]})
    phase_frame.to_csv(args.phases_out, index=False)
    summary = {
        "events": int(len(events)),
        "blocks": int(len(blocks)),
        "total_volume_m3": round(float(total.sum()), 3),
        "mean_10y_volume_m3": round(float(total.mean()), 3),
        "min_10y_volume_m3": round(float(total.min()), 3),
        "max_10y_volume_m3": round(float(total.max()), 3),
        "band_floor": FLOOR,
        "band_ceiling": CEILING,
        "periods_in_band": int(((total >= FLOOR) & (total <= CEILING)).sum()),
        "objective": round(float(score(total)), 3),
        "phase_counts": {str(int(k)): int(v) for k, v in phase_frame["phase_years"].value_counts().sort_index().items()},
        "caveat": "Per-block cut-year shift only; event volumes and final state are held fixed.",
    }
    args.summary_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
