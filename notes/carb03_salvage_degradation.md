# CARB-03: Salvage shelf-life and wood degradation

Status: first bounded slice implemented under P44 (parent #380, child #381).
This note is the authoritative design and provenance record for the FHOPS
implementation. It does not claim a complete `CARB-03` model.

## Why this exists

`CARB-03` (wood degradation and storage value loss) and its sibling `DIS-09`
(salvage shelf-life) identify a real gap: FHOPS has salvage harvest systems and
an optional `salvage_processing_mode` block field, but it has no time-dependent
degradation or product-shelf-life surface. A salvage block is therefore treated
as if its wood were green.

The IRSS/Silva21 queue points at two sources:

- Chagnon et al. (2022), *Broad-scale wood degradation dynamics in the face of
  climate change*, GCB Bioenergy 14:941-958,
  <https://doi.org/10.1111/gcbb.12951>.
- Silva21 AD 4, *Salvage harvesting of dead trees*,
  <https://www.silva21.com/projects/salvage-harvesting-of-dead-trees>.

Chagnon et al. is a meta-analysis of time-since-death by decay class. It gives a
published climate-sensitive regression, but it does **not** publish product-value
loss factors or a merchantable-grade mapping. Building a value model from it
would require a new decay-class-to-product mapping, which would be invented
science. It is therefore recorded as context, not used for numeric coefficients.

The Silva21 AD 4 project page is a 2024-2025 research project description; its
deliverable is not yet a public coefficient table. It points to the shelf-life
review by Barrette et al. (2015), which is public.

## Sources used for the first slice

### Numeric retention curve

Prestemon, J.P. and Holmes, T.P. (2008). "Timber Salvage Economics." In:
Holmes, T.P., Prestemon, J.P., Abt, K.L. (eds), *The Economics of Forest
Disturbances*. Springer, Dordrecht, pp. 167-190, section 4.2.6. Public PDF:
<https://research.fs.usda.gov/download/treesearch/32962.pdf>.

The report states the weighted-average net volume discount factors used in its
Biscuit fire analysis: **0.99 after 1 year, 0.89 after two years, 0.58 after
three years, 0.22 after four years, and zero after five years**. The factors
come from Lowell and Cahill (1996) for years 1-3 and Prestemon et al. (2006) for
years 4-5.

These numbers are encoded exactly in
`data/reference/degradation/salvage_decay.v1.json` as the
`pnw_fire_killed_mixed_conifer` curve. FHOPS adds no points and fits no model.
Ages between published years use linear interpolation; ages after the last
point use the last published fraction (zero).

**Boundary:** mixed-conifer fire-killed timber in southwest Oregon. This is a
reference curve, not a BC-specific, species-specific, or roadside-storage
specific operational curve. It must not be presented as a BC salvage rule.

### Product shelf-life windows

Barrette, J., Thiffault, E., Saint-Pierre, F., Wetzel, S., Duchesne, I. and
Krigstin, S. (2015). "Dynamics of dead tree degradation and shelf-life following
natural disturbances: can salvaged trees from boreal forests 'fuel' the forestry
and bioenergy sectors?" *Forestry* 88(3):275-290,
<https://doi.org/10.1093/forestry/cpv007>. Abstract mirrored at
<https://hero.epa.gov/reference/6726560/>.

The review states that the most suitable time to salvage for lumber is generally
limited to 1-2 years after death; pulp is usually not recommended after 3-4
years; past that period, bioenergy may be the better outlet. The Silva21 AD 4
context presentation by Hébert, Duchesne and Mvolo (IEA Bioenergy / Université
Laval, 2023) repeats the same shelf-life summary and cites Barrette et al.:

<https://task43.ieabioenergy.com/wp-content/uploads/sites/38/2023/10/Hebert-Duchesne-Mvolo_Post-fire-salvage-logging-in-Canada.pdf>.

The windows are encoded as advisory, overlapping windows. They are not a
mill-acceptance rule.

## What landed

- `src/fhops/salvage/degradation.py`: typed `salvage.decay.v1` curve library,
  provenance/boundary records, linear retention interpolation, product windows.
- `data/reference/degradation/salvage_decay.v1.json`: the published curve and
  product windows with citation, URL, boundary, and retrieval date.
- `src/fhops/salvage/report.py`: read-only consumer that joins a storage/age
  CSV to scenario blocks and reports original volume (`Block.work_required`),
  retention fraction, retained volume, optional retained value, and eligible
  products.
- `fhops report salvage-shelf-life`: CLI surface with optional CSV/Markdown
  output.
- Tests: `tests/test_salvage_degradation.py` and
  `tests/test_cli_report_salvage.py`.
- Docs: `docs/howto/salvage_shelf_life.rst`,
  `docs/api/fhops.salvage.rst`.
- Example: `examples/salvage_shelf_life/`.

## What deliberately did not change

- No MILP objective, constraint, heuristic, or solver code.
- No scenario schema change. Age is supplied by a side table.
- No price forecast. `--value-per-m3` is optional and caller-supplied; the report
  labels the result as a volume-retention proxy at a constant unit value.
- No grade recovery, lumber-price, or market model.
- No ws4 carbon-engine change. The curve contract is general enough for ws4 to
  consume later, but that would be a separate phase with its own review.
- No new curve points or fitted coefficients.

## Remaining work and blockers

1. **BC or species-specific curve.** The first curve is a US Pacific Northwest
   reference. A BC curve needs a public or project-approved source with explicit
   retention factors by species/product and a stated climate/storage boundary.
   A candidate source is the BC deadwood synthesis by Huggard and Kremsater
   (2007), but it is a habitat-decay synthesis, not a product-value curve, so it
   was not used here.
2. **Roadside storage duration.** The first curve is time since fire/death, not
   time in a roadside deck. A dedicated storage curve needs a public source for
   decking loss by species/season/product.
3. **Product-specific value.** Barrette et al. gives shelf-life windows, not
   value-loss percentages. A value model needs grade recovery and price data.
4. **ws4 consumer.** A ws4 carbon/valuation consumer should be a separate phase
   once a BC-relevant curve exists. Do not silently reuse the US reference curve
   as a BC operational assumption.

## Audit of current state

- FHOPS before this slice: `salvage_processing_mode` existed on blocks and
  salvage harvest presets existed, but `grep` found no decay/shelf-life/value
  retention code. `notes/03-fresh-gap-analysis.md` already recorded this gap.
- ws4 before this slice: carbon pools and `prices.v1` exist, but no wood-product
  degradation or salvage value-loss surface.
- IRSS registry before this slice: `CARB-03` and `DIS-09` were `shortlisted`,
  wave 2, with `CARB-03` depending on `DIS-09`.

## Verification

Commands run in the P44 worktree:

```bash
ruff format src tests
ruff check src tests
mypy src
pytest
sphinx-build -b html docs _build/html -W
```

Targeted results are recorded in `CHANGE_LOG.md`. The registry reconciliation is
recorded in `irss-expansion/CHANGE_LOG.md`.
