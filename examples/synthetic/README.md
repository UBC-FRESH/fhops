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

Reproducibility
---------------

The seeds and high-level statistics for each bundle live in ``metadata.yaml``. Regenerate a bundle with:

.. code-block:: python

   from pathlib import Path
   from fhops.scenario.synthetic import SyntheticDatasetConfig, generate_random_dataset

   config = SyntheticDatasetConfig(...)
   bundle = generate_random_dataset(config, seed=123)
   bundle.write(Path("examples/synthetic/custom"))
