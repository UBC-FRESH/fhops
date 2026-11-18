#!/usr/bin/env python3
"""Build a first-pass MKRF variable-retention matrix.

This is a matrix-level implementation of dispersed retention.  For each block
with a retention profile, the no-retention fragment is split into:

- a harvested fragment on a cloned managed track, with product curves scaled
  for the volume/value removed by the residual cohort; and
- a residual fragment on a cloned unmanaged track at the same age, with no
  scheduled treatment and feature curves scaled to the residual cohort.

The split and product factors come from ``build_mkrf_retention_profiles.py``.
This is deliberately a matrix-level screen: the residual area is set aside from
the start of the horizon, not split inside the simulator at the treatment year.
That makes the state trajectory equivalent for a one-entry reserve but does not
yet let the optimizer choose retention intensity as a treatment variable.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-mkrf-instance")
BASE = INSTANCE / "ws4" / "runtime" / "matrix_no_retention_true_patched"
PROFILE = INSTANCE / "planning" / "2026-11-18_mkrf_retention_profiles.csv"
OUT = INSTANCE / "ws4" / "runtime" / "matrix_vr_base"


def scaled_curve(
    curve_id: int,
    factor: float,
    lookup: dict[int, np.ndarray],
    rows: list[dict[str, float]],
    next_id: int,
    cache: dict[tuple[int, float], int],
) -> tuple[int, int]:
    if abs(factor - 1.0) < 1e-12:
        return curve_id, next_id
    key = (int(curve_id), round(float(factor), 10))
    if key in cache:
        return cache[key], next_id
    new_id = next_id
    next_id += 1
    for x, y in lookup[int(curve_id)]:
        rows.append({"curve_id": new_id, "x": float(x), "y": float(y) * factor})
    cache[key] = new_id
    return new_id, next_id


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(BASE, OUT)
    profile = pd.read_csv(PROFILE).set_index("block_id")
    fragments = pd.read_parquet(OUT / "fragments.parquet")
    blocks = pd.read_parquet(OUT / "blocks.parquet")
    tracks = pd.read_parquet(OUT / "tracks.parquet")
    features = pd.read_parquet(OUT / "features.parquet")
    products = pd.read_parquet(OUT / "products.parquet")
    treatments = pd.read_parquet(OUT / "treatments.parquet")
    curves = pd.read_parquet(OUT / "curves.parquet")
    curve_lookup = {
        int(curve_id): group.sort_values("x")[["x", "y"]].to_numpy()
        for curve_id, group in curves.groupby("curve_id", sort=False)
    }
    max_track = int(tracks["track_id"].max())
    max_fragment = int(fragments["fragment_id"].max())
    max_curve = int(curves["curve_id"].max())
    next_track = max_track + 1
    next_fragment = max_fragment + 1
    next_curve = max_curve + 1
    new_tracks: list[dict[str, object]] = []
    new_features: list[dict[str, object]] = []
    new_products: list[dict[str, object]] = []
    new_treatments: list[dict[str, object]] = []
    new_fragments: list[dict[str, object]] = []
    curve_rows: list[dict[str, float]] = []
    curve_cache: dict[tuple[int, float], int] = {}
    area_factor: dict[int, float] = {}

    for block_id, row in profile.iterrows():
        bid = int(block_id)
        source_frag = fragments.loc[fragments["block_id"].eq(bid)]
        if source_frag.empty:
            continue
        source = source_frag.iloc[0]
        source_track = int(source["track_id"])
        r_area = float(row["residual_area_fraction"])
        if not (0.0 < r_area < 1.0):
            continue
        harvest_volume = float(row["harvest_volume_share"])
        harvest_value = float(row["harvest_value_share"])
        residual_volume = float(row["retained_volume_share"])
        h_area = float(source["area_ha"]) * (1.0 - r_area)
        r_area_ha = float(source["area_ha"]) * r_area
        if h_area <= 0 or r_area_ha <= 0:
            continue
        harvest_track = next_track
        residual_track = next_track + 1
        next_track += 2
        source_name = str(tracks.loc[tracks["track_id"].eq(source_track), "name"].iloc[0])
        new_tracks.extend(
            [
                {
                    "track_id": harvest_track,
                    "name": f"vr-harvest:{source_name}",
                },
                {
                    "track_id": residual_track,
                    "name": f"vr-residual:{source_name}",
                },
            ]
        )
        area_factor[bid] = r_area

        # Harvested feature curves stay managed and keep their per-ha values;
        # the area is the harvested fraction.
        for feature in features.loc[features["track_id"].eq(source_track)].itertuples(
            index=False
        ):
            new_features.append(
                {
                    "track_id": harvest_track,
                    "label": feature.label,
                    "curve_id": int(feature.curve_id),
                }
            )

        # Residual feature curves are unmanaged and scaled to the residual
        # cohort's volume density.  Area features stay area-shaped; yield and
        # carbon features carry the high-graded residual density.
        residual_scale = residual_volume / r_area
        for feature in features.loc[features["track_id"].eq(source_track)].itertuples(
            index=False
        ):
            label = str(feature.label)
            new_label = label.replace("feature.area.managed", "feature.area.unmanaged")
            new_label = new_label.replace(
                "feature.yield.managed", "feature.yield.unmanaged"
            )
            new_label = new_label.replace(
                "feature.carbon.managed", "feature.carbon.unmanaged"
            )
            factor = 1.0
            if label.startswith(("feature.yield.", "feature.carbon.")):
                factor = residual_scale
            curve_id, next_curve = scaled_curve(
                int(feature.curve_id),
                factor,
                curve_lookup,
                curve_rows,
                next_curve,
                curve_cache,
            )
            new_features.append(
                {"track_id": residual_track, "label": new_label, "curve_id": curve_id}
            )

        # Harvested products are scaled by the harvested volume/value share.
        # Leave area and QMD curves unscaled; they describe the harvested area,
        # not the value ledger.
        for product in products.loc[products["track_id"].eq(source_track)].itertuples(
            index=False
        ):
            label = str(product.label)
            if label.startswith("product.yield."):
                factor = harvest_volume / (1.0 - r_area)
            elif label.startswith("product.LogValue."):
                factor = harvest_value / (1.0 - r_area)
            elif label.startswith("product.Cost_Harvesting."):
                factor = harvest_volume / (1.0 - r_area)
            elif label.startswith("product.Cost_Total."):
                factor = harvest_volume / (1.0 - r_area)
            elif label.startswith("product.NetRevenue."):
                factor = harvest_value / (1.0 - r_area)
            else:
                factor = 1.0
            curve_id, next_curve = scaled_curve(
                int(product.curve_id),
                factor,
                curve_lookup,
                curve_rows,
                next_curve,
                curve_cache,
            )
            new_products.append(
                {
                    "track_id": harvest_track,
                    "treatment": product.treatment,
                    "label": label,
                    "curve_id": curve_id,
                }
            )

        for treatment in treatments.loc[
            treatments["track_id"].eq(source_track)
        ].itertuples(index=False):
            new_treatments.append(
                {
                    "track_id": harvest_track,
                    "begin": int(treatment.begin),
                    "end": int(treatment.end),
                    "treatment": treatment.treatment,
                    "new_track": int(treatment.new_track),
                    "offset": int(treatment.offset),
                    "retain": int(treatment.retain),
                }
            )

        # The original harvested fragment keeps its identity but gets the new
        # area and track.  The residual fragment is appended.
        fragments.loc[
            fragments["block_id"].eq(bid), "area_ha"
        ] = h_area
        fragments.loc[
            fragments["block_id"].eq(bid), "track_id"
        ] = harvest_track
        new_fragments.append(
            {
                "fragment_id": next_fragment,
                "block_id": bid,
                "area_ha": r_area_ha,
                "age": int(source["age"]),
                "track_id": residual_track,
            }
        )
        next_fragment += 1

    if curve_rows:
        curves = pd.concat([curves, pd.DataFrame(curve_rows)], ignore_index=True)
    if new_tracks:
        tracks = pd.concat([tracks, pd.DataFrame(new_tracks)], ignore_index=True)
    if new_features:
        features = pd.concat([features, pd.DataFrame(new_features)], ignore_index=True)
    if new_products:
        products = pd.concat([products, pd.DataFrame(new_products)], ignore_index=True)
    if new_treatments:
        treatments = pd.concat(
            [treatments, pd.DataFrame(new_treatments)], ignore_index=True
        )
    if new_fragments:
        fragments = pd.concat(
            [fragments, pd.DataFrame(new_fragments)], ignore_index=True
        )

    blocks = (
        fragments.groupby(["block_id", "track_id"], as_index=False)
        .agg(offset=("age", "min"), area_ha=("area_ha", "sum"))
        .loc[:, ["block_id", "track_id", "offset", "area_ha"]]
    )
    curves.to_parquet(OUT / "curves.parquet", index=False)
    tracks.to_parquet(OUT / "tracks.parquet", index=False)
    features.to_parquet(OUT / "features.parquet", index=False)
    products.to_parquet(OUT / "products.parquet", index=False)
    treatments.to_parquet(OUT / "treatments.parquet", index=False)
    fragments.to_parquet(OUT / "fragments.parquet", index=False)
    blocks.to_parquet(OUT / "blocks.parquet", index=False)

    metadata = {
        "source_matrix": str(BASE),
        "profile": str(PROFILE),
        "blocks_split": len(area_factor),
        "total_area_ha": float(fragments["area_ha"].sum()),
        "residual_area_ha": float(
            sum(
                fragments.loc[
                    fragments["track_id"].isin(
                        [t["track_id"] for t in new_tracks if str(t["name"]).startswith("vr-residual")]
                    ),
                    "area_ha",
                ]
            )
        ),
        "retention_basis": "basal area",
        "selection": "DF-first, largest DBH first",
        "profile_age": "AU rotation age (or current age if older); no age interpolation yet",
        "limits": [
            "Matrix-level pre-split, not a simulator treatment-time split.",
            "Retention intensity is fixed by the silviculture group, not an optimizer decision.",
            "Species DBH shape comes from the synthetic MKRF 684 tree list.",
            "Product scaling is aggregate; grade mix is not yet re-bucketed per residual tree.",
            "Residual area is basal-area-equivalent, not a mapped physical reserve.",
        ],
    }
    (OUT / "vr_assumptions.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
