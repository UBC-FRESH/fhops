# MKRF full estate — WS4 100-year base plan

This is the default model instance in the FHOPS public console at `/fhops/`.

It is a **full-estate handoff** from the MKRF WS4 instance, not a single game stand.

## Coverage

- 1,763 blocks
- 4,810.85 ha
- EPSG:3005 geometry
- 1,221 scheduled blocks
- 1,346 harvest events
- 100-year horizon, ten 10-year periods (`P00`–`P09`)
- 3,148,735 m³ total production
- 29 targets met, 7 below, 1 above
- 4,055.45 ha carrying a scheduled harvest event

## Provenance

Source:

```text
/srv/shared-data/gep/ws4/femic/external/femic-mkrf-instance/ws4/runtime/matrix_silv
/srv/shared-data/gep/ws4/ws4-public-demo/runs/femic-mkrf-instance/scenario-base-44
```

The WS4 run is the source of truth for the estate model. FHOPS receives a read-only
tactical-operational view: block geometry, harvest decisions, period production, public financial
accounts, patch metrics, and target status. This handoff does **not** re-solve the 100-year estate
model inside FHOPS.

Net revenue and harvest cost are public WS4 model accounts:

- net revenue: CAD 376,792,739.85 over the 100-year run
- harvest cost: CAD 173,180,428.08
- net after harvest cost: CAD 203,612,311.77
- mean annual net revenue: CAD 3,767,927.40

The mean annual figure is a model output, not a budget forecast. Discounting, private contractor
overlays, and the full cost/revenue workbook are outside this public artifact.

## Regenerate

```bash
cd /srv/shared-data/gep/ws4/fhops-public-demo
PYTHONPATH=src:. /home/gep/.venv/bin/python scripts/build_mkrf_full_estate.py
```

The generated run uses:

- `harvest_decisions.csv` — block/period/treatment/area from the WS4 schedule;
- `production.csv` — period production from WS4 account values;
- `tactical_summary.json`, `summary.json`, `kpis.json`;
- `revenue_by_period.csv` — public net revenue, harvest cost, and volume by period;
- `blocks.geojson` — block polygons simplified at 4 m for web transfer;
- WS4 report surfaces: accounts, targets, patch metrics, patch accounts, ending inventory;
- `scenario.yaml`, `run.json`, and `provenance.json`.

Raw WS4 product/route tables are intentionally not copied; the public source boundary remains the
WS4 instance and its report surface.
