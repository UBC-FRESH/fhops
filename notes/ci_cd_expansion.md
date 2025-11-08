# CI/CD Expansion Plan

Date: 2025-??-??
Status: Draft — immediate actions in Phase 1.

## Objectives
- Provide consistent automation (GitHub Actions) running the coding agent command suite on pushes and pull requests.
- Add coverage reporting, dependency caching, and optional nightly/regression workflows.
- Prepare future release automation (version bump, packaging, docs updates).

## Near-Term Tasks
- [x] Author CI workflow invoking `ruff format --check`, `ruff check`, `mypy`, `pytest`, `pre-commit`, and Sphinx builds. *(`.github/workflows/ci.yml`)*
- [ ] Configure caching for Python dependencies to keep pipelines fast.
- [ ] Publish status badges in README once workflows stabilise.

## Upcoming Enhancements
- [ ] Add test matrix for multiple Python versions and OS environments.
- [ ] Integrate coverage reporting (Codecov or GitHub summary).
- [ ] Create scheduled workflow for longer regression scenarios.

## Open Questions
- Do we require smoke tests for CLI commands in CI (e.g., `fhops validate` on example scenarios)?
- Should release automation include PyPI publishing or remain manual for now?
