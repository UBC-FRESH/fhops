Contributing
============

We welcome contributions! Before starting, review the planning artefacts in the repository root:

- ``ROADMAP.md`` for phase-level priorities and status.
- ``notes/`` directory for module-specific execution plans.
- ``AGENTS.md`` for required command cadence and documentation expectations.

Key practices:

- Create feature branches and keep changes scoped to roadmap tasks.
- Run the full command suite (format, lint, type-check, tests, pre-commit, Sphinx) prior to
  submitting pull requests.
- Update the relevant note and changelog entry with progress details.
- Coordinate larger design discussions via issues or draft PRs, then reflect resolutions in the
  planning documents.

Developer onboarding
--------------------
- Use Python 3.12+ with a fresh virtual environment: ``python -m venv .venv && source .venv/bin/activate && pip install -e .[dev]``. Optional extras: ``.[geo]`` for spatial helpers, ``.[gurobi]`` for commercial MILP backends (requires a licence and ``GRB_LICENSE_FILE``).
- Read ``AGENTS.md`` for the required command cadence and docstring style, then skim ``ROADMAP.md`` and the relevant note under ``notes/`` to align with in-flight work.
- Familiarise yourself with fixtures: scenarios under ``examples/``, regression bundles in ``tests/fixtures/``, and telemetry/asset outputs in ``docs/assets/``. CLI and API examples in ``docs/howto`` mirror these resources.
- When adding CLI flags or API helpers, update the matching how-to and API reference page in the same change set so docs stay authoritative.

Command cadence (local loop)
----------------------------
Run these before handing work back (mirrors CI and ``AGENTS.md``):

1. ``ruff format src tests``
2. ``ruff check src tests``
3. ``mypy src``
4. ``pytest`` (set ``FHOPS_RUN_FULL_CLI_TESTS=1`` only when you intend to exercise the long CLI/benchmark suites)
5. ``pre-commit run --all-files`` (after ``pre-commit install``)
6. ``sphinx-build -b html docs _build/html -W``

Record the exact commands in the active ``CHANGE_LOG.md`` entry. Prefer fixing warnings over silencing them.

Common pitfalls
---------------
- Missing solver/licence setup: HiGHS ships by default; Gurobi requires ``pip install .[gurobi]`` and a valid licence (``GRB_LICENSE_FILE``). Threads can be set via ``GRB_THREADS`` or ``--mip-solver-option Threads=<n>`` on MILP commands.
- Long-running MILP tests: keep the default ``FHOPS_RUN_FULL_CLI_TESTS`` unset unless you intend to run the heavier CLI regressions; targeted tests under ``tests/planning`` and ``tests/cli`` keep rolling-horizon coverage fast.
- Large artefacts: rolling comparison CSV/PNG bundles are small and live in-repo. Notebook runs default to light mode via ``FHOPS_ANALYTICS_LIGHT=1``; unset when regenerating full ensembles.

Debugging and profiling
-----------------------
- Capture solver context with ``--telemetry-log`` (JSONL) or ``--watch`` for heuristics; the operational MILP supports ``--solver-option LogFile=...`` and ``--solver-option Threads=...``.
- Use ``--dump-bundle`` / ``--bundle-json`` on ``solve-mip-operational`` to isolate bundle issues. The same bundle can be replayed in notebooks or tests.
- For rolling-horizon runs, persist ``--out-json`` and per-iteration CSV/JSONL exports, then feed the assignments into ``fhops eval playback`` or :func:`fhops.planning.compute_rolling_kpis` to inspect deltas without rerunning solvers.
- When measuring runtimes, prefer small scenarios (``examples/tiny7``) and short caps (``--mip-time-limit``) before scaling to med42/large84.

Re-running published artefacts
------------------------------
- Rolling MASc plots/CSVs live under ``docs/assets/rolling``. Regenerate with ``fhops plan rolling`` using the solver settings recorded in the how-to (e.g., med42 with Gurobi ``Threads=64`` and short time limits), then rebuild plots with :func:`fhops.planning.comparison_dataframe`.
- Notebook assets in ``docs/examples/analytics`` execute in CI with ``FHOPS_ANALYTICS_LIGHT=1``; remove the flag locally for full-sample plots before publishing.
