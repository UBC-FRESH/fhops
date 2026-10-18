# Metadata Tables

SoftwareX requires two structured tables in the front matter:

1. **Code metadata** – repository URL, license, programming language, dependencies, documentation link, support contact, etc.
2. **Current code version** – software version identifier, permanent link/DOI, CI status, supported OS/architectures, key dependencies.

This folder stores the LaTeX snippets that render each table. The canonical manuscript
(UBC-FRESH/fhops-manuscript) reuses them, so they are kept factually correct for the release even
though the rest of this in-repo draft is superseded (see `../README.md`). Sources of truth:

- operating systems / CI: `.github/workflows/*.yml` (GitHub Actions `ubuntu-latest`, Python 3.11
  only; macOS and Windows are not tested);
- Python requirement, dependencies and their floors: `pyproject.toml` `[project]`
  (`requires-python`, `dependencies`, `optional-dependencies`);
- reproducibility log and hash recipe: `docs/softwarex/assets/benchmark_runs.log` and `../README.md`.

Re-check these entries whenever a workflow or `pyproject.toml` changes.
