Analytics Notebooks
====================

The analytics notebook series demonstrates how to analyse FHOPS playback outputs
for deterministic and stochastic scenarios. Each notebook is executed in the
repository and rendered via ``nbsphinx`` during the documentation build.

.. note::
   Continuous integration runs the notebooks in a "light" configuration by setting
   ``FHOPS_ANALYTICS_LIGHT=1`` before execution. This trims stochastic sample counts so the suite
   completes quickly. Unset the variable when you want the full ensemble baselines locally.

.. toctree::
   :maxdepth: 1

   playback_walkthrough
   stochastic_robustness
   what_if_analysis
   landing_congestion
   system_mix
   kpi_decomposition
   ensemble_resilience
   operator_sweep
   telemetry_diagnostics
   tuner_report_analysis
   benchmark_summary
