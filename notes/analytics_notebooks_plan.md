# Analytics Notebook Plan

Date: 2025-11-11  
Status: Draft — scaffolding notebooks that surface deterministic and stochastic analytics workflows.

## Objectives
- Provide executed notebooks that demonstrate schedule playback, KPI diagnostics, and what-if analysis.
- Showcase both deterministic and stochastic tooling using lightweight scenarios (minitoy + synthetic bundles).
- Reuse shared plotting/utility code so notebooks stay consistent and easy to maintain.

## Notebook Targets
1. **Playback & KPI Walkthrough (deterministic)**
   - Scenario: `examples/minitoy/scenario.yaml`
   - Story beats:
     - Load scenario + assignments, run deterministic playback.
     - Visualise shift/day tables, highlight key KPI outputs.
     - Introduce basic charts (production over days, machine utilisation).
2. **Stochastic Robustness Explorer**
   - Scenario: `examples/synthetic/medium/scenario.yaml` (SA assignments from CLI).
   - Story beats:
     - Generate stochastic ensemble using `sampling_config_for`.
     - Plot aggregates (production distribution, weather impact, utilisation bands).
     - Summarise risk metrics (mean/std, quantiles, downtime vs weather components).
3. **What-If Scenario Tweaks**
   - Base: start from mini toy or synthetic medium, adjust parameters inline (e.g., add downtime bias, adjust landing capacity).
   - Compare pre/post KPIs and visualise differences.

## Shared Utilities
- Module: `docs/examples/analytics/utils.py` *(implemented)*
  - `load_playback_tables(scenario_path, assignments_path)`
  - `run_stochastic_summary(scenario_path, assignments_path, sampling_config)`
  - Chart helpers (`plot_production_series`, `plot_utilisation_heatmap`, `plot_distribution`).
- Plot stack: prefer Altair for interactive views (fallback to matplotlib for static fallback).
- Output cache: store derived CSV/JSON under `docs/_build/analytics/` to keep notebooks lightweight when re-running.

## Execution & Automation
- Place notebooks under `docs/examples/analytics/`:
  - `playback_walkthrough.ipynb`
  - `stochastic_robustness.ipynb`
  - `what_if_analysis.ipynb`
- Store deterministic/stochastic assignment CSVs under `docs/examples/analytics/data/` for reproducible runs.
- [x] Flesh out notebooks with narrative walkthroughs and executed outputs (scenario overview, KPIs, plots).
- Provide `scripts/run_analytics_notebooks.py` to execute notebooks via `papermill`.
- CI smoke target: execute notebooks with reduced sampling counts (configurable via environment variables).

## Documentation Integration
- Use `nbsphinx` to render notebooks within Sphinx (`docs/examples/analytics/index.rst`). ✅
- Update `docs/index.rst` “Examples” to include the analytics notebooks. ✅
- Mention notebooks in `README.md` and `docs/howto/evaluation.rst` for discoverability. *(todo)*

## Open Questions
- Do we expand the what-if notebook to include solver reruns, or keep it playback-only for now?
- Decide whether to bundle pre-rendered images when runtime is high (fallback to cached HTML exports?).

## Next Actions
- [x] Scaffold utilities module (`docs/examples/analytics/utils.py`) and add minimal plotting helpers.
- [x] Create empty notebooks with headers/storyboard cells.
- [x] Wire `nbsphinx` / documentation index to anticipate the new notebooks.
- [ ] Prepare reduced sampling config for CI smoke execution.
