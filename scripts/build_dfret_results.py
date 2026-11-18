#!/usr/bin/env python3
"""Publish the residual-retention (dfret) target-search results.

Reads the no-retention baseline and the three dfret run directories, computes
NPV screens, and writes the public comparison files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo_runs"
RUNS = Path("/srv/shared-data/gep/ws4/femic/external/femic-mkrf-instance/ws4/runtime")
SOURCE = {
    "no-retention": RUNS / "dfret_no_retention_true_s44",
    "low-44-dfret": RUNS / "dfret_low_s44",
    "base-44-dfret": RUNS / "dfret_base_s44",
    "high-44-dfret": RUNS / "dfret_high_s44",
}


def periods(run: Path, account: str) -> list[float]:
    values = pd.read_csv(run / "account_values.csv")
    rows = values.loc[values["account"] == account]
    return [
        float(rows.loc[rows["offset"].between(index * 10, index * 10 + 9), "value"].sum())
        for index in range(10)
    ]


def npv(values: list[float], rate: float = 0.04) -> float:
    return sum(
        (value / 10.0) / ((1.0 + rate) ** year)
        for index, value in enumerate(values)
        for year in range(index * 10 + 1, index * 10 + 11)
    )


def metrics(run: Path) -> dict[str, float]:
    report = pd.read_csv(run / "report_accounts.csv")

    def mean(account: str, *, annual: bool = True) -> float:
        row = report.loc[report["account"] == account]
        if row.empty:
            raise KeyError(account)
        return float(row.iloc[0]["mean"]) * (100.0 if annual else 1.0)

    gross = mean("product.LogValue.managed.total")
    volume = mean("product.yield.managed.total")
    harvest = mean("product.Cost_Harvesting.managed.total")
    net = mean("product.NetRevenue.managed.total")
    net_after = net - harvest
    gross_periods = periods(run, "product.LogValue.managed.total")
    net_periods = periods(run, "product.NetRevenue.managed.total")
    harvest_periods = periods(run, "product.Cost_Harvesting.managed.total")
    after_periods = [a - b for a, b in zip(net_periods, harvest_periods)]
    targets = pd.read_csv(run / "report_targets.csv")["status"].value_counts().to_dict()
    return {
        "gross_cad": gross,
        "volume_m3": volume,
        "harvest_cost_cad": harvest,
        "net_after_all_cost_cad": net,
        "net_after_harvest_cost_cad": net_after,
        "gross_npv4_cad": npv(gross_periods),
        "net_after_all_npv4_cad": npv(net_periods),
        "net_after_harvest_npv4_cad": npv(after_periods),
        "targets_met": int(targets.get("met", 0)),
        "targets_below": int(targets.get("below", 0)),
        "targets_above": int(targets.get("above", 0)),
    }


def main() -> None:
    rows = []
    for label, run in SOURCE.items():
        row = {"scenario": label, **metrics(run)}
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(DEMO / "MKRF_DFRET_REOPTIMIZED.csv", index=False)
    lines = [
        "# MKRF residual-retention scenarios",
        "",
        "Status: **product-ledger target-search screen; the product matrix still "
        "harvests the full area. A separate state-aware value-equivalent "
        "residual-area variant is published in `MKRF_DFRET_STATE_AWARE.md`.**",
        "",
        "| Scenario | Gross | Production | Net after all cost | Net after harvest cost | "
        "Gross NPV 4% | Net NPV 4% | Targets met/below/above |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in table.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | CAD {row.gross_cad/1e6:,.1f}M | "
            f"{row.volume_m3/1e6:,.2f}M m³ | CAD {row.net_after_all_cost_cad/1e6:,.1f}M | "
            f"CAD {row.net_after_harvest_cost_cad/1e6:,.1f}M | "
            f"CAD {row.gross_npv4_cad/1e6:,.1f}M | "
            f"CAD {row.net_after_all_npv4_cad/1e6:,.1f}M | "
            f"{row.targets_met}/{row.targets_below}/{row.targets_above} |"
        )
    lines += [
        "",
        "The residual matrices were built by scaling the **product yield, gross log "
        "value, harvest cost and net revenue curves** by the largest-DF profile from "
        "the pinned MKRF 684 tree list. The no-retention matrix supplies the "
        "baseline. This is a **finance/curve screen**; the state-aware "
        "value-equivalent residual-area variant is reported separately.",
        "",
        "The residual share is applied through the product ledgers, and the target "
        "search was rerun with the same seed, target set, route configuration and "
        "100-year horizon.",
        "",
        "Files: `MKRF_DFRET_REOPTIMIZED.csv`, `MKRF_DFRET_STATE_AWARE.md`, "
        "`MKRF_DFRET_SCENARIOS.csv`, `MKRF_RETENTION_AUDIT.md`.",
    ]
    (DEMO / "MKRF_DFRET_REOPTIMIZED.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
