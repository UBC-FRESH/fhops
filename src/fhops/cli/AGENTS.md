# FHOPS CLI – Agent Guide

When working on the CLI (`src/fhops/cli`):

- Treat `docs/cli/profiles.md` and `docs/cli/heuristics.md` as the primary
  specifications for profiles and heuristic-facing flags/UX.
- For higher-level planning, read `notes/cli_profiles_plan.md`,
  `notes/cli_heuristic_upgrade_notes.md`, and `notes/cli_docs_plan.md`.
- Keep Typer command help text and Sphinx CLI docs in sync; when adding or
  changing flags, update both.
- Maintain backwards compatibility for released flags whenever possible; if you
  must deprecate a flag, add clear warnings and document the migration path in
  the CLI docs.

