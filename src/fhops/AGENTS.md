# FHOPS Core Code – Agent Guide

This file refines the root `AGENTS.md` guidelines for code under `src/fhops`.

- Before editing any module here, scan `ROADMAP.md` and the relevant note under
  `notes/` (e.g., `notes/cli_profiles_plan.md`, `notes/mip_model_plan.md`,
  `notes/simulation_eval_plan.md`) to align with the current phase.
- Keep public APIs stable unless the roadmap/note explicitly calls out a
  breaking change; when you do change behaviour, update Sphinx docs and CLI
  help in the same change set.
- Tests live under `tests/`; prefer adding focused tests next to the area you
  touch instead of broad integration-only coverage.
