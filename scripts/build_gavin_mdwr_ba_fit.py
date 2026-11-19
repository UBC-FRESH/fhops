#!/usr/bin/env python3
"""Fit a screening BA-volume-age curve from the Gavin VRI inventory.

Model: BA = b * volume + c * (1 - exp(-age / tau))
The model is zero at age zero, uses live volume and projected age, and is fitted
separately by BEC. It is an empirical screening calibration, not a plantation
growth model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
from scipy.optimize import curve_fit

INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
VRI = Path("/srv/shared-data/gep/ws4/tmp/afrf-repos/femic-afrf-gavinlake-instance/data/inventory/vri_gavin_2025.gpkg")


def model(volume: np.ndarray, age: np.ndarray, b: float, c: float, tau: float) -> np.ndarray:
    return b * volume + c * (1.0 - np.exp(-age / tau))


def fit_model(xdata: tuple[np.ndarray, np.ndarray], b: float, c: float, tau: float) -> np.ndarray:
    """Curve-fit adapter for the two-array BA model."""
    return model(xdata[0], xdata[1], b, c, tau)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vri", type=Path, default=VRI)
    parser.add_argument("--out", type=Path, default=INSTANCE / "planning" / "2026-11-19_gavin-mdwr_ba_fit.json")
    args = parser.parse_args()
    vri = gpd.read_file(args.vri)
    vri["bec"] = (
        vri["BEC_ZONE_CODE"].fillna("")
        + vri["BEC_SUBZONE"].fillna("")
        + vri["BEC_VARIANT"].fillna("")
    )
    data = vri[["bec", "BASAL_AREA", "PROJ_AGE_1", "LIVE_STAND_VOLUME_125"]].dropna()
    data = data[data["LIVE_STAND_VOLUME_125"] > 0]
    fits: dict[str, object] = {}
    for bec, group in data.groupby("bec"):
        volume = group["LIVE_STAND_VOLUME_125"].to_numpy(dtype=float)
        age = group["PROJ_AGE_1"].to_numpy(dtype=float)
        ba = group["BASAL_AREA"].to_numpy(dtype=float)
        parameters, _ = curve_fit(
            fit_model,
            (volume, age),
            ba,
            p0=[0.08, 10.0, 15.0],
            bounds=([0.0, 0.0, 1.0], [1.0, 60.0, 200.0]),
            maxfev=100000,
        )
        predicted = model(volume, age, *parameters)
        r2 = 1.0 - ((ba - predicted) ** 2).sum() / ((ba - ba.mean()) ** 2).sum()
        fits[bec] = {
            "n": int(len(group)),
            "b": round(float(parameters[0]), 8),
            "c": round(float(parameters[1]), 8),
            "tau": round(float(parameters[2]), 8),
            "r2": round(float(r2), 6),
        }
    payload = {
        "source": str(args.vri),
        "model": "BA = b * live_volume_125 + c * (1 - exp(-age / tau))",
        "units": {"BA": "m2/ha", "volume": "m3/ha", "age": "years"},
        "fits": fits,
        "caveat": "Cross-sectional VRI fit; screening calibration, not a validated growth model.",
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
