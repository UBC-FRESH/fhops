> Public project-note copy. The full instance implementation note is kept at
> `femic/external/femic-mkrf-instance/planning/2026-11-18_variable-retention-implementation.md`.

# Variable-retention implementation — first pass

Status: **first-pass matrix screen complete; core treatment-time split not yet
implemented**

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

First-pass coverage:

- 741 blocks;
- 2,306.10 ha;
- 244.55 ha of basal-area-equivalent residual area;
- retention targets 10% and 20% of pre-harvest BA;
- mean retained BA share 10.34%, volume share 11.43%, gross value share 11.65%.

Files:

```text
planning/2026-11-18_mkrf_retention_profiles.csv
planning/2026-11-18_mkrf_retention_profiles.json
```

### 2. Matrix variant

`build_mkrf_vr_matrix.py` builds `ws4/runtime/matrix_vr_base` from the
no-retention matrix. For each profiled block it:

- splits area into a harvested fraction and a basal-area-equivalent residual
  fraction;
- puts the harvested fraction on a cloned managed track;
- puts the residual fraction on a cloned **unmanaged** track at the same age;
- scales harvested product curves by the harvested volume/value share;
- scales residual yield/carbon feature curves by the residual cohort density;
- leaves the residual track with no scheduled treatment.

The matrix passes `ws4 validate`.

### 3. Target search

The VR matrix was run with the existing target set, seed 44, 120 iterations
and the no-retention schedule as the initial schedule.

| Scenario | Gross log value | Production | Net after all cost | Harvest cost | Targets |
| --- | ---: | ---: | ---: | ---: | --- |
| No retention | CAD 716.7M | 3.378M m³ | CAD 403.7M | CAD 185.8M | 31/5/1 |
| VR base, existing schedule | CAD 666.6M | 3.150M m³ | CAD 375.1M | CAD 173.3M | 30/6/1 |
| VR base, re-optimized | CAD 668.9M | 3.163M m³ | CAD 376.2M | CAD 174.0M | 28/8/1 |

Managed area falls from 4,120.7 ha to 3,876.1 ha; unmanaged area rises from
690.2 ha to 934.7 ha. Total area remains 4,810.85 ha.

The existing-schedule and re-optimized cases are close because the matrix
retention intensity is fixed by the silviculture group. The optimizer can move
harvest entries, but cannot choose 0/5/10/15/20/25/30% retention per block yet.

## Important implementation limits

- **Matrix-level pre-split, not a treatment-time split.** The residual area is
  set aside from the start of the horizon. For a one-entry reserve the state
  trajectory is close, but the simulator does not yet move area at the harvest
  year.
- **Retention intensity is fixed**, not an optimizer decision. Current groups
  use 10% or 20% BA from the silviculture assignment.
- **Species DBH shape comes from the synthetic MKRF 684 tree list**, scaled by
  VRI TPH/BA/species share. It is not a full-estate measured tree list.
- **No age interpolation yet.** The profile uses the AU rotation age, or the
  current age if older; the +50-year anchor is not wired into the matrix.
- **Aggregate product scaling.** The harvested product curves are scaled by
  volume/value share; the residual stem grade mix is not re-bucketed tree by
  tree.
- **Residual area is basal-area-equivalent**, not a mapped physical reserve.
- **The residual feature scaling is a state-density approximation**, not a
  measured big-DF growth curve.

## What must be built next

1. **Treatment-time split in the simulator/optimizer.**
   - At harvest, produce products on the harvested area only.
   - Append a residual fragment on the residual track at the pre-treatment
     offset.
   - Move the harvested fragment to the plantation track at age 0.
   - Keep area, BA, volume and value conservation.
2. **Retention intensity as a decision variable.**
   - Precompute a retention ledger over a 0–30% BA grid.
   - Let the optimizer choose the treatment variant per block.
   - Reject intensities the AU/age profile cannot represent.
3. **Age-specific distribution interpolation.**
   - Build the rotation and rotation+50 anchors.
   - Interpolate quantiles by treatment age.
   - Add the two-anchor uncertainty report.
4. **Grade-specific product removal.**
   - Buck the selected residual stems with the same stem/price model.
   - Remove their sawlog/pulp volumes and values from the harvest ledger.
5. **Validation and public scenario.**
   - Conservation tests for area/BA/volume/value.
   - Re-run low/base/high or the decided target set.
   - Publish the scenario and update the MKRF card/brief once the core split is
     in.

## Assumptions currently used

- dispersed retention, not group retention;
- retention basis = percent of pre-harvest basal area;
- DF first, largest DBH first;
- residual is a long-term reserve with no re-entry in the current rotation;
- residual area for state accounting is basal-area-equivalent;
- 10%/20% group targets are new BA targets, not reinterpreted old area targets.

These assumptions are documented but **not yet locked as an operational
prescription**.
