# Dataset Inspection Plan

## Context
- Goal: ensure shipped datasets and synthetic-data generator parameters look realistic (no >10x deviations from domain expectations) prior to broad release.
- Driver: post-v0.1.0-a1 push to let developers/users inspect datasets via CLI before ingestion, preventing GIGO and aligning with FHOPS roadmap data-quality milestones.

## Conversation Snapshot (2025-12-03)
- With v0.1.0-a1 out the door, we need to retrofit all shipped datasets (tiny7, small21, med42; large84 later) plus synthetic generator presets with realistic parameters so experts don’t see order-of-magnitude discrepancies.
- First deliverable is a dataset-inspection CLI that loads any FHOPS dataset (sample bundle or user-provided path) and emits parameter value summaries so non-developers can validate their inputs before running solvers.
- Python API / notebook helpers are deferred; the CLI is the authoritative workflow for now.
- We captured open design questions (see below) to unblock UX + implementation details in subsequent iterations.

## Working Assumptions / Decisions
- Inspect exactly one dataset per CLI invocation; batching will be layered on later via scripting.
- Shipped demo datasets can be referenced by canonical name; ad-hoc datasets use filesystem paths (need resolver that accepts either).
- Initial focus is per-element inspection (e.g., single machine/block) rather than whole dataset dumps; CLI should accept an element selector.
- Dataset-generator parameter inspection is deferred until after the core CLI is stable.
- CLI output should be human-readable tables in the terminal; machine-friendly JSON export can wait.
- First iteration only dumps raw input parameters gathered via existing schemas/contracts; missing or derived statistics are simply flagged as TODOs in the CLI output/planning doc.
- CLI must leverage the authoritative schemas/data contracts in code; flag any mismatch with planning docs.
- Element selection UI can be interactive: when the selector is incomplete, prompt step-by-step (system -> machine -> block, etc.).
- Sample datasets should assume 24-hour machine availability per day (consistent with year-round operations except brief spring shutdowns).

## Open Questions (awaiting product/UX decisions)
1. Which datasets should the first iteration validate (all shipped bundles + synthetic samples or just tiny7/small21/med42)? How do we gate large84 given it is unsolved today?
2. Should the CLI only echo raw parameters, or also compute summary statistics (ranges, means, histograms)? If stats are included, what constitutes “realistic” warnings?
3. What output formats are required in v1 (terminal tables only vs. optional JSON/CSV for CI/automation)?
4. How should users select datasets? Paths, canonical names, scenario YAML, or detection via `fhops dataset validate` outputs?
5. Do we inspect synthetic generator presets directly, or reuse the CLI by pointing it at freshly generated scenarios?
6. Should the CLI support non-interactive CI usage from day one (flags to skip prompts)?

## Next Steps
- Capture product answers to the open questions above.
- Design CLI UX + module layout once decisions land.
- Define how the interactive prompt workflow will operate (prompt text, validation, escape hatches).
- Hook into roadmap artifacts (e.g., `ROADMAP.md`) once scope is approved.

## Latest Progress
Machine productivity & costing work now lives in `notes/machine_productivity_costing_plan.md`.
