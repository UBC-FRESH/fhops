> Public project-note copy. The full instance design note is kept at
> `femic/external/femic-mkrf-instance/planning/2026-11-18_variable-retention-basis.md`.
> This copy is the discoverable summary for the FHOPS/MKRF project notes.

# Variable-retention basis and model design

Status: **research and design note; not locked, not implemented as a final
treatment yet**

Date: 2026-11-18

## Bottom line

The BC Ministry of Forests' silvicultural-systems material defines the
**retention system** qualitatively, not as a single numeric "x% retention"
rule. The operational convention is:

- **aggregated / group retention:** percent of **gross cutblock area**;
- **dispersed / single-tree retention:** percent of **pre-harvest basal area**.

That convention is stated explicitly in the BC TFL 44 management plan and in
the peer-reviewed BC variable-retention review:

> "Percentages refer to basal area for dispersed retention and gross cutblock
> area for group retention."
>
> — BC TFL 44 Management Plan 4, Appendix V, Stewardship Zones, p. 1

> "Unless otherwise noted, percent retention refers to area when referring to
> aggregated (group) retention and basal area when referring to dispersed
> (single tree) retention."
>
> — Beese et al. 2019, *Ecological Processes* 8:33, p. 7

The BC Silviculture Prescription Guidebook requires a dispersed-retention
prescription to state the "planned basal area or stand density to be retained
after harvesting." The RESULTS retention procedures describe retention levels
in **m²/ha basal area**, and the 2024 stand-level retention protocol converts
dispersed retention to **basal-area-equivalent hectares** by dividing retained
BA by the pre-harvest BA from the same BEC zone.

So the proposed answer is:

1. **If the MKRF prescription is dispersed leave-tree retention, use percent of
   pre-harvest basal area as the primary decision variable.** Select
   Douglas-fir first, largest DBH first, until the retained-BA target is met.
   Report stem count, volume, value, and crown cover as outputs.
2. **If it is group retention, use percent of gross cutblock area** and retain
   whole groups. Do not select the largest DBH for a group-retention
   percentage.
3. **Do not use one "x%" number for a mixed prescription.** Carry separate
   dispersed-BA and group-area parameters.

Crown cover and stem count are legitimate measurable retention targets, but
they produce very different residual populations. The BC SEDRSS guide requires
retention to be expressed as a measurable unit such as basal area, stems per
hectare, or volume, with a target, minimum, and maximum. It does not make crown
cover the universal basis.

## Source audit

| Source | What it establishes | Use in this note |
| --- | --- | --- |
| BC Ministry of Forests, *Silvicultural Systems Handbook for British Columbia* (2003), Part 2.1, "Retention System" | Retention system definition: retain individual trees or groups for at least one rotation; >50% of the cutblock within one tree height of retained trees; retention system is distinct from clearcut with reserves | Defines the silvicultural system; does **not** define x% as BA, stems, or crown |
| BC Ministry of Forests, *Silviculture Prescription Guidebook*, "Stocking requirements for other even-aged partial cutting systems" | Prescription must state "planned basal area or stand density to be retained after harvesting" | Dispersed retention needs a BA or density target |
| BC Ministry of Forests, *Procedures for Submitting Forest Cover Retention Data to RESULTS*, Edition 1.4, §1 and §3 | Retention/residual definitions; retention examples span low (>5 m²/ha) to high **basal area** retention; group vs dispersed reserve types | RESULTS records residual BA; group is full-retention area |
| BC Ministry of Forests, *Stand-level Retention Monitoring Protocol* (2024, v6), dispersed-retention section | Percent dispersed retention = measured retained BA / average pre-harvest BA; converted to **basal-area-equivalent hectares** for forest influence | Gives the conversion from BA to area-equivalent |
| BC TFL 44 Management Plan 4, Appendix V, Stewardship Zones, p. 1 | "Percentages refer to basal area for dispersed retention and gross cutblock area for group retention." | The clearest BC operational statement of the two bases |
| BC BCTS, *Single Entry Dispersed Retention System Operational Guide* (2011), Definitions and p. 9 | Retention system definition; SEDRS residual BA range 5–39 m²/ha; retention levels must be measurable units such as BA, sph, or volume with target/min/max | Confirms BA is a normal dispersed-retention unit; also allows stems/volume if specified |
| Beese et al. 2019, *Ecological Processes* 8:33, p. 7 | In BC, percent retention means area for aggregated retention and BA for dispersed retention unless otherwise noted | Independent peer-reviewed confirmation of the convention |

### What the provincial definition does and does not say

The 2003 handbook's retention-system definition is qualitative:

- retain individual trees or groups of trees;
- maintain structural diversity over the cutblock for at least one rotation;
- leave more than half the cutblock within one tree height of retained trees.

It does **not** say "20% retention means 20% of basal area" or "20% of stems."
The numeric basis is set by the prescription, stocking standard, or operational
plan. The consistent provincial convention for dispersed retention is BA; for
group retention it is area.

A treatment called "CC with retention" also needs a terminology check:

- If the leave trees are not distributed enough to meet the >50% forest
  influence test, it is a **clearcut with reserves**, not the formal retention
  system.
- If retained trees are distributed over the block and meet the influence test,
  it is a **retention system** (group, dispersed, or mixed).
- Either way, the **quantity** of retention must be defined explicitly.

## Why the basis matters: MKRF 684 example

The pinned `mkrf_684` tree list is one synthetic 6.86 ha stand (4,798 stems;
699 TPH; 82.48 m²/ha total BA; 4,116.6 m³; CAD 434,150 gross value at the game
price deck). It is not an estate inventory, but it is a useful controlled
example.

Selecting the largest Douglas-fir first, against three different definitions of
"10% retention":

| Basis | Target | Residual stems | Residual TPH | BA retained | Volume retained | Gross value retained | Minimum residual DF DBH |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BA | 10% | 59 | 8.6 | 10.1% | 14.2% | 14.1% | 96.1 cm |
| Stems | 10% | 480 | 69.9 | 37.8% | 45.9% | 46.0% | 55.4 cm |
| Crown projection (overlap not corrected) | 10% | 23 | 3.4 | 4.9% | 7.1% | 7.1% | 111.2 cm |

The 5% stem case is the source of the earlier "5% of stems -> 32.6% of gross
value" audit result. It is **not** a 5% basal-area target:

| Basis | Target | Residual stems | BA retained | Volume retained | Gross value retained |
| --- | ---: | ---: | ---: | ---: | ---: |
| BA | 5% | 24 | 5.1% | 7.4% | 7.3% |
| Stems | 5% | 240 | 25.4% | 32.6% | 32.6% |

Full table: `planning/2026-11-18_retention_basis_example.csv`.

This is the central modelling consequence: a prescription that says "leave
10%" can mean 8.6 TPH of very large fir (10% BA), 69.9 TPH including much
smaller fir (10% stems), or 3.4 TPH of the very largest crowns (10% crown
projection). The volume and revenue impact changes by a factor of roughly two
to six.

## Current MKRF model: what is actually implemented

The current ForestModelXML `<retention>` rule is an **initial area split**, not
a final-harvest treatment:

- `ws4/io/forest_model_xml.py` describes retention as "move a fraction of the
  area to another state."
- `ws4/build/compiler.py` allocates `area * (1 - factor)` to the managed state
  and `area * factor` to the retained/unmanaged state.
- The current MKRF XML has factors of 0.1 and 0.2 by silviculture group.
- The retained area is moved to an unmanaged state **before** the CC treatment;
  there is no species/DBH selection, no product net-out, and no treatment-time
  split between a harvested plantation and a residual big-DF cohort.
- `treatments.retain` exists in the schema and has CT values of 20 in the
  legacy review table, but the WS4 simulator does not use that field to create a
  residual cohort or split a treatment.

So the current low/base/high descriptions are **area-retention / area-set-aside
screens**, not largest-DF dispersed-retention treatments.

## Available data

### VRI 2016

The public MKRF VRI layer has per-polygon:

- live stems per hectare;
- basal area;
- crown closure;
- species composition;
- height and age;
- leading species and site index.

Joining VRI to the 1,763 MKRF fragments gives numeric BA/TPH for about 1,755
fragments; 1,630 pass the screening filters used below. Deriving QMD from BA
and TPH gives a useful age trend:

| Age bin | Blocks | Median QMD (cm) | Median BA (m²/ha) | Median TPH |
| --- | ---: | ---: | ---: | ---: |
| 0–20 | 156 | 28.6 | 45 | 700 |
| 20–40 | 153 | 20.6 | 25 | 900 |
| 40–60 | 365 | 34.9 | 50 | 500 |
| 60–80 | 457 | 45.6 | 65 | 375 |
| 80–100 | 188 | 50.5 | 68.5 | 325 |
| 100–120 | 78 | 57.5 | 70 | 262.5 |
| 120–140 | 45 | 65.1 | 75 | 225 |
| 140–180 | 146 | 62.4 | 70 | 200 |

The trend is usable for scaling, but VRI does **not** carry a species-specific
DBH distribution. It gives species shares and total BA/TPH, not a DBH CDF.

### FAIB PSP tree detail

The workspace has the full FAIB PSP tree table (3.2M tree records) and plot
headers. For CWHdm/CWHvm, after filtering live Douglas-fir with DBH 5–150 cm,
there are 23,141 tree records on 257 sites. CWHdm alone has 14,055 live FD
records on 116 sites.

The age support is uneven:

| Age window | FD records | Sites |
| --- | ---: | ---: |
| 60–80 | 498 | 12 |
| 80–100 | 2,790 | 27 |
| 100–120 | 5,409 | 31 |
| 120–140 | 58 | 1 |
| 140–180 | 2,817 | 13 |
| 180–250 | 783 | 6 |

This is **not a clean chronosequence**: the age windows mix sites, BEC
variants, regions, and sampling designs. The raw age-bin DBH medians are not
monotonic. I also could not build a reliable tree-level remeasurement growth
series from PSP because `TREE_NO` is not stable across visits in this extract
(no repeated tree IDs survived the join), so the simple "same tree measured
twice" route is not available without more work.

### Pinned MKRF 684 stand

One synthetic 6.86 ha stand with 4,798 stems at age ~99. It is useful to
validate the selection and valuation logic, but it is **not** an estate
distribution and must not be replicated to every AU as if it were measured.

### Optimal rotation age

Using the managed AU volume curves and maximum mean annual increment:

- rotation age range: 60–120 years;
- median: 90 years;
- +50-year anchor: 110–170 years.

This is a reasonable two-anchor design, but the older anchor is in a sparse VRI
and PSP sample and must be treated as an estimate.

## Proposed DBH-distribution method

### Anchors

For each AU:

1. **Rotation anchor (`R`)**: age of maximum MAI in `managed_au_curves.csv`.
2. **Older anchor (`R+50`)**: 50 years older, capped at the oldest supported
   age for that BEC/species group.

Use **VRI QMD/TPH at the block or AU age** as the scale anchor, and **PSP
CWHdm/CWHvm relative DBH shape** as the shape anchor. Do not use raw PSP age
bins directly as absolute distributions.

### Shape

For each species group (at minimum FD; ideally FD, CW, HW, other conifer,
deciduous):

- fit an empirical or Weibull **relative DBH CDF** from PSP live trees in the
  relevant BEC/snowpack zone and age window;
- trim the fit to the observed range (about 5–150 cm);
- store the CDF at `R` and `R+50`;
- interpolate the **quantile function** between the anchors for intermediate
  treatment ages; extrapolate only within a bounded range and flag it.

I would not fit one global Weibull and assume it is stable. The sample supports
a shape estimate but not a precise age curve.

### Scale and sampling

For a block/AU at treatment age `t`:

- take total TPH and total BA from VRI (or the AU curve if VRI is missing);
- apportion BA/TPH by VRI species shares;
- derive QMD from `BA = TPH * π/4 * (QMD/100)²`;
- draw or integrate expected stems over DBH bins from the relative CDF;
- sort Douglas-fir by DBH descending;
- select until the retention target is met;
- compute retained volume and gross value with the existing stem bucking and
  log-price deck, not by scaling an aggregate product curve.

This preserves the right-tail selection and the grade/value effect.

### Product and revenue accounting

The retained stems are not harvested, so:

- their volume is removed from the harvested yield;
- their bucked log assortment is removed from the harvest product ledger;
- their gross log value is removed from gross revenue;
- their harvest cost is removed (they are not processed);
- residual volume/value remains in the residual state.

A uniform multiplier on the aggregate yield curve is **not** sufficient for
this. The whole point is that the largest DF are disproportionately sawlog
value, so retention changes the **grade mix**, not just the total volume.

## Proposed state transition

At the final harvest treatment:

1. Compute the retention target and select the residual DF cohort.
2. Split the block into:
   - **harvested component**: area `A_h`, moved to the plantation/AU track at
     age 0 with the prescribed planting mix;
   - **residual component**: area `A_r`, moved to a **big-DF residual track**
     at the **same offset/age as the pre-treatment stand**, with no age reset.
3. Record the residual cohort in a separate ledger:
   - retained stems/ha and total stems;
   - retained BA/ha and total BA;
   - retained volume and gross value by species/grade;
   - residual area and residual BA density.
4. Keep the two components summable back to the original block area.

### Area split: the unresolved accounting choice

There are two different "area" concepts:

- **Physical group area**: the actual footprint of an aggregated reserve; use
  `A_r / A = group-retention area fraction`.
- **Basal-area-equivalent area**: `A_r = retained_BA / preharvest_BA_per_ha`,
  used by the BC stand-level retention protocol to convert dispersed retention
  to an area-equivalent.

For a **dispersed largest-DF** treatment, the physical footprint is scattered,
so a single area fraction is an accounting abstraction. I recommend:

- store **both** `retained_ba_m2` and `residual_area_ha`;
- use **basal-area-equivalent area** for the state split and for area reporting;
- keep the **stem/DBH cohort ledger** as the authoritative residual
  description;
- do not claim the residual area is a physical mapped reserve.

If the user wants actual groups, the correct model is a group-retention
treatment with whole-patch retention, not a right-tail DBH selection.

## Addendum: one-rotation retention is a composite managed track

The user clarified the intended tenure rule: retained trees must remain for
**one rotation**, but they remain on the **managed** block and are counted in
the next final-felling volume and gross revenue. That changes the state design.

The corrected state is:

- the full block area remains managed;
- the first final harvest removes only the harvested volume/value from the
  product ledger;
- the block transitions to a **composite plantation + retained-DF track** at
  age 0 for the plantation component, with the retained DF represented as an
  additive overstory curve in the same track;
- at the next final harvest, the composite product curves include the retained
  DF volume and value;
- after that next entry the block returns to the normal plantation track.

There is **no residual unmanaged area split** for this prescription. A
basal-area-equivalent area can still be recorded as an audit statistic, but it
must not be used to move block area out of the managed estate.

The first-pass implementation of this corrected design is
`matrix_vr_overlay_base`, built by `build_mkrf_vr_overlay_matrix.py`.

## Implementation design

### New data

`au_dbh_distribution.csv` (or parquet):

- `au_id`, `species`, `age`, `dbh_cm`, `stems_per_ha`, `ba_m2_per_ha`,
  `volume_m3_per_ha`, `value_cad_per_ha`, `source`, `fit_method`,
  `support_n`, `support_sites`.

`retention_profile.csv`:

- `au_id`, `treatment`, `basis`, `target_fraction`, `age`;
- `retained_tph`, `retained_ba_m2_ha`, `retained_volume_m3_ha`,
  `retained_gross_value_cad_ha`;
- `residual_area_ha`, `residual_ba_m2_ha`, `residual_qmd_cm`;
- `harvest_volume_m3_ha`, `harvest_gross_value_cad_ha`;
- `min_retained_dbh_cm`, `species_priority`.

`retention_ledger.parquet` per run/block/period:

- retained stems, BA, volume, value;
- residual area and residual track;
- provenance/source ID.

### Treatment and simulator change

The current schema has one treatment transition per fragment. The desired
treatment needs a **two-way split**, so this is a core model change, not a
post-hoc script.

Proposed treatment fields:

- `retention_basis`: `BA`, `STEMS`, `AREA`, `CROWN`;
- `retention_fraction` or target/min/max;
- `retention_species_priority`;
- `residual_track`;
- `harvest_track`;
- `residual_offset_rule` (`same_offset`);
- `retention_ledger_id`.

In `Simulator.apply_treatments`:

- for each fragment on a retention treatment, read the retention ledger;
- produce products only on the harvested area;
- append a new fragment for the residual track with the same offset;
- update the original fragment to the harvest track at age 0;
- preserve area conservation;
- record residual accounts.

In the optimizer:

- candidate chains must price both the harvest and residual state;
- retention intensity should be a discrete grid (e.g. 0, 5, 10, 15, 20, 25,
  30% BA) or a smoothed curve, because the DBH selection is non-linear;
- do not let the optimizer choose a retention percentage that the AU/age
  profile cannot represent.

### Validation

- Area conservation: `A_h + A_r = A`.
- BA conservation: `BA_h + BA_r = BA_pre`.
- Volume/value conservation: `V_h + V_r = V_pre` and
  `G_h + G_r = G_pre`.
- Retained stems are DF-first and largest-first.
- Residual track has the pre-treatment offset.
- Harvest track has age 0 and the prescribed planting mix.
- Product ledger contains no retained volume/value.
- The residual-track features produce a plausible future stand, not a second
  harvest of the same trees.
- Run the current area-retention mode alongside the new dispersed mode as a
  comparison, not as the same scenario.

## Decisions needed before lock

1. **Pattern:** Is MKRF's final-harvest retention dispersed, aggregated, or
   mixed? The current area split is group-like. A right-tail largest-DF
   selection only makes sense for dispersed retention or a marked leave-tree
   prescription.
2. **Primary basis:** For dispersed retention, adopt **percent of pre-harvest
   basal area** as the decision variable? This is the BC operational
   convention and the most defensible match to the user's "leave the biggest
   fir" description.
3. **Target values:** Should the existing 10%/20% area factors become 10%/20%
   **BA** targets, or should they remain group-area targets while a separate
   dispersed-BA target is introduced? I recommend the latter until the
   prescription is settled.
4. **Area accounting:** Use basal-area-equivalent residual area for the state,
   with a separate stem/BA ledger? Or use a physical group area?
5. **Retention duration:** Are these long-term reserves (no re-entry for at
   least one rotation) or short-term residuals (future harvest)? The residual
   track and re-entry rules differ.
6. **Species priority:** FD first, then CW? What happens in stands with little
   or no FD? Current MKRF groups all have some FD, but the fallback needs a
   rule.

## Sources

- BC Ministry of Forests, Forest Practices Branch. 2003. *Silvicultural
  Systems Handbook for British Columbia*. Part 2.1, "Retention System."
  https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/forestry/stand-tending/silvsystemshdbk-web.pdf
- BC Ministry of Forests. *Silviculture Prescription Guidebook*. "Stocking
  requirements for other even-aged partial cutting systems" and "Stocking
  requirements for retention systems."
  https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/forestry/silviculture/silviculture-surveys/silviculture_prescription_guidebook.pdf
- BC Ministry of Forests, Lands and Natural Resource Operations. 2016.
  *Procedures for Submitting Forest Cover to RESULTS for Openings with Treed
  Retention*, Edition 1.4.
  https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/forestry/silviculture/silviculture-results/forest_cover_retention_submissions_may_5_2016_final.pdf
- BC Ministry of Forests. 2024. *Stand-level Retention Monitoring Protocol*,
  v6.
  https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/forestry/frep/protocol-documents/frep-slr-protocol-2024_v6.pdf
- BC Timber Sales / Skeena Business Area. 2011. *Single Entry Dispersed
  Retention System Operational Guide*.
  https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/forestry/bc-timber-sales/ems-sfm-certification/business-area/skeena/single-entry-dispersed-guidelines-tsk.pdf
- TFL 44 Management Plan 4, Appendix 5, "Stewardship Zones."
  https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/forestry/timber-tenures/tree-farm-licence/management-plans/tfl-44-05-mngment-plan-4-appendix-5-stewardship-zones.pdf
- Beese, W.J., Deal, J., Dunsworth, B.G., Mitchell, S.J., and Philpott, T.J.
  2019. Two decades of variable retention in British Columbia: a review of its
  implementation and effectiveness for biodiversity conservation. *Ecological
  Processes* 8:33. https://doi.org/10.1186/s13717-019-0181-9
- BC Forest Practices Board. 2008. *High Retention Harvesting and Timber
  Sustainability on the British Columbia Coast*.
  https://www.bcfpb.ca/wp-content/uploads/2008/01/SIR20-High-Retention-BC-Coast.pdf
- Mitchell, S.J. and Beese, W.J. 2002. The retention system: reconciling
  variable retention with the principles of silvicultural systems. *Forestry
  Chronicle* 78(3):397–403.

## Data and code references

- Current retention parser: `ws4/io/forest_model_xml.py`.
- Current retention split: `ws4/build/compiler.py`.
- Current simulator: `ws4/sim/engine.py`; `treatments.retain` is not used to
  split a treatment.
- Current MKRF retention factors: `models/mkrf_patchworks_model/xml/forestmodel.xml`
  and `config/silviculture_retention_low.yaml`,
  `config/silviculture_retention_high.yaml`.
- Current area-retention matrices: `ws4/runtime/matrix_ret_low`,
  `ws4/runtime/matrix_ret_high`; no-retention baseline:
  `ws4/runtime/matrix_no_retention_true_patched`.
- VRI: `sources/mkrf-gis-2026-11-02/processed/vri_2016.gpkg`.
- PSP: `tmp/inv01-data/psp/faib_tree_detail.csv`,
  `faib_plot_header.csv`, `faib_sample_byvisit.csv`.
- MKRF 684 tree list: `fhops-public-demo/examples/game/stands/mkrf_684/`.
- Worked example: `planning/2026-11-18_retention_basis_example.csv`.
