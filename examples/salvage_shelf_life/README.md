# Salvage shelf-life example

This example joins a two-row storage/age table to the bundled `tiny7` scenario.
It is a reporting example, not a salvage schedule.

```bash
fhops report salvage-shelf-life \
  examples/tiny7/scenario.yaml \
  examples/salvage_shelf_life/storage.csv \
  --value-per-m3 10 \
  --out-dir tmp/salvage
```

`storage.csv` supplies only the age axis. Block volume comes from the scenario's
`work_required` field. The packaged retention curve is the published mixed-conifer
fire-killed reference curve described in `docs/howto/salvage_shelf_life.rst`; it
is not a BC-specific or species-specific operational curve.
