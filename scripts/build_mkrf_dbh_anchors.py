#!/usr/bin/env python3
"""Build the older-age Douglas-fir DBH anchor from FAIB PSP.

The rotation anchor is the pinned MKRF 684 tree list.  This script supplies
the second anchor (CWHdm FD, age 140-180) used by the age-interpolation
profile builder.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PSP = Path("/srv/shared-data/gep/ws4/tmp/inv01-data/psp")
OUT = Path(
    "/srv/shared-data/gep/ws4/femic/external/femic-mkrf-instance/planning/"
    "2026-11-18_mkrf_dbh_anchors.csv"
)
QUANTILES = np.linspace(0.01, 0.99, 99)


def main() -> None:
    header = pd.read_csv(
        PSP / "faib_header.csv", usecols=["SITE_IDENTIFIER", "BEC_ZONE", "BEC_SBZ"]
    )
    sample = pd.read_csv(
        PSP / "faib_sample_byvisit.csv",
        usecols=[
            "SITE_IDENTIFIER",
            "CLSTR_ID",
            "VISIT_NUMBER",
            "PROJ_AGE_1",
        ],
    )
    trees = pd.read_csv(
        PSP / "faib_tree_detail.csv",
        usecols=[
            "SITE_IDENTIFIER",
            "CLSTR_ID",
            "VISIT_NUMBER",
            "SPECIES",
            "DBH",
            "LV_D",
        ],
    )
    header = header.loc[
        header["BEC_ZONE"].eq("CWH") & header["BEC_SBZ"].eq("dm")
    ]
    sample = sample.merge(header, on="SITE_IDENTIFIER", how="inner")
    trees = trees.merge(
        sample, on=["SITE_IDENTIFIER", "CLSTR_ID", "VISIT_NUMBER"], how="inner"
    )
    trees = trees.loc[
        trees["SPECIES"].eq("FD")
        & trees["LV_D"].eq("L")
        & trees["DBH"].between(5, 150)
        & trees["PROJ_AGE_1"].between(140, 180)
    ]
    values = trees["DBH"].to_numpy(dtype=float)
    if values.size == 0:
        raise SystemExit("no CWHdm FD records in the 140-180 age window")
    frame = pd.DataFrame(
        {
            "species": "FD",
            "anchor": "rotation_plus_50",
            "quantile": QUANTILES,
            "dbh_cm": np.quantile(values, QUANTILES),
            "support_n": len(values),
            "support_sites": int(trees["SITE_IDENTIFIER"].nunique()),
            "source": "FAIB PSP CWHdm live FD, age 140-180",
        }
    )
    frame.to_csv(OUT, index=False)
    print(frame.head().to_string(index=False))
    print(
        {
            "records": len(values),
            "sites": int(trees["SITE_IDENTIFIER"].nunique()),
            "median": float(np.median(values)),
            "q90": float(np.quantile(values, 0.9)),
        }
    )


if __name__ == "__main__":
    main()
