> Public project-note copy. See the matching instance planning note.

# Variable-retention implementation — first pass

Status: **full-area one-rotation overlay, discrete retention-intensity grid,
retention policy target, two-anchor age interpolation, R+50 sensitivity and
bucked log-assortment ledger and public policy scenario complete;
coastal-grade mapping still pending**

Date: 2026-11-18

Public scenario: `mkrf-vr-policy`; brief
`MKRF_VR_POLICY.pdf`; portal card `/fhops/?run=mkrf-vr-policy`.

## What is now built

### 1. Retention profile

`build_mkrf_retention_profiles.py` builds a per-block dispersed-retention
profile using:

- VRI per-block TPH, BA, species shares and age;
- the pinned MKRF 684 tree list for species DBH/height shape;
- the game price deck for gross log value;
- the MKRF silviculture regime assignment for the group retention target;
- an AU rotation age from the managed volume curves.

The profile selects **Douglas-fir first, largest DBH first**, until the
**pre-harvest basal-area target** is met. It records retained stems, TPH,
BA, volume and value, and the residual area fraction.

The profile builder now uses two DBH anchors:

- **rotation anchor**: the pinned MKRF 684 tree list;
- **rotation+50 anchor**: FAIB PSP CWHdm live FD, age 140–180, 2,817 records
  on 13 sites (`2026-11-18_mkrf_dbh_anchors.csv`);
- quantiles are linearly blended by the profile age between the anchors;
- the blended shape is scaled to the VRI QMD and BA trends at the profile age.

The `age_interpolation_fraction` column records the blend. The current matrix
uses one profile age per block; a forced R+50 sensitivity matrix is now available.

The profile builder now writes a grid as well as the original regime-target
rows.

Grid coverage:

- 923 blocks;
- 2,728.57 ha;
- retention targets 0%, 10%, 20% and 30% of pre-harvest BA;
- 741 blocks have enough DF to produce a nonzero retained cohort in the
  overlay matrix;
- the original regime-target overlay covers 2,306.10 ha and 244.55 ha of
  basal-area-equivalent residual area.

Files:

```text
planning/2026-11-18_mkrf_retention_profile_grid.csv
planning/2026-11-18_mkrf_retention_profile_grid.json
```

Files:

```text
planning/2026-11-18_mkrf_retention_profiles.csv
planning/2026-11-18_mkrf_retention_profiles.json
```

### 2. Original area-split comparison

`build_mkrf_vr_matrix.py` builds `ws4/runtime/matrix_vr_base` as an earlier
comparison. It splits area into harvested and unmanaged residual fragments.
This is **not** the intended one-rotation rule and is retained only as a
comparison surface.

### 2b. Corrected full-area overlay

`build_mkrf_vr_overlay_matrix.py` builds
`ws4/runtime/matrix_vr_overlay_base` from the no-retention matrix. For each
profiled block it:

- keeps the full block area managed;
- reduces the first-harvest product curves by the retained volume/value;
- transitions the full area to a composite **plantation + retained-DF** track;
- adds the retained overstory to the composite yield and product curves;
- returns the block to the normal plantation track after the next final
  harvest;
- leaves feature area managed and unchanged.

The matrix passes `ws4 validate`.

The retention trees are therefore counted in the next final-felling harvest
volume and gross revenue, not moved to an unmanaged area. A two-entry check on
block 14 (offset 73 first entry, offset 153 second entry) gives:

| Entry | No retention yield | Overlay yield | No retention gross | Overlay gross |
| --- | ---: | ---: | ---: | ---: |
| First, offset 73 | 2,719.5 m³ | 2,572.0 m³ | CAD 645,738 | CAD 610,836 |
| Second, offset 153 | 1,641.9 m³ | **1,807.3 m³** | CAD 389,869 | **CAD 429,021** |

The second entry is higher because the retained DF cohort is now included in
the composite track.

### 3. Target search

The overlay matrix was run with the existing target set, seed 44, 120
iterations and the no-retention schedule as the initial schedule.

| Scenario | Gross log value | Production | Net after all cost | Harvest cost | Targets |
| --- | ---: | ---: | ---: | ---: | --- |
| No retention | CAD 716.7M | 3.378M m³ | CAD 403.7M | CAD 185.8M | 31/5/1 |
| VR overlay, existing schedule | CAD 672.2M | 3.177M m³ | CAD 378.2M | CAD 174.7M | 29/7/1 |
| VR overlay, re-optimized | CAD 674.8M | 3.188M m³ | CAD 379.7M | CAD 175.4M | 29/7/1 |

Managed area remains 4,120.7 ha and unmanaged area remains 690.2 ha; total area
remains 4,810.85 ha. This is the key correction from the earlier split matrix.
The old split comparison had managed area 3,876.1 ha and unmanaged area
934.7 ha.

### 4. Retention-intensity choice grid

`build_mkrf_vr_overlay_grid.py` builds `ws4/runtime/matrix_vr_grid`. Each
profiled block has a choice track with:

```text
CC      = no retention
VR10    = 10% pre-harvest BA
VR20    = 20% pre-harvest BA
VR30    = 30% pre-harvest BA
```

The optimizer chose the following in the 120-iteration, seed-44 run:

| Treatment | Blocks/events |
| --- | ---: |
| CC | 1,344 |
| VR10 | 14 |
| VR20 | 4 |
| VR30 | 0 |

The grid run produced:

| Scenario | Gross log value | Production | Net after all cost | Harvest cost | Targets |
| --- | ---: | ---: | ---: | ---: | --- |
| No retention | CAD 716.7M | 3.378M m³ | CAD 403.7M | CAD 185.8M | 31/5/1 |
| VR grid, pre-age profile, no policy | CAD 713.6M | 3.363M m³ | CAD 402.2M | CAD 185.0M | 29/7/1 |

The optimizer mostly chooses no retention when no policy target is present.
That is a real result, not a fallback: the grid makes retention intensity a
choice and the search is not forced to use it. The age-aware policy result is
in §5.

### 5. Explicit retention policy target

`ws4/targets_vr_policy.yaml` now uses the calibrated **400 m² retained BA per
10-year period** floor:

```text
account: product.ba.retention.total
minimum: 400 m² per 10-year period
```

The 500 m² version is retained as a sensitivity in
`ws4/targets_vr_policy_500.yaml`. This is a **scenario policy target**, not a
legal requirement. It is paired with the existing yield, net-revenue, route
and stock targets.

Starting from the no-retention schedule, retention targets are not met:

- 31 met / 15 below / 1 above at the 400 m² floor;
- 10 retention targets all below;
- the search finds only 2,350 m² retained BA across the horizon even at 600
  iterations.

Starting from a retention seed that replaces the first CC on 789 profiled
blocks with `VR10` gives:

| Scenario | Gross log value | Net after all cost | Retained BA | Targets |
| --- | ---: | ---: | ---: | --- |
| No retention, 400 m² policy evaluated | CAD 716.7M | CAD 403.7M | 0 | 31/15/1 |
| Retention seed, age-aware and bucked | CAD 655.2M | CAD 369.2M | 12,670 m² | **44/2/1** |
| Retention seed + 120 iterations | CAD 641.8M | CAD 361.2M | 13,234 m² | 42/4/1 |

The seed meets **all ten 400 m² retention targets**. The re-optimized search
reduces gross/net further but loses two target passes, so the seed remains the
cleaner policy screen at this stage.

The strong result is that the retention policy changes the economics
materially: about **CAD 61.5M less gross log value** and **CAD 34.5M less net
after all cost** than the no-retention baseline.

### 5a. Bucked log assortment ledger

The retention profile now carries the selected cohort's bucked log classes:

```text
sawlog_butt
sawlog_upper
pulp
```

The grid exposes them as first-entry products:

```text
product.retention.sawlog_butt.volume / .value
product.retention.sawlog_upper.volume / .value
product.retention.pulp.volume / .value
product.retention.total.volume / .value
```

The log-class shares come from the MKRF 684 tree list's stem bucking. They are
scaled to the matrix volume and gross-value ledger so the totals reconcile with
the first-harvest product curves.

| Scenario | Retained volume | Retained value | Butt volume | Upper volume | Pulp volume |
| --- | ---: | ---: | ---: | ---: | ---: |
| Age-aware seed | 192,030 m³ | CAD 41.29M | 24,610 m³ | 166,805 m³ | 615 m³ |
| Forced R+50 seed | 245,581 m³ | CAD 52.85M | 30,268 m³ | 215,050 m³ | 263 m³ |

This is a **bucked log-assortment ledger**, not yet a complete coastal-grade
matrix substitution. The matrix coastal grade products D/F/H/I/J/U/X/Y remain
aggregate-scaled for the first entry.

### 6. R+50 sensitivity

A forced rotation+50 profile grid and matrix are now built:

```text
planning/2026-11-18_mkrf_retention_profile_grid_r50.csv
ws4/runtime/matrix_vr_grid_r50
ws4/runtime/vr_grade_seed_r50
ws4/runtime/vr_grade_r50_s44
```

The profile age range is 110–170 years and the older PSP CWHdm anchor is used
for the full blend (`age_interpolation_fraction = 1`).

| Scenario | Gross log value | Net after all cost | Retained BA | Targets |
| --- | ---: | ---: | ---: | --- |
| Current/as-of profile, 400 m² policy | CAD 655.2M | CAD 369.2M | 12,670 m² | 44/2/1 |
| Forced R+50 profile, seed, 400 m² policy | CAD 657.7M | CAD 370.6M | 13,403 m² | 44/2/1 |
| Forced R+50 profile, re-optimized | **CAD 652.6M** | **CAD 367.7M** | **13,845 m²** | **45/1/1** |

The older-age sensitivity retains about **6% more BA** than the current-age
profile. The re-optimized R+50 case improves target performance from 44/2/1 to
45/1/1. This is a material age-distribution sensitivity, not a final
calibration.

## Important implementation limits

- **Retention intensity is a discrete grid**, currently 10/20/30% BA plus CC.
  It is not continuous and does not yet include 5/15/25%.
- **The choice track exposes CC and VRxx final treatments.** The base CT rows
  are not carried on the choice track, so the grid result is a final-harvest
  retention screen rather than a replacement for the CT schedule.
- **The composite track is additive.** It is not a two-cohort growth model and
  does not model competition, windthrow or retained-tree mortality.
- **Species DBH shape is a blend** of the synthetic MKRF 684 rotation stand
  and the PSP CWHdm rotation+50 FD anchor, scaled by VRI TPH/BA/species share.
  It is not a full-estate measured tree list.
- **Age interpolation is a two-anchor quantile blend**, not a full
  age-continuous matrix. The current matrix uses one profile age per block; the
  forced R+50 matrix is a sensitivity, not a continuous age model.
- **Bucked log assortment exists, but coastal grade mapping is not complete.**
  Sawlog butt/upper/pulp volumes and values are carried; the matrix coastal
  grades D/F/H/I/J/U/X/Y remain aggregate-scaled.
- **The retained-overstory curve is additive**, not a mapped physical reserve.

## What must be built next

1. **Coastal-grade mapping.**
   - Map the bucked sawlog butt/upper/pulp ledger to the MKRF
     D/F/H/I/J/U/X/Y grade products.
   - Reconcile retained grade volumes/values with the matrix grade curves.
2. **Grid calibration.**
   - Test 5/15/25% and a wider target set.
   - Check whether the optimizer's near-zero retention choice is driven by the
     target weights, economics, or the sparse treatment alternatives.
3. **Validation and public scenario.**
   - Conservation tests for area/BA/volume/grade value.
   - Re-run low/base/high or the decided target set.
   - Publish the scenario and update the MKRF card/brief.

## Assumptions currently used

- dispersed retention, not group retention;
- retention basis = percent of pre-harvest basal area;
- DF first, largest DBH first;
- retained trees remain for one rotation on the managed block;
- retained volume/value is removed from the first harvest and added to the next
  composite final-felling curves;
- residual area is an audit statistic only; it does not move area to unmanaged;
- 10%/20% group targets are new BA targets, not reinterpreted old area targets.

These assumptions are documented but **not yet locked as an operational
prescription**.
