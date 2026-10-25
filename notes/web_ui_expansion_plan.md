# FHOPS Web Application Expansion Plan (WS4-Style)

Date: 2026-10-24
Status: active (P12)
Phase: P12
Branch: `feature/p12-web-ui` (created from `main` at activation)
Parent issue: #171
Reference implementation: `UBC-FRESH/ws4`, Phase 18 (issue #146), design note
`notes/design/ws4-web-frontend.md`, service `ws4/web/app.py`, SPA `ws4/web/static/index.html`,
`app.js`, and `style.css`.
Reference page: <https://github.com/UBC-FRESH/ws4/blob/main/notes/design/ws4-web-frontend.md>

## 1. Executive recommendation

Add a browser surface over **the artefacts the FHOPS CLI already writes**. The UI must be a
presentation and comparison layer, not a second model: no UI-only state, no value the CLI cannot
reproduce, and no solver imported into the web request process. A run is started by invoking the
CLI; the service reads the resulting files.

The style and technology stack follow the WS4 web UI:

- **FastAPI + uvicorn** behind an optional `fhops[web]` extra.
- A **vanilla ES module SPA** served by the same process; no Node build and no JavaScript
  toolchain.
- **MapLibre GL JS** with an OpenStreetMap raster basemap, plus an SVG fallback for environments
  without WebGL.
- A header with scenario/run selectors and a day/period control; a left sidebar with tabbed panels;
  a map or schedule canvas; an optional lower-left assistant panel.
- **Skins are JSON manifests** over one application, checked against a registry. Unknown panel,
  layer, or action names are refused by name.
- **SSE** for live run telemetry, throttled to at most 2 Hz, with `204` for a finished run so
  EventSource does not reconnect forever.
- **Local-only by default.** A non-loopback bind requires `--allow-remote`; authentication is a
  later phase with its own design.
- **The agent is opt-in** (`--allow-agent`, off by default) and calls the installed `opencode` CLI;
  the service never reads provider keys.

## 2. Goal and non-goals

### Goal

Let a planner, analyst, or reviewer:

- choose a scenario and a completed or running plan;
- see the harvest schedule on a map and as a Gantt/timeline by day, shift, machine, crew, and block;
- read production, cost, utilisation, mobilisation, and hauling KPIs without a terminal;
- open the standard reports and compare two runs;
- watch a live heuristic or MIP run and see the incumbent move;
- edit the small set of inputs that are safe to round-trip (objective weights, schedule locks, and,
  when P11 lands, hauling driver/contractor settings), with validation by the same loader the CLI
  uses;
- ask the optional assistant about the scenario or run.

### Non-goals (first release)

- A second optimisation model, a database, multi-user accounts, or authentication.
- A full GIS editor, 3D, or field-data collection.
- A cloud deployment or hosted multi-tenant service.
- A replacement for the Sphinx documentation site.
- A React/Vue/Svelte build pipeline. The WS4 lesson is that a dependency-free ES module shell is
  enough for this class of tool.
- Editing arbitrary YAML from the browser. Only named, validated fields are editable.
- Recomputing a KPI or report in the browser. The service returns what the run wrote.

## 3. What FHOPS already produces

The service should discover runs from a configured root and classify them by the files present.
The first cut should read, at minimum:

| Artefact | What the UI uses it for |
|---|---|
| `scenario.yaml` and the referenced CSV bundle | Scenario identity, blocks, machines, landings, calendars, products |
| `blocks.csv`, `machines.csv`, `landings.csv` | Map features, filters, Gantt resource labels |
| `geo` metadata / GeoJSON paths | Block and landing geometry; optional road and mill layers |
| `*_solution.csv` or `assignments.csv` | Machine/block/day/shift schedule; Gantt and map treatment layers |
| `summary.json` / `*_summary.json` | Solver, objective, seed, status, runtime, file manifest |
| `telemetry.jsonl` and `telemetry-*.jsonl` | Live progress, incumbent trajectory, per-island telemetry |
| `kpis.json` or the evaluation output | Production, cost, utilisation, mobilisation, sequencing |
| Shift/day Parquet or CSV from `eval-playback` | Playback summaries and stochastic bands |
| `plan tactical-operational` outputs | Harvest decisions, production, flows, purchases, inventory, roads, silviculture, fleet |
| `plan rolling` outputs | Locked assignments, per-iteration summaries, window status |
| `fhops report` output | Standard tactical reports and downloadable files |
| P11 hauling outputs | Flows, truckloads, schedules, yard inventory, contractor workload, haul KPIs |
| `run.json` (new, P12.1) | Stable run manifest: command, scenario, seed, solver, start time, files |

### Run manifest

FHOPS does not currently write a single run manifest. P12.1 adds a small, additive `run.json`:

```json
{
  "schema_version": "1.0.0",
  "run_id": "2026-10-24T18-22-01_sa_tiny7",
  "command": "fhops solve-heur examples/tiny7/scenario.yaml --out ...",
  "scenario": "examples/tiny7/scenario.yaml",
  "solver": "sa",
  "seed": 42,
  "started_at": "2026-10-24T18:22:01Z",
  "status": "ok",
  "files": {
    "assignments": "sa_solution.csv",
    "summary": "summary.json",
    "telemetry": "telemetry.jsonl",
    "kpis": "kpis.json"
  }
}
```

The manifest is optional for old runs. The service falls back to scanning known filenames and
reports what it could not classify, rather than pretending a run is complete.

## 4. Service surface

An optional extra, `fhops[web]` (FastAPI + uvicorn + MapLibre static assets), with no change to the
core install.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Service and version |
| GET | `/api/scenarios` | Configured scenario roots and manifest summary |
| GET | `/api/scenarios/{id}` | Scenario summary and editable field descriptors |
| PUT | `/api/scenarios/{id}/objective` | Replace objective weights; validate by loading the scenario |
| PUT | `/api/scenarios/{id}/locks` | Replace schedule locks; validate by loading the scenario |
| GET | `/api/runs` | Runs under the configured roots, with summary and status |
| GET | `/api/runs/{id}` | Run manifest, files, and status |
| GET | `/api/runs/{id}/summary` | `summary.json` as written |
| GET | `/api/runs/{id}/assignments?day=&shift=&machine=&block=` | Assignment rows, filtered |
| GET | `/api/runs/{id}/kpis?scope=run|day|shift` | KPI payload, filtered |
| GET | `/api/runs/{id}/map?day=&layers=` | GeoJSON `FeatureCollection`; properties are requested layers |
| GET | `/api/runs/{id}/layers` | Layer families the run can draw, with legends |
| GET | `/api/runs/{id}/reports` | Report tree (standard and scenario files) |
| GET | `/api/runs/{id}/reports/{name}` | Report rows (JSON) plus CSV/Parquet/PNG path |
| GET | `/api/runs/{id}/events` | SSE stream; `204` when the run is finished |
| POST | `/api/runs` | Start a run from a scenario and options; returns its id |
| POST | `/api/runs/{id}/control` | Pause, resume, or stop a live run |
| GET | `/api/land-base?format=` | Optional non-forest underlay |
| GET | `/` and `/static/*` | SPA shell and assets |

The SPA must be prefix-relative. The service takes `--root-path` for a proxy subpath (for example a
hosted notebook that publishes a port under `/user/<name>/proxy/<port>/`), and the browser uses
relative API and asset URLs so one build works at `/` and under a prefix.

The service is a **reader**. A run is started by invoking the CLI as a subprocess, with a working
directory and an allowlisted output root. A crash in a search cannot take the UI down, and the
service cannot drift from the CLI's semantics.

## 5. Streaming contract

One SSE endpoint, `text/event-stream`, with named events:

```text
event: progress
data: {"iteration": 1200, "objective": 15758.97, "best": 0.0, "runtime_s": 45.2, "status": "running"}

event: kpis
data: {"total_production": 4500.0, "mobilisation_cost": 1200.0, "utilisation_ratio_mean_day": 0.71}

event: assignment
data: {"machine_id": "H1", "block_id": "b7", "day": 12, "shift_id": "DAY"}

event: done
data: {"summary": "summary.json", "status": "ok"}
```

Events are emitted from the run's own telemetry, throttled to at most 2 Hz, and the stream closes
with `done` or `error`. The stream never computes a value the run did not write. A finished run's
`/events` returns **204**, not a short stream that EventSource reconnects to. Live streams close
after ten minutes and reconnect, using the same replay path that rebuilds the map.

## 6. UI layout and visual language

Reuse the WS4 design language:

- Neutral ink/muted/line/bg palette, white panels, tabular numerals for metrics.
- Header: product mark, build/version, skin selector, scenario selector, run selector, day/period
  slider with an explicit label, status text.
- Main grid: resizable left sidebar, splitter, map or schedule canvas.
- Sidebar tabs: **Legend**, **Schedule**, **KPIs**, **Reports**, **Compare**. Add **Scenario** for
  editable objective/lock fields in the planner skin.
- Lower-left assistant panel with a draggable splitter, a "New" button, a model label, escaped
  markdown, and action chips. It is hidden unless the service starts with `--allow-agent`.
- Keyboard: left/right arrow steps one day/period; `f` fits the map; `/` focuses search.
- Empty states and errors name the missing file or artefact, not a generic "no data".

### Map

- Blocks as polygons from the scenario's GeoJSON, or points from a centroid table when geometry is
  absent. Geometry is joined on `block_id` and never written back into the scenario.
- Treatment layers: current day/shift versus cumulative through the horizon; current in the
  treatment colour, earlier in a hatch.
- Machine/crew layer: machines working on the selected day, with role colours and a legend.
- Roads: source access, built, and used, when the scenario or plan carries them.
- Mills and sort yards: point or polygon features with demand/throughput badges; P11 adds haul
  routes and yard inventory.
- A layer tree with grouped visibility, opacity, and legend swatches; a base-colour selector for a
  source attribute (for example harvest system or block status).
- Click a block for its attributes, assigned machines, production, and KPI contribution.
- MapLibre is the default renderer; the dependency-free SVG shell remains a fallback and is
  switchable in the layer tree.

### Schedule

- A Gantt/timeline by day and shift, rows for machines or crews, bars for block assignments.
- Click a bar to open the assignment, block, and KPI context.
- A playback control for shift/day summaries and optional stochastic bands.
- A table view for accessibility and copy/export.

### KPIs and reports

- KPI cards for production, cost, utilisation, mobilisation, sequencing violations, and (after P11)
  hauling cost/overtime/waiting.
- Charts drawn from the run's own series, with no client-side recomputation beyond formatting.
- Reports tree grouping the named standard reports the run actually wrote; a file list below it.
- A report builder that selects a metric and day/shift range, renders the rows, and exports exactly
  those rows as CSV.

### Comparison

- Two run selectors, A and B, independent of the header's current run.
- Map differences by block/day: A-only, B-only, both.
- KPI and assignment deltas; a table sorted by absolute delta and capped for rendering.
- Comparison is a client-side reader of the two runs; no new service state and no recomputation.

## 7. Skins

A skin is a JSON document, not a route or a fork:

```json
{
  "id": "planner",
  "title": "Planner",
  "panels": ["map", "schedule", "kpis", "reports", "compare", "scenario"],
  "layers": ["blocks", "machines", "treatments", "roads", "mills", "haul_routes"],
  "actions": ["start_run", "edit_objective", "edit_locks", "export"],
  "read_only": false
}
```

The loader checks every panel, layer, and action against a registry; an unknown name is **refused
with the name**, not ignored. `read_only` removes every mutating action, including objective/lock
editing.

Ship four manifests:

- **Builder** - scenario validation, layer authoring, attribute tables, and loader warnings.
- **Planner** - schedule, objective/locks, run control, live KPIs, and reports.
- **Analyst** - maps, KPIs, reports, and comparison; no editing.
- **Reviewer** - a deliberately small read-only skin: schedule, KPI table, report tree, provenance.

## 8. Editable fields

The first release edits only fields that can round-trip through the existing loader:

- `objective_weights` in `scenario.yaml`;
- `locked_assignments` in `scenario.yaml`;
- after P11, `hauling.driver_policy` and contractor preferred workloads.

Every PUT writes a temporary YAML, loads it with `load_scenario`, and only then replaces the file.
An invalid edit is refused with the loader's own message. There is no parallel JSON model and no
UI-only state.

Scenario editing must preserve comments and formatting where practical. If a round-trip would
destroy comments, the service must either use a comment-preserving writer or restrict editing to a
separate overlay file that the CLI has an explicit `--overlay` flag for. That decision belongs in
P12.1, before any editor is exposed.

## 9. Security and deployment

- Default bind `127.0.0.1`. A non-loopback bind is refused unless `--allow-remote` is passed.
- No authentication in the first cut. The service is a local analyst tool until there is an auth
  story; the docs say so explicitly.
- Run roots are allowlisted. Path traversal outside a configured root is rejected.
- The service never imports the optimizer into the request process. A run is a subprocess with a
  timeout and a bounded output directory.
- The assistant is opt-in (`--allow-agent`) and calls the installed `opencode` CLI with the same
  model/working-directory controls as WS4. It has the service user's shell; the docs must say that
  plainly.
- No provider keys in the service. The CLI owns authentication.
- Uploads are out of scope. Scenario files are read from configured roots.

## 10. Packaging and performance

- `fhops[web]` adds `fastapi`, `uvicorn`, and the MapLibre static assets. The core install and CLI
  remain unchanged for a user who does not install the extra.
- Package data includes `src/fhops/web/static/*`, `src/fhops/web/skins/*`, and the MapLibre vendor
  licence. The wheel must be smoke-tested in a clean venv.
- Serve static assets with cache headers and a build/version query string, as WS4 does.
- Map payloads are bounded by viewport and zoom level. The first release may return all features
  for small cases; a viewport/bbox + level-of-detail endpoint is a follow-up if a real management
  unit demands it. P12.3 should measure the payload size and record the threshold.
- The SPA must remain usable with no build step: plain modules, no bundler, no Node in CI.

## 11. Testing

- API contract tests with `fastapi.testclient` over a small fixture scenario and run.
- Scenario PUT round-trip: edit, reload through `load_scenario`, and compare the effective values.
- Skin loader: unknown panel/layer/action is refused by name; `read_only` cannot mutate.
- Map endpoint: a requested layer exists in the `FeatureCollection`; a missing artefact is a 404
  naming the file, not an empty map.
- SSE: live events are parseable; a finished run returns 204; a client disconnect does not leak a
  worker.
- Run control: `POST /api/runs` invokes the CLI with the expected arguments in a fake-run test.
- Security: non-loopback bind is refused without `--allow-remote`; path traversal is rejected.
- Static smoke: the SPA shell and module load; browser automation is optional and must not gate the
  core install.
- Package smoke: build a wheel, install `fhops[web]` in a clean venv, start the service, and hit
  `/api/health` and `/`.
- Regression: existing CLI workflows and scenario loading unchanged without the extra.

## 12. Child tasks

- **#178 P12.1** Service skeleton, run manifest, artefact discovery, and CLI entry.
- **#179 P12.2** Read-only API, SPA shell, and skin loader.
- **#180 P12.3** Map, layer tree, and day/period control.
- **#181 P12.4** Schedule/Gantt, KPI, report, and comparison panels.
- **#182 P12.5** Live runs, SSE, and run control.
- **#183 P12.6** Editable objective/locks, assistant, packaging, security, docs, and close-out.

The detailed issue bodies carry the subtasks, acceptance criteria, and verification commands.

## 13. Acceptance criteria for the phase

- `pip install fhops[web]` then `fhops web --runs <dir>` serves the SPA at `/` and a documented API.
- A completed run loads with its scenario, map, schedule, KPIs, and reports; every displayed value
  comes from a file the CLI wrote.
- The day/period control moves the map and schedule through the horizon.
- The map draws blocks, treatments, machines, roads, mills/sort yards, and (after P11) haul routes,
  with a legend and feature selection.
- Two runs compare by map difference and KPI delta.
- A live run streams progress and updates the KPIs; a finished run returns 204 on `/events`.
- The four skins load from manifests; the reviewer skin cannot edit anything.
- An objective/lock edit round-trips through the loader and is refused with the loader's message
  when invalid.
- The service refuses a non-loopback bind without `--allow-remote`; the assistant is off by default.
- The core install and CLI are unchanged for a user who does not install the extra.
- All FHOPS gates are green, including the wheel/extra smoke test.

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The web layer becomes a second model or drifts from the CLI. | Artefact-only reads; start runs through the CLI subprocess; no KPI recomputation in the browser. |
| Scenario editing destroys comments or creates invalid YAML. | Round-trip through `load_scenario`; use a comment-preserving writer or an explicit overlay file. |
| Map payloads are too large for real management units. | Measure; add viewport/zoom LOD and a tile cache only when the threshold is crossed. |
| FastAPI/uvicorn/MapLibre bloat the core install. | Optional extra; package-data smoke test; core CLI tests do not import web modules. |
| SSE through a notebook/proxy buffers or reconnects forever. | `--root-path`, relative URLs, 204 for finished runs, 10-minute reconnect, proxy guidance. |
| The assistant has shell access. | Off by default; explicit `--allow-agent`; local-only; documented as an operator feature. |
| Authentication is absent. | Loopback default; refuse remote bind without an explicit flag; state the limit. |
| The web UI is built before stable artefacts exist. | P12.1 freezes the artefact contract; P12.2 reads only what exists; unknown files are reported, not invented. |
| P11 hauling outputs change while P12 is built. | Define stable file names in P11.5; P12 treats missing layers as unavailable with a named follow-up. |

## 15. Out-of-scope follow-ups to record, not start

- Authentication, user accounts, and multi-tenant hosting.
- Real-time collaborative editing.
- Full GIS editing, 3D, and field data collection.
- Cloud job orchestration.
- A second client (desktop/mobile) or a React/Svelte rewrite.
- Embedding the Sphinx site inside the app.
