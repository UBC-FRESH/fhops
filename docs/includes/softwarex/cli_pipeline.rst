.. AUTO-GENERATED from cli_pipeline.md -- do not edit directly.

All experiments cited in the manuscript follow the same FHOPS CLI
pipeline so readers can replay each stage without bespoke tooling:

1. **Validate or snapshot scenarios.** Run
   ``fhops dataset validate <scenario.yaml>`` for each bundle (e.g.,
   ``examples/tiny7`` and ``examples/med42``) and, when needed, snapshot
   synthetic tiers via
   ``fhops synth generate out/synthetic_{small,medium,large}`` with
   fixed RNG seeds.
2. **Benchmark solvers.** Invoke ``fhops bench suite`` with explicit
   ``--scenario`` and ``--out-dir`` arguments (for the manuscript:
   ``docs/softwarex/assets/data/benchmarks/<slug>/``) plus the desired
   heuristics (``--include-ils``, ``--include-tabu``) and iteration
   budgets.
3. **Run the tuning harness.** Launch
   ``python docs/softwarex/manuscript/scripts/run_tuning_benchmarks.py``
   (wrapped by ``scripts/generate_assets.sh``) to produce
   leaderboard/comparison tables in
   ``docs/softwarex/assets/data/tuning/``.
4. **Replay schedules.** Call ``fhops playback`` on the best SA/ILS
   assignments (deterministic and stochastic modes) so utilisation and
   downtime metrics land under
   ``docs/softwarex/assets/data/playback/<scenario>/<solver>/<mode>/``.
5. **Estimate costs.** Execute ``fhops dataset estimate-cost`` for each
   machine bundle to capture owning/operating/repair totals in
   ``docs/softwarex/assets/data/costing/``.
6. **Synthetic scaling sweep.** Use
   ``python docs/softwarex/manuscript/scripts/run_synthetic_sweep.py``
   to regenerate runtime-vs-size CSV/JSON + plots under
   ``docs/softwarex/assets/data/scaling/``.

Each command appends its parameters, commit hash, runtime, and SHA-256
digests to ``docs/softwarex/assets/benchmark_runs.log`` (when run
through ``make manuscript-benchmarks`` or
``scripts/generate_assets.sh``), providing a single provenance log for
all artefacts.
