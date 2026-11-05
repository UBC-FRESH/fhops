# FHOPS 1.2.1 release candidate

Date: 2026-11-05
Issue: #432
Status: candidate prepared; tag/PyPI/GitHub release blocked on explicit approval.

## Scope

Patch release on the 1.2 line summarizing changes since v1.2.0:

- Scenario Studio presets, comparison economics/charts/export, product mix, and
  operator-policy effects.
- CTL harvester/forwarder role and timing refinements.
- Salvage shelf-life library, CLI report, Studio overlay, and comparison view.
- Serious-game dual 3D replay verification and timeline compaction.
- FEMIC ground-summary/ground-support consumers and optional scenario reference.
- Shared-kernel adapter/parity infrastructure and gate cleanup.

## Version

- `src/fhops/__init__.py`: `1.2.1`
- `tests/test_import.py`: `1.2.1`
- README install examples: `1.2.1`
- Release notes: `docs/releases/v1.2.1.md`

## Packaging

Commands:

```bash
python -m hatch clean
python -m hatch build
python -m twine check dist/*
```

Results:

- `dist/fhops-1.2.1-py3-none-any.whl`
- `dist/fhops-1.2.1.tar.gz`
- `twine check`: both PASSED
- Wheel includes `fhops/salvage/*` and
  `fhops/data/reference/degradation/salvage_decay.v1.json`.

## Smoke install

Fresh venv `/tmp/opencode/v121-smoke` installed the built wheel.

- `import fhops; fhops.__version__` -> `1.2.1`
- `fhops --help` -> success
- `fhops validate examples/tiny7/scenario.yaml` -> success (2 blocks, 9 machines)
- `fhops report salvage-shelf-life examples/tiny7/scenario.yaml
  examples/salvage_shelf_life/storage.csv --value-per-m3 10 --out-dir ...`
  -> CSV and Markdown written successfully

## Gates

- Full `pytest`: 1410 passed, 219 skipped (pre-release tree).
- `ruff format`, `ruff check`, `mypy src`, `pre-commit run --all-files`.
- Sphinx `-W`.
- Re-run these after the release-notes/version commit.

## Approval gate

Do **not** run any of the following without explicit maintainer approval:

```bash
git tag -s v1.2.1
git push --tags
python -m twine upload ... dist/*
gh release create v1.2.1 ...
```
