# Release Candidate Prep Plan

Date: 2025-11-16
Status: Active — v1.0.0 GA preflight in progress for SoftwareX submission.

## Objectives
- Freeze scope and polish docs/install instructions for the first FHOPS release candidate.
- Adopt Hatch for packaging/publishing (mirroring ws3 workflows) and ensure PyPI metadata is accurate.
- Produce changelog/release notes, version bumps, and verification checklists before tagging.
- Promote the public package from the current `1.0.0a2` prerelease line to a clean `1.0.0`
  GA release that SoftwareX reviewers can install and cite.

## Tasks
1. **Versioning & Hatch wiring**
   - [x] Add ``hatch.toml``/pyproject updates (build-system, project metadata, scripts, dependencies).
   - [x] Define version source (pyproject now uses ``[tool.hatch.version]`` pointing at ``src/fhops/__init__.__version__``; bump workflow = edit that constant + changelog).
   - [x] Configure Hatch environments/custom commands for lint/test/release parity with ws3.
   - [x] Bump final GA version metadata to ``1.0.0`` for SoftwareX submission.
     - 2026-06-14: issue #16 updates ``src/fhops/__init__.py``, ``tests/test_import.py``,
       final release notes, README/overview install wording, and the release playbook.
2. **Packaging QA**
   - [x] ``hatch build`` wheel/sdist locally and inspect contents (license, data files, examples).
     - Built `dist/fhops-0.0.2*` via `hatch build`; artifacts include CLI entry points and docs assets.
     - 2026-06-14: issue #18 rebuilt final `fhops-1.0.0` artifacts. `twine check`
       passes; the wheel contains package code plus bundled runtime `fhops/data/**` and excludes
       `docs/`, `docs/softwarex/`, `examples/`, `notes/`, and `reference-documents/`. After the
       copyright review, full-text reference PDFs/snapshots/extracts moved to the private
       `UBC-FRESH/fhops-reference-docs` submodule; the public repo keeps the Markdown
       bibliography/provenance notes and the Sphinx `reference/source_bibliography` page points
       readers to them. The sdist excludes `docs/references/`, `docs/softwarex/reference/`,
       `notes/`, and `reference-documents/` while preserving runtime JSON under `data/**`.
   - [x] Smoke install from the built wheel (fresh venv) and run ``fhops --help`` plus a tiny7 solve.
     - Created `.venv-hatch-smoke`, installed the wheel, and ran `fhops --help` + `fhops validate examples/tiny7/scenario.yaml` successfully.
     - 2026-06-14: issue #18 installed `dist/fhops-1.0.0-py3-none-any.whl` into
       `tmp/v100-wheel-smoke` and ran `fhops --help`, `fhops validate
       examples/tiny7/scenario.yaml`, a 25-iteration tiny7 `solve-heur`, and `fhops evaluate
       --assignments` successfully. The first smoke pass exposed missing `click`/`PyYAML`
       metadata and unbundled runtime JSON; both are fixed in the branch.
   - [x] Draft ``HATCH_INDEX=testpypi hatch publish`` dry-run instructions (see Section 7).
3. **Docs & README polish**
   - [x] Tighten README quickstart for pip install + hatch workflows (see README Installation).
   - [x] Ensure docs landing page highlights versioned install instructions (docs/overview.rst Installation + Quick demo).
   - [x] Link telemetry dashboards/release notes for transparency (README dashboards + release notes draft).
4. **Release Notes**
   - [x] Summarise Phase 1-3 achievements, telemetry tooling, and new CLI surfaces (see `notes/release_notes_draft.md`).
   - [x] Document breaking changes and migration guidance (schema version, mobilisation config).
   - [x] Add "Known Issues / Next" section pointing to backlog items (agentic tuner, DSS hooks).
   - [x] Publish final GA notes at ``docs/releases/v1.0.0.md``.
   - [x] Align in-repo SoftwareX release metadata/prose with the final ``v1.0.0`` tag and
     PyPI install path.
     - 2026-06-14: issue #17 updates metadata tables, narrative release references, and
       the SoftwareX workspace README synchronization guidance.
5. **Hyperparameter tuning sign-off**
   - [x] Re-run the tuning harness (baseline bundles) with the latest code; see `notes/release_tuning_results.md` and `tmp/release-tuning/` artifacts.
   - [x] Document the improvements (objective delta, runtime, win rate) in release notes and telemetry dashboards.
   - [x] Store the tuned presets/operator weights for reuse in the release tag (see `notes/release_tuned_presets.json`).
6. **Automation**
   - [x] Add GitHub Actions job template for ``hatch build`` verification (triggered on tags) — see `.github/workflows/release-build.yml`.
   - [x] Prepare release checklist in ``AGENTS.md`` (Hatch build/publish cadence documented under Release workflow).
   - [x] Restore green `main` CI before the v1.0.0 version bump/tag.
     - 2026-06-14: issue #15 branch fixes current Ruff formatting drift, modernises `StrEnum`
       lint blockers, and hardens tuner-report subprocess tests so the local lint/type/test gate
       can pass under the release verification environment.
     - 2026-06-14: issue #15 merged via PR #21 after full CI success.
   - [ ] Clean up release automation and public surfaces before the final tag.
     - 2026-06-14: issue #19 records the release-surface audit in
       `notes/release_surface_audit.md`, annotates the confusing `v0.0.1-alpha3` prerelease
       instead of deleting history, fixes the release-build workflow command exposed by
       `workflow_dispatch`, and hardens full analytics artifact collection before a fresh
       manual dashboard run.

7. **Publishing (TestPyPI → PyPI)**
   - [x] Dry run using TestPyPI:
     - ``hatch clean && hatch build``
     - ``HATCH_INDEX=testpypi hatch publish`` (requires ``HATCH_INDEX_TESTPYPI_AUTH`` or ``~/.pypirc``) ✅ 2025-11-15
     - ``python -m venv .venv-testpypi && . .venv-testpypi/bin/activate``
     - ``pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple fhops`` and run smoke commands (`fhops --help`, `fhops validate examples/tiny7/scenario.yaml`) ✅
   - [x] Document environment variables/secrets: PyPI tokens stored via ``~/.pypirc`` or passed directly to ``twine upload`` (see AGENTS.md Release workflow).
   - [ ] After TestPyPI validation, repeat for PyPI using Twine during the release tag: ``python -m twine upload -u __token__ -p 'pypi-…' dist/*``.

## References
- ws3 Hatch workflow: https://github.com/ubc-fresh/ws3
- Packaging guides: Hatch docs, PyPA best practices.
