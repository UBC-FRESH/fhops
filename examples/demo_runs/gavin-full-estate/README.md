# Gavin Lake full estate — WS4 300-year baseline

This is a full-estate FHOPS handoff from the AFRF Gavin Lake WS4 instance.

## Coverage

- 2,907 blocks
- 5,663.66 ha
- EPSG:3005 geometry
- 10,113 harvest events
- 300-year horizon
- 30 ten-year periods (`P00`–`P29`)
- 5,660,336.77 m³ total harvest
- 188,677.89 m³ mean harvest per period
- 177,070.07 m³ minimum period
- 197,806.62 m³ maximum period
- growing stock: 1,418,962.31 m³ initial → 495,510.56 m³ final
- target status: 4 met, 31 below, 26 above

The baseline clearcuts at age 80 and re-enters every 80 years. It is a
structural/even-flow baseline from the WS4 evidence surface, not a new Gavin
Lake management plan. No public net-revenue account is present in this evidence;
the handoff does not fabricate one.

## Provenance

```text
/srv/shared-data/gep/ws4/femic/external/femic-afrf-gavinlake-instance
  data/legacy_gavinlake/spatial/fragments.shp
  ws4/schedules/baseline_evenflow.csv
  ws4/evidence/baseline/
```

`ws4/targets_gavin_ltsy.yaml` is included as the runnable first-guess harvest
target. The baseline does not meet the literal legacy 500,000 m³/period target
or the 1,277,067 m³ growing-stock floor; those outcomes are preserved in
`target_report.csv`.

## Regenerate

```bash
cd /srv/shared-data/gep/ws4/fhops-public-demo
PYTHONPATH=src:. /home/gep/.venv/bin/python scripts/build_afrf_gavin_estate.py
```
