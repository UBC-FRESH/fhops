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

It contains nineteen model instances:

```text
examples/demo_runs/gavin-full-estate
examples/demo_runs/gavin-optimized
examples/demo_runs/gavin-policy
examples/demo_runs/gavin-p00-operational
examples/demo_runs/gavin-p01-operational
examples/demo_runs/knife-structural
examples/demo_runs/knife-p00-operational
examples/demo_runs/mkrf-full-estate
examples/demo_runs/mkrf-low-estate
examples/demo_runs/mkrf-high-estate
examples/demo_runs/mkrf-p00-operational
examples/demo_runs/mkrf-low-p00-operational
examples/demo_runs/mkrf-high-p00-operational
examples/demo_runs/mkrf-low-p01-operational
examples/demo_runs/mkrf-high-p01-operational
examples/demo_runs/mkrf-low-p01-haul-30d
examples/demo_runs/mkrf-low-p01-haul-year
examples/demo_runs/mkrf-high-p01-haul-30d
examples/demo_runs/tfl6-lidar-demo
```

`gavin-full-estate` is the default console run by run-id order. It is the full WS4 Gavin Lake
baseline handoff: 2,907 blocks, 5,663.66 ha, 10,113 harvest events over 300 years, 5.66 million m³
of harvest, and the full growing-stock/target evidence surface. No public Gavin net-revenue
account is present, so none is fabricated.

`gavin-optimized` is a draft WS4 simulated-annealing optimization against the original Gavin
LTSY targets. It schedules 2,863 blocks, produces 5.40 million m³, ends at 631,180 m³ growing
stock, and reports 13 targets met, 37 below, and 11 above.

`gavin-policy` is the decision-grade public policy screen: 174,000 m³/period floor, 600,000 m³
growing-stock floor, ±4% even-flow. It schedules 2,812 blocks, produces 5.39 million m³, ends at
610,004 m³, and **meets all 61 targets**. It remains a public scenario choice, not an approved
management plan.

`gavin-p00-operational` is the first operational handoff of `gavin-policy`: 192 P00 blocks,
505.14 ha, 175,533 m³, five machines, eight landings, and a 365-day screening window. It completes
all 192 blocks in 315 days with zero sequencing violations under a 1,000 m³/day screening rate.

`gavin-p01-operational` is the second operational handoff: 237 P01 blocks, 492.08 ha,
176,512 m³, five machines, eight landings, and a 365-day screening window. It completes all 237
blocks in 355 days with zero sequencing violations.

Both P00/P01 runs include a public-geography road/haul screen to Williams Lake: about 58 km
mean one-way, 3,900 loads at 45 m³, 2 loads per truck-day, and 6 required trucks for the
365-day window. This is a fleet screen, not a road-network schedule.

The MKRF scenario set also includes `mkrf-low-estate` (scenario-low-44) and
`mkrf-high-estate` (scenario-high-44). The three MKRF runs share the 1,763-block estate and
provide the console scenario comparison: base CAD 376.8M, low CAD 380.2M, high CAD 334.5M
net revenue over 100 years. See `examples/demo_runs/MKRF_SCENARIOS.md` and the NPV comparison in
`examples/demo_runs/MKRF_SCENARIO_COMPARISON.md`. The annual after-cost net revenue range is
about CAD 1.81–2.06M/year; NPV at 2/4/6% is in the comparison report.

`mkrf-p00-operational` is the first operational handoff of the MKRF base plan: 115 blocks,
654.99 ha, 390,965 m³, five machines, eight landings, a 365-day window, and a Vancouver
truck screen of 8,689 loads / 12 trucks. It completes all 115 blocks in 329 days.

`mkrf-low-p00-operational` and `mkrf-high-p00-operational` apply the same operational screen
to the low/high scenarios: 86 blocks / 367,238 m³ / 296 days and 78 blocks / 299,973 m³ /
247 days respectively, both with zero remaining work and the Vancouver truck screen.

`mkrf-low-p01-operational` and `mkrf-high-p01-operational` are the second-period operational
handoffs: low 110 blocks / 303,770 m³ / 269 days / 10 Vancouver trucks; high 112 blocks /
308,550 m³ / 264 days / 10 trucks. Both have zero remaining work and zero sequencing violations.

`mkrf-low-p01-haul-30d` is the actual FHOPS Phase I/II hauling run: 30-day low-44 P01
horizon, 110 blocks, 12 trucks, 1,110 truckloads / 49,934 m³ delivered, and 37 loads
scheduled on day 1.

`mkrf-low-p01-haul-year` is the rolling full-year Phase I aggregate: 12 monthly FHOPS
windows, 303,765.7 m³ delivered, 8,295 truckloads, plus 12 monthly Phase II day-1 samples
(282 loads). It is a rolling aggregation, not a single 365-day MILP or continuous truck schedule.
The one-page MKRF decision pack is `examples/demo_runs/MKRF_DECISION_PACK.md`.
The AFRF comparison is `examples/demo_runs/AFRF_DECISION_PACK.md`; Gavin is decision-grade,
while the new Knife GWM policy screen reaches a reserve cycle after about 120 years.

`mkrf-high-p01-haul-30d` is the matching actual FHOPS Phase I/II high-scenario sample:
30-day horizon, 112 blocks, 12 trucks, 1,110 truckloads / 49,932 m³, and 37 loads on day 1.

`knife-p00-operational` is the first operational handoff of Knife Creek: 50 blocks,
979.27 ha, 158,230 m³, completed in 138 days with zero remaining work under the 1,500 m³/day
screen and a Williams Lake truck screen.

`knife-structural` is the earlier single-cycle structural full-block Knife Creek pilot. It is
retained for comparison.

`knife-gwm-policy` is the HMZ-constrained sustained GWM state-transition policy screen. It uses
the 8-entry FVS-BC library (`ws4/state_library_v3`: 216 per-chain states, 192 transitions,
35 canonical states, 48 canonical transitions, 2 cycles) and the compiled spatial dataset
(`ws4/dataset_kc_spatial_v5`: 140 tracks, 96 treatments). It schedules 157 of 160 blocks,
1,570 entries, and 2,433,385 m³. Production is positive in all 30 periods; P00 is 208,452 m³
and P29 is 29,632 m³. The key correction is that clump-harvest volume is now counted in the
transition, not just the FVS cut. It remains a structural public policy screen, not an approved
management plan.

`knife-gwm-lidar-policy` applies the 2024 LiDAR reserve scenario as a block-level harvest gate.
Blocks with zero LiDAR harvest trees are excluded: 135 of 160 blocks are scheduled, with
1,350 entries and 2,343,814 m³. Production remains positive in all 30 periods. This is a
block-level LiDAR gate, not yet a replacement of the DBH-ranked clump proxy inside FVS.

`knife-lidar-clump-policy` is the spatial-clump FVS screen. It uses one-hectare LiDAR samples,
groups trees ≥20 m into 10 m clumps, reserves the three largest trees per 4–10-tree clump, and
runs block-level FVS entries. It calibrates LiDAR TPH and BA to VRI and assigns the dominant VRI
species. It schedules 134 of 160 blocks, 642 entries, and 2.58 million m³. Production is positive
in all 30 periods. This is a structural LiDAR pilot, not a CFI or an approved plan; LiDAR DBH is
height-allometry and species is block-dominant, not tree-level composition.

`mkrf-full-estate` is the full WS4 MKRF estate handoff:

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

The test checks the gateway doors, the console shell paths, all complete model-instance
artifacts, full-estate coverage, scenario/geometry/map payloads, KPIs, playback, and LiDAR.

## AFRF status

Gavin Lake is now a runnable full-estate handoff (`gavin-full-estate`).

Knife Creek is present as a structural full-block pilot (`knife-structural`) so the whole
block is visible in the console. The public instance still lacks an approved full-block
selection schedule and a public financial-account surface; the run is labeled accordingly.
The next Knife Creek gate is the reviewed schedule plus public account/provenance output.


## AFRF financial screening envelope

The Gavin and Knife KPIs now include a deliberately wide public AFRF finance envelope derived
from MWP #3 Figure 7 (2005 CAD/m³), inflated by a stated 1.45 CPI screening factor. It is not a
budget forecast and does not replace the AFRF ledger. Details:
`examples/demo_runs/AFRF_FINANCE.md`.
