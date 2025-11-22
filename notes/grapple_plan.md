Grapple Harvest-System Action Plan
==================================

Objective: mirror the skyline wiring work for grapple yarders so TN147/TN157/TR122/ADV5N28 (and legacy SR54/TR75) presets have dedicated harvest-system overrides, cost matrix entries, CLI docs, and tests. This lets datasets/synthetic tiers auto-populate the grapple helper inputs and cost roles without reopening the source PDFs.

Progress Tracker
----------------

- [x] **Harvest-system overrides** – `default_system_registry()` now exposes dedicated IDs for TN-147, TN-157 (alias + salvage), TR-122 (extended/shelterwood/clearcut), SR-54, TR-75 (bunched + hand-felled), ADV5N28, and FNCY12. Each preset hard-codes the published turn volume/yarding distance/stems-per-turn (plus relevant manual-falling defaults), and the synthetic tier mixes sample the new systems so datasets auto-fill the helper inputs without manual typing.
- [x] **Cost + documentation alignment** – The Skyline cost matrix already listed the CPI-aware roles; the grapple section of `docs/reference/harvest_systems.rst` now includes a dedicated table mapping every harvest-system ID → helper → defaults → cost role. Notes call out where `--show-costs` falls back to the generic role vs. the BC-specific entries (`grapple_yarder_madill009`, `grapple_yarder_cypress7280`, `grapple_yarder_adv5n28`, `grapple_yarder_tmy45`).
- [x] **CLI/test coverage** – `tests/test_cli_dataset_grapple_yarder.py` now exercises the new harvest-system IDs (TN147, TR122 shelterwood, SR54, TR75 hand-felled) to confirm the overrides fire and the CLI logs “Applied grapple-yarder defaults…”. Synthetic generator mixes were also updated so scenario smoketests keep touching the presets automatically.

Tracking the completed items here keeps the skyline/grapple punchlists aligned and documents the reference IDs to reuse when the next batch of grapple presets (e.g., ADV7N3 salvage decks) land.
