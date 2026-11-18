#!/usr/bin/env python3
"""Build an MKRF full-area variable-retention overlay matrix.

This follows the corrected state rule: a retained cohort that must remain for
one rotation does **not** remove area from the managed block.  The full block
area transitions to a composite track after the first final harvest.  The
composite track combines the plantation yield/product curves with the retained
DF cohort, so the retained trees are counted in the next final-felling volume
and gross revenue.

The first entry product curves are reduced by the retained volume/value.  The
composite track is then used for the next entry; after that entry the block
returns to the normal plantation track.
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
OUT = INSTANCE / "ws4" / "runtime" / "matrix_vr_overlay_base"
GRID = np.arange(0, 301, 10, dtype=float)


def curve_at(lookup: dict[int, np.ndarray], curve_id: int, age: float) -> float:
    values = lookup[int(curve_id)]
    if values.size == 0:
        return 0.0
    return float(
        np.interp(
            float(age),
            values[:, 0],
            values[:, 1],
            left=values[0, 1],
            right=values[-1, 1],
        )
    )


def add_curve(
    rows: list[dict[str, float]],
    next_id: int,
    values: np.ndarray,
) -> int:
    curve_id = next_id
    for x, y in zip(GRID, values, strict=True):
        rows.append({"curve_id": curve_id, "x": float(x), "y": float(max(0.0, y))})
    return curve_id


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
    values = lookup[int(curve_id)]
    new_id = next_id
    next_id += 1
    for x, y in values:
        rows.append({"curve_id": new_id, "x": float(x), "y": float(y) * factor})
    cache[key] = new_id
    return new_id, next_id


def product_factor(label: str, volume: float, value: float) -> float:
    if label.startswith("product.yield."):
        return volume
    if label.startswith("product.LogValue."):
        return value
    if label.startswith("product.Cost_Harvesting."):
        return volume
    if label.startswith("product.Cost_Total."):
        return volume
    if label.startswith("product.NetRevenue."):
        return value
    return 1.0


def is_combined_feature(label: str) -> bool:
    return label.startswith(("feature.yield.", "feature.carbon."))


def is_combined_product(label: str) -> bool:
    return label.startswith(
        (
            "product.yield.",
            "product.LogValue.",
            "product.Cost_Harvesting.",
            "product.Cost_Total.",
            "product.NetRevenue.",
        )
    )


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
    next_track = int(tracks["track_id"].max()) + 1
    next_curve = int(curves["curve_id"].max()) + 1
    new_tracks: list[dict[str, object]] = []
    new_features: list[dict[str, object]] = []
    new_products: list[dict[str, object]] = []
    new_treatments: list[dict[str, object]] = []
    curve_rows: list[dict[str, float]] = []
    scaled_cache: dict[tuple[int, float], int] = {}
    split_blocks = 0

    for block_id, row in profile.iterrows():
        block = int(block_id)
        source_frag = fragments.loc[fragments["block_id"].eq(block)]
        if source_frag.empty:
            continue
        source = source_frag.iloc[0]
        source_track = int(source["track_id"])
        source_products = products.loc[products["track_id"].eq(source_track)]
        source_treatments = treatments.loc[treatments["track_id"].eq(source_track)]
        cc = source_treatments.loc[source_treatments["treatment"].eq("CC")]
        if cc.empty:
            continue
        plantation_track = int(cc.iloc[0]["new_track"])
        plantation_features = features.loc[features["track_id"].eq(plantation_track)]
        plantation_products = products.loc[products["track_id"].eq(plantation_track)]
        plantation_treatments = treatments.loc[
            treatments["track_id"].eq(plantation_track)
        ]
        if plantation_features.empty or plantation_products.empty:
            continue
        f_vol = float(row["harvest_volume_share"])
        f_val = float(row["harvest_value_share"])
        r_vol = float(row["retained_volume_share"])
        r_val = float(row["retained_value_share"])
        profile_age = float(row["profile_age"])
        if not (0.0 < f_vol < 1.0 and 0.0 < f_val < 1.0):
            continue

        first_track = next_track
        combined_track = next_track + 1
        next_track += 2
        source_name = str(tracks.loc[tracks["track_id"].eq(source_track), "name"].iloc[0])
        plantation_name = str(
            tracks.loc[tracks["track_id"].eq(plantation_track), "name"].iloc[0]
        )
        new_tracks.extend(
            [
                {"track_id": first_track, "name": f"vr-first:{source_name}"},
                {"track_id": combined_track, "name": f"vr-combined:{plantation_name}"},
            ]
        )
        split_blocks += 1

        # First entry: full area remains managed; product curves are reduced by
        # the residual cohort volume/value.  No area moves to unmanaged.
        for feature in features.loc[features["track_id"].eq(source_track)].itertuples(
            index=False
        ):
            new_features.append(
                {
                    "track_id": first_track,
                    "label": feature.label,
                    "curve_id": int(feature.curve_id),
                }
            )
        for product in source_products.itertuples(index=False):
            factor = product_factor(str(product.label), f_vol, f_val)
            curve_id, next_curve = scaled_curve(
                int(product.curve_id),
                factor,
                curve_lookup,
                curve_rows,
                next_curve,
                scaled_cache,
            )
            new_products.append(
                {
                    "track_id": first_track,
                    "treatment": product.treatment,
                    "label": product.label,
                    "curve_id": curve_id,
                }
            )
        for treatment in source_treatments.itertuples(index=False):
            new_treatments.append(
                {
                    "track_id": first_track,
                    "begin": int(treatment.begin),
                    "end": int(treatment.end),
                    "treatment": treatment.treatment,
                    "new_track": (
                        combined_track
                        if str(treatment.treatment) == "CC"
                        else int(treatment.new_track)
                    ),
                    "offset": int(treatment.offset),
                    "retain": int(treatment.retain),
                }
            )

        # Composite plantation + retained overstory track.  The curve grid is
        # time since the first harvest.  The retained component uses the
        # pre-treatment source curve at profile_age + t, scaled so that its
        # volume/value at t=0 equals the selected residual cohort.
        for feature in plantation_features.itertuples(index=False):
            label = str(feature.label)
            base_curve = int(feature.curve_id)
            if is_combined_feature(label):
                source_curve = None
                for candidate in features.loc[
                    features["track_id"].eq(source_track)
                ].itertuples(index=False):
                    if candidate.label == label:
                        source_curve = int(candidate.curve_id)
                        break
                if source_curve is None:
                    curve_id = base_curve
                else:
                    factor = r_vol
                    values = np.array(
                        [
                            curve_at(curve_lookup, base_curve, age)
                            + factor
                            * curve_at(curve_lookup, source_curve, profile_age + age)
                            for age in GRID
                        ]
                    )
                    curve_id = add_curve(curve_rows, next_curve, values)
                    next_curve += 1
            else:
                curve_id = base_curve
            new_features.append(
                {"track_id": combined_track, "label": label, "curve_id": curve_id}
            )

        for product in plantation_products.itertuples(index=False):
            label = str(product.label)
            base_curve = int(product.curve_id)
            if is_combined_product(label):
                source_curve = None
                for candidate in source_products.itertuples(index=False):
                    if candidate.label == label:
                        source_curve = int(candidate.curve_id)
                        break
                if source_curve is None:
                    curve_id = base_curve
                else:
                    factor = r_vol
                    if label.startswith(("product.LogValue.", "product.NetRevenue.")):
                        factor = r_val
                    values = np.array(
                        [
                            curve_at(curve_lookup, base_curve, age)
                            + factor
                            * curve_at(curve_lookup, source_curve, profile_age + age)
                            for age in GRID
                        ]
                    )
                    curve_id = add_curve(curve_rows, next_curve, values)
                    next_curve += 1
            else:
                curve_id = base_curve
            new_products.append(
                {
                    "track_id": combined_track,
                    "treatment": product.treatment,
                    "label": label,
                    "curve_id": curve_id,
                }
            )

        for treatment in plantation_treatments.itertuples(index=False):
            new_treatments.append(
                {
                    "track_id": combined_track,
                    "begin": int(treatment.begin),
                    "end": int(treatment.end),
                    "treatment": treatment.treatment,
                    "new_track": int(treatment.new_track),
                    "offset": int(treatment.offset),
                    "retain": int(treatment.retain),
                }
            )

        fragments.loc[fragments["block_id"].eq(block), "track_id"] = first_track

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
        "blocks_overlaid": split_blocks,
        "total_area_ha": float(fragments["area_ha"].sum()),
        "managed_area_unchanged": True,
        "state": (
            "full block area remains managed; first harvest transitions to a "
            "composite plantation + retained-overstory track; second harvest "
            "returns to the normal plantation track"
        ),
        "basis": "basal area; DF-first largest-DBH selection",
        "limits": [
            "Composite curves are an additive approximation, not a two-cohort growth model.",
            "Retained volume/value enters the next CC product curve; future harvest is where it is counted.",
            "Profile age is currently one anchor, not rotation+50 interpolation.",
            "Species DBH shape is the synthetic MKRF 684 tree list scaled by VRI.",
            "No spatial group layout.",
        ],
    }
    (OUT / "vr_overlay_assumptions.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
