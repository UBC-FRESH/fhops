#!/usr/bin/env python3
"""Publish the state-aware residual-area target-search results.

The state matrices split each no-retention block into a harvested portion and a
value-equivalent residual portion.  The residual track carries copied feature
curves, ages through the horizon, and has no scheduled product treatment.  The
harvested net/cost curves include the fixed-cost correction, so the state totals
reconcile with the earlier product-ledger residual screen.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from build_dfret_results import metrics

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo_runs"
RUNS = Path("/srv/shared-data/gep/ws4/femic/external/femic-mkrf-instance/ws4/runtime")
MATRICES = {
    "low": RUNS / "matrix_dfret_state_low",
    "base": RUNS / "matrix_dfret_state_base",
    "high": RUNS / "matrix_dfret_state_high",
}
SOURCE = {
    "no-retention": RUNS / "dfret_no_retention_true_s44",
    "low-44-state": RUNS / "dfret_state_low_s44",
    "base-44-state": RUNS / "dfret_state_base_s44",
    "high-44-state": RUNS / "dfret_state_high_s44",
}
PRODUCT_SCREEN = {
    "low-44-state": RUNS / "dfret_low_s44",
    "base-44-state": RUNS / "dfret_base_s44",
    "high-44-state": RUNS / "dfret_high_s44",
}
LABEL = {"low-44-state": "low", "base-44-state": "base", "high-44-state": "high"}


def residual_area(label: str) -> float:
    fragments = pd.read_parquet(MATRICES[label] / "fragments.parquet")
    state = json.loads((MATRICES[label] / "state_residual.json").read_text())
    return float(fragments["area_ha"].sum()) * float(
        state["residual_share_of_block_area"]
    )


def main() -> None:
    rows = []
    for scenario, run in SOURCE.items():
        row = {"scenario": scenario, **metrics(run)}
        row["residual_area_ha"] = (
            residual_area(LABEL[scenario]) if scenario in LABEL else 0.0
        )
        rows.append(row)
    table = pd.DataFrame(rows)
    columns = [
        "scenario",
        "residual_area_ha",
        "gross_cad",
        "volume_m3",
        "harvest_cost_cad",
        "net_after_all_cost_cad",
        "net_after_harvest_cost_cad",
        "gross_npv4_cad",
        "net_after_all_npv4_cad",
        "targets_met",
        "targets_below",
        "targets_above",
    ]
    table = table.loc[:, columns]
    table.to_csv(DEMO / "MKRF_DFRET_STATE_AWARE.csv", index=False)

    lines = [
        "# MKRF state-aware residual-area scenarios",
        "",
        "Status: **state-aware residual-area proxy; not yet a species/DBH tree-level "
        "residual selector and not a decision-grade plan.**",
        "",
        "| Scenario | Residual area | Gross | Production | Net after all cost | "
        "Net after harvest cost | Gross NPV 4% | Net NPV 4% | Targets met/below/above |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in table.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.residual_area_ha:,.0f} ha | "
            f"CAD {row.gross_cad/1e6:,.1f}M | {row.volume_m3/1e6:,.2f}M m³ | "
            f"CAD {row.net_after_all_cost_cad/1e6:,.1f}M | "
            f"CAD {row.net_after_harvest_cost_cad/1e6:,.1f}M | "
            f"CAD {row.gross_npv4_cad/1e6:,.1f}M | "
            f"CAD {row.net_after_all_npv4_cad/1e6:,.1f}M | "
            f"{row.targets_met}/{row.targets_below}/{row.targets_above} |"
        )
    lines += [
        "",
        "## What is now carried in the state",
        "",
        "- Each no-retention block fragment is split into a harvested portion and a "
        "residual portion. The split is the largest-DF **value-equivalent area** "
        "from the pinned MKRF 684 profile.",
        "- The residual portion is on its own track, with copied feature curves. It "
        "ages and grows through the 100-year horizon, but has no scheduled product "
        "treatment and is not re-entered in this screen.",
        "- The harvested product curves carry the residual value/volume reduction and "
        "a fixed-cost correction. Gross, production, harvest cost, total cost and net "
        "revenue therefore reconcile with the earlier product-ledger screen at the "
        "same schedule.",
        "- The target search was rerun with the same seed (44), target set "
        "(`targets_risk_cost_opt.yaml`), route configuration, topology, patch "
        "accounts and 100-year horizon.",
        "",
        "## Results",
        "",
        "The state-aware run preserves the product-ledger economics:",
        "",
        "| Scenario | State gross | Product-screen gross | State volume | Product-screen volume | State net | Product-screen net | State targets | Product-screen targets |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for scenario, run in PRODUCT_SCREEN.items():
        state = metrics(RUNS / f"dfret_state_{LABEL[scenario]}_s44")
        product = metrics(run)
        lines.append(
            f"| {scenario} | CAD {state['gross_cad']/1e6:,.1f}M | "
            f"CAD {product['gross_cad']/1e6:,.1f}M | "
            f"{state['volume_m3']/1e6:,.2f}M m³ | "
            f"{product['volume_m3']/1e6:,.2f}M m³ | "
            f"CAD {state['net_after_all_cost_cad']/1e6:,.1f}M | "
            f"CAD {product['net_after_all_cost_cad']/1e6:,.1f}M | "
            f"{state['targets_met']}/{state['targets_below']}/{state['targets_above']} | "
            f"{product['targets_met']}/{product['targets_below']}/{product['targets_above']} |"
        )
    lines += [
        "",
        "The low case resolves one additional feature-yield target because the "
        "residual cohort remains in the state and continues to age; base and high "
        "retain the same target status.",
        "",
        "## Limits",
        "",
        "- The residual area is a **value-equivalent area proxy**, not a measured "
        "stem footprint. It is larger than the physical area that would be occupied "
        "by a scattered largest-DF retention cohort.",
        "- Species/DBH selection is still represented by the pinned MKRF 684 profile, "
        "not by a full-estate tree list.",
        "- The residual track has no scheduled re-entry or partial harvest during the "
        "horizon. A production implementation needs an explicit residual state, "
        "re-entry rule and tree-level residual selector.",
        "",
        "Files: `MKRF_DFRET_STATE_AWARE.csv`, `MKRF_DFRET_REOPTIMIZED.csv`, "
        "`MKRF_DFRET_REOPTIMIZED.md`, `MKRF_RETENTION_AUDIT.md`.",
    ]
    (DEMO / "MKRF_DFRET_STATE_AWARE.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
