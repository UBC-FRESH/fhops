# Phase 21 compliance audit

Date: 2026-11-01
Repository: `/home/gep/projects/fhops-scenario-studio`
Phase branch: `feature/p21-scenario-studio`
Parent issue: #318
Child issues: #319–#322

## Policy references

This audit follows:

- `ubc-fresh-dev-workflow/AGENTS.md`
- `docs/reference/workflow-model.rst`
- `docs/reference/git-conventions.rst`
- `docs/reference/quality-gates.rst`
- `docs/reference/phase-closeout.rst`
- `docs/agents/session-protocol.rst`

## Current compliance state

### Compliant now

- The Studio is treated as a separate feature worktree, not as changes to the public demo checkout.
- Project edits do not mutate `sandbox/cases`.
- A phase parent issue exists (#318) with linked child issues (#319–#322).
- The phase branch is now named `feature/p21-scenario-studio`.
- `ROADMAP.md`, `CHANGE_LOG.md`, and `notes/` are updated with the implementation.
- Targeted verification is recorded rather than claiming an unrun full dashboard.

### Historical deviations

1. **Implementation started before the issue tree existed.**
   - The Studio editor, 3D editor, retention, terrain, and routing work was developed before #318–#322 were created.
   - The issue tree now exists; the history is not rewritten.

2. **Branch base.**
   - `feature/p21-scenario-studio` was created from the public-demo line, not from `main`.
   - Rebasing after the fact would rewrite a long branch and risks unrelated public-demo changes. The branch is therefore a development branch until review decides the merge base.

3. **Branch name.**
   - The branch was initially `phase21-scenario-studio` and was renamed to `feature/p21-scenario-studio` at commit `cfa68e39`.

4. **No per-child pull requests or closeout report yet.**
   - The work is on one phase branch. Child PRs were not opened.
   - The phase PR and closeout report remain pending.
   - No tag, release, merge, or branch-protection change has been made.

5. **Full dashboard not run.**
   - The UBC-FRESH workflow dashboard is not present in this repository.
   - Targeted `ruff`, `pytest`, Python compile, and JavaScript syntax checks were run.
   - `mypy` was unavailable in the FHOPS virtual environment during this work.
   - No CI run exists on the phase branch yet.

## Required before phase closeout

- Open a phase pull request against the approved base.
- Run the full repository gates and record the result.
- Resolve the branch-base deviation or document an approved alternative.
- Close #319–#322 with evidence or record why they remain open.
- Write the phase closeout report and request maintainer approval.
- Do not merge or tag without approval.

## Live demo deployment

The public demo checkout is a separate branch/worktree. Updating it is a deployment action requested by the maintainer, not part of Phase 21's child implementation history.
