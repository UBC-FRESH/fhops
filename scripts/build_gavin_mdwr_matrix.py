#!/usr/bin/env python3
"""Build a Gavin Lake MDWR group-selection matrix.

The legacy Gavin matrix has one treatment, clearcut at age 80.  This script
clones the tracks used by Beaver Valley MDWR blocks, removes clearcut from those
clones, and adds a group-selection treatment with the Table 30 pass intensity and
a 40-year re-entry.

The legacy layer does not carry the adjusted 2007 Appendix 9 habitat-class
attribute.  By default the script uses the documented BEC proxy:

- ICHmk3 -> High (33% per pass)
- ICHmk3/SBSdw -> Moderate (25% per pass)
- SBSdw1 -> Low (20% per pass)

``--habitat-table`` can instead supply block-level ``model_class`` values from
the official long-term objective extraction in the instance planning folder.

The result is a full-area partial-cut volume screen.  It does not split a block
into spatial groups or model the 0.4/0.7 ha group-size limit.  The current clone
resets fragment age on every pass, so the 40-year re-entry needs a separate
state fix before its later-pass volumes can be treated as validated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
BASE = INSTANCE / "ws4" / "runtime" / "legacy_matrix"
SPATIAL = INSTANCE / "data" / "legacy_gavinlake" / "spatial" / "fragments.shp"
OUT = INSTANCE / "ws4" / "runtime" / "mdwr_group_selection"
CLASSES = {
    "ICHmk3": ("High", 0.33, "GS33"),
    "ICHmk3/SBSdw": ("Moderate", 0.25, "GS25"),
    "SBSdw1": ("Low", 0.20, "GS20"),
}
FIRST_ENTRY_AGE = 80
REENTRY_YEARS = 40
# WS4 negative-offset sentinel: retain the fragment age across a partial cut.
KEEP_AGE_OFFSET = -1


def spatial_attributes(habitat_table: Path | None = None) -> pd.DataFrame:
    frame = gpd.read_file(SPATIAL)
    frame["block_id"] = frame["RES_KEY"].astype(int)
    working = (
        frame.groupby("block_id")["WORKING_CI"]
        .agg(lambda values: values.mode().iloc[0])
        .rename("working_circle")
    )
    bec = (
        frame.groupby("block_id")["BEC"]
        .agg(lambda values: values.mode().iloc[0])
        .rename("bec")
    )
    attrs = pd.concat([working, bec], axis=1)
    if habitat_table is None:
        attrs["habitat"] = attrs["bec"].map(
            {"ICHmk3": "High", "ICHmk3/SBSdw": "Moderate", "SBSdw1": "Low"}
        ).fillna("Low")
        attrs["class_basis"] = "bec_proxy"
    else:
        table = pd.read_csv(habitat_table)
        table["block_id"] = table["block_id"].astype(int)
        table = table.set_index("block_id")
        attrs["habitat"] = table["model_class"].reindex(attrs.index).fillna("Low")
        attrs["class_basis"] = table["class_basis"].reindex(attrs.index).fillna("bec_fallback")
    return attrs.reset_index()


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
    key = (int(curve_id), round(float(factor), 12))
    if key in cache:
        return cache[key], next_id
    new_id = next_id
    next_id += 1
    values = lookup[int(curve_id)]
    for x, y in values:
        rows.append({"curve_id": new_id, "x": float(x), "y": float(y) * factor})
    cache[key] = new_id
    return new_id, next_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--habitat-table", type=Path)
    args = parser.parse_args()
    out = args.out
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(BASE, out)
    fragments = pd.read_parquet(out / "fragments.parquet")
    blocks = pd.read_parquet(out / "blocks.parquet")
    tracks = pd.read_parquet(out / "tracks.parquet")
    features = pd.read_parquet(out / "features.parquet")
    products = pd.read_parquet(out / "products.parquet")
    treatments = pd.read_parquet(out / "treatments.parquet")
    curves = pd.read_parquet(out / "curves.parquet")
    attrs = spatial_attributes(args.habitat_table).set_index("block_id")

    next_track = int(tracks["track_id"].max()) + 1
    next_curve = int(curves["curve_id"].max()) + 1
    curve_lookup = {
        int(curve_id): group.sort_values("x")[["x", "y"]].to_numpy()
        for curve_id, group in curves.groupby("curve_id", sort=False)
    }
    curve_rows: list[dict[str, float]] = []
    curve_cache: dict[tuple[int, float], int] = {}
    clone: dict[tuple[int, str], dict[str, int]] = {}
    new_tracks: list[dict[str, object]] = []
    new_features: list[dict[str, object]] = []
    new_products: list[dict[str, object]] = []
    new_treatments: list[dict[str, object]] = []
    area_by_class: dict[str, float] = {}
    blocks_by_class: dict[str, int] = {}

    def clone_track(source: int, habitat: str) -> dict[str, int]:
        nonlocal next_track
        key = (int(source), habitat)
        if key in clone:
            return clone[key]
        source_name = str(tracks.loc[tracks["track_id"] == source, "name"].iloc[0])
        initial = next_track
        cycle = next_track + 1
        next_track += 2
        clone[key] = {"initial": initial, "cycle": cycle}
        new_tracks.extend(
            [
                {"track_id": initial, "name": f"mdwr-{habitat}-initial:{source_name}"},
                {"track_id": cycle, "name": f"mdwr-{habitat}-cycle:{source_name}"},
            ]
        )
        for feature in features.loc[features["track_id"] == source].itertuples(index=False):
            for track_id in (initial, cycle):
                new_features.append(
                    {
                        "track_id": track_id,
                        "label": feature.label,
                        "curve_id": int(feature.curve_id),
                    }
                )
        return clone[key]

    # Build the clones only for MDWR fragments, and assign those fragments to
    # the initial group-selection track.
    for index, row in fragments.iterrows():
        block_id = int(row["block_id"])
        if block_id not in attrs.index:
            continue
        props = attrs.loc[block_id]
        if props["working_circle"] != "MDWR":
            continue
        habitat = str(props["habitat"])
        if habitat not in CLASSES_BY_HABITAT:
            habitat = "Low"
        tracks_for_block = clone_track(int(row["track_id"]), habitat)
        fragments.at[index, "track_id"] = tracks_for_block["initial"]
        area_by_class[habitat] = area_by_class.get(habitat, 0.0) + float(row["area_ha"])
        blocks_by_class[habitat] = blocks_by_class.get(habitat, 0) + 1
        block_rows = blocks.loc[blocks["block_id"] == block_id]
        if not block_rows.empty:
            blocks.loc[block_rows.index, "track_id"] = tracks_for_block["initial"]

    # Add products and treatments for every clone.  The CC product curves are
    # the full-stand curves; the pass fraction scales yield, treated area, and
    # carbon removal.  Feature curves are copied unchanged.
    for (source, habitat), ids in clone.items():
        fraction = CLASSES_BY_HABITAT[habitat][1]
        treatment = CLASSES_BY_HABITAT[habitat][2]
        source_products = products.loc[
            (products["track_id"] == source) & (products["treatment"] == "CC")
        ]
        for target_track in (ids["initial"], ids["cycle"]):
            for product in source_products.itertuples(index=False):
                name = str(product.label)
                factor = (
                    fraction
                    if name.startswith("product.yield.")
                    or name.startswith("product.area.")
                    or name.startswith("product.carbon.")
                    else 1.0
                )
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
                        "track_id": int(target_track),
                        "treatment": treatment,
                        "label": name,
                        "curve_id": int(curve_id),
                    }
                )
        new_treatments.extend(
            [
                {
                    "track_id": int(ids["initial"]),
                    "begin": FIRST_ENTRY_AGE,
                    "end": 998,
                    "treatment": treatment,
                    "new_track": int(ids["cycle"]),
                    "offset": KEEP_AGE_OFFSET,
                    "retain": 0,
                },
                {
                    "track_id": int(ids["cycle"]),
                    "begin": REENTRY_YEARS,
                    "end": 998,
                    "treatment": treatment,
                    "new_track": int(ids["cycle"]),
                    "offset": KEEP_AGE_OFFSET,
                    "retain": 0,
                },
            ]
        )

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

    curves.to_parquet(out / "curves.parquet", index=False)
    tracks.to_parquet(out / "tracks.parquet", index=False)
    features.to_parquet(out / "features.parquet", index=False)
    products.to_parquet(out / "products.parquet", index=False)
    treatments.to_parquet(out / "treatments.parquet", index=False)
    fragments.to_parquet(out / "fragments.parquet", index=False)
    blocks.to_parquet(out / "blocks.parquet", index=False)

    metadata = {
        "source": str(BASE),
        "spatial": str(SPATIAL),
        "working_circle": "MDWR",
        "no_clearcut_in_mdwr": True,
        "first_entry_age": FIRST_ENTRY_AGE,
        "reentry_years": REENTRY_YEARS,
        "partial_cut_age_semantics": "negative offset preserves fragment age",
        "table30": {
            "High": {"fraction": 0.33, "treatment": "GS33", "cohorts": 3, "max_age": 120},
            "Moderate": {"fraction": 0.25, "treatment": "GS25", "cohorts": 4, "max_age": 160},
            "Low": {"fraction": 0.20, "treatment": "GS20", "cohorts": 5, "max_age": 200},
        },
        "habitat_class_source": (
            "official_fine_map" if args.habitat_table else "bec_proxy"
        ),
        "habitat_table": str(args.habitat_table) if args.habitat_table else None,
        "habitat_table_sha256": (
            hashlib.sha256(args.habitat_table.read_bytes()).hexdigest()
            if args.habitat_table
            else None
        ),
        "habitat_class_proxy": {
            "ICHmk3": "High",
            "ICHmk3/SBSdw": "Moderate",
            "SBSdw1": "Low",
            "note": (
                "BEC proxy used only where the official table falls back or "
                "where no habitat table is supplied."
            ),
        },
        "area_by_class_ha": area_by_class,
        "blocks_by_class": blocks_by_class,
        "new_tracks": len(new_tracks),
        "new_curve_points": len(curve_rows),
        "limits": [
            "Full-area partial-cut volume screen, not spatial group layout.",
            "No 0.4/0.7 ha group-size constraint.",
            "No preparatory-thinning pass.",
            "Carbon curves are scaled with the pass fraction as a rough screen.",
        ],
    }
    (out / "mdwr_assumptions.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "built",
        out,
        "classes",
        area_by_class,
        "blocks",
        blocks_by_class,
        "tracks",
        len(new_tracks),
        "curves",
        len(curve_rows),
    )


CLASSES_BY_HABITAT = {
    value[0]: (value[0], value[1], value[2]) for value in CLASSES.values()
}


if __name__ == "__main__":
    main()
