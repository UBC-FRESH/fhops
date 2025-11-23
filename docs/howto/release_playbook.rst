Release & Contribution Playbook
===============================

This playbook captures the operational steps for preparing FHOPS releases (tags, docs, changelog) and
the expectations for contributions (PR checklist, planning artefacts). Use it before publishing
Phase 4 milestones or reviewing external contributions.

Release Preparation
-------------------

1. **Audit Roadmap & Notes**

   - Verify Phase checkpoints in ``FHOPS_ROADMAP.md`` and linked notes (``notes/*.md``) reflect the
     state of the release (no unchecked items for completed work).
   - Update `notes/sphinx-documentation.md` to confirm documentation coverage or new TODOs.

2. **Version & Changelog**

   - Bump the version string in ``pyproject.toml`` (``[project].version``) and ensure the same value
     appears in ``src/fhops/__init__.py`` if applicable.
   - Append a new section to ``CHANGE_LOG.md`` summarising the release (date, highlights, command
     suite used for verification). Remember: the pre-commit hook enforces that the changelog is
     touched in every PR.

3. **Docs & Telemetry**

   - Run the full doc build locally:

     .. code-block:: bash

        sphinx-build -b html docs docs/_build/html

   - Execute the weekly telemetry workflow (from :doc:`telemetry_ops`) so the latest notebook and
     tuning history are published before tagging.
   - Trigger or verify a Read the Docs build (ensure the live docs match the release tag).

4. **Testing**

   - Run the required command suite (per ``CODING_AGENT.md``):

     .. code-block:: bash

        pip install -e .[dev]
        ruff format src tests docs
        ruff check src tests docs
        mypy src
        pytest
        pre-commit run --all-files

   - Optional: execute ``scripts/run_analytics_notebooks.py --light`` as a final smoke test.

5. **Tag & Publish**

   - Once tests/docs pass, create a tag (e.g., ``git tag v0.1.0``) and push both branch + tag.
   - Draft GitHub release notes using the ``CHANGE_LOG.md`` entry; include highlights (features,
     docs, telemetry updates) and verification commands.

Contribution Checklist
----------------------

Every PR (internal or external) should meet the following criteria:

1. **Planning Artefacts**

   - Link to the relevant roadmap item and note file (e.g.,
     “See ``FHOPS_ROADMAP.md`` Phase 2: Metaheuristic Roadmap; working detail in ``notes/metaheuristic_roadmap.md``”).
   - Update the note/roadmap when the PR discharges a task (checked boxes, status updates).

2. **Changelog Requirement**

   - Add a bullet to ``CHANGE_LOG.md`` describing the change (one entry per PR). The pre-commit hook
     blocks commits without a changelog update; use ``SKIP=require-changelog-update`` only when
     explicitly approved (e.g., merge conflict resolution).

3. **Docs & Tests**

   - For user-visible features, update the relevant Sphinx page (how-to, reference, API).
   - Include or update tests (unit, regression, CLI) when functionality changes.
   - Mention any doc/test gaps in the PR description if deferring to a follow-up.

4. **Command Suite**

   - Run the standard checklist locally (``ruff format`` → ``pre-commit run --all-files``). CI
     re-runs the same commands; failures will block merges.

5. **Template Usage**

   - Fill out the PR template (summary, testing, docs touched, roadmap links). If contributing from
     forks, provide the command output snippets in the description or attach logs.

6. **Telemetry & Notebooks (when applicable)**

   - When changes affect tuning or analytics, run the relevant notebook/telemetry scripts and attach
     the resulting artefacts (or reference the CI run).

Where to Update Next
--------------------

- PR template: `.github/pull_request_template.md` (mirror the checklist above).
- CI workflows: ensure release/tuning/notebook jobs stay green before tagging.
- README badges: update telemetry/history badges when the Pages URL changes.
