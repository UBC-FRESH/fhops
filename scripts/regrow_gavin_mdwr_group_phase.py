#!/usr/bin/env python3
"""Regrow the shifted Gavin MDWR group cut volumes at their new ages.

Only the first cut for each group is delayed by the phase. Later cuts keep the
same interval and therefore the same age; their ledger volumes are unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")


def value_at(frame: pd.DataFrame, age: float) -> float:
    if frame.empty:
        return 0.0
    clipped = min(max(float(age), float(frame.x.min())), float(frame.x.max()))
    idx = int((frame.x - clipped).abs().idxmin())
    return float(frame.loc[idx, "y"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-group-matrix-legal-s40")
    parser.add_argument("--cuts", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_cuts_legal_s40.csv")
    parser.add_argument("--phases", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_horizon.csv")
    parser.add_argument("--mapping", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_matrix_legal_s40_map.csv")
    parser.add_argument("--groups", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_groups_all_legal_s40.csv")
    parser.add_argument("--out", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_regrown.csv")
    parser.add_argument("--summary", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_phase_regrown.json")
    args = parser.parse_args()

    cuts = pd.read_csv(args.cuts)
    cuts = cuts.loc[cuts["ba_ok"]].copy()
    phases = pd.read_csv(args.phases).set_index("block_id")["phase_years"]
    mapping = pd.read_csv(args.mapping)
    mapping_key = {(int(r.source_block_id), int(r.group_index)): int(r.group_block_id) for r in mapping.itertuples(index=False)}
    groups = pd.read_csv(args.groups).set_index("group_id")
    fragments = pd.read_parquet(args.matrix / "fragments.parquet").set_index("block_id")
    tracks = pd.read_parquet(args.matrix / "tracks.parquet").set_index("track_id")
    treatments = pd.read_parquet(args.matrix / "treatments.parquet")
    features = pd.read_parquet(args.matrix / "features.parquet")
    curves = pd.read_parquet(args.matrix / "curves.parquet")
    curve_by_id = {int(cid): frame.sort_values("x") for cid, frame in curves.groupby("curve_id")}
    feature_by_track = {(int(r.track_id), str(r.label)): int(r.curve_id) for r in features.itertuples(index=False)}
    plant_by_track = {int(r.track_id): int(r.new_track) for r in treatments.itertuples(index=False) if str(r.treatment) == "CC"}

    first_cut = cuts.sort_values(["group_id", "entry_year"]).drop_duplicates("group_id").set_index("group_id")["entry_year"].to_dict()
    rows: list[dict[str, object]] = []
    for row in cuts.itertuples(index=False):
        block_id = int(row.block_id)
        group_id = int(row.group_id)
        phase = int(phases.get(block_id, 0))
        year = int(row.entry_year) + phase
        matrix_group = mapping_key.get((block_id, int(groups.loc[group_id, "group_index"])))
        if matrix_group is None or matrix_group not in fragments.index:
            rows.append(row._asdict() | {"entry_year": year, "regrown": False})
            continue
        initial_track = int(fragments.loc[matrix_group, "track_id"])
        initial_age = float(fragments.loc[matrix_group, "age"])
        is_first = int(first_cut[group_id]) == int(row.entry_year)
        if is_first:
            track = initial_track
            age = initial_age + year
        else:
            track = plant_by_track.get(initial_track, initial_track)
            age = float(row.age)
        volume_curve = feature_by_track.get((track, "feature.yield.managed.total"))
        ba_curve = feature_by_track.get((track, "feature.ba.managed.total"))
        volume_frame = curve_by_id.get(int(volume_curve)) if volume_curve else None
        ba_frame = curve_by_id.get(int(ba_curve)) if ba_curve else None
        volume = value_at(volume_frame, age) * float(row.area_ha) if volume_frame is not None else float(row.volume_m3)
        ba = value_at(ba_frame, age) * float(row.area_ha) if ba_frame is not None else float(row.ba_m2)
        rows.append({
            "block_id": block_id,
            "group_id": group_id,
            "cohort": int(row.cohort),
            "entry_index": int(row.entry_index),
            "entry_year": year,
            "age": round(age, 3),
            "area_ha": float(row.area_ha),
            "volume_m3": round(volume, 3),
            "ba_m2": round(ba, 3),
            "ba_ok": bool(row.ba_ok),
            "regrown": True,
        })
    frame = pd.DataFrame(rows)
    frame.to_csv(args.out, index=False)
    period = frame.groupby((frame.entry_year // 10) * 10)["volume_m3"].sum()
    summary = {
        "events": int(len(frame)),
        "total_volume_m3": round(float(frame.volume_m3.sum()), 3),
        "mean_10y_volume_m3": round(float(period.reindex(range(0, 300, 10), fill_value=0).mean()), 3),
        "min_10y_volume_m3": round(float(period.reindex(range(0, 300, 10), fill_value=0).min()), 3),
        "max_10y_volume_m3": round(float(period.reindex(range(0, 300, 10), fill_value=0).max()), 3),
        "periods": int(len(period)),
        "regrown_events": int(frame.regrown.sum()),
        "caveat": "First cut delayed by phase and regrown on the group curve; later cuts keep interval ages.",
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
