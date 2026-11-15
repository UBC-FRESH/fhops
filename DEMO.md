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
examples/demo_runs/mkrf-cedar-flat
examples/demo_runs/tfl6-lidar-demo
```

`mkrf-cedar-flat` is the default console run. It includes the MKRF Cedar Flat scenario,
matching block/landing geometry, tree inventory, operational assignments, playback summaries,
KPIs, reports, and `run.json`.

`tfl6-lidar-demo` includes the TFL 6 LiDAR scenario, seven-block EPSG:3005 geometry, operational
assignments, playback summaries, KPIs, reports, LiDAR support, and `run.json`.

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

The test checks the gateway doors, the console shell paths, the complete model-instance
artifacts, scenario/geometry/map payloads, KPIs, playback, and LiDAR.
