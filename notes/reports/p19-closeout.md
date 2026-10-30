# P19 close-out: Nemora tree-inventory handoff

Phase: P19
Parent issue: #300
Branch: `feature/phase19-nemora-handoff`
Date: 2026-10-30
Status: queued for approval.

## Outcomes

- P19.1: committed a 40-tree synthetic `fhops.tree.inventory.v1` fixture exported
  by Nemora 0.1.0a1. FHOPS validates it with block B01, 40 trees, 4 species, no
  errors.
- P19.2: added a one-block/one-landing scenario, a how-to page, and an
  end-to-end test. The fixture runs through `fhops tree system`: 21.512 m³,
  0 unreachable, no warnings.
- P19.3: gates and release decision.

## Verification

- `pytest -q tests/tree` — pass.
- Targeted handoff test — pass.
- `ruff format --check src tests` — pass.
- `ruff check src tests` — pass.
- `mypy src` — pass.
- `pre-commit run --all-files` — pass.
- `sphinx-build -b html docs _build/html -W` — pass.
- Full `pytest -q` — **two pre-existing HiGHS option-error tests fail locally**
  due the installed HiGHS behavior; tree tests and P19 tests pass. This is
  reported, not claimed as green.

## Release decision

No `1.2.1` release now. The change is a fixture/example/docs/test addition, not
a runtime behaviour change. It can ship with the next scheduled FHOPS release.
No tag or publication occurs in P19.

## Limits

- Synthetic tree list, not a tree map.
- One block/one landing reference system.
- No operational, financial, or regulatory claim.
