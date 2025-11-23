Thesis Evaluation Workflow (Chapter 2)
======================================

This guide translates Rosalia Jaffray’s MASc proposal (Chapter 2: “Does FHOPS work, and does it close
the gaps we identified in Chapter 1?”) into a repeatable workflow. Use it when preparing the thesis
case-study experiments: assemble operational datasets, run FHOPS solvers, evaluate KPIs, and document
trade-offs for Chapter 2 narratives.

Context & Goals
---------------

- Chapter 1 (literature review) catalogues BC operational-planning gaps (data accessibility, solver
  transparency, mobilisation awareness, shift-level sequencing).
- Chapter 2 must show that FHOPS can **replicate and improve** existing planning efforts via
  reproducible case studies on small-scale operations.
- Deliverables for each case:

  1. Validated FHOPS scenario (data contract-compliant, shift-aware, mobilisation-enabled).
  2. Baseline solver runs (MIP + heuristics) with traceable KPIs.
  3. Trade-off discussion (production vs mobilisation vs utilisation).
  4. Documentation package (commands, telemetry, plots) that can be cited in the thesis.

Pipeline Overview
-----------------

1. **Curate the Case Dataset**

   - Start from ``examples/med42`` or ``examples/large84`` as a template.
   - Replace ``data/*.csv`` with the case-study inventory (blocks, machines, landings, calendars,
     production rates, optional ``road_construction``).
   - If the case uses known harvest systems, add a ``harvest_system_id`` column per block using IDs from
     :doc:`../reference/harvest_systems`.
   - Record provenance notes (tenure, timeline, data sources) in ``README.md`` for the case folder.

2. **Validate the Scenario**

   .. code-block:: bash

      fhops validate case_study/scenario.yaml

   - Fix reported errors (missing references, shift IDs, schema version) before running solvers.
   - Use ``docs/howto/data_contract.rst`` if new columns/optional extras are required.

   .. seealso::

      :func:`fhops.cli.main.validate` – command reference for the scenario validator (includes all CLI options and schema checks).

3. **Run Baseline Solvers**

   - **MIP (reference solution)**:

     .. code-block:: bash

        fhops solve-mip case_study/scenario.yaml \
          --out case_study/out/mip_solution.csv \
          --driver auto --time-limit 1800

   - **Simulated Annealing (fast heuristic)**:

     .. code-block:: bash

        fhops solve-heur case_study/scenario.yaml \
          --out case_study/out/sa_solution.csv \
          --iters 12000 --seed 42 \
          --operator-preset explore \
          --telemetry-log case_study/out/sa_telemetry.jsonl \
          --show-operator-stats

   - Optional: add ``fhops solve-ils`` and ``fhops solve-tabu`` for comparative analysis.

   - Document runtime, objective values, and solver settings (Chapter 2 must highlight reproducibility).

   .. seealso::

      :func:`fhops.cli.main.solve_mip_cmd`, :func:`fhops.cli.main.solve_heur_cmd`, :func:`fhops.cli.main.solve_ils_cmd`, and :func:`fhops.cli.main.solve_tabu_cmd` – each CLI entrypoint documents the complete option set, telemetry hooks, and solver-specific notes.

4. **Evaluate KPIs & Mobilisation Spend**

   .. code-block:: bash

      fhops evaluate case_study/scenario.yaml case_study/out/mip_solution.csv \
        --shift-out case_study/out/mip_shift.csv \
        --day-out case_study/out/mip_day.csv \
        --summary-md case_study/out/mip_summary.md

   - Collect:

     * ``total_production`` and ``completed_blocks``.
     * ``mobilisation_cost`` and ``mobilisation_cost_by_machine`` (Chapter 1 gap: no cost audit).
     * ``utilisation_ratio`` (shift/day), ``makespan``.
     * ``sequencing_violation_*`` counts (showing constraints hold).

   - Repeat for heuristic schedules. Compare KPI deltas in a table (include convergence rationale).

   .. seealso::

      :func:`fhops.cli.main.evaluate` for KPI-only summaries and :func:`fhops.cli.main.eval_playback` for shift/day playback exports (deterministic or stochastic).

5. **Benchmark Trade-offs**

   - Run the benchmark harness to quantify solver differences and generate plots:

     .. code-block:: bash

        fhops bench suite --scenario case_study/scenario.yaml \
          --include-ils --include-tabu --out-dir case_study/bench \
          --time-limit 900 --sa-iters 12000 --tabu-iters 8000 --ils-iters 400
        python scripts/render_benchmark_plots.py case_study/bench/summary.csv \
          --out-dir case_study/bench/plots

   - Use the summary CSV/JSON to extract:

     * Objective gap vs best heuristic (evidence of improved solution quality).
     * Runtime ratios (feasibility for small-scale operators).
     * Operator telemetry (link back to mobilization-aware operators when discussing Chapter 1 needs).

   .. seealso::

      :func:`fhops.cli.benchmarks.bench_suite` – benchmark CLI helper that powers ``fhops bench suite``.

6. **Synthesize Chapter 2 Materials**

   - Insert KPI tables, mobilisation spend charts, and sequencing status into the chapter draft.
   - Reference appendix artefacts: telemetry logs, shift/day CSVs, benchmark plots.
   - Describe how FHOPS addresses Chapter 1 gaps (e.g., distance-aware mobilisation, shift calendars,
     open-source reproducibility).

Worked Example (med42 Template)
-------------------------------

1. Copy ``examples/med42`` to ``case_study/``; replace ``data/`` with the case inventory.
2. Run validation + solvers as above. Capture commands and seeds for thesis appendices.
3. Highlight insights:

   - ``kpi_mobilisation_cost`` decreased by X % when switching from default to mobilisation-focused
     operator preset.
   - Sequencing violations remained zero, confirming registry accuracy for the target system.
   - Runtime remained under N minutes on lab hardware (relevant for small operations).

4. Discuss trade-offs (production vs mobilisation vs utilisation) with references to Chapter 1 gaps.

Tips & References
-----------------

- Maintain a ``case_study/log.md`` file capturing every command, seed, and data edit (supports Chapter 2 audit trail).
- Include small screenshots or plots (generated from ``case_study/bench/plots``) to visualise KPI movement.
- Cite the proposal folders under ``tmp/jaffray-rosalia-masc-*`` when referencing scope and motivation.
- Keep FHOPS docs updated (see ``notes/sphinx-documentation.md``) whenever new thesis-driven workflows appear.
