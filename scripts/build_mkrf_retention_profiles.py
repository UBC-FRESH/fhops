#!/usr/bin/env python3
"""Build first-pass MKRF dispersed-retention profiles.

The profile uses:

- VRI per-block TPH, basal area and species shares for scale;
- the pinned MKRF 684 tree list for species-specific DBH/height shape;
- the game price deck for gross log value;
- a basal-area retention target from the MKRF silviculture regime assignment.

This is a bootstrap profile, not a measured estate tree list.  It is intended
to make the selection and accounting logic explicit and testable before the
core treatment-split operator is added to WS4.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-mkrf-instance")
WORKSPACE = Path("/srv/shared-data/gep/ws4")
VRI_PATH = WORKSPACE / "sources" / "mkrf-gis-2026-11-02" / "processed" / "vri_2016.gpkg"
STAND = ROOT / "examples" / "game" / "stands" / "mkrf_684"
LEVEL = ROOT / "examples" / "game" / "levels" / "mkrf_684"
OUT = INSTANCE / "planning" / "2026-11-18_mkrf_retention_profiles.csv"
SUMMARY = INSTANCE / "planning" / "2026-11-18_mkrf_retention_profiles.json"

sys.path.insert(0, str(ROOT / "src"))

from fhops.game.value import PriceSchedule  # noqa: E402
from fhops.stem import ReferenceStemModel  # noqa: E402
from fhops.tree_inventory import load_tree_inventory  # noqa: E402


def _species_code(value: object) -> str:
    code = str(value).strip().upper()
    return {"FDC": "FD", "FDI": "FD", "FDL": "FD"}.get(code, code)


def _vri_species(row: pd.Series) -> dict[str, float]:
    totals: dict[str, float] = {}
    for index in range(1, 7):
        code = row.get(f"TCL_1_TSP_{index}_TREE_SPECIES_CODE")
        pct = row.get(f"TCL_1_TSP_{index}_SPECIES_PCT")
        if pd.isna(code) or pd.isna(pct):
            continue
        code = _species_code(code)
        if not code:
            continue
        totals[code] = totals.get(code, 0.0) + float(pct)
    total = sum(totals.values())
    if total <= 0:
        return {"FD": 1.0}
    return {key: value / total for key, value in totals.items() if value > 0}


def _tree_value(tree, model, prices) -> tuple[float, float]:
    result = model.evaluate(tree)
    value = prices.value_logs(result.logs)["gross_log_value"]
    return float(result.merchantable_volume_m3), float(value)


def main() -> None:
    regime = pd.read_csv(
        INSTANCE / "data" / "model_input_bundle" / "silviculture_regime_assignment.csv"
    )
    assignment = pd.read_csv(
        INSTANCE / "data" / "model_input_bundle" / "stand_au_assignment.csv"
    )[["res_key", "au_id", "forest_cover_id"]]
    vri = gpd.read_file(VRI_PATH)
    vri["forest_cover_id"] = vri["FOREST_COVER_OBJECT_ID"].astype(int)
    merged = (
        regime.merge(assignment, left_on="RES_KEY", right_on="res_key", how="left")
        .merge(vri, on="forest_cover_id", how="left")
    )

    managed = pd.read_csv(
        INSTANCE / "data" / "model_input_bundle" / "managed_au_curves.csv"
    )
    rotation: dict[str, int] = {}
    for au_id, frame in managed.groupby("au_id"):
        frame = frame.sort_values("age")
        valid = frame["age"] > 0
        mai = frame.loc[valid, "volume"] / frame.loc[valid, "age"]
        rotation[str(au_id)] = int(frame.loc[mai.idxmax(), "age"])

    inventory = load_tree_inventory(
        STAND / "trees.csv", metadata_path=STAND / "inventory.meta.json"
    )
    prices = PriceSchedule.from_path(LEVEL / "prices.yaml")
    model = ReferenceStemModel(
        form_factor=0.2, log_length_m=6.1, sawlog_min_dbh_cm=20.0
    )
    by_species: dict[str, list[tuple[float, float, float, float]]] = {}
    for tree in inventory.rows:
        species = _species_code(tree.species_code)
        volume, value = _tree_value(tree, model, prices)
        by_species.setdefault(species, []).append(
            (float(tree.dbh_cm), float(tree.height_m), volume, value)
        )
    for species in by_species:
        by_species[species].sort(key=lambda row: row[0])

    rows: list[dict[str, object]] = []
    for record in merged.itertuples(index=False):
        block_id = int(record.RES_KEY)
        area = float(record.area_ha)
        age = float(record.AGE_2020)
        au_id = str(record.au_id) if pd.notna(record.au_id) else ""
        rotation_age = rotation.get(au_id, 90)
        profile_age = min(180, max(60, max(age, rotation_age)))
        ba = float(record.TCL_1_BASAL_AREA) if pd.notna(record.TCL_1_BASAL_AREA) else np.nan
        tph = (
            float(record.TCL_1_VRI_LIVE_STEMS_PER_HA)
            if pd.notna(record.TCL_1_VRI_LIVE_STEMS_PER_HA)
            else np.nan
        )
        if not (math.isfinite(ba) and math.isfinite(tph) and ba > 0 and tph > 0):
            continue
        qmd = 100.0 * math.sqrt(4.0 * ba / (math.pi * tph))
        if not (5.0 <= qmd <= 100.0):
            continue
        shares = _vri_species(pd.Series(record._asdict()))
        target_pct = float(record.retention_pct) / 100.0
        if not math.isfinite(target_pct) or target_pct <= 0:
            continue

        # Scale the representative species shapes to the VRI QMD.  Use a
        # quantile grid so the selection remains tractable for 1,763 blocks.
        cohort: list[dict[str, float | str]] = []
        for species, share in sorted(shares.items(), key=lambda item: -item[1]):
            source = by_species.get(species) or by_species.get("FD")
            if not source:
                continue
            source_dbh = np.array([row[0] for row in source], dtype=float)
            source_height = np.array([row[1] for row in source], dtype=float)
            source_volume = np.array([row[2] for row in source], dtype=float)
            source_value = np.array([row[3] for row in source], dtype=float)
            count = max(24, int(round(240 * share)))
            quantiles = np.linspace(0.01, 0.99, count)
            dbh = np.clip(
                np.quantile(source_dbh, quantiles) * (qmd / np.median(source_dbh)),
                5.0,
                150.0,
            )
            height = np.interp(dbh, source_dbh, source_height)
            weights = np.full(count, area * tph * share / count, dtype=float)
            volume = np.interp(dbh, source_dbh, source_volume)
            value = np.interp(dbh, source_dbh, source_value)
            for d, h, w, v, g in zip(dbh, height, weights, volume, value, strict=True):
                cohort.append(
                    {
                        "species": species,
                        "dbh": float(max(5.0, d)),
                        "height": float(min(60.0, max(2.0, h))),
                        "weight": float(w),
                        "volume_per_tree": float(max(0.0, v)),
                        "value_per_tree": float(max(0.0, g)),
                    }
                )
        if not cohort:
            continue
        frame = pd.DataFrame(cohort)
        frame["ba_per_tree"] = math.pi / 4.0 * (frame["dbh"] / 100.0) ** 2
        frame["ba_total"] = frame["weight"] * frame["ba_per_tree"]
        frame["volume_total"] = frame["weight"] * frame["volume_per_tree"]
        frame["value_total"] = frame["weight"] * frame["value_per_tree"]
        # Normalize the cohort to the VRI BA; this keeps area and BA coherent
        # even when the representative shape differs from the block.
        ba_total = float(frame["ba_total"].sum())
        if ba_total <= 0:
            continue
        scale = ba / (ba_total / area)
        frame["weight"] *= scale
        frame["ba_total"] = frame["weight"] * frame["ba_per_tree"]
        frame["volume_total"] = frame["weight"] * frame["volume_per_tree"]
        frame["value_total"] = frame["weight"] * frame["value_per_tree"]
        target_ba = target_pct * float(frame["ba_total"].sum())
        df = frame.loc[frame["species"].eq("FD")].sort_values("dbh", ascending=False)
        selected = df.loc[df["ba_total"].cumsum().le(target_ba)]
        if len(selected) < len(df):
            selected = df.iloc[: len(selected) + 1]
        if selected.empty:
            continue
        total_ba = float(frame["ba_total"].sum())
        total_volume = float(frame["volume_total"].sum())
        total_value = float(frame["value_total"].sum())
        retained_ba = float(selected["ba_total"].sum())
        retained_volume = float(selected["volume_total"].sum())
        retained_value = float(selected["value_total"].sum())
        retained_tph = float(selected["weight"].sum() / area)
        rows.append(
            {
                "block_id": block_id,
                "au_id": au_id,
                "silv_group": str(record.silv_group),
                "area_ha": area,
                "current_age": age,
                "rotation_age": rotation_age,
                "profile_age": profile_age,
                "vri_tph": tph,
                "vri_ba_m2_ha": ba,
                "qmd_cm": qmd,
                "retention_target_ba_pct": target_pct,
                "total_stems": float(frame["weight"].sum()),
                "total_ba_m2": total_ba,
                "total_volume_m3": total_volume,
                "total_gross_value_cad": total_value,
                "retained_stems": float(selected["weight"].sum()),
                "retained_tph": retained_tph,
                "retained_ba_m2": retained_ba,
                "retained_ba_share": retained_ba / total_ba,
                "retained_volume_share": retained_volume / total_volume,
                "retained_value_share": retained_value / total_value,
                "min_retained_dbh_cm": float(selected["dbh"].min()),
                "residual_area_fraction": retained_ba / total_ba,
                "harvest_volume_share": 1.0 - retained_volume / total_volume,
                "harvest_value_share": 1.0 - retained_value / total_value,
                "profile_note": (
                    "VRI scale + MKRF 684 species shape; BA target; "
                    "DF-first largest-DBH selection; synthetic bootstrap"
                ),
            }
        )

    out = pd.DataFrame(rows).sort_values("block_id")
    out.to_csv(OUT, index=False)
    summary = {
        "blocks": int(len(out)),
        "area_ha": float(out["area_ha"].sum()),
        "mean_retained_ba_share": float(out["retained_ba_share"].mean()),
        "mean_retained_volume_share": float(out["retained_volume_share"].mean()),
        "mean_retained_value_share": float(out["retained_value_share"].mean()),
        "retention_target_pct": sorted(out["retention_target_ba_pct"].unique().tolist()),
        "profile_age_range": [
            float(out["profile_age"].min()),
            float(out["profile_age"].max()),
        ],
        "source": {
            "vri": str(VRI_PATH),
            "tree_list": str(STAND / "trees.csv"),
            "price_deck": str(LEVEL / "prices.yaml"),
            "regime": str(
                INSTANCE
                / "data"
                / "model_input_bundle"
                / "silviculture_regime_assignment.csv"
            ),
        },
        "caveat": (
            "First-pass bootstrap. Species DBH shapes come from one synthetic "
            "MKRF stand; VRI supplies scale. Not a full-estate tree list."
        ),
    }
    SUMMARY.write_text(pd.Series(summary).to_json(indent=2) + "\n", encoding="utf-8")
    print(out.head().to_string(index=False))
    print(pd.Series(summary).to_string())


if __name__ == "__main__":
    main()
