#!/usr/bin/env python3
"""Audit MKRF retention value treatment and build a high-grading sensitivity.

The WS4 compiler represents a ForestModelXML ``<retention>`` rule as an
*area split*: a fraction of each eligible fragment is moved to an unmanaged
state.  It does not select species, DBH, or individual retained stems.

This script:
1. records the current low/base/high area-retention numbers;
2. measures the value profile of the largest Douglas-fir stems in the pinned
   MKRF RES_KEY 684 tree list;
3. applies that profile as a high-grading sensitivity to the current
   low/base/high schedules.

It is an audit/sensitivity, not a re-optimized WS4 run.  The tree list is
synthetic and represents one stand, not the whole MKRF estate.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from fhops.game.value import PriceSchedule
from fhops.stem import ReferenceStemModel
from fhops.tree_inventory import load_tree_inventory

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo_runs"
STAND = ROOT / "examples" / "game" / "stands" / "mkrf_684"
LEVEL = ROOT / "examples" / "game" / "levels" / "mkrf_684"

RUNS = {
    "low-44": (DEMO / "mkrf-low-estate", "low"),
    "base-44": (DEMO / "mkrf-full-estate", "base"),
    "high-44": (DEMO / "mkrf-high-estate", "high"),
}
COMPARISON = DEMO / "MKRF_SCENARIO_COMPARISON.csv"
FRACTIONS = np.array([0.05, 0.10, 0.15, 0.20, 0.30])


def account_total(
    frame: pd.DataFrame, account: str, *, annual: bool = True
) -> float:
    """Return a 100-year total, or a level total for area accounts."""
    row = frame.loc[frame["account"] == account]
    if row.empty:
        raise KeyError(f"missing account {account!r}")
    factor = 100.0 if annual else 1.0
    return float(row.iloc[0]["mean"]) * factor


def tree_value_profile() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Value the pinned MKRF 684 tree list and rank the largest Douglas-fir."""
    inventory = load_tree_inventory(
        STAND / "trees.csv", metadata_path=STAND / "inventory.meta.json"
    )
    prices = PriceSchedule.from_path(LEVEL / "prices.yaml")
    model = ReferenceStemModel(
        form_factor=0.2,
        log_length_m=6.1,
        sawlog_min_dbh_cm=20.0,
    )
    rows = []
    for tree in inventory.rows:
        result = model.evaluate(tree)
        value = prices.value_logs(result.logs)["gross_log_value"]
        rows.append(
            {
                "tree_id": tree.tree_id,
                "species": tree.species_code,
                "dbh_cm": tree.dbh_cm,
                "volume_m3": result.merchantable_volume_m3,
                "gross_value_cad": value,
            }
        )
    frame = pd.DataFrame(rows)
    total_value = float(frame["gross_value_cad"].sum())
    total_volume = float(frame["volume_m3"].sum())
    fd = frame.loc[frame["species"].eq("FD")].sort_values(
        "dbh_cm", ascending=False
    )
    profile = []
    for fraction in FRACTIONS:
        count = max(1, round(len(frame) * float(fraction)))
        selected = fd.head(count)
        profile.append(
            {
                "tree_fraction": float(fraction),
                "selected_df_trees": int(len(selected)),
                "volume_share": float(selected["volume_m3"].sum() / total_volume),
                "value_share": float(selected["gross_value_cad"].sum() / total_value),
            }
        )
    summary = pd.DataFrame(
        [
            {
                "stand": "mkrf_684",
                "trees": len(frame),
                "fd_trees": len(fd),
                "total_volume_m3": total_volume,
                "total_gross_value_cad": total_value,
                "value_per_m3_cad": total_value / total_volume,
            }
        ]
    )
    return summary, pd.DataFrame(profile)


def interpolation(fraction: float, profile: pd.DataFrame, column: str) -> float:
    """Interpolate a retention share from the stand profile."""
    return float(
        np.interp(
            fraction,
            profile["tree_fraction"].to_numpy(),
            profile[column].to_numpy(),
        )
    )


def build() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    comparison = pd.read_csv(COMPARISON).set_index("scenario")
    stand_summary, profile = tree_value_profile()
    rows = []
    for label, (run_dir, scenario_key) in RUNS.items():
        accounts = pd.read_csv(run_dir / "report_accounts.csv")
        managed = account_total(
            accounts, "feature.area.managed.total", annual=False
        )
        retention = account_total(
            accounts, "feature.area.retention.total", annual=False
        )
        gross = account_total(accounts, "product.LogValue.managed.total")
        harvest_cost = account_total(accounts, "product.Cost_Harvesting.managed.total")
        total_cost = account_total(accounts, "product.Cost_Total.managed.total")
        volume = float(comparison.loc[scenario_key, "total_production_m3"])
        current_net_all_cost = gross - total_cost
        current_net_after_harvest = float(
            comparison.loc[scenario_key, "net_after_harvest_cost_cad"]
        )
        gross_npv4 = float(comparison.loc[scenario_key, "npv_gross_4pct_cad"])
        net_npv4 = float(comparison.loc[scenario_key, "npv_net_4pct_cad"])

        eligible = managed + retention
        retention_fraction = retention / eligible if eligible else 0.0
        value_share = interpolation(retention_fraction, profile, "value_share")
        volume_share = interpolation(retention_fraction, profile, "volume_share")

        # The area-retention model removes an average area slice.  Potential
        # gross/volume is the average yield if that area slice were harvested.
        potential_gross = gross / (1.0 - retention_fraction)
        potential_volume = volume / (1.0 - retention_fraction)
        corrected_gross = potential_gross * (1.0 - value_share)
        corrected_volume = potential_volume * (1.0 - volume_share)

        harvest_per_m3 = harvest_cost / volume
        corrected_harvest = corrected_volume * harvest_per_m3
        other_cost = total_cost - harvest_cost
        corrected_net_all_cost = corrected_gross - other_cost - corrected_harvest
        corrected_net_after_harvest = corrected_net_all_cost - corrected_harvest

        rows.append(
            {
                "scenario": label,
                "managed_area_ha": managed,
                "retention_area_ha": retention,
                "retention_fraction": retention_fraction,
                "residual_value_share": value_share,
                "residual_volume_share": volume_share,
                "current_gross_cad": gross,
                "potential_gross_cad": potential_gross,
                "corrected_gross_cad": corrected_gross,
                "gross_change_cad": corrected_gross - gross,
                "gross_change_pct": corrected_gross / gross - 1.0,
                "current_volume_m3": volume,
                "potential_volume_m3": potential_volume,
                "corrected_volume_m3": corrected_volume,
                "volume_change_pct": corrected_volume / volume - 1.0,
                "current_harvest_cost_cad": harvest_cost,
                "corrected_harvest_cost_cad": corrected_harvest,
                "current_net_all_cost_cad": current_net_all_cost,
                "corrected_net_all_cost_cad": corrected_net_all_cost,
                "current_net_after_harvest_cad": current_net_after_harvest,
                "corrected_net_after_harvest_cad": corrected_net_after_harvest,
                "current_gross_npv4_cad": gross_npv4,
                "corrected_gross_npv4_cad": gross_npv4 * corrected_gross / gross,
                "current_net_npv4_cad": net_npv4,
                "corrected_net_npv4_cad": net_npv4
                * corrected_net_after_harvest
                / current_net_after_harvest,
                "residual_value_premium": value_share / retention_fraction
                if retention_fraction
                else 0.0,
            }
        )
    return pd.DataFrame(rows), stand_summary, profile


def write_report(
    scenarios: pd.DataFrame, stand_summary: pd.DataFrame, profile: pd.DataFrame
) -> None:
    out_csv = DEMO / "MKRF_RETENTION_VALUE_SCENARIOS.csv"
    scenarios.to_csv(out_csv, index=False)
    stand = stand_summary.iloc[0]
    lines = [
        "# MKRF retention-value audit",
        "",
        "Status: **audit and sensitivity, not a re-optimized WS4 scenario**.",
        "",
        "## Finding",
        "",
        "WS4's ForestModelXML `<retention>` rule is implemented as an **area split**. "
        "The compiler moves a fraction of an eligible fragment's area to an "
        "unmanaged state. It does not select species, DBH, or the largest "
        "Douglas-fir stems. The retained area therefore removes an average "
        "area slice, not a high-graded residual cohort.",
        "",
        "This explains why the current low/base/high numbers move mainly with "
        "retained area: gross log value per managed hectare is nearly constant "
        "across the variants. The model is not representing the operational "
        "prescription described as ‘leave the biggest Douglas-fir’.",
        "",
        "## Audit tree list",
        "",
        f"`{stand['stand']}` has **{int(stand['trees']):,}** pinned trees, "
        f"**{int(stand['fd_trees']):,}** Douglas-fir, "
        f"{stand['total_volume_m3']:,.1f} m³ merchantable volume and "
        f"CAD {stand['total_gross_value_cad']:,.0f} gross log value "
        f"(CAD {stand['value_per_m3_cad']:.2f}/m³, game price deck).",
        "",
        "The tree list is synthetic and represents one stand; it is used here "
        "to measure the value profile, not as an estate inventory.",
        "",
        "| Fraction of all stems | Selected largest DF | Volume share | Gross-value share |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for row in profile.itertuples(index=False):
        lines.append(
            f"| {row.tree_fraction:.0%} | {row.selected_df_trees:,} | "
            f"{row.volume_share:.1%} | {row.value_share:.1%} |"
        )
    lines += [
        "",
        "## Sensitivity method",
        "",
        "- Current WS4 low/base/high schedules are treated as the **area-retention** case.",
        "- The current retention-area fraction is used as a proxy for the fraction "
        "of stems left as residual.",
        "- Residual stems are selected as the largest Douglas-fir from the "
        "MKRF 684 tree list, then the resulting value and volume shares are applied "
        "to the current schedule's potential gross/volume.",
        "- Potential gross and volume add back the average retained area slice. "
        "This isolates the difference between average-area retention and "
        "largest-DF stem retention.",
        "- Harvest cost is scaled with harvested volume; other costs are held fixed. "
        "No schedule is re-optimized and no target is re-run.",
        "",
        "## Corrected scenario numbers",
        "",
        "| Scenario | Retention ha | Gross current | Gross corrected | Δ gross | "
        "Volume current | Volume corrected | Net after all cost current | "
        "Net after all cost corrected | NPV4 gross current | NPV4 gross corrected |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in scenarios.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.retention_area_ha:,.1f} | "
            f"CAD {row.current_gross_cad/1e6:,.1f}M | "
            f"CAD {row.corrected_gross_cad/1e6:,.1f}M | "
            f"{row.gross_change_pct:+.1%} | "
            f"{row.current_volume_m3/1e6:,.2f}M m³ | "
            f"{row.corrected_volume_m3/1e6:,.2f}M m³ | "
            f"CAD {row.current_net_all_cost_cad/1e6:,.1f}M | "
            f"CAD {row.corrected_net_all_cost_cad/1e6:,.1f}M | "
            f"CAD {row.current_gross_npv4_cad/1e6:,.1f}M | "
            f"CAD {row.corrected_gross_npv4_cad/1e6:,.1f}M |"
        )
    lines += [
        "",
        "The public **net-after-harvest-cost** convention is retained in "
        f"`{out_csv.name}`; it is lower because the existing public comparison "
        "subtracts harvest cost from the already netted revenue account. The "
        "table above uses **net after all cost** to avoid that double-counting.",
        "",
        "| Scenario | Current net NPV 4% | Corrected net NPV 4% |",
        "| --- | ---: | ---: |",
    ]
    for row in scenarios.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | CAD {row.current_net_npv4_cad/1e6:,.1f}M | "
            f"CAD {row.corrected_net_npv4_cad/1e6:,.1f}M |"
        )
    lines += [
        "",
        "## Why the correction is material",
        "",
        "Retained area is only 4.4%, 8.8% and 15.7% of the eligible area, but "
        "the largest-DF profile represents 32.6%, 42.8% and 55.1% of gross value. "
        "Per retained hectare, the high-graded residual is about 7.4x, 4.9x and "
        "3.5x the average value of the area slice in the low/base/high cases.",
        "",
        "## Files",
        "",
        f"- `{out_csv.name}` — full current/corrected metrics",
        "- `MKRF_RETENTION_AUDIT.md` — this report",
        "- `MKRF_SCENARIO_COMPARISON.csv` — existing area-retention comparison",
        "",
        "## Decision boundary",
        "",
        "These corrected numbers show the direction and magnitude of the "
        "high-grading error. They are not an approved AAC, cash-flow forecast, "
        "or re-optimized plan. A production fix should make the retention "
        "operator species/DBH-aware, or apply an explicit residual-tree profile "
        "inside each harvested block, and then re-run the target search.",
    ]
    (DEMO / "MKRF_RETENTION_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (DEMO / "MKRF_RETENTION_PROFILE.csv").write_text(
        profile.to_csv(index=False), encoding="utf-8"
    )
    print(scenarios.to_string(index=False))
    print(f"wrote {out_csv}")
    print(f"wrote {DEMO / 'MKRF_RETENTION_AUDIT.md'}")


if __name__ == "__main__":
    scenario_table, stand_table, tree_profile = build()
    write_report(scenario_table, stand_table, tree_profile)
