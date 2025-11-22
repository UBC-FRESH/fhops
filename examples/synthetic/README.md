Synthetic Reference Datasets
============================

This directory contains ready-to-use synthetic FHOPS scenario bundles generated via
``fhops.scenario.synthetic.generate_random_dataset``.

Bundles
-------

* ``small`` – 4 blocks, 6 days, 2 machines.
* ``medium`` – 8 blocks, 12 days, 4 machines.
* ``large`` – 16 blocks, 18 days, 6 machines (two shifts per day).

Each bundle includes a ``scenario.yaml`` pointing at the CSV tables under ``data/``. The YAML can be
loaded directly with ``fhops.scenario.io.load_scenario``; the regression tests (`tests/test_synthetic_dataset.py`)
exercise this path to ensure compatibility.

Harvest systems
---------------

``data/blocks.csv`` includes a ``harvest_system_id`` column for every tier. The values map directly to the
registry documented in ``docs/reference/harvest_systems.rst``. Filter the column (e.g.,
``cut -d, -f14 data/blocks.csv | sort -u``) to see which systems are used before running solver tests.

Columns & metadata
------------------

The generators now attach terrain/prescription tags to every block and assign each machine to a crew
with recorded capability notes. The tables therefore expose:

* ``blocks.csv`` — includes ``terrain`` and ``prescription`` columns alongside the scheduling window.
* ``machines.csv`` — adds a ``crew`` column mapping machines to the generated crew IDs.
* ``crew_assignments.csv`` — the scenario-level mapping written for the loader/validators so downstream
  tooling can recover crew → machine relationships.

Bundle metadata is captured in two places:

* ``examples/synthetic/<tier>/metadata.yaml`` summarises the sample-level counts, terrain/prescription mix,
  crew capability pools, and blackout windows.
* ``examples/synthetic/metadata.yaml`` aggregates the same information for all tiers so automation can
  reference the library without reading every directory.

Reproducibility
---------------

The seeds and high-level statistics for each bundle live in ``metadata.yaml``. Regenerate a bundle with:

.. code-block:: python

   from pathlib import Path
   from fhops.scenario.synthetic import SyntheticDatasetConfig, generate_random_dataset

   config = SyntheticDatasetConfig(...)
   bundle = generate_random_dataset(config, seed=123)
   bundle.write(Path("examples/synthetic/custom"))
