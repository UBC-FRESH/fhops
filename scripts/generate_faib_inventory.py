#!/usr/bin/env python3
"""Generate a FAIB-PSP stand inventory for a game level.

This is a development-time producer. FHOPS consumes the exported CSV/metadata.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from nemora.sampling import sample_distribution
from nemora.synthesis.stems import TreePlacementConfig, place_trees
from scipy.stats import weibull_min

FIXED_GENERATED_UTC = "2026-10-31T00:00:00+00:00"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stand-id", required=True)
    parser.add_argument("--stands-dir", type=Path, default=Path("examples/game/stands"))
    parser.add_argument("--psp-dir", type=Path, required=True)
    parser.add_argument("--bec-zone", required=True)
    parser.add_argument("--bec-subzone", required=True)
    parser.add_argument("--bec-variant", default=None)
    parser.add_argument("--tsa", required=True)
    parser.add_argument("--age-min", type=float, required=True)
    parser.add_argument("--age-max", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    return parser.parse_args()


def _load_stand(stands_dir: Path, stand_id: str) -> tuple[dict[str, Any], gpd.GeoDataFrame]:
    catalog = yaml.safe_load((stands_dir / "catalog.yaml").read_text(encoding="utf-8"))
    for stand in catalog["stands"]:
        if stand["level_id"] == stand_id:
            return stand, gpd.read_file(stands_dir / stand["boundary"], engine="pyogrio")
    raise SystemExit(f"Unknown stand id: {stand_id}")


def _latest_live_trees(
    psp_dir: Path, args: argparse.Namespace
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trees = pd.read_csv(psp_dir / "psp_trees_selected.csv", low_memory=False)
    plots = pd.read_csv(psp_dir / "faib_plot_header.csv", low_memory=False)
    header = pd.read_csv(psp_dir / "faib_header.csv", low_memory=False)
    mask = (
        (header.BEC_ZONE == args.bec_zone)
        & (header.BEC_SBZ == args.bec_subzone)
        & (header.TSA_DESC == args.tsa)
    )
    if args.bec_variant is not None:
        mask &= header.BEC_VAR.astype("Float64") == float(args.bec_variant)
    sites = set(header.loc[mask, "SITE_IDENTIFIER"].astype(int))
    trees = trees[trees.LV_D == "L"].copy()
    trees = trees[
        trees.VISIT_NUMBER == trees.groupby("SITE_IDENTIFIER").VISIT_NUMBER.transform("max")
    ]
    trees = trees[trees.SITE_IDENTIFIER.isin(sites)].copy()
    plot_cols = ["SITE_IDENTIFIER", "CLSTR_ID", "VISIT_NUMBER", "PLOT", "PLOT_AREA_MAIN"]
    plots = plots[plot_cols].drop_duplicates()
    trees = trees.merge(
        plots,
        on=["SITE_IDENTIFIER", "CLSTR_ID", "VISIT_NUMBER", "PLOT"],
        how="left",
    )
    trees = trees[trees.PLOT_AREA_MAIN > 0].copy()
    tree_age = trees.groupby("SITE_IDENTIFIER").AGE_TOT.median()
    age_ok = tree_age[(tree_age >= args.age_min) & (tree_age <= args.age_max)].index
    trees = trees[trees.SITE_IDENTIFIER.isin(age_ok)].copy()
    if trees.empty:
        raise SystemExit("No PSP trees matched the selected BEC/TSA/age window.")
    return trees, header


def _target_metrics(trees: pd.DataFrame) -> dict[str, Any]:
    plot = trees.groupby(["SITE_IDENTIFIER", "PLOT"], as_index=False).agg(
        n=("DBH", "size"),
        area=("PLOT_AREA_MAIN", "first"),
        ba=("BA_TREE", "sum"),
        qmd=("DBH", lambda s: float(np.sqrt(np.mean(s**2)))),
        height=("HEIGHT", "mean"),
    )
    plot["tph"] = plot.n / plot.area
    plot["ba_ha"] = plot.ba / plot.area
    ba_share = (trees.groupby("SPECIES").BA_TREE.sum() / trees.BA_TREE.sum()).sort_values(
        ascending=False
    )
    species = {str(k): float(v) for k, v in ba_share.items() if v >= 0.005}
    total = sum(species.values())
    return {
        "tph": float(plot.tph.mean()),
        "qmd_cm": float(plot.qmd.mean()),
        "height_m": float(plot.height.mean()),
        "ba_m2_per_ha": float(plot.ba_ha.mean()),
        "species_ba_share": {k: v / total for k, v in species.items()},
        "plot_count": int(plot.SITE_IDENTIFIER.nunique()),
        "tree_count": int(len(trees)),
        "age_median": float(trees.AGE_TOT.median()),
    }


def _height_models(trees: pd.DataFrame) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    models: dict[str, dict[str, float]] = {}
    for species, frame in trees.groupby("SPECIES"):
        if len(frame) < 20:
            continue
        x = np.log(frame.DBH.to_numpy(float))
        y = np.log(frame.HEIGHT.to_numpy(float))
        c1, c0 = np.polyfit(x, y, 1)
        residual = y - (c0 + c1 * x)
        models[str(species)] = {
            "c0": float(c0),
            "c1": float(c1),
            "sigma": float(np.std(residual, ddof=1)),
        }
    x = np.log(trees.DBH.to_numpy(float))
    y = np.log(trees.HEIGHT.to_numpy(float))
    c1, c0 = np.polyfit(x, y, 1)
    models["ALL"] = {
        "c0": float(c0),
        "c1": float(c1),
        "sigma": float(np.std(y - (c0 + c1 * x), ddof=1)),
    }
    return models, models["ALL"]


def _polygon_parts(geometry: Any) -> list[np.ndarray]:
    if geometry.geom_type == "Polygon":
        return [np.asarray(geometry.exterior.coords, dtype=float)]
    if geometry.geom_type == "MultiPolygon":
        return [np.asarray(part.exterior.coords, dtype=float) for part in geometry.geoms]
    raise SystemExit(f"Unsupported geometry: {geometry.geom_type}")


def _shoelace(polygon: np.ndarray) -> float:
    x, y = polygon[:, 0], polygon[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def _place(geometry: Any, count: int, rng: np.random.Generator) -> np.ndarray:
    parts = _polygon_parts(geometry)
    areas = np.asarray([abs(_shoelace(p)) for p in parts])
    exact = areas / areas.sum() * count
    counts = np.floor(exact).astype(int)
    counts[np.argmax(exact - counts)] += count - int(counts.sum())
    points = []
    for part, part_count in zip(parts, counts, strict=True):
        if part_count:
            points.append(
                place_trees(
                    part, int(part_count), rng=rng, config=TreePlacementConfig(min_spacing=1.0)
                )
            )
    return np.vstack(points)


def _write_inventory(
    rows: list[dict[str, object]], out_dir: Path, stand_id: str, provenance: dict[str, Any]
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "trees.csv"
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
    metadata = {
        "schema_version": "fhops.tree.inventory.v1",
        "inventory_id": f"{stand_id}-faib-psp-v1",
        "generated_utc": FIXED_GENERATED_UTC,
        "source_id": provenance["source_id"],
        "producer": "Nemora",
        "method": provenance["method"],
        "crs": "EPSG:3005",
        "units": {"x_y": "m", "elevation": "m", "dbh": "cm", "height": "m", "crown_radius": "m"},
        "review_status": "not_reviewed",
        "reviewed_by": None,
        "block_ids": [str(rows[0]["block_id"])],
        "caveats": provenance["caveats"],
        "tree_count": len(rows),
        "inventory_sha256": digest,
    }
    (out_dir / "inventory.meta.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    provenance = dict(provenance)
    provenance["inventory_sha256"] = digest
    provenance["tree_count"] = len(rows)
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
    stand, boundary = _load_stand(args.stands_dir, args.stand_id)
    trees, _header = _latest_live_trees(args.psp_dir, args)
    metrics = _target_metrics(trees)
    area_ha = float(boundary.geometry.area.sum() / 10000.0)
    target_count = int(round(metrics["tph"] * area_ha))
    rng = np.random.default_rng(args.seed)
    shape, _loc, scale = weibull_min.fit(trees.DBH.to_numpy(float), floc=0)
    draws = sample_distribution(
        "weibull",
        {"a": float(shape), "beta": float(scale), "s": 0.0},
        target_count * 3,
        random_state=rng,
    )
    draws = draws[(draws >= 5.0) & (draws <= 150.0)][:target_count]
    while draws.size < target_count:
        extra = sample_distribution(
            "weibull",
            {"a": float(shape), "beta": float(scale), "s": 0.0},
            (target_count - draws.size) * 2,
            random_state=rng,
        )
        draws = np.concatenate([draws, extra[(extra >= 5.0) & (extra <= 150.0)]])[:target_count]
    qmd_draw = float(np.sqrt(np.mean(draws**2)))
    qmd_scale = metrics["qmd_cm"] / qmd_draw
    dbh = np.maximum(draws * qmd_scale, 5.0)
    height_models, _fallback = _height_models(trees)
    species_choices = list(metrics["species_ba_share"])
    species_probs = np.asarray(list(metrics["species_ba_share"].values()), dtype=float)
    species = rng.choice(species_choices, size=target_count, p=species_probs / species_probs.sum())
    heights = np.zeros(target_count)
    for species_code in sorted(set(species)):
        idx = np.where(species == species_code)[0]
        model = height_models.get(str(species_code), height_models["ALL"])
        base = np.exp(
            model["c0"]
            + model["c1"] * np.log(np.maximum(dbh[idx], 2.0))
            + rng.normal(0, model["sigma"], size=idx.size)
        )
        heights[idx] = base
    heights *= metrics["height_m"] / float(heights.mean())
    heights = np.clip(heights, 2.0, 55.0)
    points = _place(boundary.geometry.iloc[0], target_count, rng)
    order = rng.permutation(target_count)
    dbh, heights, species, points = dbh[order], heights[order], species[order], points[order]
    block_id = "B01"
    rows: list[dict[str, object]] = []
    for i, ((x, y), d, h, sp) in enumerate(
        zip(points, dbh, heights, species, strict=True), start=1
    ):
        rows.append(
            {
                "tree_id": f"{args.stand_id.upper()}-{i:06d}",
                "block_id": block_id,
                "x_m": f"{float(x):.6f}",
                "y_m": f"{float(y):.6f}",
                "elevation_m": "",
                "species_code": str(sp),
                "dbh_cm": f"{float(d):.6f}",
                "height_m": f"{float(h):.6f}",
                "crown_radius_m": f"{max(0.5, float(d) * 0.08):.6f}",
                "status": "live",
                "confidence": "1.0",
                "source_id": f"faib-psp-{args.bec_zone.lower()}{args.bec_subzone.lower()}",
                "source_tile_id": "",
                "merchantable_height_m": "",
                "defect": "",
                "grade_hint": "",
            }
        )
    out_dir = args.out_dir or (args.stands_dir / args.stand_id)
    provenance = {
        "source_id": f"faib-psp-{args.bec_zone.lower()}{args.bec_subzone.lower()}",
        "stand_id": args.stand_id,
        "boundary": str(args.stands_dir / stand["boundary"]),
        "seed": args.seed,
        "method": "Weibull DBH fit to FAIB PSP live trees; species composition and height allometry from the same BEC/TSA/age window; deterministic placement inside the VRI polygon.",
        "target_area_ha": area_ha,
        "target_metrics": metrics,
        "weibull": {"shape": float(shape), "scale_cm": float(scale), "qmd_scale": qmd_scale},
        "psp_source": "FAIB Ground Plot Compilations, faib_tree_detail.csv + faib_plot_header.csv + faib_header.csv",
        "psp_window": {key: str(value) for key, value in vars(args).items()},
        "caveats": [
            "Synthetic tree map; not a surveyed stand or operational inventory.",
            "DBH distribution is fitted to regional PSP live trees in the stated BEC/TSA/age window.",
            "Species composition and height allometry are regional PSP summaries, not measured stand values.",
            "Tree placement is deterministic Poisson, not a mapped stem map.",
        ],
    }
    _write_inventory(rows, out_dir, args.stand_id, provenance)
    print(
        json.dumps(
            {
                "stand_id": args.stand_id,
                "trees": target_count,
                "area_ha": area_ha,
                **metrics,
                "out_dir": str(out_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
