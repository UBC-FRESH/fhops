#!/usr/bin/env python3
"""Build a group-level WS4 matrix with a group-specific BA account.

This extends the group matrix prototype:

- each group gets its own initial track and plantation successor track;
- the initial track carries the source volume curve and a group-specific BA
  curve derived from VRI BA and the volume curve;
- the plantation track carries the base CC successor volume curve and the
  proportional BA curve;
- CC groups are cut on the cohort schedule.

BA is a screening proportional curve, not a calibrated basal-area growth model.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
BASE = INSTANCE / "ws4" / "runtime" / "legacy_matrix"
CLONE = INSTANCE / "ws4" / "runtime" / "mdwr_group_selection_official_reentry"
COHORTS = {"High": 3, "Moderate": 4, "Low": 5}
CYCLE = {"High": 120, "Moderate": 160, "Low": 200}
HORIZON = 300


def value_at(x: np.ndarray, y: np.ndarray, age: float) -> float:
    if not len(x):
        return 0.0
    clipped = min(max(float(age), float(x[0])), float(x[-1]))
    return float(np.interp(clipped, x, y))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-group-matrix-ba")
    parser.add_argument("--schedule-out", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-group-schedule-ba.csv")
    parser.add_argument("--mapping-out", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_matrix_ba_map.csv")
    parser.add_argument("--manifest", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_matrix_ba.json")
    parser.add_argument("--groups", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_layout.csv")
    parser.add_argument("--schedule", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-schedule-official-ba-temporal-s10.csv")
    parser.add_argument("--habitat", type=Path, default=INSTANCE / "planning" / "2026-11-18_gavin_mdwr_official_habitat.csv")
    parser.add_argument("--ba-table", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_basal_area.csv")
    args = parser.parse_args()

    base_tracks = pd.read_parquet(BASE / "tracks.parquet")
    base_features = pd.read_parquet(BASE / "features.parquet")
    base_products = pd.read_parquet(BASE / "products.parquet")
    base_curves = pd.read_parquet(BASE / "curves.parquet")
    base_treatments = pd.read_parquet(BASE / "treatments.parquet")
    clone_tracks = pd.read_parquet(CLONE / "tracks.parquet")
    clone_fragments = pd.read_parquet(CLONE / "fragments.parquet").drop_duplicates("block_id").set_index("block_id")
    base_name_to_id = dict(zip(base_tracks["name"], base_tracks["track_id"]))
    clone_name = dict(zip(clone_tracks["track_id"], clone_tracks["name"]))
    habitat = pd.read_csv(args.habitat).set_index("block_id")
    ba = pd.read_csv(args.ba_table).set_index("block_id")
    entries = pd.read_csv(args.schedule)
    entries = entries[entries["treatment"].astype(str).str.startswith("GS")]
    first_entry = entries.groupby("block_id")["offset"].min().to_dict()
    groups = pd.read_csv(args.groups)
    groups = groups.loc[groups["entry_offset"].notna()].copy()
    groups["block_id"] = groups["block_id"].astype(int)
    groups["area_ha"] = groups["area_ha"].astype(float)
    groups = groups.sort_values(["block_id", "group_index"])

    if args.out.exists():
        shutil.rmtree(args.out)
    shutil.copytree(BASE, args.out)

    next_track = int(base_tracks["track_id"].max()) + 1
    next_curve = int(base_curves["curve_id"].max()) + 1
    curve_rows: list[dict[str, float]] = []
    track_rows: list[dict[str, object]] = []
    feature_rows: list[dict[str, object]] = []
    product_rows: list[dict[str, object]] = []
    treatment_rows: list[dict[str, object]] = []
    block_rows: list[dict[str, object]] = []
    fragment_rows: list[dict[str, object]] = []
    schedule_rows: list[dict[str, object]] = []
    mapping_rows: list[dict[str, object]] = []
    group_id = 0
    for block_id, block_groups in groups.groupby("block_id", sort=False):
        if block_id not in first_entry or block_id not in clone_fragments.index or block_id not in habitat.index:
            continue
        clone_track_id = int(clone_fragments.loc[block_id, "track_id"])
        clone_track_name = str(clone_name.get(clone_track_id, ""))
        if ":" not in clone_track_name:
            continue
        source_name = clone_track_name.split(":", 1)[1]
        source_track = base_name_to_id.get(source_name)
        if source_track is None:
            continue
        transition = base_treatments.loc[
            (base_treatments["track_id"] == source_track)
            & (base_treatments["treatment"] == "CC")
        ]
        if transition.empty:
            continue
        successor_track = int(transition["new_track"].iloc[0])
        source_curve_row = base_features.loc[
            (base_features["track_id"] == source_track)
            & (base_features["label"] == "feature.yield.managed.total")
        ]
        successor_curve_row = base_features.loc[
            (base_features["track_id"] == successor_track)
            & (base_features["label"] == "feature.yield.managed.total")
        ]
        if source_curve_row.empty or successor_curve_row.empty:
            continue
        source_curve_id = int(source_curve_row["curve_id"].iloc[0])
        successor_curve_id = int(successor_curve_row["curve_id"].iloc[0])
        source_curve = base_curves.loc[base_curves["curve_id"] == source_curve_id].sort_values("x")
        successor_curve = base_curves.loc[base_curves["curve_id"] == successor_curve_id].sort_values("x")
        class_name = str(habitat.loc[block_id, "model_class"])
        n_cohorts = COHORTS[class_name]
        cycle = CYCLE[class_name]
        initial_age = int(round(float(clone_fragments.loc[block_id, "age"])))
        initial_ba = float(ba.loc[block_id, "ba_m2_ha"]) if block_id in ba.index else 0.0
        source_v0 = value_at(source_curve["x"].to_numpy(), source_curve["y"].to_numpy(), initial_age)
        first = int(first_entry[block_id])
        target = float(block_groups["area_ha"].sum()) / n_cohorts
        cohort = 0
        accumulated = 0.0
        assignments: dict[int, int] = {}
        for index, row in block_groups.iterrows():
            assignments[index] = min(cohort, n_cohorts - 1)
            accumulated += float(row["area_ha"])
            if accumulated >= target and cohort < n_cohorts - 1:
                cohort += 1
                accumulated = 0.0
        for index, row in block_groups.iterrows():
            group_id += 1
            cohort_index = assignments[index]
            start = first + cohort_index * 40
            cuts = list(range(start, HORIZON, cycle))
            if not cuts:
                continue
            area = float(row["area_ha"])
            initial_track = next_track
            plant_track = next_track + 1
            next_track += 2
            ba_initial_curve = next_curve
            next_curve += 1
            ba_plant_curve = next_curve
            next_curve += 1
            for x, y in zip(source_curve["x"], source_curve["y"]):
                curve_rows.append({"curve_id": ba_initial_curve, "x": float(x), "y": float(initial_ba * min(1.0, y / source_v0)) if source_v0 else 0.0})
            for x, y in zip(successor_curve["x"], successor_curve["y"]):
                curve_rows.append({"curve_id": ba_plant_curve, "x": float(x), "y": float(initial_ba * min(1.0, y / source_v0)) if source_v0 else 0.0})
            track_rows.extend(
                [
                    {"track_id": initial_track, "name": f"group-{group_id}-initial"},
                    {"track_id": plant_track, "name": f"group-{group_id}-plant"},
                ]
            )
            feature_rows.extend(
                [
                    {"track_id": initial_track, "label": "feature.yield.managed.total", "curve_id": source_curve_id},
                    {"track_id": initial_track, "label": "feature.ba.managed.total", "curve_id": ba_initial_curve},
                    {"track_id": plant_track, "label": "feature.yield.managed.total", "curve_id": successor_curve_id},
                    {"track_id": plant_track, "label": "feature.ba.managed.total", "curve_id": ba_plant_curve},
                ]
            )
            source_products = base_products.loc[(base_products["track_id"] == source_track) & (base_products["treatment"] == "CC")]
            successor_products = base_products.loc[(base_products["track_id"] == successor_track) & (base_products["treatment"] == "CC")]
            for target_track, products in ((initial_track, source_products), (plant_track, successor_products)):
                for product in products.itertuples(index=False):
                    product_rows.append(
                        {
                            "track_id": target_track,
                            "treatment": "CC",
                            "label": str(product.label),
                            "curve_id": int(product.curve_id),
                        }
                    )
            treatment_rows.extend(
                [
                    {"track_id": initial_track, "begin": 0, "end": 998, "treatment": "CC", "new_track": plant_track, "offset": 0, "retain": 0},
                    {"track_id": plant_track, "begin": 0, "end": 998, "treatment": "CC", "new_track": plant_track, "offset": 0, "retain": 0},
                ]
            )
            block_rows.append({"block_id": group_id, "track_id": initial_track, "offset": initial_age, "area_ha": area})
            fragment_rows.append({"fragment_id": group_id, "block_id": group_id, "area_ha": area, "age": initial_age, "track_id": initial_track})
            for cut in cuts:
                schedule_rows.append({"block_id": group_id, "treatment": "CC", "offset": int(cut)})
            mapping_rows.append(
                {
                    "group_block_id": group_id,
                    "source_block_id": block_id,
                    "group_index": int(row["group_index"]),
                    "cohort": cohort_index,
                    "habitat_class": class_name,
                    "area_ha": area,
                    "initial_ba_m2_ha": round(initial_ba, 6),
                    "first_cut": int(cuts[0]),
                    "cycle_years": cycle,
                }
            )

    tracks = pd.DataFrame(track_rows)
    features = pd.DataFrame(feature_rows)
    products = pd.DataFrame(product_rows)
    treatments = pd.DataFrame(treatment_rows)
    curves = pd.concat([base_curves, pd.DataFrame(curve_rows)], ignore_index=True)
    blocks = pd.DataFrame(block_rows)
    fragments = pd.DataFrame(fragment_rows)
    schedule = pd.DataFrame(schedule_rows)
    mapping = pd.DataFrame(mapping_rows)
    tracks.to_parquet(args.out / "tracks.parquet", index=False)
    features.to_parquet(args.out / "features.parquet", index=False)
    products.to_parquet(args.out / "products.parquet", index=False)
    treatments.to_parquet(args.out / "treatments.parquet", index=False)
    curves.to_parquet(args.out / "curves.parquet", index=False)
    blocks.to_parquet(args.out / "blocks.parquet", index=False)
    fragments.to_parquet(args.out / "fragments.parquet", index=False)
    schedule.to_csv(args.schedule_out, index=False)
    mapping.to_csv(args.mapping_out, index=False)
    manifest = {
        "source_matrix": str(BASE),
        "groups": int(len(mapping)),
        "blocks": int(len(blocks)),
        "source_blocks": int(mapping["source_block_id"].nunique()) if not mapping.empty else 0,
        "scheduled_area_ha": round(float(mapping["area_ha"].sum()), 3),
        "cuts": int(len(schedule)),
        "cohorts": COHORTS,
        "cycle_years": CYCLE,
        "ba_account": "feature.ba.managed.total",
        "caveat": "Group-specific BA is a proportional volume-ratio curve; not a calibrated BA growth model.",
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
