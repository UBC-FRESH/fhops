#!/usr/bin/env python3
"""Generate a pinned Nemora/PSP tree inventory for a game stand.

The script is a development-time producer. FHOPS consumes the exported CSV and
metadata; it does not import Nemora at runtime.

Example::

    PYTHONPATH=/path/to/nemora/src python scripts/generate_game_inventory.py \
      --stand-id kc_57254551 --psp-dir /path/to/kc/data/psp
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from nemora.sampling import sample_distribution
from nemora.synthesis.stems import TreePlacementConfig, place_trees

LOWER_CM = 9.1
FIXED_GENERATED_UTC = "2026-10-31T00:00:00+00:00"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stand-id", default="kc_57254551")
    parser.add_argument("--stands-dir", type=Path, default=Path("examples/game/stands"))
    parser.add_argument("--psp-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=57254551)
    parser.add_argument("--harvest-fraction", type=float, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    return parser.parse_args()


def _load_stand(stands_dir: Path, stand_id: str) -> tuple[dict[str, Any], gpd.GeoDataFrame]:
    catalog = yaml.safe_load((stands_dir / "catalog.yaml").read_text(encoding="utf-8"))
    for stand in catalog["stands"]:
        if stand["level_id"] == stand_id:
            frame = gpd.read_file(stands_dir / stand["boundary"], engine="pyogrio")
            return stand, frame
    raise SystemExit(f"Unknown stand id: {stand_id}")


def _fit_assets(psp_dir: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    regression = json.loads(
        (psp_dir / "idf_cariboo_psp_weibull_regression.json").read_text(encoding="utf-8")
    )
    sample = pd.read_csv(psp_dir / "idf_cariboo_psp_stemlist_sample.csv")
    return regression, sample


def _draw_dbh(
    *,
    qmd_cm: float,
    tpa: int,
    regression: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict[str, float]]:
    model = regression["models"]["log_beta_qmd"]
    b0, b1 = model["coef"]
    beta = float(math.exp(b0 + b1 * math.log(qmd_cm)))
    a = float(regression["pooled_a"])
    draws = LOWER_CM + sample_distribution(
        "weibull", {"a": a, "beta": beta, "s": 1.0}, tpa * 3, random_state=rng
    )
    draws = draws[(draws >= LOWER_CM) & (draws <= 150.0)][:tpa]
    while draws.size < tpa:
        extra = LOWER_CM + sample_distribution(
            "weibull",
            {"a": a, "beta": beta, "s": 1.0},
            (tpa - draws.size) * 3,
            random_state=rng,
        )
        draws = np.concatenate([draws, extra[(extra >= LOWER_CM) & (extra <= 150.0)]])[:tpa]
    qmd_draw = float(np.sqrt(np.mean(draws**2)))
    scale = qmd_cm / qmd_draw
    draws = np.maximum(draws * scale, LOWER_CM)
    return draws, {
        "pooled_a": a,
        "predicted_beta": beta,
        "qmd_calibration_scale": scale,
        "realized_qmd_cm": float(np.sqrt(np.mean(draws**2))),
        "realized_ba_m2_ha": float(np.sum(0.00007854 * draws**2)),
    }


def _height_model(sample: pd.DataFrame) -> dict[str, float]:
    tree = sample[sample["species"] == "FD"].copy()
    if tree.empty:
        raise SystemExit("PSP sample has no FD trees for the height model.")
    x = np.log(tree["dbh_cm"].to_numpy(float))
    y = np.log(tree["height_m"].to_numpy(float))
    c1, c0 = np.polyfit(x, y, 1)
    residual = y - (c0 + c1 * x)
    return {"c0": float(c0), "c1": float(c1), "sigma": float(np.std(residual, ddof=1))}


def _draw_heights(
    dbh: np.ndarray,
    *,
    height_model: dict[str, float],
    target_mean_height_m: float,
    rng: np.random.Generator,
) -> np.ndarray:
    base = np.exp(
        height_model["c0"]
        + height_model["c1"] * np.log(np.maximum(dbh, 2.0))
        + rng.normal(0.0, height_model["sigma"], size=dbh.size)
    )
    base = np.clip(base, 2.0, 55.0)
    scale = target_mean_height_m / float(base.mean())
    return np.clip(base * scale, 2.0, 55.0)


def _polygon_parts(geometry: Any) -> list[np.ndarray]:
    if geometry.geom_type == "Polygon":
        return [np.asarray(geometry.exterior.coords, dtype=float)]
    if geometry.geom_type == "MultiPolygon":
        return [np.asarray(part.exterior.coords, dtype=float) for part in geometry.geoms]
    raise SystemExit(f"Unsupported stand geometry: {geometry.geom_type}")


def _place_in_geometry(
    geometry: Any,
    count: int,
    *,
    rng: np.random.Generator,
) -> np.ndarray:
    parts = _polygon_parts(geometry)
    areas = np.asarray([abs(_shoelace(part)) for part in parts], dtype=float)
    if areas.sum() <= 0:
        raise SystemExit("Stand geometry has no area.")
    exact = areas / areas.sum() * count
    counts = np.floor(exact).astype(int)
    counts[np.argmax(exact - counts)] += count - int(counts.sum())
    points: list[np.ndarray] = []
    for part, part_count in zip(parts, counts, strict=True):
        if part_count <= 0:
            continue
        points.append(
            place_trees(
                part,
                int(part_count),
                rng=rng,
                config=TreePlacementConfig(min_spacing=1.0, mode="poisson"),
            )
        )
    return np.vstack(points)


def _shoelace(polygon: np.ndarray) -> float:
    x = polygon[:, 0]
    y = polygon[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def _write_inventory(
    *,
    rows: list[dict[str, object]],
    out_dir: Path,
    stand_id: str,
    inventory_label: str,
    filename: str,
    provenance: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / filename
    columns = [
        "tree_id",
        "block_id",
        "x_m",
        "y_m",
        "elevation_m",
        "species_code",
        "dbh_cm",
        "height_m",
        "crown_radius_m",
        "status",
        "confidence",
        "source_id",
        "source_tile_id",
        "merchantable_height_m",
        "defect",
        "grade_hint",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    block_id = str(rows[0]["block_id"])
    metadata = {
        "schema_version": "fhops.tree.inventory.v1",
        "inventory_id": f"{stand_id}-{inventory_label}-nemora-psp-v1",
        "generated_utc": FIXED_GENERATED_UTC,
        "source_id": provenance["source_id"],
        "producer": "Nemora",
        "method": provenance["method"],
        "crs": "EPSG:3005",
        "units": {
            "x_y": "m",
            "elevation": "m",
            "dbh": "cm",
            "height": "m",
            "crown_radius": "m",
        },
        "review_status": "not_reviewed",
        "reviewed_by": None,
        "block_ids": [block_id],
        "caveats": provenance["caveats"],
        "tree_count": len(rows),
        "inventory_sha256": digest,
    }
    meta_name = "inventory.meta.json" if filename == "trees.csv" else "residual.meta.json"
    (out_dir / meta_name).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    provenance = dict(provenance)
    provenance[f"{inventory_label}_inventory_sha256"] = digest
    provenance[f"{inventory_label}_tree_count"] = len(rows)
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Generate and write one pinned inventory."""
    args = parse_args()
    stand, boundary = _load_stand(args.stands_dir, args.stand_id)
    if stand["level_id"] != "kc_57254551":
        raise SystemExit("Only kc_57254551 has a PSP target wired up so far.")
    regression, sample = _fit_assets(args.psp_dir)
    area_ha = float(boundary.geometry.area.sum() / 10000.0)
    tpa = int(round(float(stand["stems_per_ha"])))
    tree_count = int(round(tpa * area_ha))
    if "basal_area_m2_per_ha" not in stand:
        raise SystemExit("Stand catalog is missing basal_area_m2_per_ha.")
    target_qmd_cm = 100.0 * math.sqrt(
        4.0 * float(stand["basal_area_m2_per_ha"]) / (math.pi * float(stand["stems_per_ha"]))
    )
    target_mean_height_m = float(stand.get("height_m", 29.2))
    rng = np.random.default_rng(args.seed)
    dbh, fit = _draw_dbh(
        qmd_cm=target_qmd_cm,
        tpa=tree_count,
        regression=regression,
        rng=rng,
    )
    heights = _draw_heights(
        dbh,
        height_model=_height_model(sample),
        target_mean_height_m=target_mean_height_m,
        rng=rng,
    )
    points = _place_in_geometry(boundary.geometry.iloc[0], tree_count, rng=rng)
    if len(points) != tree_count:
        raise SystemExit(f"Placed {len(points)} points, expected {tree_count}.")
    order = rng.permutation(tree_count)
    dbh = dbh[order]
    heights = heights[order]
    block_id = "KC01"
    rows: list[dict[str, object]] = []
    for index, ((x, y), diameter, height) in enumerate(
        zip(points, dbh, heights, strict=True), start=1
    ):
        rows.append(
            {
                "tree_id": f"{args.stand_id.upper()}-{index:06d}",
                "block_id": block_id,
                "x_m": f"{float(x):.6f}",
                "y_m": f"{float(y):.6f}",
                "elevation_m": "",
                "species_code": "FDI",
                "dbh_cm": f"{float(diameter):.6f}",
                "height_m": f"{float(height):.6f}",
                "crown_radius_m": f"{max(0.5, float(diameter) * 0.08):.6f}",
                "status": "live",
                "confidence": "1.0",
                "source_id": "idf-cariboo-psp-weibull-regression",
                "source_tile_id": "",
                "merchantable_height_m": "",
                "defect": "",
                "grade_hint": "",
            }
        )
    harvest_fraction = (
        float(args.harvest_fraction)
        if args.harvest_fraction is not None
        else float(stand.get("harvest_fraction", 0.60))
    )
    if not 0.0 < harvest_fraction < 1.0:
        raise SystemExit("harvest-fraction must be strictly between 0 and 1.")
    harvest_count = int(round(tree_count * harvest_fraction))
    harvest_indices = set(rng.choice(tree_count, size=harvest_count, replace=False).tolist())
    harvest_rows = [row for index, row in enumerate(rows) if index in harvest_indices]
    residual_rows = [row for index, row in enumerate(rows) if index not in harvest_indices]
    out_dir = args.out_dir or (args.stands_dir / args.stand_id)
    provenance = {
        "source_id": "idf-cariboo-psp-weibull-regression",
        "stand_id": args.stand_id,
        "boundary": str(args.stands_dir / stand["boundary"]),
        "seed": args.seed,
        "method": (
            "Weibull DBH distribution regressed from IDF Cariboo PSP QMD/TPA; "
            "FD height allometry calibrated to VRI mean height; deterministic "
            "Poisson placement inside the VRI polygon."
        ),
        "target_qmd_cm": target_qmd_cm,
        "target_tpa": tpa,
        "target_area_ha": area_ha,
        "target_mean_height_m": target_mean_height_m,
        "harvest_fraction": harvest_fraction,
        "residual_fraction": 1.0 - harvest_fraction,
        "fit": fit,
        "qmd_source": "VRI basal area and live stems/HA",
        "height_source": "VRI projected height and PSP FD allometry",
        "psp_sources": {
            "regression": str(args.psp_dir / "idf_cariboo_psp_weibull_regression.json"),
            "sample": str(args.psp_dir / "idf_cariboo_psp_stemlist_sample.csv"),
        },
        "caveats": [
            "Synthetic tree map; not a surveyed stand or operational inventory.",
            "DBH distribution is a QMD/TPA-conditioned PSP regression, not a growth model.",
            "Height is an FD allometry calibrated to VRI mean height, not a measured tree height.",
            "Tree placement is deterministic Poisson, not a mapped stem map.",
            "Harvest/residual split is a deterministic synthetic selection-cut allocation, not a prescription.",
        ],
    }
    _write_inventory(
        rows=harvest_rows,
        out_dir=out_dir,
        stand_id=args.stand_id,
        inventory_label="harvest",
        filename="trees.csv",
        provenance=provenance,
    )
    _write_inventory(
        rows=residual_rows,
        out_dir=out_dir,
        stand_id=args.stand_id,
        inventory_label="residual",
        filename="residual_trees.csv",
        provenance=provenance,
    )
    print(
        json.dumps(
            {
                "stand_id": args.stand_id,
                "stand_trees": tree_count,
                "harvest_trees": len(harvest_rows),
                "residual_trees": len(residual_rows),
                "harvest_fraction": harvest_fraction,
                "area_ha": area_ha,
                "tpa": tpa,
                "target_qmd_cm": target_qmd_cm,
                "realized_qmd_cm": fit["realized_qmd_cm"],
                "target_mean_height_m": target_mean_height_m,
                "out_dir": str(out_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
