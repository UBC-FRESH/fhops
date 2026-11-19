#!/usr/bin/env python3
"""Build a temporal 40 m²/ha basal-area gate for the Gavin MDWR schedule.

The 2007 transition/deep snowpack GAR order, as summarized in BC MDWR
Information Note #3, requires at least 40 m²/ha of pre-harvest basal area before
group selection is initiated. This script builds a screening ledger:

- start from the area-weighted VRI 2025 basal area for each MDWR block;
- grow basal area between entries with the block's WS4 volume curve as a proxy;
- accept an entry only when the proxy BA is at least 40 m²/ha;
- defer an entry year by year if the threshold is not met;
- after an accepted pass, reduce BA by the Table 30 pass fraction and continue.

The BA growth proxy is deliberately simple and is not a validated BA model.
Blocks with unknown VRI coverage are held. Non-MDWR clearcut events are carried
through unchanged.

Run from the public-demo repository root with instance runtime inputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
PASS_FRACTION = {"High": 0.33, "Moderate": 0.25, "Low": 0.20}
MIN_BA = 40.0
FIRST_YEAR = 2026
HORIZON = 300


def load_curve(matrix: Path, track_id: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Return the total-volume curve for a track, if present."""
    features = pd.read_parquet(matrix / "features.parquet")
    curves = pd.read_parquet(matrix / "curves.parquet")
    row = features.loc[
        (features["track_id"] == track_id)
        & (features["label"] == "feature.yield.managed.total")
    ]
    if row.empty:
        return None
    curve_id = int(row["curve_id"].iloc[0])
    curve = curves.loc[curves["curve_id"] == curve_id].sort_values("x")
    if curve.empty:
        return None
    return curve["x"].to_numpy(dtype=float), curve["y"].to_numpy(dtype=float)


def value_at(curve: tuple[np.ndarray, np.ndarray] | None, age: float) -> float | None:
    """Interpolate a track curve at an age; clamp to the curve domain."""
    if curve is None:
        return None
    x, y = curve
    if not np.isfinite(age) or x.size == 0:
        return None
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
        "--schedule",
        type=Path,
        default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-schedule-official.csv",
    )
    parser.add_argument(
        "--ba-table",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_basal_area.csv",
    )
    parser.add_argument(
        "--habitat-table",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-18_gavin_mdwr_official_habitat.csv",
    )
    parser.add_argument(
        "--out-schedule",
        type=Path,
        default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-schedule-official-ba-temporal.csv",
    )
    parser.add_argument(
        "--out-ledger",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_ba_ledger.csv",
    )
    parser.add_argument(
        "--stagger",
        type=int,
        default=0,
        help="Spread first entries by up to this many years using the block id.",
    )
    parser.add_argument(
        "--out-manifest",
        type=Path,
        default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_ba_ledger.json",
    )
    args = parser.parse_args()

    fragments = pd.read_parquet(args.matrix / "fragments.parquet")
    fragments["block_id"] = fragments["block_id"].astype(int)
    ba = pd.read_csv(args.ba_table)
    ba["block_id"] = ba["block_id"].astype(int)
    ba = ba.set_index("block_id")
    habitat = pd.read_csv(args.habitat_table)
    habitat["block_id"] = habitat["block_id"].astype(int)
    habitat = habitat.set_index("block_id")
    schedule = pd.read_csv(args.schedule)
    schedule["block_id"] = schedule["block_id"].astype(int)

    mdwr_blocks = set(ba.index)
    mdwr_schedule = schedule[schedule["block_id"].isin(mdwr_blocks)]
    first_entry = mdwr_schedule.groupby("block_id")["offset"].min().to_dict()
    non_mdwr = schedule[~schedule["block_id"].isin(mdwr_blocks)].copy()

    curve_cache: dict[int, tuple[np.ndarray, np.ndarray] | None] = {}
    accepted_rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []

    for row in fragments.loc[fragments["block_id"].isin(mdwr_blocks)].itertuples(index=False):
        block_id = int(row.block_id)
        if block_id not in first_entry:
            continue
        block_ba = ba.loc[block_id]
        status = str(block_ba["ba_status"])
        initial_ba = float(block_ba["ba_m2_ha"]) if pd.notna(block_ba["ba_m2_ha"]) else None
        initial_age = float(row.age)
        track_id = int(row.track_id)
        if track_id not in curve_cache:
            curve_cache[track_id] = load_curve(args.matrix, track_id)
        curve = curve_cache[track_id]
        habitat_row = habitat.loc[block_id] if block_id in habitat.index else None
        model_class = str(habitat_row["model_class"]) if habitat_row is not None else "Low"
        fraction = PASS_FRACTION.get(model_class, 0.20)

        ledger = {
            "block_id": block_id,
            "area_ha": round(float(row.area_ha), 6),
            "habitat_class": model_class,
            "initial_age": round(initial_age, 3),
            "initial_ba_m2_ha": None if initial_ba is None else round(initial_ba, 6),
            "ba_status": status,
            "first_candidate_offset": int(first_entry[block_id]),
            "accepted_entries": 0,
            "deferred_attempts": 0,
            "first_accepted_age": None,
            "last_accepted_age": None,
            "note": "",
        }
        if status == "unknown" or initial_ba is None or curve is None:
            ledger["note"] = (
                "held: unknown VRI BA" if status == "unknown" else
                "held: missing BA or volume curve"
            )
            ledger_rows.append(ledger)
            continue

        current_ba = initial_ba
        current_age = initial_age
        candidate = int(first_entry[block_id])
        if args.stagger > 0:
            candidate += (block_id * 17) % args.stagger
        while candidate < HORIZON:
            age = initial_age + candidate
            curve_at_entry = value_at(curve, age)
            curve_at_current = value_at(curve, current_age)
            if curve_at_entry is None or curve_at_current in (None, 0.0):
                ledger["deferred_attempts"] += 1
                candidate += 1
                continue
            ba_pre = current_ba * (curve_at_entry / curve_at_current)
            if ba_pre + 1e-9 < MIN_BA:
                ledger["deferred_attempts"] += 1
                candidate += 1
                continue

            ledger["accepted_entries"] += 1
            ledger["first_accepted_age"] = (
                candidate + initial_age if ledger["first_accepted_age"] is None
                else ledger["first_accepted_age"]
            )
            ledger["last_accepted_age"] = candidate + initial_age
            accepted_rows.append(
                {
                    "block_id": block_id,
                    "treatment": f"GS{int(round(fraction * 100))}",
                    "offset": int(candidate),
                    "ba_pre_m2_ha": round(ba_pre, 6),
                    "ba_post_m2_ha": round(ba_pre * (1.0 - fraction), 6),
                    "age": round(candidate + initial_age, 3),
                }
            )
            current_ba = ba_pre * (1.0 - fraction)
            current_age = candidate + initial_age
            candidate += 40

        if ledger["accepted_entries"] == 0:
            ledger["note"] = "held: did not reach 40 m²/ha within the horizon"
        ledger_rows.append(ledger)

    accepted = pd.DataFrame(
        accepted_rows,
        columns=[
            "block_id",
            "treatment",
            "offset",
            "ba_pre_m2_ha",
            "ba_post_m2_ha",
            "age",
        ],
    )
    accepted = accepted[["block_id", "treatment", "offset"]]
    output_schedule = pd.concat(
        [non_mdwr[["block_id", "treatment", "offset"]], accepted],
        ignore_index=True,
    ).sort_values(["offset", "block_id"])
    output_schedule.to_csv(args.out_schedule, index=False)
    pd.DataFrame(ledger_rows).to_csv(args.out_ledger, index=False)

    ledger_frame = pd.DataFrame(ledger_rows)
    manifest = {
        "matrix": str(args.matrix),
        "schedule": str(args.schedule),
        "ba_table": str(args.ba_table),
        "habitat_table": str(args.habitat_table),
        "gate_m2_ha": MIN_BA,
        "pass_fraction": PASS_FRACTION,
        "horizon_years": HORIZON,
        "stagger_years": args.stagger,
        "mdwr_blocks": int(len(mdwr_blocks)),
        "mdwr_blocks_with_accepted_entry": int(ledger_frame.loc[ledger_frame["accepted_entries"] > 0, "block_id"].nunique()),
        "mdwr_blocks_held": int((ledger_frame["accepted_entries"] == 0).sum()),
        "accepted_entries": int(len(accepted)),
        "accepted_area_ha": round(float(ledger_frame.loc[ledger_frame["accepted_entries"] > 0, "area_ha"].sum()), 3),
        "deferred_attempts": int(ledger_frame["deferred_attempts"].sum()),
        "caveat": "BA growth is a WS4 volume-ratio proxy, not a validated basal-area model; entries are screened annually from the first scheduled year.",
    }
    args.out_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
