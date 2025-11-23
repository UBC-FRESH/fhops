# Shared Include Plan (Sphinx ↔ SoftwareX Manuscript)

The `sections/includes/` directory hosts text blocks and table fragments that must stay identical between the SoftwareX LaTeX manuscript and the FHOPS Sphinx documentation. Source-of-truth will live here as Markdown/CSV, then export scripts will render:

1. `*.tex` – pulled into `fhops-softx.tex` via `\input{sections/includes/...}`
2. `*.rst` – included from the Sphinx tree via ``.. include::`` directives (or Copied into appropriate RST files during doc builds)

Automation hook (Phase 1 deliverable): extend `docs/softwarex/manuscript/scripts/export_docs_assets.py` so `make assets` produces both output formats from the Markdown/CSV primaries.

## Mapping table

| Manuscript Section | Primary Sphinx Source(s) | Planned include(s) | Notes / Tasks |
|--------------------|--------------------------|--------------------|---------------|
| 1. Motivation & significance | `docs/overview.rst`, `docs/roadmap.rst`, `notes/thesis_alignment.md` | `motivation_story.md` → `motivation_story.tex/.rst` | Explain real modelling gaps (open tooling, integrated workflows) and cite Jaffray review. Keep BC case-study carve-out for Rosalia. |
| 2. Software description – Architecture | `docs/reference/architecture.rst`, `docs/howto/system_sequencing.rst`, `docs/api/*` | `architecture_summary.md`, `pipeline_diagram.*` | Text + figure describing scenario→solver→playback pipeline. Manuscript figure reused in docs `overview`. |
| 2. Software description – Heuristics/tuners | `docs/howto/heuristic_presets.rst`, `docs/howto/parallel_heuristics.rst`, `docs/howto/tabu.rst`, `docs/howto/ils.rst`, `docs/howto/telemetry_tuning.rst` | `heuristic_matrix.csv` + `heuristic_text.md` | CSV drives both manuscript table and Sphinx reference page; describe SA/ILS/Tabu + tuner automation. |
| 3. Illustrative example | `docs/howto/quickstart.rst`, `docs/howto/benchmarks.rst`, `docs/howto/synthetic_datasets.rst` | `illustrative_walkthrough.md`, `benchmark_table.csv` | Align CLI steps + dataset notes; reuse same telemetry screenshots. |
| 4. Impact | `docs/roadmap.rst`, `docs/references/adoption.rst`, release notes | `impact_story.md` | Summarize adoption + roadmap commitments once metrics ready. |
| Metadata tables | `docs/softwarex/reference/README.md`, `README.md`, `pyproject.toml` | `metadata_basics.yaml` | Single YAML feeds both LaTeX metadata tables and Sphinx “About FHOPS” page. |

## Action items

- [ ] Draft `motivation_story.md` (source-of-truth) keyed to Guide-for-Authors requirements; wire exporter to emit `.tex` + `.rst`.
- [ ] Define template + script for table exports (heuristics, benchmark KPIs) so Sphinx and LaTeX stay in sync.
- [ ] Update Sphinx `overview.rst` and `docs/templates/includes/` to ``.. include::`` the generated `.rst` snippets once available.
- [ ] Add CI check (Phase 3) to confirm no drift between `.md` primaries and rendered assets.

> Ownership: Lead author (Gregory Paradis). Automation support: Codex tasks under Phase 1 asset/export work.
