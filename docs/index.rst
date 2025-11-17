FHOPS Documentation
===================

Welcome to the Forest Harvesting Operations Planning System (FHOPS) docs. These pages explain the
platform architecture, data contract, optimisation stack, heuristics, and evaluation workflows. The
structure mirrors our roadmap so that implementation status stays transparent.

The executed analytics notebook suite (:doc:`examples/analytics/index`) demonstrates end-to-end
playback, stochastic robustness, and benchmarking stories. The notebooks run in CI with the
``FHOPS_ANALYTICS_LIGHT=1`` flag to keep stochastic samples lightweight; unset it locally for full
ensembles.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   reference/dashboards
   overview
   howto/quickstart
   howto/data_contract
   howto/benchmarks
   howto/heuristic_presets
   howto/parallel_heuristics
   howto/evaluation
   howto/telemetry_tuning
   howto/synthetic_datasets
   howto/system_sequencing
   howto/ils
   howto/tabu

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api/index
   reference/cli
   reference/playback_aggregates
   reference/harvest_systems
   reference/telemetry

.. toctree::
   :maxdepth: 1
   :caption: Examples

   examples/robustness
   examples/analytics/index

.. toctree::
   :maxdepth: 1
   :caption: Project Processes

   contributing
   roadmap
   howto/mobilisation_geo
   planning/productivity_gaps
