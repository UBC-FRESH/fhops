#!/usr/bin/env python3
"""Publish the Gavin Lake MDWR no-clearcut / group-selection screen.

Source run: the 40-year Table 30 schedule simulated on the MDWR clone matrix.
The handoff is a tactical-operational public screen; it is not a re-optimized
policy and it does not carry private finance.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance")
RUN = INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-simcheck"
OUT = ROOT / "examples" / "demo_runs" / "gavin-mdwr"
SOURCE = ROOT / "examples" / "demo_runs" / "gavin-policy"


def periods() -> list[dict[str, object]]:
    return [
        {
            "period_id": f"P{index:02d}",
            "start_date": f"{2026 + index * 10}-01-01",
            "end_date": f"{2035 + index * 10}-12-31",
            "duration_years": 10,
        }
        for index in range(30)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=RUN)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--matrix", type=Path, default=INSTANCE / "ws4" / "runtime" / "mdwr_group_selection")
    parser.add_argument(
        "--schedule",
        type=Path,
        default=INSTANCE / "ws4" / "runtime" / "gavin-mdwr-40-schedule.csv",
    )
    parser.add_argument("--classes-csv", type=Path)
    parser.add_argument("--label", default="Gavin Lake — MDWR no-clearcut / group-selection screen (draft)")
    parser.add_argument(
        "--habitat-source",
        default="BEC habitat-class proxy",
    )
    parser.add_argument(
        "--habitat-caveat",
        default="Habitat classes use a BEC proxy; the adjusted Appendix 9 map is still pending review.",
    )
    args = parser.parse_args()
    run_dir = args.run
    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copyfile(SOURCE / "blocks.geojson", out / "blocks.geojson")
    shutil.copyfile(SOURCE / "policy_targets.yaml", out / "policy_targets.yaml")

    scenario = yaml.safe_load((SOURCE / "scenario.yaml").read_text(encoding="utf-8"))
    scenario["name"] = "Gavin Lake MDWR no-clearcut / group-selection screen"
    scenario["periods"] = periods()
    scenario["source"] = f"Gavin MDWR clone matrix; Table 30 group selection; {args.habitat_source}"
    scenario["notes"] = (
        "No clearcut in MDWR. Group selection uses 33/25/20% per pass by "
        f"{args.habitat_source}, 40-year re-entry, and a full-area partial-cut "
        "volume approximation. Not a spatial group-layout or approved plan."
    )
    (out / "scenario.yaml").write_text(
        yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8"
    )

    schedule = pd.read_csv(args.schedule)
    schedule["period_id"] = schedule["offset"].astype(int).map(
        lambda offset: f"P{int(offset) // 10:02d}"
    )
    area = pd.read_parquet(args.matrix / "fragments.parquet").set_index("block_id")["area_ha"]
    schedule["area_ha"] = schedule["block_id"].map(area).fillna(0.0)
    schedule = schedule[["block_id", "treatment", "offset", "period_id", "area_ha"]]
    schedule.to_csv(out / "schedule.csv", index=False)
    schedule.rename(columns={"treatment": "system_id"})[
        ["period_id", "block_id", "system_id", "area_ha"]
    ].to_csv(out / "harvest_decisions.csv", index=False)

    values = pd.read_csv(run_dir / "account_values.csv")
    values = values.loc[values["account"] == "product.yield.managed.total"]
    values["period"] = (values["offset"].astype(int) // 10).astype(int)
    production = values.groupby("period", as_index=False)["value"].sum()
    production["period_id"] = production["period"].map(lambda p: f"P{int(p):02d}")
    production["product_id"] = "all_products"
    production["volume_m3"] = production["value"]
    production[["period_id", "product_id", "volume_m3"]].to_csv(
        out / "production.csv", index=False
    )
    production.to_csv(out / "harvest_by_period.csv", index=False)

    shutil.copyfile(run_dir / "report_targets.csv", out / "report_targets.csv")
    shutil.copyfile(run_dir / "ending_inventory.csv", out / "ending_inventory.csv")

    report = pd.read_csv(run_dir / "report_accounts.csv")
    feature = report.loc[report["account"] == "feature.yield.managed.total"].iloc[0]
    targets = pd.read_csv(run_dir / "report_targets.csv")["status"].value_counts().to_dict()
    volumes = production["volume_m3"].tolist()
    if args.classes_csv is not None:
        classes = pd.read_csv(args.classes_csv)
        class_rows = {
            name: {
                "area_ha": round(float(group["area_ha"].sum()), 3),
                "blocks": int(len(group)),
                "pass_fraction": fraction,
            }
            for name, fraction in (("High", 0.33), ("Moderate", 0.25), ("Low", 0.20))
            for group in [classes.loc[classes["model_class"] == name]]
        }
    else:
        class_rows = {
            "High": {"area_ha": 14.269, "blocks": 19, "pass_fraction": 0.33},
            "Moderate": {"area_ha": 213.063, "blocks": 136, "pass_fraction": 0.25},
            "Low": {"area_ha": 2571.978, "blocks": 1288, "pass_fraction": 0.20},
        }
    summary = {
        "run_id": "gavin-mdwr",
        "label": args.label,
        "planning_level": "tactical_operational",
        "source": f"Gavin MDWR clone matrix; Table 30 group selection; {args.habitat_source}; 40-year re-entry",
        "horizon_years": 300,
        "periods": 30,
        "period_width_years": 10,
        "blocks_total": 2907,
        "blocks_scheduled": int(schedule["block_id"].nunique()),
        "schedule_events": int(len(schedule)),
        "area_total_ha": 5663.666,
        "scheduled_area_ha": round(float(schedule.groupby("block_id")["area_ha"].first().sum()), 3),
        "total_production_m3": round(float(production["volume_m3"].sum()), 3),
        "mean_period_production_m3": round(float(production["volume_m3"].mean()), 3),
        "min_period_production_m3": round(float(min(volumes)), 3),
        "max_period_production_m3": round(float(max(volumes)), 3),
        "growing_stock_initial_m3": round(float(feature["max"]), 3),
        "growing_stock_final_m3": round(float(feature["final"]), 3),
        "incumbent_objective": None,
        "iterations": 0,
        "targets_met": int(targets.get("met", 0)),
        "targets_below": int(targets.get("below", 0)),
        "targets_above": int(targets.get("above", 0)),
        "status_note": (
            "MDWR no-clearcut/group-selection screen; the 174k, 600k-stock and "
            "±4% even-flow policy targets are not met. Not a decision-grade plan."
        ),
        "finance_note": "No public AFRF net-revenue ledger is used or fabricated for this screen.",
        "mdwr_area_ha": 2799.31,
        "mdwr_blocks": 1443,
        "group_selection_classes": class_rows,
        "mdwr_clearcuts": 0,
    }
    for name in ("summary.json", "kpis.json", "tactical_summary.json"):
        (out / name).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    run_meta = {
        "schema_version": "1.0.0",
        "run_id": "gavin-mdwr",
        "domain": "tactical_operational",
        "run_type": "tactical_operational",
        "status": "policy-screen",
        "files": {
            "summary": "summary.json",
            "kpis": "kpis.json",
            "harvest_decisions": "harvest_decisions.csv",
            "production": "production.csv",
            "tactical_summary": "tactical_summary.json",
        },
        "warnings": [
            args.habitat_caveat,
            "Full-area partial-cut volume screen; no spatial group layout or 0.4/0.7 ha size cap.",
            "No preparative thinning; no private finance.",
        ],
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "command": "WS4 Gavin MDWR no-clearcut / group-selection simulation",
        "scenario": "scenario.yaml",
        "solver": "ws4-simulate",
    }
    (out / "run.json").write_text(json.dumps(run_meta, indent=2) + "\n", encoding="utf-8")
    def relative_to_instance(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(INSTANCE.resolve()))
        except ValueError:
            return path.name

    provenance = {
        "instance": "femic-afrf-gavinlake-instance",
        "matrix": relative_to_instance(args.matrix),
        "source_run": relative_to_instance(run_dir),
        "schedule": relative_to_instance(args.schedule),
        "spatial": "data/legacy_gavinlake/spatial/fragments.shp",
        "table30": "2007 AFRF MP #3 Table 30; 33/25/20% per pass; 40-year cycle",
        "caveats": [
            args.habitat_caveat,
            "Full-area partial-cut screen; no spatial group layout or group-size cap.",
            "No preparative thinning and no private finance.",
            "Target status is reported against the existing 174k policy target; the MDWR screen does not meet it.",
        ],
    }
    (out / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    (out / "README.md").write_text(
        "\n".join(
            [
                "# Gavin Lake MDWR no-clearcut / group-selection screen",
                "",
                "This is a public tactical-operational screen, not an approved plan.",
                "",
                "The Beaver Valley MDWR is 2,799.31 ha in 1,443 blocks. No MDWR",
                "clearcut is scheduled. Group selection uses Table 30 pass",
                "fractions (High 33%, Moderate 25%, Low 20%), a 40-year re-entry",
                "and a full-area partial-cut volume approximation.",
                "",
                f"Habitat classes: {args.habitat_source}.",
                args.habitat_caveat,
                "",
                f"Production: {summary['total_production_m3']:,.0f} m³ / 300 years.",
                f"Targets: {summary['targets_met']} met, {summary['targets_below']} below,",
                f"{summary['targets_above']} above against the 174k policy target set.",
                "",
                "Limits: full-area partial-cut screen; no spatial group layout, no",
                "0.4/0.7 ha group-size cap, no preparatory thinning, no private",
                "finance. The legal habitat-class map and legal-order check are",
                "still required before a compliance claim.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
