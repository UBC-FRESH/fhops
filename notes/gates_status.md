# Gate status after P52

## Passing

- `ruff format src tests sandbox`
- `ruff check src tests sandbox`
- `mypy src` — 191 source files
- `pytest` — 1399 passed, 219 skipped
- `pre-commit run --all-files`
- `sphinx-build -b html docs _build/html -W` — with the local Pandoc shim below
- Targeted Studio/tree tests — 46 passed
- `node --check` for Studio comparison/replay/edit bundles

## Local Pandoc setup

CI downloads a standalone Pandoc distribution. Locally the venv already has
`pypandoc_binary` (Pandoc 3.9), but nbsphinx also requires a `pandoc` executable
on `PATH`. Use:

```bash
PATH="$PWD/.venv/bin:$PATH" sphinx-build -b html docs _build/html -W
```

The venv's `bin/pandoc` is provided by `pypandoc_binary`; if it is missing,
install it with `python -m pip install pypandoc_binary`.

## Historical note

The earlier HiGHS option-error failures were a highspy 1.12 diagnostics change:
configuration failures now raise a `ValueError` naming `iteration_count` rather
than returning the older `ERROR` log line naming `threads`. The robustness tests
now accept either configuration diagnostic and remain case-insensitive.
