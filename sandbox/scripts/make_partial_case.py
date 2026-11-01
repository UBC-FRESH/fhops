"""Create a partial-harvest case by declaring a prescription on a stand.

A case inventory is the stand. ``case.json.harvest`` declares the treatment, and
the runner derives the cut list deterministically (see
:mod:`sandbox.tree_lab.harvest`). This script copies an existing case and adds
the prescription — it never edits the tree list.

Usage
-----
``python -m sandbox.scripts.make_partial_case --source sandbox/cases/afrf-gavin \
    --case-id afrf-partial-30 --target-ba 0.30 --rule proportional``
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from sandbox.tree_lab.cases import Case, CaseError, ensure_pinned, load_case
from sandbox.tree_lab.harvest import (
    HarvestError,
    derive_cut,
    derive_residual,
    harvest_prescription,
)


def make_partial_case(
    source: Case,
    *,
    case_id: str,
    target_ba_fraction: float,
    rule: str,
    seed: int,
    out_root: Path,
    diameter_limit_cm: float | None = None,
) -> dict[str, Any]:
    """Copy ``source`` into ``out_root`` and add a partial-harvest prescription.

    The inventory is copied unchanged: it remains the stand, not a cut list.
    """
    if out_root.exists() and any(out_root.iterdir()):
        raise CaseError(f"Output case directory is not empty: {out_root}")
    shutil.copytree(source.root, out_root)

    manifest = dict(source.manifest)
    label_stem = source.label.split(" — ")[0]
    rule_text = rule.replace("_", " ")
    harvest: dict[str, Any] = {
        "type": "partial",
        "marking_rule": rule,
        "target_basal_area_fraction": target_ba_fraction,
        "seed": seed,
    }
    if diameter_limit_cm is not None:
        harvest["diameter_limit_cm"] = diameter_limit_cm
    manifest.update(
        {
            "case_id": case_id,
            "label": f"{label_stem} — {target_ba_fraction:.0%} BA {rule_text} (partial cut)",
            "harvest": harvest,
            "caveats": [
                "Inventory is the full stand; the harvest prescription selects the cut trees.",
                f"Marking rule: {rule_text}; target {target_ba_fraction:.0%} of basal area.",
                "Synthetic tree list; not a surveyed stand or tree map.",
                "Reference machine model; not an operational plan.",
            ],
        }
    )
    manifest.pop("residual_trees", None)
    (out_root / "case.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    scenario = out_root / "scenario" / "scenario.yaml"
    text = scenario.read_text(encoding="utf-8")
    text = text.replace(f"name: {source.label}", f"name: {manifest['label']}", 1)
    scenario.write_text(text, encoding="utf-8")

    case = load_case(out_root)
    pin = ensure_pinned(case)
    from fhops.tree_inventory import load_tree_inventory

    stand = load_tree_inventory(case.path("inventory"), metadata_path=case.path("metadata"))
    prescription = harvest_prescription(case)
    cut = derive_cut(stand, prescription)
    residual = derive_residual(stand, prescription)
    return {
        "case_id": case_id,
        "case_dir": str(out_root),
        "inventory_trees": len(stand.rows),
        "cut_trees": len(cut),
        "residual_trees": len(residual),
        "harvest": prescription,
        "pin": pin,
    }


def main(argv: list[str] | None = None) -> int:
    """Create one partial-harvest case."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Source case directory.")
    parser.add_argument("--case-id", required=True, help="New case id (directory name).")
    parser.add_argument("--out", type=Path, help="Cases root. Defaults to the source parent.")
    parser.add_argument(
        "--target-ba", type=float, default=0.30, help="Basal area fraction removed."
    )
    parser.add_argument(
        "--rule", choices=("proportional", "from_below", "diameter_limit"), default="proportional"
    )
    parser.add_argument("--diameter-limit-cm", type=float, help="DBH threshold for diameter_limit.")
    parser.add_argument("--seed", type=int, default=20261030)
    args = parser.parse_args(argv)

    source = load_case(args.source)
    out_root = (args.out or args.source.parent) / args.case_id
    try:
        result = make_partial_case(
            source,
            case_id=args.case_id,
            target_ba_fraction=args.target_ba,
            rule=args.rule,
            seed=args.seed,
            out_root=out_root,
            diameter_limit_cm=args.diameter_limit_cm,
        )
    except (CaseError, HarvestError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
