Live Dashboards
===============

Everything under ``https://ubc-fresh.github.io/fhops/`` is rebuilt automatically on every
successful ``main`` run. These artefacts mirror the telemetry tuning workflows described in
:doc:`../howto/telemetry_tuning` so refer to that guide for deeper context.

Direct links:

- `Global telemetry history <https://ubc-fresh.github.io/fhops/telemetry/history_summary.html>`_
  – interactive trend chart.
- `Latest per-scenario history snapshot <https://ubc-fresh.github.io/fhops/telemetry/latest_history_summary.html>`_
  – leaderboard for the latest report label (`.md` source lives alongside the HTML file).
- `Latest tuner report <https://ubc-fresh.github.io/fhops/telemetry/latest_tuner_report.html>`_
  – raw Markdown table rendered as HTML (Markdown source is still published).
- `Latest tuner comparison <https://ubc-fresh.github.io/fhops/telemetry/latest_tuner_comparison.html>`_
  / `leaderboard <https://ubc-fresh.github.io/fhops/telemetry/latest_tuner_leaderboard.html>`_
  – win counts and runtime ratios.
- `Per-bundle difficulty tables <https://ubc-fresh.github.io/fhops/telemetry/tuner_difficulty.html>`_
  – gap + success rates per tier (CSV + Markdown versions live beside the HTML files).
- `History deltas <https://ubc-fresh.github.io/fhops/telemetry/history_delta.html>`_
  – latest vs. previous snapshot change log (HTML rendered from Markdown). CSV/MD sources live beside this file.

Embedded previews
-----------------

If you are browsing these docs on GitHub Pages the most recent dashboards should render inline
below. Each tile links to the full-screen version for deeper inspection.

.. raw:: html

   <style>
   .dashboard-grid {
       display: grid;
       grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
       gap: 1.5rem;
       margin-bottom: 1rem;
   }
   .dashboard-grid iframe {
       width: 100%;
       min-height: 360px;
       border: 1px solid #d0d0d0;
       border-radius: 6px;
       background: #fff;
   }
   </style>
   <div class="dashboard-grid">
     <iframe src="https://ubc-fresh.github.io/fhops/telemetry/history_summary.html"
             title="Telemetry history"></iframe>
     <iframe src="https://ubc-fresh.github.io/fhops/telemetry/latest_history_summary.html"
             title="Latest per-scenario snapshot"></iframe>
     <iframe src="https://ubc-fresh.github.io/fhops/telemetry/latest_tuner_report.html"
             title="Latest tuner report"></iframe>
     <iframe src="https://ubc-fresh.github.io/fhops/telemetry/latest_tuner_comparison.html"
             title="Latest tuner comparison"></iframe>
     <iframe src="https://ubc-fresh.github.io/fhops/telemetry/latest_tuner_leaderboard.html"
             title="Latest tuner leaderboard"></iframe>
     <iframe src="https://ubc-fresh.github.io/fhops/telemetry/tuner_difficulty.html"
             title="Per-bundle difficulty"></iframe>
     <iframe src="https://ubc-fresh.github.io/fhops/telemetry/history_delta.html"
             title="History delta"></iframe>
   </div>

See :ref:`telemetry_dashboard_interpretation` for guidance on how to respond to each signal.
