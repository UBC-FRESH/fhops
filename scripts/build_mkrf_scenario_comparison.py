"""Build the MKRF base/low/high scenario comparison with NPV screens."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2] if Path.cwd().name == "scripts" else Path.cwd()
ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "base": "mkrf-full-estate",
    "low": "mkrf-low-estate",
    "high": "mkrf-high-estate",
}
RATES = (0.02, 0.04, 0.06)


def npv_for_periods(frame: pd.DataFrame, value_column: str, rate: float) -> float:
    """NPV of annual cash flows spread uniformly through each 10-year period."""
    total = 0.0
    for index, row in frame.iterrows():
        annual = float(row[value_column]) / 10.0
        start = index * 10 + 1
        for year in range(start, start + 10):
            total += annual / ((1.0 + rate) ** year)
    return total


def main() -> None:
    rows = []
    period_rows = []
    details = {}
    for label, run_id in RUNS.items():
        run = ROOT / "examples" / "demo_runs" / run_id
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        periods = pd.read_csv(run / "revenue_by_period.csv")
        periods = periods.reset_index(drop=True)
        periods["net_after_cost_cad"] = periods["net_revenue_cad"] - periods["harvest_cost_cad"]
        for index, row in periods.iterrows():
            period_rows.append(
                {
                    "scenario": label,
                    "run_id": run_id,
                    "period_id": row["period_id"],
                    "period_number": index + 1,
                    "years": f"{index * 10 + 1}-{(index + 1) * 10}",
                    "volume_m3": round(float(row["volume_m3"]), 3),
                    "net_revenue_cad": round(float(row["net_revenue_cad"]), 3),
                    "harvest_cost_cad": round(float(row["harvest_cost_cad"]), 3),
                    "net_after_cost_cad": round(float(row["net_after_cost_cad"]), 3),
                }
            )
        rates = {f"{int(rate * 100)}pct": round(npv_for_periods(periods, "net_after_cost_cad", rate), 3) for rate in RATES}
        gross_rates = {f"{int(rate * 100)}pct": round(npv_for_periods(periods, "net_revenue_cad", rate), 3) for rate in RATES}
        cost_rates = {f"{int(rate * 100)}pct": round(npv_for_periods(periods, "harvest_cost_cad", rate), 3) for rate in RATES}
        row = {
            "scenario": label,
            "run_id": run_id,
            "source": summary.get("source", ""),
            "blocks_scheduled": summary.get("blocks_scheduled"),
            "area_total_ha": summary.get("area_total_ha"),
            "scheduled_area_ha": summary.get("scheduled_area_ha"),
            "total_production_m3": summary.get("total_production_m3"),
            "net_revenue_cad": summary.get("net_revenue_cad"),
            "harvest_cost_cad": summary.get("harvest_cost_cad"),
            "net_after_harvest_cost_cad": summary.get("net_revenue_after_harvest_cost_cad"),
            "annualized_net_after_cost_cad": round(float(periods["net_after_cost_cad"].sum()) / 100.0, 3),
            "targets_met": summary.get("targets_met"),
            "targets_below": summary.get("targets_below"),
            "targets_above": summary.get("targets_above"),
            "npv_net_2pct_cad": rates["2pct"],
            "npv_net_4pct_cad": rates["4pct"],
            "npv_net_6pct_cad": rates["6pct"],
            "npv_gross_4pct_cad": gross_rates["4pct"],
            "npv_cost_4pct_cad": cost_rates["4pct"],
        }
        rows.append(row)
        details[label] = {"summary": row, "periods": periods.to_dict("records")}
        # Add flat comparison fields to the run so the console Compare panel exposes them.
        for name in ("summary.json", "kpis.json", "tactical_summary.json"):
            payload = json.loads((run / name).read_text(encoding="utf-8"))
            payload.update(
                {
                    "npv_net_2pct_cad": rates["2pct"],
                    "npv_net_4pct_cad": rates["4pct"],
                    "npv_net_6pct_cad": rates["6pct"],
                    "npv_gross_4pct_cad": gross_rates["4pct"],
                    "npv_cost_4pct_cad": cost_rates["4pct"],
                    "annualized_net_after_cost_cad": row["annualized_net_after_cost_cad"],
                }
            )
            (run / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary = pd.DataFrame(rows)
    summary.to_csv(ROOT / "examples" / "demo_runs" / "MKRF_SCENARIO_COMPARISON.csv", index=False)
    (ROOT / "examples" / "demo_runs" / "MKRF_SCENARIO_COMPARISON.json").write_text(
        json.dumps({"discount_rates": list(RATES), "discounting": "annual cash flows uniform within each 10-year period", "scenarios": details}, indent=2) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(period_rows).to_csv(ROOT / "examples" / "demo_runs" / "MKRF_SCENARIO_PERIODS.csv", index=False)
    lines = [
        "# MKRF scenario comparison",
        "",
        "NPV screens use annual cash flows spread uniformly within each 10-year period. Net is after harvest cost.",
        "",
        "| Scenario | Blocks | Production | Net after cost | Annualized | NPV 2% | NPV 4% | NPV 6% | Targets (met/below/above) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['scenario']} | {row['blocks_scheduled']:,} | {row['total_production_m3']:,.0f} m³ | CAD {row['net_after_harvest_cost_cad']:,.0f} | CAD {row['annualized_net_after_cost_cad']:,.0f}/yr | CAD {row['npv_net_2pct_cad']:,.0f} | CAD {row['npv_net_4pct_cad']:,.0f} | CAD {row['npv_net_6pct_cad']:,.0f} | {row['targets_met']}/{row['targets_below']}/{row['targets_above']} |"
        )
    (ROOT / "examples" / "demo_runs" / "MKRF_SCENARIO_COMPARISON.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary[["scenario", "total_production_m3", "net_after_harvest_cost_cad", "annualized_net_after_cost_cad", "npv_net_2pct_cad", "npv_net_4pct_cad", "npv_net_6pct_cad"]].to_string(index=False))


if __name__ == "__main__":
    main()
