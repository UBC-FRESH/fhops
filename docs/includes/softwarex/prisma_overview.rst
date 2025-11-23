.. FHOPS SoftwareX PRISMA overview

FHOPS uses the same PRISMA-inspired workflow diagram in both the SoftwareX manuscript
and the user guide. The LaTeX source lives at
``docs/softwarex/manuscript/sections/includes/prisma_overview.tex`` and is rendered
whenever ``make assets`` runs. Until we add an auto-exported PNG, the Sphinx docs reuse
the narrative from that figure instead of embedding the raw TikZ diagram.

**Pipeline summary**

1. **Inputs:** Scenario contract artefacts (blocks, machines, landings, calendars) plus
   curated reference datasets and automation configs.
2. **FHOPS core:** Data-ingest validators, solver stack (MIP + SA/ILS/Tabu with tuner
   harness), and evaluation/telemetry modules.
3. **Shared artefacts:** Benchmark tables, tuning leaderboards, playback + robustness
   summaries, costing demos, scaling sweeps, and Markdown/CSV snippets rendered via
   ``export_docs_assets.py``.
4. **Outputs:** SoftwareX manuscript assets, the reproducible submission bundle, and the
   mirrored Sphinx documentation sections that highlight FHOPS’ differentiators.

.. note::
   Once the PNG export workflow lands we will replace this textual summary with a direct
   ``.. figure::`` reference so the documentation shows the exact same visual as the
   manuscript.
