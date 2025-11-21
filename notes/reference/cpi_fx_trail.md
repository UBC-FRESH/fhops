CPI & FX Audit Trail
====================

Use this note whenever we have to explain how historical FPInnovations/USFS cost tables are inflated to present-day CAD or converted from USD. It captures the exact series, queries, and multipliers so the CLI and docs can cite reproducible numbers.

## CPI (Statistics Canada Table 18-10-0005-01, All-items CPI 2002=100)

- Source file already in repo: `data/costing/cpi_canada_all_items_2002_100.json`.
- Series pulled from StatCan Table 18-10-0005-01 via the official CSV download and stored at 2002=100. `src/fhops/costing/inflation.py` reads this JSON and targets 2024 by default.
- Key values and multipliers (2024 CPI = **160.9**). Multipliers are `160.9 ÷ CPI(year)` and match `inflation_multiplier(year, 2024)`:

| Year | CPI (index) | 2024/Year multiplier |
| --- | --- | --- |
| 1979 | 40.0 | 4.0225 |
| 1984 | 60.6 | 2.6551 |
| 1989 | 74.8 | 2.1511 |
| 1994 | 85.7 | 1.8775 |
| 1997 | 90.4 | 1.7799 |
| 2002 | 100.0 | 1.6090 |
| 2004 | 104.7 | 1.5368 |

Usage: `fhops.costing.inflation.inflate_value( value, from_year )` already applies these numbers, but when documenting a machine-rate conversion cite “Statistics Canada Table 18-10-0005-01 (All-items CPI, 2002=100); multiplier X”.

## CAD/USD FX (StatCan WDS vector v37426 + BoC Valet FXAUSDCAD)

### StatCan monthly averages (through 2017)

- Table: `Foreign exchange rates in Canadian dollars, Bank of Canada, monthly` (archived CANSIM 176-0064, productId 10100009).
- Vector: **37426** (`Canada; United States dollar, noon spot rate, average`) obtained via `getSeriesInfoFromCubePidCoord`.
- Query (examples are exact URLs we used):
  ```
  https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorByReferencePeriodRange?vectorIds="37426"&startRefPeriod=1979-01-01&endReferencePeriod=2004-12-01
  ```
- Annual averages were computed by taking the simple mean of the 12 monthly noon averages per calendar year. Resulting CAD per USD values:

| Year | CAD / USD (average) |
| --- | --- |
| 1979 | 1.1714 |
| 1984 | 1.2951 |
| 1989 | 1.1840 |
| 1994 | 1.3657 |
| 1997 | 1.3846 |
| 2002 | 1.5703 |
| 2004 | 1.3013 |

Use these when converting US machine-rate tables from the 1979–2004 window (e.g., LeDoux 1984 or OpCost 2002). Cite: “Statistics Canada CANSIM 176-0064 (vector v37426, noon spot rate average) via WDS `getDataFromVectorByReferencePeriodRange`”.

### Modern annual averages (2017 onward)

- Table 176-0064 stops in 2017, so we pull current annual averages from the Bank of Canada Valet `FXAUSDCAD` series (`https://www.bankofcanada.ca/valet/observations/FXAUSDCAD/json?recent=10`).
- Example: 2024 annual average **1.3698** CAD/USD (observation date `2024-01-01`).
- When we upsell archived FPInnovations costs to 2024 CAD but still need to cite the USD→CAD conversion, reference “Bank of Canada Valet FXAUSDCAD (annual average)”.

## Workflow reminder

1. Inflate nominal CAD figures with the CPI multipliers above (`inflate_value` call).
2. For USD tables published in year *Y*, convert to CAD using the matching CAD/USD average (StatCan up to 2017, BoC Valet afterwards), *then* run the CPI multiplier.
3. Record both steps in docs or telemetry (e.g., “USD 268/h × 1.2951 CAD/USD × 2.6551 CPI = 2024 CAD 920/h”).

## Outstanding items

- Add similar tables for EUR→CAD or other currencies once we ingest European FPInnovations studies; StatCan 176-0064 already contains most G-10 vectors.
- Capture BC fuel-price escalators (diesel $/L) using the same CPI helper so cost narratives stay consistent.
