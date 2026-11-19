#!/usr/bin/env python3
"""Build a schematic spatially explicit cohort model for the Gavin MDWR.

The model uses the 10 m cell group prototype, partitions each block's groups into
Table 30 cohorts, and grows each group with the block's WS4 volume curve. A
cohort is cut every High 120 / Moderate 160 / Low 200 years, with cohort starts
staggered by 40 years. It is a group-level screening model, not an operational
growth model:

- regeneration uses the same volume curve as the block, not a separate
  plantation curve;
- group BA is a proportional screening value;
- windthrow, minimum group size, and within-group mortality are absent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
HORIZON = 300
COHORTS = {"High": 3, "Moderate": 4, "Low": 5}
CYCLE_YEARS = {"High": 120, "Moderate": 160, "Low": 200}


def value_at(x: np.ndarray, y: np.ndarray, age: float) -> float:
    """Interpolate a curve at age, clamping to its domain."""
    if not len(x):
        return 0.0
    clipped = min(max(float(age), float(x[0])), float(x[-1]))
    return float(np.interp(clipped, x, y))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=INSTANCE / "ws4" / "runtime" / "mdwr_group_selection_official_reentry",
    )
    parser.add_argument(
        "--groups",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_group_layout.csv",
    )
    parser.add_argument(
        "--schedule",
        type=Path,
        default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-schedule-official-ba-temporal-s10.csv",
    )
    parser.add_argument(
        "--ba-table",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_basal_area.csv",
    )
    parser.add_argument(
        "--habitat",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-18_gavin_mdwr_official_habitat.csv",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_cohort_harvest.csv",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_cohort_summary.json",
    )
    args = parser.parse_args()

    fragments = pd.read_parquet(args.matrix / "fragments.parquet")
    fragments = fragments.drop_duplicates("block_id").set_index("block_id")
    features = pd.read_parquet(args.matrix / "features.parquet")
    curves = pd.read_parquet(args.matrix / "curves.parquet")
    total_volume = features.loc[features["label"] == "feature.yield.managed.total"]
    volume_lookup = {
        int(row.track_id): int(row.curve_id)
        for row in total_volume.itertuples(index=False)
    }
    curve_lookup = {
        int(curve_id): group.sort_values("x")[["x", "y"]].to_numpy(dtype=float)
        for curve_id, group in curves.groupby("curve_id", sort=False)
    }
    groups = pd.read_csv(args.groups)
    groups = groups.loc[groups["entry_offset"].notna()].copy()
    groups["block_id"] = groups["block_id"].astype(int)
    groups["area_ha"] = groups["area_ha"].astype(float)
    groups = groups.sort_values(["block_id", "group_index"])
    schedule = pd.read_csv(args.schedule)
    schedule = schedule[schedule["treatment"].astype(str).str.startswith("GS")]
    first_entry = schedule.groupby("block_id")["offset"].min().to_dict()
    ba = pd.read_csv(args.ba_table).set_index("block_id")
    habitat = pd.read_csv(args.habitat).set_index("block_id")

    rows: list[dict[str, object]] = []
    for block_id, block_groups in groups.groupby("block_id", sort=False):
        if block_id not in first_entry or block_id not in fragments.index:
            continue
        block = fragments.loc[block_id]
        class_name = str(habitat.loc[block_id, "model_class"])
        n_cohorts = COHORTS[class_name]
        cycle = CYCLE_YEARS[class_name]
        first = int(first_entry[block_id])
        initial_age = float(block["age"])
        track_id = int(block["track_id"])
        curve_id = volume_lookup.get(track_id)
        if curve_id is None:
            continue
        curve = curve_lookup[curve_id]
        block_ba = float(ba.loc[block_id, "ba_m2_ha"]) if block_id in ba.index else 0.0
        block_area = float(block_groups["area_ha"].sum())
        if block_area <= 0:
            continue
        # Partition groups into area-balanced cohorts; retain deterministic group order.
        cohort_target = block_area / n_cohorts
        cohort = 0
        accumulated = 0.0
        assignments: dict[int, int] = {}
        for index, row in block_groups.iterrows():
            assignments[index] = min(cohort, n_cohorts - 1)
            accumulated += float(row["area_ha"])
            if accumulated >= cohort_target and cohort < n_cohorts - 1:
                cohort += 1
                accumulated = 0.0
        for index, row in block_groups.iterrows():
            cohort_index = assignments[index]
            start = first + cohort_index * 40
            group_age = initial_age + start
            initial_volume_ha = value_at(curve[:, 0], curve[:, 1], group_age)
            volume = initial_volume_ha * float(row["area_ha"])
            group_ba = (
                block_ba * float(row["area_ha"]) / block_area
                if block_area > 0
                else 0.0
            )
            cut_year = start
            first_cut = True
            while cut_year < HORIZON:
                if first_cut:
                    cut_volume = volume
                    cut_ba = group_ba
                else:
                    cut_volume = value_at(curve[:, 0], curve[:, 1], group_age) * float(row["area_ha"])
                    cut_ba = (
                        block_ba * float(row["area_ha"]) / block_area
                        * min(1.0, cut_volume / max(volume, 1e-9))
                    )
                rows.append(
                    {
                        "block_id": block_id,
                        "cohort": cohort_index,
                        "group_index": int(row["group_index"]),
                        "cut_year": int(cut_year),
                        "group_age": round(group_age, 3),
                        "area_ha": round(float(row["area_ha"]), 6),
                        "volume_m3": round(float(cut_volume), 3),
                        "ba_m2": round(float(cut_ba), 3),
                        "habitat_class": class_name,
                    }
                )
                # Next cut for this group is one full cohort cycle later.
                cut_year += cycle
                group_age = cycle
                first_cut = False
            # no state is carried after the last cut; this is a harvest screen

    frame = pd.DataFrame(rows)
    frame.to_csv(args.out_csv, index=False)
    period = (frame["cut_year"] // 10).astype(int) if not frame.empty else pd.Series(dtype=int)
    period_values = frame.groupby(period)["volume_m3"].sum() if not frame.empty else pd.Series(dtype=float)
    summary = {
        "groups": int(args.groups and len(frame)),
        "blocks": int(frame["block_id"].nunique()) if not frame.empty else 0,
        "cut_events": int(len(frame)),
        "total_volume_m3": round(float(frame["volume_m3"].sum()), 3) if not frame.empty else 0.0,
        "mean_10y_volume_m3": round(float(period_values.mean()), 3) if not period_values.empty else 0.0,
        "min_10y_volume_m3": round(float(period_values.min()), 3) if not period_values.empty else 0.0,
        "max_10y_volume_m3": round(float(period_values.max()), 3) if not period_values.empty else 0.0,
        "cohorts": COHORTS,
        "cycle_years": CYCLE_YEARS,
        "caveat": "Schematic group-level cohort screen; same volume curve after regeneration, proportional BA, no windthrow or minimum group size.",
    }
    args.out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
