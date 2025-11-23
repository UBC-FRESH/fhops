# Contributing

1. Create a virtual env (Python 3.12+), `pip install -e .[dev]`.
2. Enable pre-commit: `pre-commit install`.
3. Run tests: `pytest`.
4. Prefer feature branches and open PRs against `main`.
5. Use Hatch for release validation:
   - `hatch run dev:suite` to mirror the CI command cadence locally.
   - For release candidates, `hatch clean && hatch build` and `HATCH_INDEX=<index> hatch publish`
     (see `CODING_AGENT.md` / `notes/release_candidate_prep.md` for the full checklist).
6. Document everything:
   - **Docstrings**: Every public module/class/function must ship a NumPy-style docstring with:
     1. A one-line summary in sentence case.
     2. Explicit ``Parameters`` / ``Returns`` / ``Raises`` / ``Notes`` (omit the ones you do not
        need). Document **every** argument—including units, allowable ranges, defaults, and any
        coupling to other arguments. For complex payloads (mappings, dataclasses, CLI results)
        describe the schema: required keys/fields, types, and semantic meaning.
     3. Provenance: cite the dataset, publication, or field trial that backs a productivity/costing
        helper. When behaviour depends on a CLI flag or workflow sequence, include a short example
        snippet so Sphinx readers can copy/paste it.
     4. Return semantics: list the dataclass attributes, tuple ordering, or DataFrame columns along
        with units. If a function mutates inputs or writes telemetry, state that up front.
     5. Validation: if you clamp values (e.g., payload multipliers, slope limits), explain the rule
        so users understand the guard rails.
   - **Consistency**: Module docstrings must explain why the module exists (e.g., Pyomo model
     builder, CLI dataset adapter) and link to the relevant docs section. Keep docstrings, CLI help,
     and ``docs/api`` narrative guides in sync—Sphinx renders docstrings verbatim.
   - **Docs build**: When adding a new command or helper, update the relevant Sphinx page,
     regenerate the API docs, and run ``sphinx-build -b html docs _build/html -W`` to ensure the new
     docstrings render cleanly without warnings.
