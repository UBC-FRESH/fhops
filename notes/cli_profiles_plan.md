# CLI Profiles & Ergonomics Plan

Date: 2025-11-12  
Status: Draft — to guide Phase 2 CLI enhancements.

## Objectives
- Introduce reusable solver configuration profiles (e.g., presets for heuristics, multi-start, ILS/Tabu).
- Simplify CLI usage for common workflows (quick start, diversification, mobilisation-heavy scenarios).
- Ensure documentation and telemetry reflect profile usage clearly.

## Planned Tasks
- [x] Define profile schema and registry (e.g., YAML/JSON or Python mapping) under `cli/profiles`.
  * Create `Profile` dataclass with fields: `name`, `description`, `sa`, `ils`, `tabu`, and optional `bench_suite` overrides.
  * Each solver config holds: `operator_presets`, `operator_weights`, `batch_neighbours`, `parallel_workers`, `parallel_multistart`, plus solver-specific kwargs (e.g., `tabu_tenure`, `perturbation_strength`).
  * Seed initial profiles aligned with existing presets: `default`, `explore`, `mobilisation`, `stabilise`, `intense-diversify`, `parallel-explore`.
- [ ] Implement CLI flags (`--operator-profile`, `--profile`) resolving to presets across heuristics/ILS/Tabu.
- [ ] Ensure profiles integrate with existing preset/weight overrides without surprising behaviour.
- [ ] Surface profile usage in telemetry/logging.
- [ ] Document profiles in Sphinx (CLI reference + how-tos).

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
- [ ] Unit tests ensuring profiles expand to expected solver arguments.
- [ ] CLI integration tests covering profile selection + overrides.
- [ ] Regression tests verifying telemetry records selected profile.

## Documentation
- [ ] Update CLI reference with profile descriptions and examples.
- [ ] Add how-to section illustrating when to choose each profile.
- [ ] Note profile usage in benchmark/heuristic docs.

## Open Questions
- Should profiles cover both SA/ILS/Tabu simultaneously or remain solver-specific?
- Do we need user-defined profile loading (e.g., from `~/.fhops/presets.yaml`)?
- How to handle conflicting flags (profile + individual options) — precedence rules?

## Evaluation & Reporting
- [ ] Update changelog and Phase 2 roadmap once profiles ship.
- [ ] Capture telemetry fields (`profile_name`, `profile_version`) for downstream analytics.
