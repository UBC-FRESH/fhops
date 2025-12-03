# PR Summary

## Sequencing & MILP Model
- Rewired the operational MILP builder to consume the shared `OperationalProblem` metadata so SequencingTracker rules (role filters, head-start buffers, loader batches) are enforced verbatim in Pyomo. Added per-role activation binaries, per-block inventories, landing-level loader constraints, and default production initialisation. Large84 now surfaces real loader deficits instead of silently passing.
- Expanded the sequencing/unit tests to cover landing-sharing and head-start cases using the refreshed tiny7/large84 bundles.

## Dataset & Benchmark Refresh
- Rebuilt the small21/med42/large84 scenarios with the lighter tiny7 block profile (6/12/24 blocks) plus updated distance matrices and docs so each ladder tier sits just under system capacity.
- Regenerated SA/ILS/Tabu benchmark fixtures, deterministic & stochastic KPI exports, and the regression baseline to align with the new staging logic. `fhops.cli.benchmarks.run_benchmark_suite` now calls `solve_operational_milp`, so CLI/benchmarks/tests share the same solver plumbing.

## Heuristic Runtime & Scoring
- Overhauled the heuristic schedule representation: dense per-machine shift matrices, mobilisation caches, dirty tracking for machines/blocks/slots, block-slot indices, and local repair support. Operators mutate only the affected slots, reducing per-candidate cost.
- Updated `evaluate_schedule` to reward delivered loader production, softened leftover penalties, added scenario-aware auto profiles/batching, and exposed staged vs delivered volume in telemetry/watch metadata. Tiny7/Small21 SA runs finally outperform the greedy seed with the new defaults.

## Warm-Start Support
- `_apply_incumbent_start` now reconstructs every Pyomo variable implied by a heuristic assignment (assignments, production, transitions, activation binaries, inventories, landing surplus, leftovers) and sets Pyomo’s warm-start flag. CLI + benchmark harnesses pass the `OperationalProblem` context so warm starts work for scenario runs, not just bundles.
- Added `docs/howto/mip_warm_starts.rst`, expanded the CLI reference, and documented the med42 experiment in `notes/mip_tractability_plan.md`, making it clear that warm starts are operational but do not yet improve med42/large84 runtimes.

## CLI & Testing Infrastructure
- Introduced `--solver-option`/`--incumbent` flags on `fhops solve-mip-operational`, restored the Tiny7 explore preset fixture, and expanded warm-start tests/CLI fakes to accept the new context plumbing.
- Added `tests/conftest.py` with the `FHOPS_RUN_FULL_CLI_TESTS` gate so benchmark/tuner suites (and future CLI integrations) can be skipped during everyday `pytest` runs; set the env var in CI to exercise the full stack.

## Testing
- `.venv/bin/ruff format src tests docs`
- `.venv/bin/ruff check src tests`
- `.venv/bin/mypy src`
- Targeted pytest runs across sequencing, heuristics, CLI, KPI, and benchmark suites (full `pytest` run still >1 min even after gating; trimming the remaining CLI integrations is deferred).

## Known Limitations / Follow-Ups
- Warm starts provide no measurable benefit on med42/large84 until we can generate stronger incumbents (longer SA, repairs, rolling-horizon MILPs). Option-sweep work remains blocked on that.
- Only the benchmark/tuner suites currently honor `FHOPS_RUN_FULL_CLI_TESTS`; dataset/productivity/playback CLI tests still run by default, keeping full `pytest` at ~80 s. Additional gating/mocking is required in a follow-up PR.
