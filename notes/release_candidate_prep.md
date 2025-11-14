# Release Candidate Prep Plan

Date: 2025-11-16
Status: Draft — drive the v0.x RC process.

## Objectives
- Freeze scope and polish docs/install instructions for the first FHOPS release candidate.
- Adopt Hatch for packaging/publishing (mirroring ws3 workflows) and ensure PyPI metadata is accurate.
- Produce changelog/release notes, version bumps, and verification checklists before tagging.

## Tasks
1. **Versioning & Hatch wiring**
   - [ ] Add ``hatch.toml``/pyproject updates (build-system, project metadata, scripts, dependencies).
   - [ ] Define version source (e.g., ``src/fhops/__init__.py``) and document bump workflow.
   - [ ] Configure Hatch environments/custom commands for lint/test/release parity with ws3.
2. **Packaging QA**
   - [ ] ``hatch build`` wheel/sdist locally and inspect contents (license, data files, examples).
   - [ ] Smoke install from the built wheel (fresh venv) and run ``fhops --help`` plus a minitoy solve.
   - [ ] Draft ``hatch publish --repo testpypi`` dry-run instructions (no secrets committed).
3. **Docs & README polish**
   - [ ] Tighten README quickstart for pip install + hatch workflows.
   - [ ] Ensure docs landing page highlights versioned install instructions.
   - [ ] Link telemetry dashboards/release notes for transparency.
4. **Release Notes**
   - [ ] Summarise Phase 1-3 achievements, telemetry tooling, and new CLI surfaces.
   - [ ] Document breaking changes and migration guidance (schema version, mobilisation config).
   - [ ] Add "Known Issues / Next" section pointing to backlog items (agentic tuner, DSS hooks).
5. **Automation**
   - [ ] Add GitHub Actions job template for ``hatch build`` verification (triggered on tags).
   - [ ] Prepare release checklist in ``CODING_AGENT.md`` (bump version, run hatch build, tag, publish).

## References
- ws3 Hatch workflow: https://github.com/ubc-fresh/ws3
- Packaging guides: Hatch docs, PyPA best practices.
