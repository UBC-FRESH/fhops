# P12 close-out — FHOPS Web Application (WS4-style)

Date: 2026-10-25
Parent issue: #171
Phase branch: `feature/p12-web-ui`
Evidence commit: `5b1dfa3` (P12.6 code/docs); this report is committed immediately after it.
Pull request: #186 (draft phase PR)

## Outcome

P12 delivers an optional browser surface over the artefacts the FHOPS CLI writes. It is one
FastAPI service and one vanilla ES module SPA with three planning lenses:

- **Operational:** shift-level machine/crew Gantt, assignments, playback, KPIs, reports, objective
  weights and schedule locks, and live CLI runs.
- **Hauling:** Ghotb-derived Phase I flows/truckloads, Phase II/III truck/loader schedule, yard
  inventory, contractor workload, driver policy/contractor preferences, and live runs.
- **Tactical–operational:** TOPM-style period harvest decisions, production, product flows,
  facility demand/inventory, roads, silviculture, fleet, demand-envelope overlays, and live runs.

The service remains a reader for artefacts: it imports no optimizer into the request process. Live
runs are allowlisted CLI subprocesses; scenario edits round-trip through the existing loader; tactical
edits are overlays and never rewrite the base bundle.

## Delivered child issues

| Issue | Scope | Evidence |
|---:|---|---|
| #178 P12.1 | Service skeleton, `run.json`, three-domain discovery, `fhops web`/`manifest`/`discover` | `6fb8533` |
| #179 P12.2 | Read-only API, SPA shell, skin loader, four skins | `c175f81` |
| #180 P12.3 | Map, layer tree, day/shift/period control, MapLibre + SVG fallback | `01f3d41`, fixes through `44a4edf` |
| #181 P12.4 | Domain Gantt/tables, KPI cards, reports, comparison | `fe2d9f7` |
| #182 P12.5 | Full live-run allowlist, domain-tagged SSE, pause/resume/stop | `c076d89`, `8cd5a20` |
| #183 P12.6 | Editing, assistant, packaging, security, docs, close-out | `5b1dfa3` |

P11.7 marine/barge hauling was merged from `main` before P12.5 (`3bb2a3c`); hauling preserves the
marine fields and layers.

## Acceptance evidence

- **Operational run:** the demo loads assignments, shift Gantt, KPIs, reports, comparison, and a
  MapLibre/SVG map; values come from the run's files.
- **Hauling run:** flows, truckloads, truck/loader Gantt, yard inventory, contractor workload, truck
  and loader tables, KPIs, and reports load from `haul_*` artefacts.
- **Tactical run:** period Gantt, harvest/production/flows/inventory/purchases/roads/silviculture/
  fleet tables, KPIs, and reports load from the tactical bundle.
- **Live runs:** operational `solve-heur`/`solve-ils`/`solve-tabu`/`solve-mip-operational`,
  playback, rolling horizon; hauling `haul plan`/`schedule`/`solve`; tactical solve/report. Demo runs
  completed through the API, SSE carried `domain`, `window`, objective/KPI, and assignment events,
  and finished `/events` returned 204.
- **Editing:** objective/lock edits validate through `load_scenario`; a negative weight was refused
  with the loader message and the file was unchanged. A UI objective save preserved an existing
  YAML comment. Tactical demand overlays validated and produced a derived scenario while the base
  file stayed byte-identical.
- **Skins:** `operational-planner`, `hauling-planner`, `tactical-planner`, and `reviewer` load.
  Reviewer has no Scenario/Run tab and no mutating action; `read_only` validation is tested.
- **Assistant:** off by default (`/api/agent` 403, panel hidden). With `--allow-agent`, the endpoint
  calls only the configured command prefix and returns its response; no shell is used.
- **Packaging:** a wheel built with hatchling contains the SPA, MapLibre vendor assets, licence, and
  four skins. A clean venv `pip install 'fhops[web]'` served `/api/health` and `/` with `?v=9`. A
  core-only clean venv ran `fhops --help` with no FastAPI/uvicorn installed.
- **Security:** non-loopback bind is refused without `--allow-remote`; static/scenario traversal is
  rejected; scenario and run inputs are allowlisted to the workspace/run roots; assistant prompts are
  length-bounded.

## Verification commands

```bash
PYTHONPATH=src pytest -q tests/web                  # 50 passed
pytest -q                                           # only the two pre-existing HiGHS failures
ruff format --check src tests
ruff check src tests
mypy src
PATH=/tmp/opencode/pandoc-3.1.3/bin:$PATH sphinx-build -b html docs /tmp/opencode/fhops-p12-docs -W
node --check src/fhops/web/static/app.js
```

Headless DOM harness evidence (`/tmp/opencode/jsdom-test`):
- Map/layer/time controls and run panels render with no JS page errors.
- All three Scenario panels render; operational objective save reaches `Objective saved.` and the
  scenario reloads through the loader.
- Reviewer has no Scenario/Run tabs; assistant is hidden without `--allow-agent`.

Full `pytest` retains the two pre-existing HiGHS option-error failures:
`tests/model/test_milp_driver_robustness.py::test_highs_option_error_is_reported_as_solver_error`
and `tests/test_legacy_mip_driver.py::test_highs_option_error_is_reported_as_solver_error[highs-exec]`.
They are unrelated to P12 and were present before the phase.

## Deviations and limits

- **Skin naming:** the plan's generic `builder/planner/analyst/reviewer` names were superseded by the
  2026-10-25 domain clarification: `operational-planner`, `hauling-planner`, `tactical-planner`,
  `reviewer`. The domain manifests carry the same role coverage.
- **Hauling edit scope:** inline `hauling:` sections are editable. Scenarios that store hauling in a
  separate YAML file return a named 400; editing that file directly is a follow-up.
- **Tactical run wiring:** the editor writes a validated overlay and a derived merged scenario; the
  UI passes the derived path to the Run tab. Direct `--overlay` plumbing on
  `plan tactical-operational` remains a follow-up because the CLI already exposes `scenario overlay`.
- **Comment preservation:** top-level operational/hauling sections are replaced in place, preserving
  comments elsewhere. Comments inside the edited section may be normalized.
- **No authentication:** the service is a local analyst tool. Remote binds require an explicit flag
  and still have no login.
- **Browser automation:** unavailable in this environment; verification used the TestClient, the
  headless jsdom harness, and the live demo.

## Follow-ups (not part of P12)

- Add `--overlay` to tactical solve/report commands for a one-command overlay run.
- Add a comment-preserving nested writer for separate hauling YAML files.
- Add authentication and multi-user run scheduling before any shared deployment.
- Add viewport/zoom level-of-detail if a management unit makes map payloads too large.
