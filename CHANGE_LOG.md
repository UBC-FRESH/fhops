# Development Change Log

## 2025-11-07 — Planning Framework Bootstrap
- Established structured roadmap (`FHOPS_ROADMAP.md`) with phase tracking and detailed next steps.
- Authored coding agent runbook (`CODING_AGENT.md`) aligning workflow commands with Nemora practices.
- Seeded notes directory, backlog tracker, and Sphinx/RTD scaffolding to mirror the Nemora planning stack.
- Added `.readthedocs.yaml`, `docs/requirements.txt`, and a GitHub Actions workflow executing the full agent command suite.
- Refined `.readthedocs.yaml` using the Nemora template while still installing project extras for doc builds.
- Introduced `.pre-commit-config.yaml` to enforce lint/type standards via hooks.
- Bootstrapped modular package skeletons and migrated scenario contracts/loaders into `fhops.scenario`, leaving shims (`fhops.core.types`, `fhops.data.loaders`) with deprecation warnings.
- Commands executed:
  - `ruff format src tests` (clean run locally; reverted formatting edits to keep scope focused on planning work).
  - `ruff check src tests` *(fails — pre-existing import ordering and typing updates required across legacy modules).*
  - `mypy src` *(fails — missing third-party stubs and legacy type issues in core/solver modules).*
  - `pytest` *(fails — existing regression suite depends on Nemora fixtures under `tmp/` and currently errors when reading reference CSVs).*
  - `pre-commit run --all-files` *(fails in `ruff` stage for the same lint issues noted above).*
  - `sphinx-build -b html docs _build/html -W` *(passes; docs scaffold builds cleanly).*
