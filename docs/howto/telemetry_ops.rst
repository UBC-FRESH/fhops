Telemetry Ops Runbook
=====================

This runbook codifies the “always-on” telemetry workflow for FHOPS: how we capture tuning
runs, keep the weekly analytics notebooks current, maintain the telemetry store, and publish
artefacts (CI + GitHub Pages). Use it as the operational checklist for Phase 4.

Weekly Notebook Pipeline
------------------------

1. **Schedule**

   - CI: primary workflows run on every push; the “full analytics” notebook suite should run at
     least **weekly** via a scheduled GitHub Actions workflow (e.g., Sunday 03:00 UTC) to keep
     stochastic KPIs fresh.
   - Local smoke: when large changes land, run notebooks (`scripts/run_analytics_notebooks.py --light`)
     before opening a PR.

2. **Commands**

   .. code-block:: bash

      # Light CI run (already wired in workflows)
      python scripts/run_analytics_notebooks.py --out docs/examples/analytics --light

      # Full local run before the weekly upload (no --light)
      python scripts/run_analytics_notebooks.py --out tmp/analytics_full

   - Ensure ``FHOPS_ANALYTICS_LIGHT=1`` is **unset** for the weekly full run so stochastic ensembles
     execute at full sample counts. Record duration in the workflow logs.

3. **Artefact handling**

   - CI stores ``analytics-notebooks`` (rendered HTML/MD) and ``telemetry-report`` (CSV/MD/HTML) as artifacts.
   - Weekly workflow should download the latest ``telemetry-report`` artifact, append it to
     ``docs/examples/analytics/data/tuner_reports/``, and re-run the history script (see below).
   - If GitHub Pages is enabled, publish the refreshed HTML files (`history_summary.html`,
     `history_delta.html`, analytics notebooks) to the Pages branch.

Telemetry Store Maintenance
---------------------------

* **Location** – default telemetry directory: ``telemetry/`` (JSONL, SQLite, history snapshots).
* **Rotation policy**

  - Keep the **latest 4 weeks** of JSONL/SQLite telemetry in the repo (rename older files to
    `.archive/` or move to long-term storage to prevent bloat).
  - Archive large step logs (``telemetry/steps/*.jsonl``) after generating summary reports.

  .. seealso::

     :func:`fhops.cli.telemetry.prune` – CLI helper for trimming run logs and deleting aligned step files.

* **Vacuum & integrity**

  .. code-block:: bash

     sqlite3 telemetry/runs.sqlite "PRAGMA optimize; VACUUM;"
     sqlite3 telemetry/runs.sqlite "PRAGMA quick_check;"

  Run weekly (after the full notebook workflow) to keep the SQLite store compact and healthy.

* **Locks/contention**

  - Avoid simultaneous writes to the same JSONL/SQLite file (especially when running multiple tuning
    commands concurrently). Use separate ``--telemetry-log`` paths per developer or configure the CI
    job to serialize writes.
  - If a workflow crashes mid-write, delete the partially written row from the JSONL file and re-run.
    SQLite should remain consistent thanks to WAL journaling, but ``PRAGMA quick_check`` will confirm.

Automation Checklist
--------------------

1. **CI (per push)**

   - `fhops tune-grid` / `fhops tune-random` on smoke scenarios (minitoy, med42).
   - `fhops telemetry report` → `telemetry-report` artifact with `tuner_report.{csv,md}`, `history/`.
   - `scripts/analyze_tuner_reports.py --history-dir` to regenerate `history_summary.*` and `history_delta.*`.

2. **Weekly full run**

   - Execute notebooks without `--light`.
   - Run the longer tuning bundles (e.g., `fhops tune-bayes --bundle synthetic --trials 6`).
   - Rebuild history charts and push to GitHub Pages.
   - Commit updated history CSV/MD files if the repo tracks canonical snapshots.

3. **Manual interventions**

   - When telemetry schema fields change, update `scripts/analyze_tuner_reports.py` and rerun the
     history command so older snapshots stay compatible (document the migration in `CHANGE_LOG.md`).
   - If GitHub Pages fails to update, inspect the Pages workflow logs and check for large HTML files
     (GitHub rejects >100 MB). Trim sample counts or compress images as needed.

.. seealso::

   :func:`fhops.cli.main.solve_heur_cmd`, :func:`fhops.cli.main.solve_ils_cmd`, and :func:`fhops.cli.main.solve_tabu_cmd` – solver entrypoints that emit ``--telemetry-log`` metadata used by this runbook.
   :func:`fhops.cli.main.tune_random_cli`, :func:`fhops.cli.main.tune_grid_cli`, and :func:`fhops.cli.main.tune_bayes_cli` – tuning orchestrators responsible for the weekly telemetry bundles.
   :func:`fhops.cli.benchmarks.bench_suite` – benchmarking command that feeds KPI comparisons into the telemetry store.
   :func:`fhops.cli.telemetry.report` – generates CSV/Markdown summaries from ``telemetry/runs.sqlite`` for publication.

Runbook Template (per week)
---------------------------

.. code-block:: text

   Week of YYYY-MM-DD
   -------------------
   [ ] Run full notebooks (duration: __)
   [ ] Run extended tuning bundles (commands + seeds)
   [ ] Generate telemetry report / history / delta
   [ ] Upload analytics + telemetry artefacts (CI + Pages)
   [ ] Vacuum telemetry/runs.sqlite
   [ ] Archive >4-week-old telemetry logs
   [ ] Update README badges if history chart moved

Keep a copy of this checklist in `docs/howto/telemetry_ops.rst` (or a shared issue template) and
tick each box when the weekly workflow completes.

References
----------

- :doc:`telemetry_tuning` – CLI usage, report interpretation, dashboard links.
- `.github/workflows/*telemetry*.yml` – scheduled workflow definitions (tune, notebooks, Pages).
- `scripts/run_analytics_notebooks.py` – executed commands for notebooks.
- `scripts/analyze_tuner_reports.py` – history/delta generation.
