# CLI Profiles & Ergonomics Plan

Date: 2025-11-12
Status: Complete — profiles shipped with CLI wiring/tests/docs. This note is
now superseded by `docs/cli/profiles.md` for long-term specification and
should only be updated with transient planning details that have not yet been
folded into the docs.

## Objectives
- Introduce reusable solver configuration profiles (e.g., presets for heuristics, multi-start, ILS/Tabu).
- Simplify CLI usage for common workflows (quick start, diversification, mobilisation-heavy scenarios).
- Ensure documentation and telemetry reflect profile usage clearly.

## Planned Tasks
- [x] Define profile schema and registry (e.g., YAML/JSON or Python mapping) under `cli/profiles`.
  * Create `Profile` dataclass with fields: `name`, `description`, `sa`, `ils`, `tabu`, and optional `bench_suite` overrides.
  * Each solver config holds: `operator_presets`, `operator_weights`, `batch_neighbours`, `parallel_workers`, `parallel_multistart`, plus solver-specific kwargs (e.g., `tabu_tenure`, `perturbation_strength`).
  * Seed initial profiles aligned with existing presets: `default`, `explore`, `mobilisation`, `stabilise`, `intense-diversify`, `parallel-explore`.
- [x] Implement CLI flags (`--operator-profile`, `--profile`) resolving to presets across heuristics/ILS/Tabu.
- [x] Ensure profiles integrate with existing preset/weight overrides without surprising behaviour.
- [x] Surface profile usage in telemetry/logging.
- [x] Document profiles in Sphinx (CLI reference + how-tos).

## Immediate Next Steps
- [x] Survey existing presets (`operator presets`, benchmark recipes) to seed profile catalog.
- [x] Decide on configuration format (code-based registry vs. external YAML).
  * Profiles will be defined in a Python module (e.g., `fhops.cli.profiles`) exposing `Profile` dataclasses and a default registry. This avoids packaging extra assets and keeps typing straightforward.
  * Follow-up work can allow optional user overrides from `~/.fhops/profiles.yaml`, but is out of scope for the first iteration.
- [x] Draft CLI UX (command examples, flag names).
  * Introduce a shared `--profile NAME` option for `solve-heur`, `solve-ils`, `solve-tabu`, and `bench suite`.
  * Profiles set baseline options (operator presets, weights, batch/parallel knobs, ILS/Tabu parameters). Explicit CLI arguments still override.
  * Add `--list-profiles` to print available profiles and short descriptions; optionally `fhops profile describe NAME`.
  * Example usage:

    .. code-block:: bash

       fhops solve-heur examples/med42/scenario.yaml --profile explore
       fhops solve-ils examples/med42/scenario.yaml --profile stabilise --perturbation-strength 5
       fhops bench suite --include-ils --include-tabu --profile mobilisation --out-dir tmp/bench_profiles

## Tests
- [x] Unit tests ensuring profiles expand to expected solver arguments.
- [x] CLI integration tests covering profile selection + overrides.
- [x] Regression tests verifying telemetry records selected profile.

## Documentation
- [x] Update CLI reference with profile descriptions and examples.
- [x] Add how-to section illustrating when to choose each profile.
- [x] Note profile usage in benchmark/heuristic docs.

## Open Questions & Follow-ups
- Should we enable user-defined profiles (e.g., `~/.fhops/profiles.yaml`) in a future release?
- Consider exposing `fhops profile describe NAME` for detailed dumps (current TODO).
- Telemetry now records ``profile`` and ``profile_version``; downstream analytics can consume these fields.
- **Block completion policy**: Instrument profiles (and eventually solver defaults) to enforce the business rule that once a machine starts a block it must finish it before moving elsewhere. The current heuristics allow hop-scotching across partially cut blocks, which means the optimisation problem is effectively under-specified and produces infeasible production plans (e.g., KPI `completed_blocks` stays at 0.0). We need to encode “finish-the-block” constraints directly in the heuristics/objective and treat any end-of-horizon leftover volume as an exception that incurs a moderate penalty but is otherwise tolerated.
- **Scenario capacity realism**: Patch the `med42` example (and follow-on synthetic bundles) with sufficient machine/system capacity so the total work required across blocks can actually finish within the planning horizon. Right now we routinely saturate every machine and still leave large volumes unfinished, which isn’t how operations planning behaves. Expanding the system roster (or rebalancing production rates) must become part of the example refresh before we tune heuristics/profiles against it.

## 2025-12-08 Updates
- SA now enforces block completion internally: during evaluation we track each machine’s active block, override any attempt to switch/idle while wood remains, and mutate the schedule so downstream assignments (KPI runs, telemetry, CSV exports) stay consistent with the “finish before moving” policy.
- `examples/med42` picked up a third crew (H9–H12) plus matching calendar availability, mobilisation parameters, and production-rate rows cloned from the existing crews. The added capacity keeps total available machine hours slightly ahead of the 8.9 k m³ workload so SA/ILS/Tabu can actually complete all blocks without running every machine at 100 % utilisation.
- SA scoring now pays primarily for block completion (bonus proportional to the block’s volume) and only gives a small fractional reward for in-progress production. This reshapes the annealing landscape so the solver gets the biggest payoff from fully finishing blocks instead of endlessly shaving the easy ones.
- `_init_greedy` now runs a coverage pass that walks every block (earliest window first) and explicitly assigns the best available machine/shift until the block starts (and ideally finishes) before falling back to the classic best-rate fill. This guarantees that every block is on the radar from iteration zero instead of relying on annealing moves to discover untouched work.
- Added a leftover-volume penalty (5× the remaining m³) plus an on-the-fly reassign hook inside `_evaluate` so any machine that finishes early (or finds itself outside a block’s window) immediately grabs another block with work remaining during that shift. This keeps idle slots hunting for unfinished blocks instead of wasting time on already-complete work.
- Recomputed `prod_rates.csv` via the FHOPS productivity helpers instead of raw heuristics: Lahrsen (2025) for feller-bunchers, ADV6N7 grapple-skidder regression for skidders, Berry (2019) Kinleith processors for roadside processors, and TN-261 loader-forwarder regression for loaders. Distances are derived from block windows/landing capacity (clamped between 120–650 m for skidders, 80–350 m for loaders) and everything is scaled to the 24 h/3-shift day we model in med42.
- Reverted the med42 calendar to the full 42-day horizon but collapsed the roster to a single 4-machine system (H1–H4) and scaled block workloads upward (~30% more volume, slightly higher stem size, slightly lower density). This keeps the dataset aligned with the “Medium42” narrative while ensuring capacity is tight even with empirically-derived productivity rates.
- Further increased block areas/volumes (work_required × 1.8) so total workload now exceeds 20 k m³, guaranteeing the lone system can’t finish everything and the heuristics have to prioritise.
- Scaled the regression-derived productivity rates down by ~10× (then nudged up to an effective 0.14×) so Lahrsen/ADV6N7/TN-261 outputs land in the 6–9 m³/PMH range—just enough for the four-machine system to *almost* finish the 20 k m³ workload within 42 days.
