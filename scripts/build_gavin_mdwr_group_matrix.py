#!/usr/bin/env python3
"""Build a group-level WS4 matrix and schedule for the Gavin MDWR.

Each 10 m cell group becomes a WS4 block/fragment. Groups are partitioned into
Table 30 cohorts and clearcut as group openings on their cohort cycle. This
carries group-level volume through the WS4 matrix, but it does not add a
group-specific BA account; BA remains a separate screening ledger.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
BASE = INSTANCE / "ws4" / "runtime" / "legacy_matrix"
CLONE = INSTANCE / "ws4" / "runtime" / "mdwr_group_selection_official_reentry"
COHORTS = {"High": 3, "Moderate": 4, "Low": 5}
CYCLE = {"High": 120, "Moderate": 160, "Low": 200}
HORIZON = 300


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-group-matrix")
    parser.add_argument("--schedule-out", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-group-schedule.csv")
    parser.add_argument("--mapping-out", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_matrix_map.csv")
    parser.add_argument("--manifest", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_matrix.json")
    parser.add_argument("--groups", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_layout.csv")
    parser.add_argument("--schedule", type=Path, default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-schedule-official-ba-temporal-s10.csv")
    parser.add_argument("--habitat", type=Path, default=INSTANCE / "planning" / "2026-11-18_gavin_mdwr_official_habitat.csv")
    args = parser.parse_args()

    base_tracks = pd.read_parquet(BASE / "tracks.parquet")
    clone_tracks = pd.read_parquet(CLONE / "tracks.parquet")
    clone_fragments = pd.read_parquet(CLONE / "fragments.parquet")
    base_name_to_id = dict(zip(base_tracks["name"], base_tracks["track_id"]))
    clone_name = dict(zip(clone_tracks["track_id"], clone_tracks["name"]))
    clone_fragments = clone_fragments.drop_duplicates("block_id").set_index("block_id")
    habitat = pd.read_csv(args.habitat).set_index("block_id")
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
    block_rows: list[dict[str, object]] = []
    fragment_rows: list[dict[str, object]] = []
    schedule_rows: list[dict[str, object]] = []
    mapping_rows: list[dict[str, object]] = []
    group_id = 0
    for block_id, block_groups in groups.groupby("block_id", sort=False):
        if block_id not in first_entry or block_id not in clone_fragments.index:
            continue
        clone_track_id = int(clone_fragments.loc[block_id, "track_id"])
        clone_track_name = str(clone_name.get(clone_track_id, ""))
        if ":" not in clone_track_name:
            continue
        source_name = clone_track_name.split(":", 1)[1]
        source_track = base_name_to_id.get(source_name)
        if source_track is None:
            continue
        class_name = str(habitat.loc[block_id, "model_class"])
        n_cohorts = COHORTS[class_name]
        cycle = CYCLE[class_name]
        initial_age = int(round(float(clone_fragments.loc[block_id, "age"])))
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
            cut_year = start
            cuts = []
            while cut_year < HORIZON:
                cuts.append(cut_year)
                cut_year += cycle
            if not cuts:
                continue
            area = float(row["area_ha"])
            block_rows.append(
                {
                    "block_id": group_id,
                    "track_id": int(source_track),
                    "offset": initial_age,
                    "area_ha": area,
                }
            )
            fragment_rows.append(
                {
                    "fragment_id": group_id,
                    "block_id": group_id,
                    "area_ha": area,
                    "age": initial_age,
                    "track_id": int(source_track),
                }
            )
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
                    "first_cut": int(cuts[0]),
                    "cycle_years": cycle,
                }
            )
    blocks = pd.DataFrame(block_rows)
    fragments = pd.DataFrame(fragment_rows)
    schedule = pd.DataFrame(schedule_rows)
    mapping = pd.DataFrame(mapping_rows)
    blocks.to_parquet(args.out / "blocks.parquet", index=False)
    fragments.to_parquet(args.out / "fragments.parquet", index=False)
    schedule.to_csv(args.schedule_out, index=False)
    mapping.to_csv(args.mapping_out, index=False)
    manifest = {
        "source_matrix": str(BASE),
        "clone_matrix": str(CLONE),
        "groups": int(len(mapping)),
        "blocks": int(len(blocks)),
        "source_blocks": int(mapping["source_block_id"].nunique()) if not mapping.empty else 0,
        "scheduled_area_ha": round(float(mapping["area_ha"].sum()), 3),
        "cuts": int(len(schedule)),
        "cohorts": COHORTS,
        "cycle_years": CYCLE,
        "caveat": "Group-level WS4 volume run; no group-specific BA account, plantation calibration, windthrow, or minimum group size.",
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
