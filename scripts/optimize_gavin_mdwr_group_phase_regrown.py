#!/usr/bin/env python3
"""Greedy phase optimisation with regrown first-cut volumes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
FLOOR = 10316.89
CEILING = 30950.67
PERIODS = 30


def value_at(frame: pd.DataFrame | None, age: float) -> float:
    if frame is None or frame.empty:
        return 0.0
    clipped = min(max(float(age), float(frame.x.min())), float(frame.x.max()))
    return float(frame.loc[int((frame.x - clipped).abs().idxmin()), "y"])


def score(vector: np.ndarray) -> float:
    return float((np.maximum(0, FLOOR - vector) ** 2 + np.maximum(0, vector - CEILING) ** 2).sum())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-group-matrix-legal-s40")
    parser.add_argument("--cuts", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_cuts_legal_s40.csv")
    parser.add_argument("--phases", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_horizon.csv")
    parser.add_argument("--mapping", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_matrix_legal_s40_map.csv")
    parser.add_argument("--groups", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_groups_all_legal_s40.csv")
    parser.add_argument("--out-phases", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_regrown_opt.csv")
    parser.add_argument("--out-summary", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_regrown_opt.json")
    parser.add_argument("--restarts", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    cuts = pd.read_csv(args.cuts)
    cuts = cuts.loc[cuts.ba_ok].copy()
    mapping = pd.read_csv(args.mapping)
    key = {(int(r.source_block_id), int(r.group_index)): int(r.group_block_id) for r in mapping.itertuples(index=False)}
    groups = pd.read_csv(args.groups).set_index("group_id")
    fragments = pd.read_parquet(args.matrix / "fragments.parquet").set_index("block_id")
    features = pd.read_parquet(args.matrix / "features.parquet")
    curves = pd.read_parquet(args.matrix / "curves.parquet")
    curve_by_id = {int(cid): frame.sort_values("x") for cid, frame in curves.groupby("curve_id")}
    feature_by_track = {(int(r.track_id), str(r.label)): int(r.curve_id) for r in features.itertuples(index=False)}
    first_cut = cuts.sort_values(["group_id", "entry_year"]).drop_duplicates("group_id").set_index("group_id")["entry_year"].to_dict()

    blocks = sorted(cuts.block_id.unique())
    max_year = cuts.groupby("block_id")["entry_year"].max().to_dict()
    vectors: dict[int, dict[int, np.ndarray]] = {}
    for block in blocks:
        block_rows = cuts[cuts.block_id == block]
        max_phase = min(119, 299 - int(max_year[block]))
        candidates = range(0, max(0, max_phase) + 1)
        block_vectors = {}
        for phase in candidates:
            arr = np.zeros(PERIODS)
            for row in block_rows.itertuples(index=False):
                period = (int(row.entry_year) + phase) // 10
                if not 0 <= period < PERIODS:
                    continue
                if int(first_cut[int(row.group_id)]) == int(row.entry_year):
                    gid = int(row.group_id)
                    mg = key.get((int(row.block_id), int(groups.loc[gid, "group_index"])))
                    if mg is not None and mg in fragments.index:
                        track = int(fragments.loc[mg, "track_id"])
                        age = float(fragments.loc[mg, "age"]) + int(row.entry_year) + phase
                        cid = feature_by_track.get((track, "feature.yield.managed.total"))
                        volume = value_at(curve_by_id.get(int(cid)) if cid else None, age) * float(row.area_ha)
                    else:
                        volume = float(row.volume_m3)
                else:
                    volume = float(row.volume_m3)
                arr[period] += volume
            block_vectors[phase] = arr
        vectors[block] = block_vectors
    import random
    rng = random.Random(args.seed)
    initial = pd.read_csv(args.phases).set_index("block_id")["phase_years"].to_dict()
    initial = {int(b): int(initial.get(int(b), 0)) for b in blocks}
    starts = [initial]
    for _ in range(args.restarts - 1):
        starts.append({b: rng.choice(list(vectors[b].keys())) for b in blocks})
    best_phases = None
    best_total = None
    best = float("inf")
    for phases in starts:
        phases = {b: min(phases[b], max(vectors[b])) for b in blocks}
        total = sum((vectors[b][phases[b]] for b in blocks), np.zeros(PERIODS))
        current = score(total)
        for _ in range(4):
            changed = False
            for block in blocks:
                old = phases[block]
                base = total - vectors[block][old]
                local = current
                local_phase = old
                for phase, vec in vectors[block].items():
                    cand = base + vec
                    val = score(cand)
                    if val < local - 1e-9:
                        local = val
                        local_phase = phase
                if local_phase != old:
                    phases[block] = local_phase
                    total = base + vectors[block][local_phase]
                    current = local
                    changed = True
            if not changed:
                break
        if current < best:
            best = current
            best_total = total.copy()
            best_phases = dict(phases)
    phases = best_phases
    total = best_total
    frame = pd.DataFrame({"block_id": blocks, "phase_years": [phases[b] for b in blocks]})
    frame.to_csv(args.out_phases, index=False)
    summary = {
        "events": int(len(cuts)),
        "blocks": len(blocks),
        "total_volume_m3": round(float(total.sum()), 3),
        "mean_10y_volume_m3": round(float(total.mean()), 3),
        "min_10y_volume_m3": round(float(total.min()), 3),
        "max_10y_volume_m3": round(float(total.max()), 3),
        "periods_in_band": int(((total >= FLOOR) & (total <= CEILING)).sum()),
        "objective": round(float(score(total)), 3),
        "caveat": "First cut regrown at shifted age; later cuts keep interval volumes.",
    }
    args.out_summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
