# Release Candidate Prep Plan

Date: 2025-11-16
Status: Draft — drive the v0.x RC process.

## Objectives
- Freeze scope and polish docs/install instructions for the first FHOPS release candidate.
- Adopt Hatch for packaging/publishing (mirroring ws3 workflows) and ensure PyPI metadata is accurate.
- Produce changelog/release notes, version bumps, and verification checklists before tagging.

## Tasks
1. **Versioning & Hatch wiring**
   - [x] Add ``hatch.toml``/pyproject updates (build-system, project metadata, scripts, dependencies).
   - [x] Define version source (pyproject now uses ``[tool.hatch.version]`` pointing at ``src/fhops/__init__.__version__``; bump workflow = edit that constant + changelog).
   - [x] Configure Hatch environments/custom commands for lint/test/release parity with ws3.
2. **Packaging QA**
   - [x] ``hatch build`` wheel/sdist locally and inspect contents (license, data files, examples).
     - Built `dist/fhops-0.0.2*` via `hatch build`; artifacts include CLI entry points and docs assets.
   - [x] Smoke install from the built wheel (fresh venv) and run ``fhops --help`` plus a minitoy solve.
     - Created `.venv-hatch-smoke`, installed the wheel, and ran `fhops --help` + `fhops validate examples/minitoy/scenario.yaml` successfully.
   - [ ] Draft ``hatch publish --repo testpypi`` dry-run instructions (no secrets committed).
3. **Docs & README polish**
   - [ ] Tighten README quickstart for pip install + hatch workflows.
   - [ ] Ensure docs landing page highlights versioned install instructions.
   - [ ] Link telemetry dashboards/release notes for transparency.
4. **Release Notes**
   - [x] Summarise Phase 1-3 achievements, telemetry tooling, and new CLI surfaces (see `notes/release_notes_draft.md`).
   - [x] Document breaking changes and migration guidance (schema version, mobilisation config).
   - [x] Add "Known Issues / Next" section pointing to backlog items (agentic tuner, DSS hooks).
5. **Hyperparameter tuning sign-off**
   - [x] Re-run the tuning harness (baseline bundles) with the latest code; see `notes/release_tuning_results.md` and `tmp/release-tuning/` artifacts.
   - [x] Document the improvements (objective delta, runtime, win rate) in release notes and telemetry dashboards.
   - [x] Store the tuned presets/operator weights for reuse in the release tag (see `notes/release_tuned_presets.json`).
6. **Automation**
   - [x] Add GitHub Actions job template for ``hatch build`` verification (triggered on tags) — see `.github/workflows/release-build.yml`.
   - [ ] Prepare release checklist in ``CODING_AGENT.md`` (bump version, run hatch build, tag, publish).

7. **Publishing (TestPyPI → PyPI)**
   - [ ] Dry run using TestPyPI:
     - ``python -m pip install --upgrade build twine``
     - ``rm -rf dist``
     - ``hatch run release:build``
     - ``python -m twine upload --repository testpypi dist/*`` (requires ``TESTPYPI_TOKEN``)
     - ``pip install -i https://test.pypi.org/simple/ fhops`` and run smoke commands
   - [ ] Document environment variables/secrets: ``TESTPYPI_TOKEN`` and ``PYPI_TOKEN`` (GitHub secrets) plus local ``~/.pypirc`` fallback.
   - [ ] After TestPyPI validation, repeat for PyPI (`twine upload dist/*`) during the release tag.

## References
- ws3 Hatch workflow: https://github.com/ubc-fresh/ws3
- Packaging guides: Hatch docs, PyPA best practices.
