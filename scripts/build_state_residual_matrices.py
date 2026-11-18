#!/usr/bin/env python3
"""Build a state-aware residual-area proxy matrix.

This is the next step after the residual-product screen.  For each block, the
no-retention fragment is split into:

- a harvested portion on the original managed track; and
- a residual portion on a new managed track with copied features and no
  scheduled treatment.

The residual portion remains in the state and continues to age/grow.  The split
fraction is the largest-DF **value-equivalent area** from the audit profile.
This is an area proxy for a stem cohort, not a measured tree-level residual
prescription.

The harvested curves receive a fixed-cost correction: the area split removes
the residual value-equivalent area, while the no-retention net/cost curves still
contain whole-block fixed costs.  Net revenue and total cost are therefore
scaled to reconcile with the product-ledger residual screen at the same
schedule.
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
BASE_REPORT = INSTANCE / "ws4" / "runtime" / "dfret_no_retention_true_s44" / "report_accounts.csv"
PROFILE = ROOT / "examples" / "demo_runs" / "MKRF_RETENTION_PROFILE.csv"
AREA_RUNS = {
    "low": ROOT / "examples" / "demo_runs" / "mkrf-low-estate" / "report_accounts.csv",
    "base": ROOT / "examples" / "demo_runs" / "mkrf-full-estate" / "report_accounts.csv",
    "high": ROOT / "examples" / "demo_runs" / "mkrf-high-estate" / "report_accounts.csv",
}


def mean(frame: pd.DataFrame, account: str, *, annual: bool) -> float:
    row = frame.loc[frame["account"] == account]
    if row.empty:
        raise KeyError(account)
    return float(row.iloc[0]["mean"]) * (100.0 if annual else 1.0)


def factors(label: str) -> dict[str, float]:
    profile = pd.read_csv(PROFILE)
    area = pd.read_csv(AREA_RUNS[label])
    base = pd.read_csv(BASE_REPORT)
    managed = mean(area, "feature.area.managed.total", annual=False)
    retention = mean(area, "feature.area.retention.total", annual=False)
    tree_fraction = retention / (managed + retention)
    value_share = float(
        np.interp(
            tree_fraction,
            profile["tree_fraction"].to_numpy(),
            profile["value_share"].to_numpy(),
        )
    )
    volume_share = float(
        np.interp(
            tree_fraction,
            profile["tree_fraction"].to_numpy(),
            profile["volume_share"].to_numpy(),
        )
    )
    gross = mean(base, "product.LogValue.managed.total", annual=True)
    harvest = mean(base, "product.Cost_Harvesting.managed.total", annual=True)
    total_cost = mean(base, "product.Cost_Total.managed.total", annual=True)
    net = gross - total_cost
    other = total_cost - harvest
    harvested_area_factor = 1.0 - value_share
    new_gross = gross * (1.0 - value_share)
    new_harvest = harvest * (1.0 - volume_share)
    new_total_cost = other + new_harvest
    new_net = new_gross - new_total_cost
    return {
        "retention_fraction": tree_fraction,
        "value_share": value_share,
        "volume_share": volume_share,
        "residual_share_of_block_area": value_share,
        "harvested_area_factor": harvested_area_factor,
        "yield_curve_factor": (1.0 - volume_share) / harvested_area_factor,
        "harvest_curve_factor": (1.0 - volume_share) / harvested_area_factor,
        "net_curve_factor": new_net / (net * harvested_area_factor),
        "total_cost_curve_factor": new_total_cost / (total_cost * harvested_area_factor),
        "gross_curve_factor": 1.0,
    }


def scale_products(out: Path, values: dict[str, float]) -> int:
    products = pd.read_parquet(out / "products.parquet")
    curves = pd.read_parquet(out / "curves.parquet")
    curve_lookup = {
        int(curve_id): group[["x", "y"]].to_numpy()
        for curve_id, group in curves.groupby("curve_id", sort=False)
    }
    next_id = int(curves["curve_id"].max()) + 1
    cache: dict[tuple[int, float], int] = {}
    rows = []

    def scaled_curve(curve_id: int, factor: float) -> int:
        nonlocal next_id
        if abs(factor - 1.0) < 1e-12:
            return curve_id
        key = (int(curve_id), round(float(factor), 12))
        if key in cache:
            return cache[key]
        new_id = next_id
        next_id += 1
        for x, y in curve_lookup[int(curve_id)]:
            rows.append({"curve_id": new_id, "x": float(x), "y": float(y) * factor})
        cache[key] = new_id
        return new_id

    for index, row in products.iterrows():
        name = str(row["label"])
        if name.startswith("product.yield."):
            factor = values["yield_curve_factor"]
        elif name.startswith("product.LogValue."):
            factor = values["gross_curve_factor"]
        elif name.startswith("product.Cost_Harvesting."):
            factor = values["harvest_curve_factor"]
        elif name.startswith("product.Cost_Total."):
            factor = values["total_cost_curve_factor"]
        elif name.startswith("product.NetRevenue."):
            factor = values["net_curve_factor"]
        else:
            factor = 1.0
        new_id = scaled_curve(int(row["curve_id"]), factor)
        if new_id != int(row["curve_id"]):
            products.at[index, "curve_id"] = new_id
    if rows:
        pd.concat([curves, pd.DataFrame(rows)], ignore_index=True).to_parquet(
            out / "curves.parquet", index=False
        )
    products.to_parquet(out / "products.parquet", index=False)
    return len(cache)


def build(label: str, values: dict[str, float]) -> Path:
    out = INSTANCE / "ws4" / "runtime" / f"matrix_dfret_state_{label}"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(BASE, out)
    fragments = pd.read_parquet(out / "fragments.parquet")
    tracks = pd.read_parquet(out / "tracks.parquet")
    features = pd.read_parquet(out / "features.parquet")
    residual_share = values["residual_share_of_block_area"]
    next_track = int(tracks["track_id"].max()) + 1
    next_fragment = int(fragments["fragment_id"].max()) + 1
    new_tracks = []
    new_fragments = []
    new_features = []
    track_map: dict[int, int] = {}
    for row in fragments.itertuples(index=False):
        tid = int(row.track_id)
        if tid not in track_map:
            track_map[tid] = next_track
            next_track += 1
            name = str(tracks.loc[tracks["track_id"] == tid, "name"].iloc[0])
            new_tracks.append({"track_id": track_map[tid], "name": f"residual:{name}"})
            for feature in features.loc[features["track_id"] == tid].itertuples(index=False):
                new_features.append(
                    {
                        "track_id": track_map[tid],
                        "label": feature.label,
                        "curve_id": int(feature.curve_id),
                    }
                )
        area = float(row.area_ha)
        new_fragments.append(
            {
                "fragment_id": next_fragment,
                "block_id": int(row.block_id),
                "area_ha": area * residual_share,
                "age": int(row.age),
                "track_id": track_map[tid],
            }
        )
        next_fragment += 1
    harvested = fragments.copy()
    harvested["area_ha"] = harvested["area_ha"].astype(float) * (1.0 - residual_share)
    fragments_out = pd.concat([harvested, pd.DataFrame(new_fragments)], ignore_index=True)
    tracks_out = pd.concat([tracks, pd.DataFrame(new_tracks)], ignore_index=True)
    features_out = pd.concat([features, pd.DataFrame(new_features)], ignore_index=True)
    blocks = (
        fragments_out.groupby(["block_id", "track_id"], as_index=False)
        .agg(offset=("age", "min"), area_ha=("area_ha", "sum"))
        .loc[:, ["block_id", "track_id", "offset", "area_ha"]]
    )
    fragments_out.to_parquet(out / "fragments.parquet", index=False)
    tracks_out.to_parquet(out / "tracks.parquet", index=False)
    features_out.to_parquet(out / "features.parquet", index=False)
    blocks.to_parquet(out / "blocks.parquet", index=False)
    scaled = scale_products(out, values)
    (out / "state_residual.json").write_text(
        json.dumps(
            {
                "label": label,
                **values,
                "residual_tracks": len(new_tracks),
                "residual_fragments": len(new_fragments),
                "scaled_product_curves": scaled,
                "note": (
                    "Value-equivalent area proxy; residual tracks have copied "
                    "features and no scheduled treatment. Harvested net/cost curves "
                    "carry the fixed-cost correction."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        label,
        values,
        "tracks",
        len(new_tracks),
        "fragments",
        len(new_fragments),
        "scaled curves",
        scaled,
    )
    return out


if __name__ == "__main__":
    for label in ("low", "base", "high"):
        build(label, factors(label))
