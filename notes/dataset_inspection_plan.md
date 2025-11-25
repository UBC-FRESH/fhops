# Dataset Inspection Plan

## Context
- Goal: ensure shipped datasets and synthetic-data generator parameters look realistic (no >10x deviations from domain expectations) prior to broad release.
- Driver: post-v0.1.0-a1 push to let developers/users inspect datasets via CLI before ingestion, preventing GIGO and aligning with FHOPS roadmap data-quality milestones.

## Conversation Snapshot (2025-02-??)
- We agreed to focus on dataset + synthetic generator parameter realism now that the release candidate is out.
- First concrete step is a CLI that compiles and dumps parameter summaries for any provided dataset; Python API can follow later.
- This inspection CLI is intended both for developers and “regular” users to validate newly created datasets.

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
1. What future extensions do we need beyond raw parameters (e.g., derived statistics, anomaly detection)?
2. When we add machine-friendly output, should it be JSON, CSV, or something tied to internal tooling?
3. Which CLI UX patterns should we support besides interactive prompts (flags for non-interactive CI usage)?

## Next Steps
- Capture product answers to the open questions above.
- Design CLI UX + module layout once decisions land.
- Define how the interactive prompt workflow will operate (prompt text, validation, escape hatches).
- Hook into roadmap artifacts (e.g., `ROADMAP.md`) once scope is approved.

## Latest Progress
Machine productivity & costing work now lives in `notes/machine_productivity_costing_plan.md`.
