# MKRF Cedar Flat demo model instance

This is the default model instance loaded by the public FHOPS console at `/fhops/`.

It is built from the committed MKRF Cedar Flat game fixture:

- one block (`B01`, about 6.86 ha) and one landing (`L1`);
- the committed block and landing GeoJSON in EPSG:3005;
- the full scenario bundle, including the 4,798-tree FAIB-PSP synthetic inventory;
- an operational tree-length schedule generated with FHOPS simulated annealing;
- deterministic day/shift playback summaries;
- computed KPI and summary JSON;
- a `run.json` manifest pointing at `scenario/scenario.yaml`.

## Derived role capacities

The source game scenario supplies only the feller-buncher production rate. The operational
planner needs capacities for the downstream machines as well, so this instance adds role
capacities derived from the committed precomputed MKRF tree-system optimum
(`examples/game/precomputed/mkrf_684.json`):

```text
rate(machine) = processed_volume_m3 / machine_hours * 24
```

The derived values are recorded in `scenario/prod_rates.csv`; they are scheduling inputs for
this demo, not field-measured machine rates. The source scenario and tree inventory are
unchanged apart from making the inventory paths run-local.

## Regenerate

```bash
fhops solve-heur scenario/scenario.yaml \
  --out assignments.csv --iters 500 --seed 7 --kpi-mode basic
fhops eval-playback scenario/scenario.yaml \
  --assignments assignments.csv \
  --shift-out shift_summary.csv --day-out day_summary.csv \
  --summary-md playback_summary.md
fhops web manifest . \
  --domain operational --run-type solve \
  --scenario scenario/scenario.yaml \
  --solver simulated-annealing --seed 7 --status completed
```

The KPI JSON is computed from the scenario and assignments with
`fhops.evaluation.compute_kpis`.

The map loader reads the scenario's `geo.block_geojson` and `geo.crs`; `blocks.geojson` is
also available at the run root as a fallback geometry source.
