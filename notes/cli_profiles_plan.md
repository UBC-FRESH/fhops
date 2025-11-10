# CLI Profiles & Ergonomics Plan

Date: 2025-11-12
Status: Complete — profiles shipped with CLI wiring/tests/docs.

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
