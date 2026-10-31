# FHOPS Tree Lab — Agent Handoff

Your agent is looking in the right repo but the wrong branch/place. **Tree Lab is not a separate FHOPS package and is not on `main`.** It is an unmerged sandbox application built on top of FHOPS.

## Exact locations

### Tree Lab app

```text
/home/gep/projects/fhops-public-demo
branch: public-demo
commit: 7c66ce9f
```

Key files:

```text
sandbox/tree_lab/app.py          FastAPI service
sandbox/tree_lab/runner.py       calls `fhops tree system` + `fhops tree scene`
sandbox/tree_lab/cases.py        case discovery/validation
sandbox/tree_lab/static/index.html
sandbox/tree_lab/static/app.js
sandbox/tree_lab/static/viewer.js   3D machine/deck/truck viewer
sandbox/cases/                   demo cases
sandbox/runs/                    generated run assets
```

Older/source Tree Lab worktree:

```text
/home/gep/projects/fhops-tree-lab
branch: feature/phase20-cable-yarder
commit: 02ee6e21
```

### Scenario Studio worktree

```text
/home/gep/projects/fhops-scenario-studio
branch: phase21-scenario-studio
commit: 4a96f9a6
```

Key files:

```text
sandbox/studio/app.py
sandbox/studio/projects.py
sandbox/studio/static/studio.html
sandbox/studio/static/studio.js
sandbox/studio/static/studio_replay.html
sandbox/studio/static/studio_replay.js
```

Studio projects and runs:

```text
build/studio_projects/<project_id>/project.json
build/studio_projects/<project_id>/derived_cases/
build/studio_projects/<project_id>/runs/<run_id>/
```

### Handoff document

```text
/home/gep/projects/fhops-tree-lab-handoff.md
```

That document describes the Tree Lab mission, architecture, case layout, 3D viewer, agent workflow, and bootstrap commands.

## What your agent is missing

It is technically correct that there is **no separate “tree lab” package** in the released FHOPS distribution. The multi-machine 4D layer is here:

- `fhops tree system` → multi-machine event simulation
- `fhops tree scene` → deterministic glTF/GLB + scene assets
- `sandbox/tree_lab` → web runner, 4D timeline, machine/truck/deck animation
- `sandbox/studio` → interactive scenario editing and derived runs

So the agent should not run `fhops tree simulate` alone. It should use `fhops tree system`, then `fhops tree scene`, then the Tree Lab viewer.

## Verify from the agent shell

```bash
cd /home/gep/projects/fhops-public-demo
git branch --show-current
ls sandbox/tree_lab
ls sandbox/cases
ls sandbox/runs

cd /home/gep/projects/fhops-scenario-studio
git branch --show-current
ls sandbox/studio
```

Run Tree Lab locally:

```bash
cd /home/gep/projects/fhops-public-demo
PYTHONPATH=src:. /home/gep/projects/fhops/.venv/bin/python \
  -m sandbox.tree_lab.app --port 8811
```

Run Studio locally:

```bash
cd /home/gep/projects/fhops-scenario-studio
./run_studio.sh
# http://127.0.0.1:8791/
```

## Important JupyterHub caveat

These are **local worktree branches**, not branches on `UBC-FRESH/fhops`:

- `public-demo`
- `phase21-scenario-studio`
- `feature/phase20-cable-yarder`

If JupyterHub18 is a different container, those paths may not be visible. The code needs to be transferred as a worktree archive or git bundle, or the branches need to be pushed to a shared remote first. The agent will not find Tree Lab by cloning `UBC-FRESH/fhops main`.

## Live public endpoints

Tree Lab:

```text
https://fhops.01101.dev/sandbox-v20261031i/
```

Studio:

```text
https://fresh01.01101.dev/studio/
```

Studio 3D replay:

```text
https://fresh01.01101.dev/studio/replay?project=<project_id>&run=<run_id>
```

The `/replay?...` URL now redirects to the Studio replay route.
