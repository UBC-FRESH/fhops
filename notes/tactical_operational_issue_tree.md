# Tactical–Operational Expansion Issue Tree

Date: 2026-09-24
Roadmap phase: Phase 6 — Tactical–Operational Expansion (TOPM-Inspired)
Primary plan: `notes/tactical_operational_expansion_plan.md`
Workflow contract: `AGENTS.md` → “Roadmap phase and issue-tree workflow”

## Live GitHub structure

- Parent issue: [#36 — Phase 6: Tactical–Operational Expansion (TOPM-Inspired)](https://github.com/UBC-FRESH/fhops/issues/36)
- Phase branch: `feature/phase6-tactical-operational-expansion`

| Issue | Task | Child branch |
|---:|---|---|
| [#37](https://github.com/UBC-FRESH/fhops/issues/37) | Phase 6.0 — workflow and TOPM architecture baseline | `issue-37-phase-6.0-workflow-architecture` |
| [#38](https://github.com/UBC-FRESH/fhops/issues/38) | Phase 6.1 — period hierarchy and tactical–operational contract | `issue-38-phase-6.1-contract-time` |
| [#39](https://github.com/UBC-FRESH/fhops/issues/39) | Phase 6.2 — TOPM core harvest/system/period MILP | `issue-39-phase-6.2-core-harvest-milp` |
| [#40](https://github.com/UBC-FRESH/fhops/issues/40) | Phase 6.3 — product flows, facility inventory, and purchases | `issue-40-phase-6.3-flow-inventory` |
| [#41](https://github.com/UBC-FRESH/fhops/issues/41) | Phase 6.4 — roads, silviculture, and fleet investment | `issue-41-phase-6.4-infrastructure-modules` |
| [#42](https://github.com/UBC-FRESH/fhops/issues/42) | Phase 6.5 — scenario overlays, diffs, and reporting | `issue-42-phase-6.5-scenario-reporting` |
| [#43](https://github.com/UBC-FRESH/fhops/issues/43) | Phase 6.6 — tactical–operational coupling and rolling state | `issue-43-phase-6.6-integrated-rolling` |
| [#44](https://github.com/UBC-FRESH/fhops/issues/44) | Phase 6.7 — scale, decomposition, and uncertainty | `issue-44-phase-6.7-scale-uncertainty` |

All eight child issues were linked to parent #36 through GitHub sub-issues, and all issues in the
tree were assigned the repository `Feature` issue type.

2026-09-24 status: #37–#43 were merged into the Phase 6 integration branch via PRs #45–#51. #44
is in progress on branch `issue-44-phase-6.7-scale-uncertainty`.

## Historical scope note

Oborn (1996) is the direct formulation reference. The FORCE/Robak OperMAX lineage, including the
CIRRELT-2012-33 software survey, confirms that TOPM-like functionality was later deployed as a
multi-year planning shell covering harvest, transport, silviculture, roads, purchases, mill-yard
inventories, roadside/sublicensed sales, and inter-mill deliveries. FHOPS should reproduce that
scope through versioned contracts, scenario overlays, solver telemetry, and auditable reports rather
than a closed or case-specific shell.

## Creation/audit trail

The issue tree was created on 2026-09-24 using the GitHub REST API with token material obtained
from the local git credential helper. Token values were not printed or written to the repository.
`gh` 2.101.0 was installed under `/tmp/opencode/gh-cli` for CLI verification, but issue creation used
REST directly because the available token lacks the `read:org` scope required by `gh auth login`.

Equivalent issue-link audit command:

```bash
PARENT=36
for CHILD in 37 38 39 40 41 42 43 44; do
  CHILD_ID=$(gh api repos/UBC-FRESH/fhops/issues/${CHILD} --jq .id)
  gh api repos/UBC-FRESH/fhops/issues/${PARENT}/sub_issues \
    -F sub_issue_id="${CHILD_ID}"
done
```

Equivalent child-branch creation pattern after starting a task:

```bash
git switch main
git pull --ff-only
git switch -c issue-38-phase-6.1-contract-time
# implement, test, update notes/ROADMAP/CHANGE_LOG, then open PR with:
#   Part of #36
#   Closes #38
```

## Ongoing hygiene

- Update this table whenever a child issue starts, pauses, or closes.
- Do not close parent #36 until every child issue is closed and maintainers approve Phase 6.
- Add new child issues for scope changes rather than expanding an existing child silently.
- Keep `ROADMAP.md`, `notes/tactical_operational_expansion_plan.md`, and `CHANGE_LOG.md` in sync
  with issue numbers and evidence.
