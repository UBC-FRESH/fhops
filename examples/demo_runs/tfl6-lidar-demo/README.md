# TFL 6 LiDAR demo model instance

This is the model instance loaded by the public FHOPS console at `/fhops/`.

It is a self-contained, runnable FHOPS operational model instance built from the committed
`examples/lidar_tfl6` fixture:

- seven LiDAR-backed TFL 6 blocks with matching `blocks.geojson` geometry;
- the full scenario bundle (block, machine, landing, calendar, productivity tables);
- an operational simulated-annealing assignment (`assignments.csv`);
- deterministic shift/day playback summaries;
- computed KPI and summary JSON;
- a `run.json` manifest pointing at `scenario/scenario.yaml`.

The fixture is a smoke-test model instance. Machine rates, 20 m3/ha work volumes, landing
capacity, and the road job are synthetic planning values, not a field inventory or calibrated
cost model. LiDAR values and clipped VRI geometry are from the public LidarBC fixture and retain
the OGL-BC attribution in `scenario/provenance.json`.

## Regenerate

```bash
fhops solve-heur scenario/scenario.yaml \
  --out assignments.csv --iters 120 --seed 7 --kpi-mode basic
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
