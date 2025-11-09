# CLI Profiles & Ergonomics Plan

Date: 2025-11-12  
Status: Draft — to guide Phase 2 CLI enhancements.

## Objectives
- Introduce reusable solver configuration profiles (e.g., presets for heuristics, multi-start, ILS/Tabu).
- Simplify CLI usage for common workflows (quick start, diversification, mobilisation-heavy scenarios).
- Ensure documentation and telemetry reflect profile usage clearly.

## Planned Tasks
- [ ] Define profile schema and registry (e.g., YAML/JSON or Python mapping) under `cli/profiles`.
- [ ] Implement CLI flags (`--operator-profile`, `--profile`) resolving to presets across heuristics/ILS/Tabu.
- [ ] Ensure profiles integrate with existing preset/weight overrides without surprising behaviour.
- [ ] Surface profile usage in telemetry/logging.
- [ ] Document profiles in Sphinx (CLI reference + how-tos).

## Immediate Next Steps
- [x] Survey existing presets (`operator presets`, benchmark recipes) to seed profile catalog.
- [ ] Decide on configuration format (code-based registry vs. external YAML).
- [ ] Draft CLI UX (command examples, flag names).

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
