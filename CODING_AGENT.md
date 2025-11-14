# Coding Agent Operating Notes

These notes govern day-to-day execution for Codex (and collaborators) working in FHOPS. Follow
them for every milestone, feature branch, or pull request.

## Command cadence (run before handing work back)
1. `ruff format src tests`
2. `ruff check src tests`
3. `mypy src`
4. `pytest`
5. `pre-commit run --all-files` *(after `pre-commit install`)*
6. `sphinx-build -b html docs _build/html -W`

Record the exact commands executed in the current `CHANGE_LOG.md` entry. Address warnings
instead of suppressing them; escalate only if consensus is reached with maintainers.

## Planning hygiene
- Update `FHOPS_ROADMAP.md` phase checkboxes and "Detailed Next Steps" entries whenever work
  starts, pauses, or completes.
- Keep the relevant note under `notes/` in sync with actionable tasks, tests, documentation, and
  open questions. Treat these as living documents—never let TODOs drift into memory.
- **Every change set must be recorded in `CHANGE_LOG.md` immediately after implementation.**
  Summaries should mirror status updates shared with maintainers; do not skip this step.
- Before proposing new work, re-read the latest roadmap/notes/changelog entries to avoid jumping
  the queue or rehashing solved problems.

## Code & documentation expectations
- Prefer small, reviewable commits aligned with roadmap tasks.
- When behaviour changes, update Sphinx docs, README, or CLI help in the same change set.
- Guard against regressions with targeted tests; add fixtures/examples as needed and document
  them under the relevant note.
- Keep PR descriptions concise but linked to roadmap phases and note sections for traceability.

## Release workflow (RC prep)
- Packaging uses Hatch (mirroring the ws3 repo). Keep ``pyproject.toml`` / ``hatch.toml`` in sync
  and use ``hatch build`` for local validation before any publish step.
- Follow `notes/release_candidate_prep.md` for the current RC checklist (version bump, wheel/sdist
  smoke tests, release notes, CI tag jobs). Update that note and the roadmap after each milestone.
- Release day cadence: bump version, regenerate changelog entry, `hatch build`, smoke install in a
  clean venv, tag (`git tag -s vX.Y.Z`), push tag, then publish (TestPyPI first, PyPI second if
  applicable). Document the exact commands in the changelog.

## Collaboration guidelines
- Flag blockers or scope shifts by opening a dedicated section in the pertinent note and linking
  it from the next changelog entry.
- Use draft PRs or issue threads to capture design discussion; sync the outcome back into notes
  and the roadmap to keep the planning artefacts authoritative.
