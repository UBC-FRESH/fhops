# FHOPS public demo

Local stable service:

- Host: `0.0.0.0`
- Port: `8780`
- Gateway landing: `/`
- Full FHOPS console: `/fhops/`
- Scenario Studio: `/studio/`
- 3D Tree Lab sandbox: `/sandbox/` (redirects to `/sandbox-v20261031i/`)
- Experimental classroom game: `/game`
- Health: `/api/health` (the full console uses the same `/api` root)

The gateway at `/` keeps all four doors. The game is deliberately the last, muted
experimental door; it is not the main FHOPS planning workflow.

## Model instance loaded by the console

The console is not intended to open as an empty workbench. Its run discovery root is:

```text
examples/demo_runs
```

It contains two validated model instances:

```text
examples/demo_runs/mkrf-full-estate
examples/demo_runs/tfl6-lidar-demo
```

`mkrf-full-estate` is the default console run. It is the full WS4 MKRF estate handoff:

- 1,763 blocks covering 4,810.85 ha in EPSG:3005;
- 1,221 blocks scheduled across 1,346 harvest events;
- a 100-year base plan in ten 10-year periods (`P00`–`P09`);
- 3.15 million m³ of total production;
- public WS4 net-revenue and harvest-cost accounts;
- patch-size metrics, target status, inventory, and provenance reports.

The handoff is read-only in FHOPS; the source of truth is the MKRF WS4 instance and its
`scenario-base-44` full-estate run. `scripts/build_mkrf_full_estate.py` documents and reproduces
the conversion.

`tfl6-lidar-demo` remains the operational example: seven-block TFL 6 LiDAR scenario, assignments,
playback, KPIs, reports, and LiDAR support.

The console auto-selects the first run, so `/fhops/` opens with map geometry and results
available. Do not add benchmark-only or metadata-only directories to the console run root. A
run without a scenario and block geometry recreates the empty-map failure mode. The contract
test at `tests/test_public_demo_contract.py` is the regression guard.

## Start/restart

The local service is managed by systemd:

```bash
sudo systemctl restart fhops-public-demo.service
sudo systemctl status fhops-public-demo.service --no-pager
```

Legacy helper scripts remain available:

```bash
cd /srv/shared-data/gep/ws4/fhops-public-demo
./run_public_demo.sh
scripts/start_public_demo_supervisor.sh
scripts/public_demo_health.sh
```

The supervisor runs in a detached tmux session, checks
`http://127.0.0.1:8780/studio/api/health` every 5 seconds, and restarts uvicorn if the origin is
down. A user crontab entry recreates the tmux supervisor every minute and after reboot.

## Deployment

The public origin should reverse-proxy the root to:

```text
http://10.232.253.210:8780
```

The full console uses absolute `/api` and `/static` paths, so it is served at `/fhops/` without
path-prefix rewriting. The gateway, Studio, Tree Lab, and game are all hosted by the same service.

App-level public-demo limits remain active: 300 requests/minute per client and a 64 KiB request
body cap. Nginx should add its own edge rate/size limits.

## Verification

```bash
cd /srv/shared-data/gep/ws4/fhops-public-demo
/home/gep/.venv/bin/python -m pytest tests/test_public_demo_contract.py -q
```

The test checks the gateway doors, the console shell paths, both complete model-instance
artifacts, full-estate coverage, scenario/geometry/map payloads, KPIs, playback, and LiDAR.
