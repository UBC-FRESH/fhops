#!/usr/bin/env python3
"""Build the MKRF full-area variable-retention intensity grid.

Each profiled block gets a choice track with:

- CC: no retention;
- VR10, VR20 and VR30: first-entry retention at 10/20/30% of pre-harvest BA.

Each VR treatment transitions the full block area to its own composite
plantation + retained-overstory track.  The next CC on that composite track
returns to the normal plantation track.  This makes retention intensity a
discrete optimizer choice while preserving the one-rotation managed-area rule.

The grid keeps only the product/feature labels required by the current target
search; the full matrix remains the source of the other accounts.
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
PROFILE = INSTANCE / "planning" / "2026-11-18_mkrf_retention_profile_grid.csv"
OUT = INSTANCE / "ws4" / "runtime" / "matrix_vr_grid"
GRID = np.arange(0, 301, 20, dtype=float)
INTENSITIES = (0.10, 0.20, 0.30)
KEY_FEATURES = {
    "feature.area.managed.total",
    "feature.area.managed.seral.le10",
    "feature.area.managed.seral.le5",
    "feature.yield.managed.total",
    "feature.yield.managed.merch.total",
    *{f"feature.yield.managed.indsp.{s}" for s in ("Ba", "Cw", "Dec", "Dr", "Fd", "Hw", "Oth", "Yc")},
}
KEY_PRODUCTS = {
    "product.area.managed.total",
    "product.yield.managed.total",
    "product.LogValue.managed.total",
    "product.Cost_Harvesting.managed.total",
    "product.Cost_Total.managed.total",
    "product.NetRevenue.managed.total",
}


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


def add_grid_curve(
    rows: list[dict[str, float]], next_id: int, values: np.ndarray
) -> tuple[int, int]:
    curve_id = next_id
    for x, y in zip(GRID, values, strict=True):
        rows.append({"curve_id": curve_id, "x": float(x), "y": float(max(0.0, y))})
    return curve_id, next_id + 1


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


def factor_for_product(label: str, volume: float, value: float) -> float:
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


def is_volume_feature(label: str) -> bool:
    return label.startswith(("feature.yield.", "feature.carbon."))


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(BASE, OUT)
    profiles = pd.read_csv(PROFILE)
    profiles = profiles.loc[profiles["retention_target_ba_pct"].gt(0)].copy()
    profile_by_block: dict[int, dict[float, dict[str, object]]] = {}
    for row in profiles.itertuples(index=False):
        profile_by_block.setdefault(int(row.block_id), {})[
            round(float(row.retention_target_ba_pct), 2)
        ] = row._asdict()

    fragments = pd.read_parquet(OUT / "fragments.parquet")
    blocks = pd.read_parquet(OUT / "blocks.parquet")
    tracks = pd.read_parquet(OUT / "tracks.parquet")
    features = pd.read_parquet(OUT / "features.parquet")
    products = pd.read_parquet(OUT / "products.parquet")
    treatments = pd.read_parquet(OUT / "treatments.parquet")
    curves = pd.read_parquet(OUT / "curves.parquet")
    lookup = {
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
    blocks_overlaid = 0

    for block_id, targets in profile_by_block.items():
        if not all(key in targets for key in INTENSITIES):
            continue
        source_frag = fragments.loc[fragments["block_id"].eq(block_id)]
        if source_frag.empty:
            continue
        source = source_frag.iloc[0]
        source_track = int(source["track_id"])
        source_products = products.loc[products["track_id"].eq(source_track)]
        source_treatments = treatments.loc[treatments["track_id"].eq(source_track)]
        source_features = features.loc[features["track_id"].eq(source_track)]
        source_cc = source_treatments.loc[source_treatments["treatment"].eq("CC")]
        source_cc_products = source_products.loc[source_products["treatment"].eq("CC")]
        if source_cc.empty or source_cc_products.empty:
            continue
        plantation_track = int(source_cc.iloc[0]["new_track"])
        plantation_features = features.loc[features["track_id"].eq(plantation_track)]
        plantation_products = products.loc[products["track_id"].eq(plantation_track)]
        plantation_treatments = treatments.loc[
            treatments["track_id"].eq(plantation_track)
        ]
        if plantation_features.empty or plantation_products.empty:
            continue
        choice_track = next_track
        next_track += 1
        source_name = str(tracks.loc[tracks["track_id"].eq(source_track), "name"].iloc[0])
        new_tracks.append({"track_id": choice_track, "name": f"vr-choice:{source_name}"})
        blocks_overlaid += 1

        # Choice track: full managed source features and the base CC treatment.
        for feature in source_features.itertuples(index=False):
            new_features.append(
                {
                    "track_id": choice_track,
                    "label": feature.label,
                    "curve_id": int(feature.curve_id),
                }
            )
        for product in source_cc_products.itertuples(index=False):
            new_products.append(
                {
                    "track_id": choice_track,
                    "treatment": "CC",
                    "label": product.label,
                    "curve_id": int(product.curve_id),
                }
            )
        source_cc_row = source_cc.iloc[0]
        new_treatments.append(
            {
                "track_id": choice_track,
                "begin": int(source_cc_row["begin"]),
                "end": int(source_cc_row["end"]),
                "treatment": "CC",
                "new_track": plantation_track,
                "offset": int(source_cc_row["offset"]),
                "retain": int(source_cc_row["retain"]),
            }
        )

        for intensity in INTENSITIES:
            row = targets[intensity]
            f_vol = float(row["harvest_volume_share"])
            f_val = float(row["harvest_value_share"])
            r_vol = float(row["retained_volume_share"])
            r_val = float(row["retained_value_share"])
            profile_age = float(row["profile_age"])
            label = f"VR{int(round(intensity * 100)):02d}"
            combined_track = next_track
            next_track += 1
            new_tracks.append(
                {"track_id": combined_track, "name": f"vr-combined-{label}:{source_name}"}
            )

            # First-entry VR products on the choice track.
            for product in source_cc_products.itertuples(index=False):
                name = str(product.label)
                factor = factor_for_product(name, f_vol, f_val)
                curve_id, next_curve = scaled_curve(
                    int(product.curve_id),
                    factor,
                    lookup,
                    curve_rows,
                    next_curve,
                    scaled_cache,
                )
                new_products.append(
                    {
                        "track_id": choice_track,
                        "treatment": label,
                        "label": name,
                        "curve_id": curve_id,
                    }
                )
            new_treatments.append(
                {
                    "track_id": choice_track,
                    "begin": int(source_cc_row["begin"]),
                    "end": int(source_cc_row["end"]),
                    "treatment": label,
                    "new_track": combined_track,
                    "offset": int(source_cc_row["offset"]),
                    "retain": int(source_cc_row["retain"]),
                }
            )

            # Retention policy accounts.  These are first-entry products, not
            # harvested timber: they expose the retained cohort to targets.
            area = float(row["area_ha"])
            retained_ba = float(row["retained_ba_m2"])
            retained_volume = float(row["total_volume_m3"]) * r_vol
            retained_value = float(row["total_gross_value_cad"]) * r_val
            for account, value in (
                ("product.ba.retention.total", retained_ba / area),
                ("product.area.retention.total", float(row["residual_area_fraction"])),
                ("product.volume.retention.total", retained_volume / area),
                ("product.LogValue.retention.total", retained_value / area),
            ):
                curve_id, next_curve = add_grid_curve(
                    curve_rows,
                    next_curve,
                    np.full(GRID.shape, float(value), dtype=float),
                )
                new_products.append(
                    {
                        "track_id": choice_track,
                        "treatment": label,
                        "label": account,
                        "curve_id": curve_id,
                    }
                )

            # Composite track features: plantation plus retained overstory.
            for feature in plantation_features.itertuples(index=False):
                name = str(feature.label)
                if name not in KEY_FEATURES:
                    continue
                base_curve = int(feature.curve_id)
                if is_volume_feature(name):
                    source_match = source_features.loc[source_features["label"].eq(name)]
                    if source_match.empty:
                        curve_id = base_curve
                    else:
                        source_curve = int(source_match.iloc[0]["curve_id"])
                        values = np.array(
                            [
                                curve_at(lookup, base_curve, age)
                                + r_vol * curve_at(lookup, source_curve, profile_age + age)
                                for age in GRID
                            ]
                        )
                        curve_id, next_curve = add_grid_curve(
                            curve_rows, next_curve, values
                        )
                else:
                    curve_id = base_curve
                new_features.append(
                    {"track_id": combined_track, "label": name, "curve_id": curve_id}
                )

            # Composite track products.  Only key labels are retained.
            for product in plantation_products.loc[
                plantation_products["treatment"].eq("CC")
            ].itertuples(index=False):
                name = str(product.label)
                if name not in KEY_PRODUCTS:
                    continue
                base_curve = int(product.curve_id)
                if name.startswith(
                    (
                        "product.yield.",
                        "product.LogValue.",
                        "product.Cost_Harvesting.",
                        "product.Cost_Total.",
                        "product.NetRevenue.",
                    )
                ):
                    source_match = source_cc_products.loc[
                        source_cc_products["label"].eq(name)
                    ]
                    if source_match.empty:
                        curve_id = base_curve
                    else:
                        source_curve = int(source_match.iloc[0]["curve_id"])
                        factor = r_val if name.startswith(
                            ("product.LogValue.", "product.NetRevenue.")
                        ) else r_vol
                        values = np.array(
                            [
                                curve_at(lookup, base_curve, age)
                                + factor
                                * curve_at(lookup, source_curve, profile_age + age)
                                for age in GRID
                            ]
                        )
                        curve_id, next_curve = add_grid_curve(
                            curve_rows, next_curve, values
                        )
                else:
                    curve_id = base_curve
                new_products.append(
                    {
                        "track_id": combined_track,
                        "treatment": "CC",
                        "label": name,
                        "curve_id": curve_id,
                    }
                )

            # Next final harvest from the composite track returns to the normal
            # plantation track.
            plantation_cc = plantation_treatments.loc[
                plantation_treatments["treatment"].eq("CC")
            ]
            if not plantation_cc.empty:
                row_cc = plantation_cc.iloc[0]
                new_treatments.append(
                    {
                        "track_id": combined_track,
                        "begin": int(row_cc["begin"]),
                        "end": int(row_cc["end"]),
                        "treatment": "CC",
                        "new_track": int(row_cc["new_track"]),
                        "offset": int(row_cc["offset"]),
                        "retain": int(row_cc["retain"]),
                    }
                )

        fragments.loc[fragments["block_id"].eq(block_id), "track_id"] = choice_track

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
        "blocks_with_choice": blocks_overlaid,
        "intensities": list(INTENSITIES),
        "treatments": ["CC", "VR10", "VR20", "VR30"],
        "state": (
            "full managed area; CC is no retention; VRxx uses a composite "
            "plantation + retained-overstory track; next CC returns to normal plantation"
        ),
        "area_ha": float(fragments["area_ha"].sum()),
        "retained_product_labels": sorted(KEY_PRODUCTS),
        "retained_feature_labels": sorted(KEY_FEATURES),
        "limits": [
            "Composite curves are additive, not a two-cohort growth model.",
            "The grid uses a 20-year curve grid for combined tracks.",
            "Only target-relevant product/feature labels are retained on the choice and composite tracks.",
            "Profile age uses a rotation/rotation+50 quantile blend; one profile age per block.",
            "Species DBH shape is the synthetic MKRF 684 tree list at rotation and PSP CWHdm FD at rotation+50, scaled by VRI.",
        ],
    }
    (OUT / "vr_grid_assumptions.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
