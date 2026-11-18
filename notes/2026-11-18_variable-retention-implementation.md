> Public project-note copy. The full instance implementation note is kept at
> `femic/external/femic-mkrf-instance/planning/2026-11-18_variable-retention-implementation.md`.

# Variable-retention implementation — first pass

Status: **full-area one-rotation overlay and discrete retention-intensity grid
complete; age interpolation and grade-specific bucking still pending**

Date: 2026-11-18

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
| VR grid, re-optimized | CAD 713.6M | 3.363M m³ | CAD 402.2M | CAD 185.0M | 29/7/1 |

The optimizer mostly chooses no retention under the current target set. That is
a real result, not a fallback: the grid makes retention intensity a choice and
the search is not forced to use it.

## Important implementation limits

- **Retention intensity is a discrete grid**, currently 10/20/30% BA plus CC.
  It is not continuous and does not yet include 5/15/25%.
- **The choice track exposes CC and VRxx final treatments.** The base CT rows
  are not carried on the choice track, so the grid result is a final-harvest
  retention screen rather than a replacement for the CT schedule.
- **The composite track is additive.** It is not a two-cohort growth model and
  does not model competition, windthrow or retained-tree mortality.
- **Species DBH shape comes from the synthetic MKRF 684 tree list**, scaled by
  VRI TPH/BA/species share. It is not a full-estate measured tree list.
- **No age interpolation yet.** The profile uses the AU rotation age, or the
  current age if older; the +50-year anchor is not wired into the matrix.
- **Aggregate product scaling.** The harvested product curves are scaled by
  volume/value share; the residual stem grade mix is not re-bucketed tree by
  tree.
- **The retained-overstory curve is additive**, not a mapped physical reserve.

## What must be built next

1. **Age-specific distribution interpolation.**
   - Build the rotation and rotation+50 anchors.
   - Interpolate quantiles by treatment age.
   - Add the two-anchor uncertainty report.
2. **Grade-specific product removal.**
   - Buck the selected residual stems with the same stem/price model.
   - Remove their sawlog/pulp volumes and values from the first-harvest ledger
     and add them to the next composite final-felling ledger.
3. **Grid calibration.**
   - Test 5/15/25% and a wider target set.
   - Check whether the optimizer's near-zero retention choice is driven by the
     target weights, economics, or the sparse treatment alternatives.
4. **Validation and public scenario.**
   - Conservation tests for area/BA/volume/value.
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
