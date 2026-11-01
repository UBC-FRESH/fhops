# FHOPS Tree Lab sandbox

A local-only demonstration of the FHOPS tree-scale workflow: four research-forest
demo cases, a 3D multi-machine playback UI, and a local-agent console that
generates candidate cases behind a validation gate.

This is a **demonstration sandbox**. It is not an operational, financial, or
regulatory tool. Tree lists are synthetic. Three footprints are placeholder
rectangles; the K80 cable concept uses an actual FEMIC forest-cover polygon.
The cable layout and cycle model are reference concepts, not engineering
designs.

## What is real and what is synthetic

| Item | Status |
|---|---|
| AFRF Gavin Lake stand attributes (6.91 ha, age 77 in 2019, `SBSdw1`) | published research-forest values |
| MKRF Malcolm Knapp stand attributes (6.14 ha, age 74 in 2020, `CWHdm`) | published research-forest values |
| K80/Raven Creek stand `FOREST_COV=666` (7.79 ha, age 74, `CWHvm1`, Low Operability) | actual FEMIC forest-cover polygon and attributes from the MKRF instance |
| Case centre coordinates | public forest location, reprojected to EPSG:3005 |
| Block footprint | **synthetic** placeholder rectangles, except the K80 case which uses the actual FEMIC stand polygon (not a harvest-block survey) |
| Tree list | **synthetic** plot-conditioned point list (not ITD/ITC, not a tree map) |
| Machine parameters and cycle times | **reference model**, not calibrated to these stands; K80 cable layout is a concept |
| Merchantable volume | FHOPS `ReferenceStemModel` (scaffold, not an operational taper) |

Every case manifest and scene manifest repeats these caveats.

## Bootstrap

From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[web]'

# Generate cases, pin inventories, build a demo run for each case
python -m sandbox.scripts.bootstrap
```

The bootstrap is idempotent. Use `--force` to regenerate the case inputs and
`--skip-runs` to stop after pinning.

## Run the UI

```bash
python -m sandbox.tree_lab.app --port 8801            # read-only demo
python -m sandbox.tree_lab.app --port 8801 --allow-agent  # enable the agent console
```

Open <http://127.0.0.1:8801>. The server binds to loopback by default. Use SSH
port forwarding or the approved container proxy; do not expose it publicly.

## Serving behind a proxy

The app uses relative asset and API URLs and accepts both prefix-preserving and
prefix-stripping proxies, so it works when a reverse proxy serves it under a
path prefix (JupyterHub, code-server, Jupyter Server Proxy). Start it with the
same prefix:

```bash
python -m sandbox.tree_lab.app --port 8801 \
  --root-path /jupyterhub03/user/<you>/codeserver/proxy/8801
```

Then open `https://<host>/jupyterhub03/user/<you>/codeserver/proxy/8801/`.

Important: JupyterHub routes `/user/<name>/...` to **that user's own server**.
`user/gep/.../proxy/8801` reaches `gep`'s session, not this container, so it will
show whatever `gep` has on port 8801 (for example a static file server). Only
the user who started this app can reach it through their own proxy path; other
users need an SSH tunnel to this container or a shared proxy mapping.

## Demo flow

1. **Cases** — AFRF Gavin and MKRF cards show provenance, tree count, volume,
   volume per hectare, and the latest run.
2. **Run** — start a run; the exact `fhops tree system` / `fhops tree scene`
   commands, durations, exit codes, KPIs, machine utilisation, warnings, and a
   machine Gantt are shown.
3. **3D** — play, pause, scrub, change speed, and reset. Feller, skidders,
   processor, loader, and trucks animate from `system_events.json`; processed
   trees disappear; the HUD tracks trees and volume; the timeline strip shows
   machine state.
4. **Agent** — ask for a variant. The local `opencode` CLI creates a candidate
   under `sandbox/cases/_candidates/`. Validate, then Accept, then Run.
5. **Data** — inspect the manifest, provenance, checksums, scenario YAML, and an
   inventory sample.

## Partial harvests are prescriptions on a stand

A case inventory is the **stand**. `case.json.harvest` declares the treatment and
the runner derives the cut list deterministically:

```json
"harvest": {
  "type": "partial",
  "marking_rule": "proportional",
  "target_basal_area_fraction": 0.30
}
```

The run writes the derived cut-list inventory to `runs/<case>/<run>/inputs/` and
feeds it to `fhops tree system`; `run.json.harvest.derived` records the cut
count, residual count, removed volume, and removed basal-area fraction. The 3D
view draws the residual stand as teal, never-processed trees.

Rules: `proportional` (random across the diameter distribution), `from_below`
(remove the smallest trees first), `diameter_limit` (all trees above a DBH
threshold). `clear_cut` (the default) cuts every stem.

```bash
python -m sandbox.scripts.make_partial_case \
  --source sandbox/cases/afrf-gavin --case-id afrf-partial-30 \
  --target-ba 0.30 --rule proportional
```

## K80 / Raven Creek cable-yarder concept

The `mkrf-k80-cable` case uses the actual FEMIC forest-cover stand
`FOREST_COV=666` west of Raven Creek near the north K80 road area. The tree
list is synthetic; the 60% slope is a scenario assumption, not a DEM-derived
measurement. The footprint is a forest-cover polygon, not a surveyed harvest
block.

The case is a **sandbox reference cable model**. It combines:

* TN-98 all-species hand-falling time for motor-manual falling;
* BK/Aubuchon standing-skyline turn time for a yarder at the K80 road with a
  spar beyond the north treeline;
* a deterministic payload grouping and loader timeline.

The events include a hand faller, cable yarder, and loader. The 3D view draws a
sloped ground plane, the actual stand outline, the skyline, the spar tree, the
cable yarder, and the animated event timeline. It is not a field-calibrated
cable engineering design and is not an operational plan.

```bash
python -m sandbox.scripts.build_cable_case --force
python -m sandbox.tree_lab.app --port 8801 --allow-agent
```

## Architecture

```text
sandbox/
  tree_lab/
    app.py        FastAPI app (loopback, agent disabled by default)
    cases.py      case schema, discovery, validation, pinning
    runner.py     fhops tree system / cable concept + fhops tree scene runner
    cable.py      sandbox reference cable-yarder event model
    agent.py      prompt template, guardrails, candidate validation/acceptance
    static/       SPA, viewer, vendored Three.js (no CDN)
  cases/          afrf-gavin, afrf-partial-30, mkrf, mkrf-k80-cable
  schemas/        case.schema.json
  scripts/        generate_cases.py, build_cable_case.py, bootstrap.py, quality_dashboard.py
  runs/           generated; git-ignored
```

A case is a directory with `case.json`, `scenario/`, `tree_inventory/`, and
`assignments.csv`. Manifest paths are relative to the case directory; absolute
paths, `..` traversal, and escaping symlinks are rejected.

Each run writes `run.json` with the exact command, duration, exit code, FHOPS
version and commit, input hashes, KPIs, warnings, and caveats.

## Agent guardrails

* Disabled unless the app starts with `--allow-agent`.
* Runs `opencode run --format json` with the repository as workspace and a
  prompt that restricts writes to `sandbox/cases/_candidates/`.
* A before/after `git status` snapshot rejects any run that touched files
  outside the candidate directory.
* Candidate layout is allowlisted; symlinks, oversized files, and extra entries
  are rejected.
* Candidates must pass the case schema, the `fhops.tree.inventory.v1` contract,
  the scenario loader, and a smoke `fhops tree system` run.
* Acceptance is an explicit user action, refuses to overwrite existing cases,
  and never runs the candidate automatically.
* Prompt, model, duration, and validation results are appended to
  `sandbox/runs/agent_log.jsonl`. No credentials are read or logged.
* The model defaults to `opencode-go/deepseek-v4.1-flash` and is passed to
  `opencode run --model`; override it with `--agent-model provider/model` or
  `--agent-model ""` to fall back to the local `opencode` config. The provider
  is hosted; configure a local model if prompts must not leave the machine.

## Tests and quality dashboard

```bash
pytest tests/tree_lab
python -m sandbox.scripts.quality_dashboard
```

The dashboard runs ruff format/check, mypy, pytest, and the Tree Lab tests, and
writes `sandbox/runs/quality.json` with a green/red summary.

## Limits

* One block, one landing, one feller, one optional processor set, one loader per
  ground-system run; cross-block travel and multi-machine traffic are out of scope.
* Tree lists are synthetic; no real inventory is bundled. The K80 case uses an
  actual FEMIC stand footprint but still has a synthetic tree list.
* Ground is flat for ground-system cases. The K80 cable concept uses a synthetic
  60% planar slope; it is not a DEM.
* The cable-yarder cycle and layout are a sandbox reference model, not a
  calibrated cable engineering design.
* No operational, financial, or regulatory claim is made.
