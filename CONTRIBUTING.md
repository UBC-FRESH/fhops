# Contributing

1. Create a virtual env (Python 3.12+), `pip install -e .[dev]`.
2. Enable pre-commit: `pre-commit install`.
3. Run tests: `pytest`.
4. Prefer feature branches and open PRs against `main`.
5. Use Hatch for release validation:
   - `hatch run dev:suite` to mirror the CI command cadence locally.
   - For release candidates, `hatch clean && hatch build` and `HATCH_INDEX=<index> hatch publish`
     (see `CODING_AGENT.md` / `notes/release_candidate_prep.md` for the full checklist).
