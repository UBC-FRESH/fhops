#!/usr/bin/env python3
"""Build residual-retention (dfret) matrix variants from the no-retention base.

The no-retention matrix keeps the area managed.  Product curves are reduced by
the residual value/volume profile and by the residual share of harvest cost.
This is the first matrix-level residual-retention screen; the state transition
still treats the block as harvested and must be upgraded before the results are
decision-grade.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-mkrf-instance")
DEMO = ROOT / "examples" / "demo_runs"
BASE = INSTANCE / "ws4" / "runtime" / "matrix_no_retention_true_patched"
PROFILE = DEMO / "MKRF_RETENTION_PROFILE.csv"
BASE_REPORT = INSTANCE / "ws4" / "runtime" / "dfret_no_retention_true_s44" / "report_accounts.csv"

RUNS = {
    "low": DEMO / "mkrf-low-estate" / "report_accounts.csv",
    "base": DEMO / "mkrf-full-estate" / "report_accounts.csv",
    "high": DEMO / "mkrf-high-estate" / "report_accounts.csv",
}


def mean(frame: pd.DataFrame, account: str, *, annual: bool) -> float:
    row = frame.loc[frame["account"] == account]
    if row.empty:
        raise KeyError(account)
    return float(row.iloc[0]["mean"]) * (100.0 if annual else 1.0)


def interpolate(profile: pd.DataFrame, fraction: float, column: str) -> float:
    return float(
        np.interp(
            fraction,
            profile["tree_fraction"].to_numpy(),
            profile[column].to_numpy(),
        )
    )


def build_factors() -> dict[str, dict[str, float]]:
    profile = pd.read_csv(PROFILE)
    base = pd.read_csv(BASE_REPORT)
    gross = mean(base, "product.LogValue.managed.total", annual=True)
    harvest = mean(base, "product.Cost_Harvesting.managed.total", annual=True)
    total_cost = mean(base, "product.Cost_Total.managed.total", annual=True)
    net = gross - total_cost
    other = total_cost - harvest
    factors: dict[str, dict[str, float]] = {}
    for label, path in RUNS.items():
        area = pd.read_csv(path)
        managed = mean(area, "feature.area.managed.total", annual=False)
        retention = mean(area, "feature.area.retention.total", annual=False)
        fraction = retention / (managed + retention)
        value_share = interpolate(profile, fraction, "value_share")
        volume_share = interpolate(profile, fraction, "volume_share")
        new_gross = gross * (1.0 - value_share)
        new_harvest = harvest * (1.0 - volume_share)
        new_net = new_gross - other - new_harvest
        factors[label] = {
            "retention_fraction": fraction,
            "value_factor": 1.0 - value_share,
            "volume_factor": 1.0 - volume_share,
            "net_factor": new_net / net,
            "gross_factor": new_gross / gross,
            "total_cost_factor": (new_harvest + other) / total_cost,
        }
    return factors


def scale_matrix(label: str, factors: dict[str, float]) -> Path:
    out = INSTANCE / "ws4" / "runtime" / f"matrix_dfret_{label}"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(BASE, out)
    products = pd.read_parquet(out / "products.parquet")
    curves = pd.read_parquet(out / "curves.parquet")
    curve_lookup = {
        int(curve_id): group[["x", "y"]].to_numpy()
        for curve_id, group in curves.groupby("curve_id", sort=False)
    }
    next_id = int(curves["curve_id"].max()) + 1
    cache: dict[tuple[int, float], int] = {}
    new_rows = []

    def scaled_curve(curve_id: int, factor: float) -> int:
        nonlocal next_id
        if abs(factor - 1.0) < 1e-12:
            return curve_id
        key = (int(curve_id), round(float(factor), 12))
        if key in cache:
            return cache[key]
        values = curve_lookup[int(curve_id)]
        new_id = next_id
        next_id += 1
        for x, y in values:
            new_rows.append({"curve_id": new_id, "x": float(x), "y": float(y) * factor})
        cache[key] = new_id
        return new_id

    for index, row in products.iterrows():
        label_name = str(row["label"])
        if label_name.startswith("product.yield."):
            factor = factors["volume_factor"]
        elif label_name.startswith("product.LogValue."):
            factor = factors["value_factor"]
        elif label_name.startswith("product.Cost_Harvesting."):
            factor = factors["volume_factor"]
        elif label_name.startswith("product.Cost_Total."):
            factor = factors["total_cost_factor"]
        elif label_name.startswith("product.NetRevenue."):
            factor = factors["net_factor"]
        else:
            factor = 1.0
        new_id = scaled_curve(int(row["curve_id"]), factor)
        if new_id != int(row["curve_id"]):
            products.at[index, "curve_id"] = new_id

    if new_rows:
        curves = pd.concat([curves, pd.DataFrame(new_rows)], ignore_index=True)
        curves.to_parquet(out / "curves.parquet", index=False)
    products.to_parquet(out / "products.parquet", index=False)
    (out / "dfret_factors.json").write_text(
        pd.Series(factors).to_json(indent=2) + "\n", encoding="utf-8"
    )
    print(label, factors, "new curves", len(cache))
    return out


if __name__ == "__main__":
    factors = build_factors()
    for label, values in factors.items():
        scale_matrix(label, values)
