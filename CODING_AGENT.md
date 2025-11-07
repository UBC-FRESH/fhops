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
- Append a dated summary to `CHANGE_LOG.md` at the end of each deliverable, mirroring the report
  sent to the user or maintainer.
- Before proposing new work, re-read the latest roadmap/notes/changelog entries to avoid jumping
  the queue or rehashing solved problems.

## Code & documentation expectations
- Prefer small, reviewable commits aligned with roadmap tasks.
- When behaviour changes, update Sphinx docs, README, or CLI help in the same change set.
- Guard against regressions with targeted tests; add fixtures/examples as needed and document
  them under the relevant note.
- Keep PR descriptions concise but linked to roadmap phases and note sections for traceability.

## Collaboration guidelines
- Flag blockers or scope shifts by opening a dedicated section in the pertinent note and linking
  it from the next changelog entry.
- Use draft PRs or issue threads to capture design discussion; sync the outcome back into notes
  and the roadmap to keep the planning artefacts authoritative.
