# Gate status after P45

## Passing

- `ruff format src tests sandbox`
- `ruff check src tests sandbox`
- `mypy src` — 188 source files
- `pre-commit run --all-files`
- Targeted Studio/tree tests — 56 passed
- `node --check` for Studio comparison/replay/edit bundles

## Known environment failures

- Full local `pytest` still fails the two pre-existing HiGHS option-error
  assertions:
  - `tests/model/test_milp_driver_robustness.py::test_highs_option_error_is_reported_as_solver_error`
  - `tests/test_legacy_mip_driver.py::test_highs_option_error_is_reported_as_solver_error[highs-exec]`
- Local Sphinx cannot run because Pandoc is unavailable
  (`nbsphinx.NotebookError: PandocMissing`).

These are environment/pre-existing issues, not P45 regressions. CI `lint-test-docs`
is green on the P45 PR and main.
