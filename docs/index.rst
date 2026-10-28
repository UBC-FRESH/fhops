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

   overview
   howto/quickstart
   howto/tree_scale
   howto/data_contract
   howto/benchmarks
   howto/heuristic_presets
   howto/mip_warm_starts
   howto/optimization_formulation
   howto/parallel_heuristics
   howto/evaluation
   howto/thesis_eval
   howto/telemetry_tuning
   howto/telemetry_ops
   howto/release_playbook
   howto/synthetic_datasets
   howto/system_sequencing
   howto/ils
   howto/tabu
   howto/rolling_horizon
   howto/tactical_operational
   howto/hauling
   howto/hydrology_quickstart
   howto/web

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api/index
   reference/cli
   reference/playback_aggregates
   reference/harvest_systems
   reference/hauling
   reference/hauling_formulation
   reference/web
   reference/telemetry
   reference/dashboards
   reference/source_bibliography
   reference/femic_lidar
   reference/femic_lidar_fixture
   reference/femic_hydrology
   reference/hydrology_contract_index
   reference/tree_inventory
   reference/stem_models
   reference/tree_simulation
   reference/tree_replay
   reference/tree_scene
   reference/tree_system

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
