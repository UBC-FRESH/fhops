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
- **Docstrings**:
  - Every public module/class/function must have a descriptive docstring that follows the
    project-wide NumPy style. Write a one-sentence summary line, then add ``Parameters`` /
    ``Returns`` / ``Raises`` / ``Notes`` sections (omit empty sections). Always describe **every**
    public argument with units, accepted ranges, defaults, and side-effects. When a parameter is a
    mapping or dataclass, spell out the expected keys/fields.
  - Cite provenance (FERIC/FPInnovations study IDs, TN/TR numbers, academic publications) so the
    rendered API docs explain where each regression originates. Note any assumptions (e.g., BC-only
    slope envelopes, salvage-mode defaults, CPI base year).
  - Detail return payloads: list dataclass attributes, tuple ordering, DataFrame schemas, and any
    telemetry side effects. If a helper writes logs or mutates inputs, state it explicitly.
  - Include short ``Examples`` snippets when the workflow spans multiple steps (scenario →
    optimiser → evaluator) or when CLI helpers require a sequence of flags.
  - When validation clamps or coerces inputs, document the rule (e.g., “payload multiplier is
    clipped to > 0 and ≤ 1.0”). This keeps Sphinx readers aligned with the runtime behaviour.
  - Module docstrings must explain *why* the module exists (e.g., CLI entry point, Pyomo builder,
    playback adapter) and cite the datasets or publications behind productivity/costing helpers.
  - Treat docstrings as part of the contract: describe return schemas for dataclasses, tuples,
    DataFrames, and generators; call out deterministic vs stochastic behaviour; include short code
    snippets when they clarify multi-step flows (scenario → optimiser → evaluator, etc.).
  - When updating or adding functionality, keep docstrings, ``docs/api`` pages, and CLI reference
    text in sync. Sphinx consumes these docstrings verbatim, so run ``sphinx-build -b html docs
    _build/html -W`` after every docstring sweep.

## Release workflow (RC prep)
- Packaging uses Hatch (mirroring the ws3 repo). Keep ``pyproject.toml`` / ``hatch.toml`` in sync
  and use ``hatch build`` for local validation before any publish step.
- Follow `notes/release_candidate_prep.md` for the current RC checklist (version bump, wheel/sdist
  smoke tests, release notes, CI tag jobs). Update that note and the roadmap after each milestone.
- Release day cadence: bump version, regenerate changelog entry, `hatch build`, smoke install in a
  clean venv, tag (`git tag -s vX.Y.Z`), push tag, then publish (TestPyPI first, PyPI second if
  applicable). Version source lives at `src/fhops/__init__.__version__` (pyproject uses Hatch's
  dynamic version hook). Document the exact commands in the changelog.
- GitHub Actions workflow `.github/workflows/release-build.yml` mirrors this process on tags by
  running `hatch run release:build` and uploading `dist/` artifacts; verify the job succeeds before
  publishing to TestPyPI/PyPI.
- TestPyPI/PyPI publishing cadence (Hatch-only):
  1. `hatch clean && hatch build`
  2. `HATCH_INDEX=testpypi hatch publish` (configure `HATCH_INDEX_TESTPYPI_AUTH` or `~/.pypirc`)
  3. Create fresh venv, `pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple fhops`, run smoke commands
  4. `HATCH_INDEX=pypi hatch publish` once verification passes (uses `HATCH_INDEX_PYPI_AUTH`)
  5. Tag release (`git tag -s vX.Y.Z && git push --tags`)

## Collaboration guidelines
- Flag blockers or scope shifts by opening a dedicated section in the pertinent note and linking
  it from the next changelog entry.
- Use draft PRs or issue threads to capture design discussion; sync the outcome back into notes
  and the roadmap to keep the planning artefacts authoritative.
