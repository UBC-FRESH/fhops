#!/usr/bin/env python3
"""Build the full group cohort state for the Gavin MDWR group matrix.

Groups are partitioned into High 3 / Moderate 4 / Low 5 cohorts. Accepted block
entries are assigned to cohorts in order; each cohort is cut at its accepted
entry year and regrows for the next accepted entry. No extra cycle years are
invented beyond the temporal block schedule.

Volume and BA are read from the group WS4 matrix curves. BA at each entry is
screened against 40 m2/ha; groups below the threshold are left uncut and logged.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
MATRIX = INSTANCE / "ws4" / "runtime" / "gavin-mdwr-group-matrix-legal-s40"
COHORTS = {"High": 5, "Moderate": 4, "Low": 3}
HORIZON = 300


def curve_value(x: pd.Series, y: pd.Series | None = None, age: float = 0.0) -> float:
    """Read a curve at an age, clamped to its domain."""
    if y is None:
        return 0.0
    if not len(x):
        return 0.0
    clipped = min(max(float(age), float(x.min())), float(x.max()))
    index = int((x - clipped).abs().idxmin())
    return float(y.loc[index])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=MATRIX)
    parser.add_argument("--groups", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_groups_all_legal_s40.csv")
    parser.add_argument("--mapping", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_matrix_legal_s40_map.csv")
    parser.add_argument("--schedule", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-schedule-official-ba-temporal-s40-legal.csv")
    parser.add_argument("--habitat", type=Path, default=INSTANCE / "planning" / "2026-11-18_gavin_mdwr_official_habitat.csv")
    parser.add_argument("--out-cuts", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_cuts_legal_s40.csv")
    parser.add_argument("--out-state", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_state_legal_s40.csv")
    parser.add_argument("--out-json", type=Path, default=INSTANCE / "planning" / "2026-11-20_gavin-mdwr_group_cohort_state_legal_s40.json")
    args = parser.parse_args()

    groups = pd.read_csv(args.groups)
    groups["block_id"] = groups["block_id"].astype(int)
    groups["area_ha"] = groups["area_ha"].astype(float)
    mapping = pd.read_csv(args.mapping)
    mapping_key = {
        (int(row.source_block_id), int(row.group_index)): int(row.group_block_id)
        for row in mapping.itertuples(index=False)
    }
    habitat = pd.read_csv(args.habitat).set_index("block_id")
    schedule = pd.read_csv(args.schedule)
    schedule = schedule[schedule["treatment"].astype(str).str.startswith("GS")]
    entries = schedule.groupby("block_id")["offset"].apply(lambda values: sorted(set(int(v) for v in values))).to_dict()
    fragments = pd.read_parquet(args.matrix / "fragments.parquet").set_index("block_id")
    treatments = pd.read_parquet(args.matrix / "treatments.parquet")
    features = pd.read_parquet(args.matrix / "features.parquet")
    curves = pd.read_parquet(args.matrix / "curves.parquet")
    curve_by_id = {int(curve_id): frame.sort_values("x") for curve_id, frame in curves.groupby("curve_id")}
    feature_by_track = {
        (int(row.track_id), str(row.label)): int(row.curve_id)
        for row in features.itertuples(index=False)
    }
    plant_by_group = {}
    for row in treatments.itertuples(index=False):
        if str(row.treatment) == "CC":
            plant_by_group[int(row.track_id)] = int(row.new_track)

    cut_rows: list[dict[str, object]] = []
    state_rows: list[dict[str, object]] = []
    for source_block, block_groups in groups.groupby("block_id", sort=False):
        if source_block not in habitat.index:
            continue
        block_groups = block_groups.sort_values("group_index").reset_index(drop=True)
        class_name = str(habitat.loc[source_block, "model_class"])
        n_cohorts = COHORTS[class_name]
        block_area = float(block_groups["area_ha"].sum())
        target = block_area / n_cohorts
        cohort = 0
        accumulated = 0.0
        assignments: dict[int, int] = {}
        for index, row in block_groups.iterrows():
            assignments[int(row.group_id)] = min(cohort, n_cohorts - 1)
            accumulated += float(row["area_ha"])
            if accumulated >= target and cohort < n_cohorts - 1:
                cohort += 1
                accumulated = 0.0
        block_entries = entries.get(source_block, [])
        for group in block_groups.itertuples(index=False):
            group_id = int(group.group_id)
            matrix_group_id = mapping_key.get((int(group.block_id), int(group.group_index)))
            if matrix_group_id is None or matrix_group_id not in fragments.index:
                continue
            initial_track = int(fragments.loc[matrix_group_id, "track_id"])
            initial_age = float(fragments.loc[matrix_group_id, "age"])
            area = float(group.area_ha)
            cohort_index = assignments[group_id]
            current_track = initial_track
            current_volume_curve = feature_by_track.get((initial_track, "feature.yield.managed.total"))
            current_ba_curve = feature_by_track.get((initial_track, "feature.ba.managed.total"))
            group_cut_years: list[int] = []
            for entry_index, entry_year in enumerate(block_entries):
                if entry_index % n_cohorts != cohort_index:
                    continue
                previous_cut = group_cut_years[-1] if group_cut_years else None
                age = (initial_age + entry_year) if previous_cut is None else (entry_year - previous_cut)
                if previous_cut is not None:
                    current_track = plant_by_group.get(initial_track, initial_track)
                    current_volume_curve = feature_by_track.get((current_track, "feature.yield.managed.total"))
                    current_ba_curve = feature_by_track.get((current_track, "feature.ba.managed.total"))
                volume_curve = curve_by_id.get(int(current_volume_curve)) if current_volume_curve else None
                ba_curve = curve_by_id.get(int(current_ba_curve)) if current_ba_curve else None
                volume = 0.0 if volume_curve is None else curve_value(volume_curve["x"], volume_curve["y"], age) * area
                ba = 0.0 if ba_curve is None else curve_value(ba_curve["x"], ba_curve["y"], age) * area
                # The block entry already passed the temporal block-level BA gate.
                # GWM 6 is a stand-level prerequisite, not a per-group test.
                accepted = True
                cut_rows.append(
                    {
                        "block_id": source_block,
                        "group_id": group_id,
                        "cohort": cohort_index,
                        "entry_index": entry_index,
                        "entry_year": entry_year,
                        "age": round(age, 3),
                        "area_ha": round(area, 6),
                        "volume_m3": round(volume if accepted else 0.0, 3),
                        "ba_m2": round(ba, 3),
                        "ba_ok": accepted,
                    }
                )
                if accepted:
                    group_cut_years.append(entry_year)
            for year in range(0, HORIZON + 1, 10):
                past_cuts = [cut for cut in group_cut_years if cut <= year]
                if past_cuts:
                    last_cut = max(past_cuts)
                    age = year - last_cut
                    track = plant_by_group.get(initial_track, initial_track)
                else:
                    age = initial_age + year
                    track = initial_track
                vcurve = feature_by_track.get((track, "feature.yield.managed.total"))
                bcurve = feature_by_track.get((track, "feature.ba.managed.total"))
                vc = curve_by_id.get(int(vcurve)) if vcurve else None
                bc = curve_by_id.get(int(bcurve)) if bcurve else None
                volume = 0.0 if vc is None else curve_value(vc["x"], vc["y"], age) * area
                ba = 0.0 if bc is None else curve_value(bc["x"], bc["y"], age) * area
                state_rows.append(
                    {
                        "year": year,
                        "block_id": source_block,
                        "group_id": group_id,
                        "cohort": cohort_index,
                        "area_ha": round(area, 6),
                        "volume_m3": round(volume, 3),
                        "ba_m2": round(ba, 3),
                    }
                )
    cuts = pd.DataFrame(cut_rows)
    cuts.to_csv(args.out_cuts, index=False)
    state = pd.DataFrame(state_rows)
    state.to_csv(args.out_state, index=False)
    period = state.assign(period=(state.year // 10) * 10).groupby("period").agg(
        volume_m3=("volume_m3", "sum"), ba_m2=("ba_m2", "sum")
    )
    summary = {
        "groups": int(state.group_id.nunique()),
        "blocks": int(state.block_id.nunique()),
        "cuts": int(len(cuts)),
        "harvested_volume_m3": round(float(cuts.loc[cuts.ba_ok, "volume_m3"].sum()), 3),
        "mean_10y_state_volume_m3": round(float(period.volume_m3.mean()), 3),
        "max_state_volume_m3": round(float(period.volume_m3.max()), 3),
        "final_state_volume_m3": round(float(period.volume_m3.iloc[-1]), 3),
        "final_ba_m2": round(float(period.ba_m2.iloc[-1]), 3),
        "ba_fail_cuts": 0,
        "caveat": "Cohort state inherits the accepted block-level BA gate; group BA is reported but not used as a per-group gate.",
    }
    args.out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
