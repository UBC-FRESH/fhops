# Merge v1.0.1 (operational corrections) into main (1.1.0 tactical extension)

Status: plan, evidence from a trial merge. Date: 2026-10-17.

## Why

`main` (1.1.0a1, the tactical-operational extension) and `v1.0.1` (the operational corrections frozen
for the accepted SoftwareX manuscript) are sibling lines from the common ancestor `d98fd10`. Neither
is an ancestor of the other, and 38 commits of operational corrections on the v1.0.1 line are absent
from `main`. `main`'s operational heuristics are byte-identical to the v1.0.0-era ancestor, so 1.1.0a1
scores a different (pre-1.0.1) problem. This blocks the SA performance work and, more broadly, makes
1.1.0a1 inconsistent with the accepted manuscript.

## Evidence the merge is tractable

Relative to `d98fd10`:

- `main` changed 16 files, almost all new tactical modules (`model/milp/tactical_operational.py`,
  `planning/tactical_operational/*`, `cli/reporting.py`, `cli/scenario.py`, `cli/synthetic.py`).
- `v1.0.1` changed 31 files, the operational corrections (heuristics, operational MILP, rolling,
  sequencing, playback, contract, loaders).
- Only 4 files changed on both lines: `src/fhops/__init__.py`, `cli/main.py`, `cli/planning.py`,
  `planning/__init__.py`.

A trial `git merge feature/phase8-v101-maintenance` into `main` gives **13 conflicts**, small in size:

| File | Conflict hunks | Resolution |
|---|---|---|
| `docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.tex` | 11 | v1.0.1 (the accepted, labelled formulation) |
| `docs/includes/softwarex/fhops_operational_formulation.rst` | 6 | v1.0.1 |
| `docs/softwarex/manuscript/sections/includes/cli_pipeline.tex` | 3 | v1.0.1 |
| `docs/reference/cli.rst`, `docs/includes/softwarex/cli_pipeline.rst` | 2 each | union: v1.0.1 CLI plus main's tactical commands |
| `src/fhops/__init__.py` | 1 | version bump to the new tag |
| `src/fhops/cli/planning.py` | 1 | union: v1.0.1 operational CLI plus main's tactical CLI |
| `tests/test_import.py` | 1 | union |
| `CHANGE_LOG.md`, `README.md`, `docs/overview.rst`, formulation `.md`, `export_docs_assets.py` | 1 each | union |

`src/fhops/cli/main.py` and `src/fhops/planning/__init__.py` auto-merged.

## Version

Recommendation: **1.1.0b1**. The merge stays in the 1.1.0 minor (it adds no capability beyond what
1.1.0a1 announced) but advances the pre-release from alpha to beta, which is the signal that the
operational correctness of 1.0.1 is restored. `1.1.0a2` is the alternative if the team wants to stay
in alpha; `1.2.0a1` overstates the change. After validation, `1.1.0rc1` then `1.1.0`.

## Plan

- Merge `feature/phase8-v101-maintenance` into `main` on a release branch, resolving the 13 conflicts
  as above.
- Run the full gate suite, and in particular the v1.0.1 operational regression tests
  (`tests/initial_state/test_v100_regression.py`, `tests/heuristics/test_objective_exact.py`) together
  with the tactical tests.
- Bump the version to 1.1.0b1, regenerate the affected docs and assets, and write release notes.
- Tag and publish after the maintainer approves the release close-out.

## Consequence for the SA performance work

The SA tuning should start from the merge result (1.1.0b1), not from `main`, so it optimizes the
corrected objective.
