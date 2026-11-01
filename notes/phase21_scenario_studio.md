# Phase 21 — Scenario Studio

Status: in progress
Branch: `p21-demo-integration`
Worktree: `/home/gep/projects/fhops-scenario-studio`
Parent issue: TBD (create from `notes/phase21_issue_tree.md`)

## Purpose

Scenario Studio is an interactive authoring layer over immutable Tree Lab cases.
It lets users move landings, edit block boundaries, mark retention trees, change
machine systems and operator policies, and run the edited scenario without
mutating the source fixtures or the public demo.

The first slice is deliberately a **2D plan editor plus a real simulation run**.
It is not yet a full 3D Minecraft-style terrain editor. The project schema and
tool UI are designed so the 3D terrain/deck/obstacle work can be added without
rewriting project storage.

## First slice implemented

- Separate FastAPI service: `python -m sandbox.studio.app` (default port 8791)
- Immutable case loading from `sandbox/cases/`
- Project storage under `build/studio_projects/`
- Project list, create, load, save, delete, dataset, and JSON export endpoints
- Tree-preserving project overlay
- Editable block boundary polygon and area/stat recomputation
- Editable landing with road snapping
- Editable road polyline
- Tree-level retention marking with a brush
- Retention target field and retained basal-area statistic
- Machine catalog, add/remove machines, and per-machine operator policy presets
- Visual terrain heightfield brush (prototype; simulation hook pending)
- Derived-case materialization:
  - filters trees outside boundary and retained trees
  - applies edited landing
  - applies edited machine system
  - applies feller productivity multiplier for the selected operator policy
- “Run scenario” calls the existing FHOPS Tree Lab runner and returns KPIs
- Undo/redo, fit, pan, zoom, keyboard save and undo
- API and materials smoke tests

## Explicit limitations in this slice

- Terrain edits generate a DEM and are used for route/grade checks; the feller and
  skidder route models remain reference approximations and can reject steep terrain.
- Operator policies map feller, skidder, loader, grade, and processor output
  coefficients; continuous policy-state physics is not modelled.
- Retention clumps are filled polygons and block felling and machine routing;
  stream buffers are authoring geometry, not surveyed hydrology.
- No multi-landing or road-network routing yet.
- No authentication; this is a local development tool.

## Delivered in Phase 21

- 2D and 3D editing pages, including terrain, road, boundary, landing, retention,
  and undo/redo.
- Derived-case materialization with DEM/road handoff, persisted routes, and
  blocked-work warnings.
- Retention clumps and riparian/corridor presets with tree exclusion and routing
  obstacles.
- Operator-policy translation for feller, skidder, loader, grade, and processor.
- 3D replay, run history, KPI comparison, export/import, and Tree Lab promotion.

## Run locally

```bash
cd /home/gep/projects/fhops-scenario-studio
./run_studio.sh
# open http://127.0.0.1:8791/
```

## Follow-ups

See `notes/phase22_followups.md` for processor-specific policy coefficients,
stream-centreline authoring, and closeout corrections.

## Verification

```bash
PYTHONPATH=src:. /home/gep/projects/fhops/.venv/bin/python -m pytest -q tests/studio/test_studio_projects.py
node --check sandbox/studio/static/studio.js
PYTHONPATH=src:. /home/gep/projects/fhops/.venv/bin/python -m py_compile sandbox/studio/app.py sandbox/studio/projects.py
```
