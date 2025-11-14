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
   - [ ] Re-run the tuning harness (baseline + synthetic bundles) with the latest code, capturing tuned vs. default results for SA/ILS/Tabu.
   - [ ] Document the improvements (objective delta, runtime, win rate) in release notes and telemetry dashboards.
   - [ ] Store the tuned presets/operator weights for reuse in the release tag (commit JSON/YAML or note location).
6. **Automation**
   - [ ] Add GitHub Actions job template for ``hatch build`` verification (triggered on tags).
   - [ ] Prepare release checklist in ``CODING_AGENT.md`` (bump version, run hatch build, tag, publish).

## References
- ws3 Hatch workflow: https://github.com/ubc-fresh/ws3
- Packaging guides: Hatch docs, PyPA best practices.
