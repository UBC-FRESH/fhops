# Phase 21 issue tree

Status: local development; GitHub issues not yet created in this worktree.

If GitHub CLI is available, create the parent and children with the commands
below, then replace `TBD` in `notes/phase21_scenario_studio.md` and
`ROADMAP.md`.

## Parent

Title: `Phase 21 — Scenario Studio`

```bash
gh issue create \
  --title "Phase 21 — Scenario Studio" \
  --body "Interactive scenario editor over immutable Tree Lab cases. See notes/phase21_scenario_studio.md. Branch: phase21-scenario-studio." \
  --label enhancement
```

## Children

1. `P21.1 — Studio project schema and editor shell`
2. `P21.2 — Boundary, landing, road, retention, and machine editor`
3. `P21.3 — Derived-case materialization and edited-scenario runs`
4. `P21.4 — Visual terrain/obstacle tools and simulation hook`
5. `P21.5 — 3D editor integration and replay preview`
6. `P21.6 — Operator policy simulation integration`
7. `P21.7 — Studio tests, docs, and closeout`

Each child should link back to the parent and remain on the
`phase21-scenario-studio` branch until the phase is reviewed.
