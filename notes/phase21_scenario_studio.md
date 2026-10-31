# Phase 21 — Scenario Studio

Status: in progress  
Branch: `phase21-scenario-studio`  
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

- 2D top-down editor, not yet direct 3D manipulation
- Terrain edits are visual only; they do not yet drive machine routing/grade
- Operator policies are stored for every machine, but only the feller policy is
  currently mapped into the simulation runner
- Retention clumps are tree-level selections; no filled clump polygons yet
- No obstacle or stream tools yet
- No multi-landing or road-network routing yet
- No 3D preview of the derived run yet; the run result panel shows KPIs only
- No authentication; this is a local development tool

## Run locally

```bash
cd /home/gep/projects/fhops-scenario-studio
./run_studio.sh
# open http://127.0.0.1:8791/
```

## Next slices

1. Add a 3D edit/preview pane using the existing tree scene and brush raycasting.
2. Add terrain simulation hook (DEM/heightfield + route grade).
3. Add retention clump polygons, riparian buffers, and no-harvest obstacles.
4. Add machine operator policy coefficients for skidders, processors, and loaders.
5. Add editable road networks, multiple landings, and landing capacity checks.
6. Add a 3D replay preview for the derived run.
7. Add project comparison against the base case and promotion to a game level.

## Verification

```bash
PYTHONPATH=src:. /home/gep/projects/fhops/.venv/bin/python -m pytest -q tests/studio/test_studio_projects.py
node --check sandbox/studio/static/studio.js
PYTHONPATH=src:. /home/gep/projects/fhops/.venv/bin/python -m py_compile sandbox/studio/app.py sandbox/studio/projects.py
```
