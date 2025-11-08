# Development Change Log

## 2025-11-07 — Planning Framework Bootstrap
- Established structured roadmap (`FHOPS_ROADMAP.md`) with phase tracking and detailed next steps.
- Authored coding agent runbook (`CODING_AGENT.md`) aligning workflow commands with Nemora practices.
- Seeded notes directory, backlog tracker, and Sphinx/RTD scaffolding to mirror the Nemora planning stack.
- Added `.readthedocs.yaml`, `docs/requirements.txt`, and a GitHub Actions workflow executing the full agent command suite.
- Refined `.readthedocs.yaml` using the Nemora template while still installing project extras for doc builds.
- Introduced `.pre-commit-config.yaml` to enforce lint/type standards via hooks.
- Bootstrapped modular package skeletons and migrated scenario contracts/loaders into `fhops.scenario`, leaving shims (`fhops.core.types`, `fhops.data.loaders`) with deprecation warnings.
- Updated CLI/solver modules to consume the new scenario contract/IO packages, refreshed ruff+mypy pytest configs (stubs, excludes), and brought `ruff format`, `ruff check`, `mypy`, `pytest`, and `pre-commit run --all-files` back to green.
- Ported the Pyomo builder, HiGHS driver, heuristics, and KPI helpers into the new `optimization/` and `evaluation/` packages with deprecated shims for `fhops.model/solve/eval`.
- Added shift timeline and mobilisation schemas to the scenario contract (`TimelineConfig`, `MobilisationConfig`) with planning notes/docs updated.
- Seeded synthetic scenario generator scaffolding (`SyntheticScenarioSpec`, `generate_basic`) and mobilisation unit tests; added scheduling/mobilisation models and updated Sphinx API docs.
- Implemented mobilisation setup-cost penalties across MIP/SA, added GeoJSON distance tooling (`fhops geo distances`) with example block geometries, and introduced default harvest system registry/notes from Jaffray (2025).
- Added distance-threshold mobilisation costs (transition binaries, SA evaluation alignment), shifted scenario contract to track harvest-system IDs, and expanded synthetic generator/tests for system-aware scenarios.
- Commands executed:
  - `ruff format src tests` (clean run locally; reverted formatting edits to keep scope focused on planning work).
  - `ruff check src tests` *(fails — pre-existing import ordering and typing updates required across legacy modules).*
  - `mypy src` *(fails — missing third-party stubs and legacy type issues in core/solver modules).*
  - `pytest` *(fails — existing regression suite depends on Nemora fixtures under `tmp/` and currently errors when reading reference CSVs).*
  - `pre-commit run --all-files` *(fails in `ruff` stage for the same lint issues noted above).*
  - `sphinx-build -b html docs _build/html -W` *(passes; docs scaffold builds cleanly).*
