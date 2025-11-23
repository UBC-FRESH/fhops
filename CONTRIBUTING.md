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
   - Public modules/classes/functions need clear NumPy-style docstrings: a summary line followed by
     ``Parameters`` / ``Returns`` / ``Raises`` / ``Notes`` sections as applicable. Document **every
     argument** (units, ranges, defaults) plus the structure of return payloads (dataclasses,
     tuples, DataFrames). Cite the underlying study/dataset for productivity or costing helpers and
     drop in short code snippets when the workflow spans multiple steps.
   - When adding a new command or helper, update the relevant Sphinx page, regenerate the API docs,
     and run ``sphinx-build -b html docs _build/html -W`` to ensure the new docstrings render
     cleanly.
