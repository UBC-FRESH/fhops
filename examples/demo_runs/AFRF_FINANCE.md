# AFRF public finance screening envelope

The Gavin and Knife runs now carry a **screening envelope** for net revenue. It is not a budget
forecast and it is not a substitute for AFRF's actual cash-flow ledger.

## Source

The only public AFRF financial series in the committed instance package is
**Figure 7** of the AFRF Management and Working Plan #3 (January 2007), which reports average
log value, production cost, and adjusted net value for fiscal 1988–2005 in **2005 CAD/m³**.

The chart is a small printed bar chart, not a tabular financial statement. The envelope therefore
uses broad low/base/high values read from the public chart rather than pretending to have the
underlying ledger:

| Basis | Adjusted net value, 2005 CAD/m³ | Log cost, 2005 CAD/m³ |
| --- | ---: | ---: |
| low | 55 | 28 |
| base | 75 | 32 |
| high | 100 | 50 |

These are multiplied by **1.45** as a 2005→2026 CPI screening factor. The resulting current-dollar
net values are about CAD 80 / 109 / 145 per m³.

## What is calculated

For each run:

```text
scenario_net_revenue = total_production_m3 × net_value_per_m3_2026
scenario_annual_net_revenue = scenario_net_revenue / horizon_years
```

The runs expose `finance_net_revenue_cad_{low,base,high}`,
`finance_annual_net_revenue_cad_{low,base,high}`, `finance_net_value_per_m3_2026_cad_*`, and
`finance_harvest_cost_per_m3_2026_cad_*`.

## Screening results

| Run | Annual net revenue, low | Base | High |
| --- | ---: | ---: | ---: |
| Gavin baseline | CAD 1.50M | CAD 2.05M | CAD 2.74M |
| Gavin LTSY draft | CAD 1.44M | CAD 1.96M | CAD 2.61M |
| Knife structural cycle | CAD 0.17M | CAD 0.24M | CAD 0.31M |

These are planning screens. They exclude actual AFRF overhead, road and silviculture accounting,
stumpage/taxes, working-capital timing, price by grade/species, and private contractor rates. The
MKRF run remains the one with a source-model public net-revenue account.
