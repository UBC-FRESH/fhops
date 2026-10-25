# Phase close-out report: P11 log hauling and mill delivery (Ghotb decomposition)

Phase: P11 — Log Hauling and Mill Delivery Optimization (Ghotb-Inspired)
Parent issue: #170
Phase branch: `feature/p11-log-hauling`
Pull request: #185 (`feature/p11-log-hauling` into `main`)
Evidence head: `fb7c6ce`
Report commit: this commit (adds this report)
Date: 2026-10-25
Status: queued for approval. Nothing is merged, tagged, released, or changed in repository settings.

## Recommendation

Approve these actions. The agent carries them out in this order and reads back each result. Each
item can be approved or declined on its own.

1. Mark #185 ready for review (it is currently a draft), then squash-merge it into `main` and delete
   the phase branch.

   ```bash
   gh pr ready 185 -R UBC-FRESH/fhops
   gh pr merge 185 -R UBC-FRESH/fhops --squash --delete-branch
   ```

2. Close #170 with a close-out comment that cites the merge commit and this report.

3. Keep the phase branch history out of `main`; the squash commit is the integration record.

Deferred, named for a separate approval (not part of this report):

- A tag or GitHub release for the hauling feature. The package version and release line are a
  separate decision; P11 adds an optional layer and does not itself bump the version.
- PyPI/TestPyPI publication.
- Any change to P12 (#171); it remains queued.

## Objectives and acceptance

- **#172 P11.1 — provenance, contract, and formulation audit. Met.** Optional `hauling:` contract,
  schema `1.1.0` with `1.0.0` compatibility, loader validation, example skeleton, and the
  equation-level audit in `notes/hauling_formulation_audit.md`.
- **#173 P11.2 — Phase I monthly flow MILP and goal programming. Met.** Cost, workload, and
  normalized goal solves; flows, truckloads, yard inventory, roadside inventory, contractor
  workload, and summary printer. Example cost solve is optimal.
- **#174 P11.3 — Phase II daily routing and scheduling MILP. Met, with a stated tractability
  limit.** Continuous-time truck/loader assignment, MTZ routing, loader order, synchronization,
  regular/overtime, `simulate_plan`, and `validate_schedule`. Exact parity on the 9-load synthetic
  case. The exact MIP has no incumbent within 60 s on 10-12 identical-load cases; the SA schedules
  are feasible and validated. This is recorded below and in `notes/reports/p11-validation.md`.
- **#175 P11.4 — SA solution approach, SPT decoder, and calibration. Met.** Route-permutation SA,
  SPT loader order, swap/reversion/insertion, thesis Taguchi defaults, deterministic seeds,
  overtime violation penalty, and a calibration/benchmark script. 9-load objective parity with the
  MIP at 1350.00.
- **#176 P11.5 — FHOPS integration, CLI, reporting, and example case. Met.** Operational and
  tactical bridges, `fhops haul validate|plan|schedule|solve|report`, stable artefact names,
  Markdown report, and a 13-block/3-yard/60-truck scale case.
- **#177 P11.6 — validation, documentation, formulation sync, and close-out. Met.** Canonical
  formulation assets, drift check, parity/scale evidence, docs, and this report.

## Evidence

### Tests and gates

- `PYTHONPATH=src pytest -q tests/hauling` -> **64 passed**.
- Full `PYTHONPATH=src pytest -q` -> only the two pre-existing HiGHS option-error failures remain
  (`tests/model/test_milp_driver_robustness.py`,
  `tests/test_legacy_mip_driver.py`). They are unrelated to hauling and fail on `main` too.
- `ruff format --check src tests scripts/generate_hauling_scale_case.py
  scripts/validate_hauling_parity.py` -> clean.
- `ruff check src tests scripts/...` -> clean.
- `mypy src` -> no issues (137 files).
- `pre-commit run --files <changed files>` -> passed.
- `sphinx-build -b html docs <build> -W` with pandoc 3.1.3 -> build succeeded.
- `python scripts/check_formulation_assets.py` with pandoc 3.1.3 -> formulation assets synchronized.

### CLI evidence

- `fhops haul validate examples/hauling/scenario.yaml` -> valid; supply/demand residuals zero.
- `fhops haul plan examples/hauling/scenario.yaml --out-dir <dir> --time-limit 30` -> Phase I
  optimal, 7 files.
- `fhops haul schedule examples/hauling/scenario.yaml --out-dir <dir> --flow-dir <flow> --day 1
  --solver sa --sa-iters 50` -> feasible; schedule/truck/loader files.
- `fhops haul solve examples/hauling/scenario.yaml --out-dir <dir> --day 1 --solver mip
  --time-limit 30` -> combined summary and 10 files; MIP objective 2992.50.
- `fhops haul report <run>` -> Markdown report.

### Parity and scale evidence

From `notes/reports/p11-validation.md`:

| loads | exact MIP | SA | note |
|---:|---:|---:|---|
| 9 | 1350.00 | 1350.00 | exact objective parity; zero violations |
| 10 | no incumbent in 60 s | 1500.00 | SA feasible, zero violations |
| 11 | no incumbent in 60 s | 1620.00 | SA feasible, zero violations |
| 12 | no incumbent in 60 s | 1770.00 | SA feasible, zero violations |

The scale case (`examples/hauling_scale/`, day 1, 92 loads) returns a Phase I feasible incumbent at
30 s and an SA schedule with zero violation minutes. The exact MIP is not run at that size.

The parity cases are synthetic, thesis-shaped instances (one block/yard, three trucks); they are
not a reproduction of the confidential company data. The thesis reports exact-MIP intractability at
13 loads; our exact model hits that wall earlier on identical-load instances because of fleet and
loader symmetry. Symmetry breaking and an SA-derived MIP start are recorded follow-ups.

### Formulation evidence

- Source: `docs/softwarex/manuscript/sections/includes/fhops_hauling_formulation.md`.
- Generated: `fhops_hauling_formulation.tex` and
  `docs/includes/softwarex/fhops_hauling_formulation.rst`.
- Sphinx page: `docs/reference/hauling_formulation.rst`.
- Drift check: `scripts/check_formulation_assets.py` -> synchronized.

## Workflow compliance

- Parent #170 and children #172-#177 exist and are linked as sub-issues.
- The phase branch `feature/p11-log-hauling` was cut from `main` at `d130fed`; the activation commit
  is `7375e1d`.
- Commits start with the task ID (`P11.1`, `P11.2`, …).
- `ROADMAP.md`, `CHANGE_LOG.md`, `notes/log_hauling_expansion_plan.md`,
  `notes/hauling_formulation_audit.md`, and `notes/log_hauling_issue_tree.md` are in step.
- The phase PR #185 starts with `Part of #170`; it is a draft awaiting this approval.
- The merge, branch deletion, and parent closure are queued here and are not executed.

## CI evidence

- P11.5 head `5143743`: workflow run `40163945291`, `lint-test-docs` **pass** (11m53s).
- P11.6 head `fb7c6ce`: workflow run `TBD`, `lint-test-docs`
  TBD.
- `deploy-history` is skipped on pull-request events by configuration.

## Deviations and risks

1. **Exact MIP tractability.** The exact Phase II model returns no incumbent within 60 s on the
   10-12 identical-load parity cases. The SA schedules are feasible and validated, but the exact
   model is weaker than the thesis's CPLEX results on similar counts. Follow-ups: symmetry breaking
   for identical trucks/loads, a tighter time formulation, and a MIP start from the SA plan.
2. **Scale case overtime.** `examples/hauling_scale/` allows 300 overtime minutes so the synthetic
   day is feasible. It is a stress case, not a thesis-data reproduction.
3. **SA decoder loader assignment.** The SA decoder assigns each load to the fastest loader at its
   location; it does not search loader assignment. The exact MIP does.
4. **Tactical demand spread.** The tactical bridge spreads a period's demand evenly across the
   hauling horizon because the tactical period is coarser than a day. The assumption is warned.
5. **Operational sort split.** The operational bridge uses equal sort shares unless `sort_shares`
   is supplied. The assumption is warned; it is not a product-yield model.
6. **Confidential data.** The thesis company data is not redistributable; no dollar reproduction of
   the case is claimed.
7. **Status mapping.** `maxTimeLimit`/`maxIteration` terminations with an incumbent are reported as
   `feasible`, not `error`; this is what makes the scale run useful.

## Recommended next steps

1. Approve and execute items 1-3 in the Recommendation.
2. After the merge, activate P12 (#171) at #178 (service skeleton, run manifest, artefact discovery).
   The web UI is already designed to read the stable hauling artefacts from P11.5.
3. Defer a version bump/tag/release to a separate maintainer decision.

## Decision

Approve as written, or approve with the changes stated in the review.
