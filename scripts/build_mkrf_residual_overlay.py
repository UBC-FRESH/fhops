#!/usr/bin/env python3
"""Build a high-grading overlay on the no-retention MKRF baseline.

This is the bridge between the completed retention-value audit and the
residual-retention operator.  It does not claim to be a re-optimized WS4
scenario.  It starts from the actual no-retention matrix/schedule, then applies
the largest-DF value/volume profile from the pinned MKRF 684 tree list.

Inputs
------
- ws4/runtime/dfret_no_retention_true_s44/report_accounts.csv
- ws4/runtime/dfret_no_retention_true_s44/account_values.csv
- examples/demo_runs/MKRF_RETENTION_PROFILE.csv
- examples/demo_runs/mkrf-*/report_accounts.csv (area-retention fractions)

Outputs
-------
- examples/demo_runs/MKRF_DFRET_SCENARIOS.csv
- examples/demo_runs/MKRF_DFRET_SCENARIOS.md
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo_runs"
INSTANCE = Path("/srv/shared-data/gep/ws4/femic/external/femic-mkrf-instance")
RUN = INSTANCE / "ws4" / "runtime" / "dfret_no_retention_true_s44"
PROFILE = DEMO / "MKRF_RETENTION_PROFILE.csv"

AREA_RUNS = {
    "low-44": DEMO / "mkrf-low-estate" / "report_accounts.csv",
    "base-44": DEMO / "mkrf-full-estate" / "report_accounts.csv",
    "high-44": DEMO / "mkrf-high-estate" / "report_accounts.csv",
}


def account_mean(frame: pd.DataFrame, account: str, *, annual: bool) -> float:
    row = frame.loc[frame["account"] == account]
    if row.empty:
        raise KeyError(account)
    value = float(row.iloc[0]["mean"])
    return value * 100.0 if annual else value


def npv(period_values: list[float], rate: float = 0.04) -> float:
    """NPV with annual cash flows spread uniformly within 10-year periods."""
    total = 0.0
    for index, value in enumerate(period_values):
        annual = value / 10.0
        for year in range(index * 10 + 1, index * 10 + 11):
            total += annual / ((1.0 + rate) ** year)
    return total


def period_values(accounts: pd.DataFrame, account: str) -> list[float]:
    rows = accounts.loc[accounts["account"] == account]
    values = []
    for period in range(10):
        lo = period * 10
        values.append(float(rows.loc[rows["offset"].between(lo, lo + 9), "value"].sum()))
    return values


def interpolate(profile: pd.DataFrame, fraction: float, column: str) -> float:
    return float(
        np.interp(
            fraction,
            profile["tree_fraction"].to_numpy(),
            profile[column].to_numpy(),
        )
    )


def build() -> pd.DataFrame:
    baseline = pd.read_csv(RUN / "report_accounts.csv")
    values = pd.read_csv(RUN / "account_values.csv")
    profile = pd.read_csv(PROFILE)

    gross = account_mean(baseline, "product.LogValue.managed.total", annual=True)
    volume = account_mean(baseline, "product.yield.managed.total", annual=True)
    harvest = account_mean(baseline, "product.Cost_Harvesting.managed.total", annual=True)
    total_cost = account_mean(baseline, "product.Cost_Total.managed.total", annual=True)
    net = gross - total_cost
    other_cost = total_cost - harvest
    harvest_per_m3 = harvest / volume

    gross_periods = period_values(values, "product.LogValue.managed.total")
    net_periods = period_values(values, "product.NetRevenue.managed.total")
    base_gross_npv = npv(gross_periods)
    base_net_npv = npv(net_periods)

    rows = []
    for label, path in AREA_RUNS.items():
        area = pd.read_csv(path)
        managed = account_mean(area, "feature.area.managed.total", annual=False)
        retention = account_mean(area, "feature.area.retention.total", annual=False)
        fraction = retention / (managed + retention)
        value_share = interpolate(profile, fraction, "value_share")
        volume_share = interpolate(profile, fraction, "volume_share")

        corrected_gross = gross * (1.0 - value_share)
        corrected_volume = volume * (1.0 - volume_share)
        corrected_harvest = corrected_volume * harvest_per_m3
        corrected_net = corrected_gross - other_cost - corrected_harvest
        corrected_gross_npv = base_gross_npv * corrected_gross / gross
        corrected_net_npv = base_net_npv * corrected_net / net

        rows.append(
            {
                "scenario": label.replace("-44", "-44-dfret"),
                "retention_fraction": fraction,
                "residual_value_share": value_share,
                "residual_volume_share": volume_share,
                "baseline_gross_cad": gross,
                "residual_gross_cad": corrected_gross,
                "gross_change_pct": corrected_gross / gross - 1.0,
                "baseline_volume_m3": volume,
                "residual_volume_m3": corrected_volume,
                "volume_change_pct": corrected_volume / volume - 1.0,
                "baseline_harvest_cost_cad": harvest,
                "residual_harvest_cost_cad": corrected_harvest,
                "baseline_net_after_all_cost_cad": net,
                "residual_net_after_all_cost_cad": corrected_net,
                "baseline_gross_npv4_cad": base_gross_npv,
                "residual_gross_npv4_cad": corrected_gross_npv,
                "baseline_net_npv4_cad": base_net_npv,
                "residual_net_npv4_cad": corrected_net_npv,
            }
        )
    return pd.DataFrame(rows)


def write_report(table: pd.DataFrame) -> None:
    out_csv = DEMO / "MKRF_DFRET_SCENARIOS.csv"
    table.to_csv(out_csv, index=False)
    lines = [
        "# MKRF no-retention / residual overlay",
        "",
        "Status: **overlay on a no-retention WS4 baseline; not yet a re-optimized "
        "residual-retention search**.",
        "",
        "The no-retention matrix was rebuilt, its product curve bank was repaired "
        "against the canonical matrix, and the target search completed. The "
        "largest-DF value/volume profile from the pinned MKRF 684 tree list was "
        "then applied to the no-retention gross and volume.",
        "",
        "| Scenario | Retained fraction | Residual value share | Gross baseline | "
        "Residual gross | Gross change | Volume baseline | Residual volume | "
        "Net after all cost baseline | Net after all cost residual | NPV4 gross "
        "baseline | NPV4 gross residual | NPV4 net baseline | NPV4 net residual |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: |",
    ]
    for row in table.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.retention_fraction:.2%} | "
            f"{row.residual_value_share:.1%} | "
            f"CAD {row.baseline_gross_cad/1e6:,.1f}M | "
            f"CAD {row.residual_gross_cad/1e6:,.1f}M | "
            f"{row.gross_change_pct:+.1%} | "
            f"{row.baseline_volume_m3/1e6:,.2f}M m³ | "
            f"{row.residual_volume_m3/1e6:,.2f}M m³ | "
            f"CAD {row.baseline_net_after_all_cost_cad/1e6:,.1f}M | "
            f"CAD {row.residual_net_after_all_cost_cad/1e6:,.1f}M | "
            f"CAD {row.baseline_gross_npv4_cad/1e6:,.1f}M | "
            f"CAD {row.residual_gross_npv4_cad/1e6:,.1f}M | "
            f"CAD {row.baseline_net_npv4_cad/1e6:,.1f}M | "
            f"CAD {row.residual_net_npv4_cad/1e6:,.1f}M |"
        )
    lines += [
        "",
        "The retained fraction is the current area-retention share, used here "
        "as a proxy for the residual stem fraction. The value/volume split is "
        "the MKRF 684 largest-DF profile. This is a high-grading overlay, not a "
        "replacement for a species/DBH-aware residual operator.",
        "",
        "The no-retention product curve table was repaired by mapping the "
        "canonical product/feature curves onto the no-retention tracks; this "
        "fixed the 482-curve collapse and restored separate LogValue, harvest "
        "cost and NetRevenue accounts.",
        "",
        "Files: `MKRF_DFRET_SCENARIOS.csv`, `MKRF_RETENTION_AUDIT.md`, "
        "`MKRF_RETENTION_PROFILE.csv`.",
    ]
    (DEMO / "MKRF_DFRET_SCENARIOS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(table.to_string(index=False))
    print(f"wrote {out_csv}")


if __name__ == "__main__":
    write_report(build())
