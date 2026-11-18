> Public project-note copy. See the matching instance planning note.

# MKRF variable-retention policy — release audit

Status: **release audit passed with one reporting correction.**

Date: 2026-11-18

## Scope

Audited the public `mkrf-vr-policy` handoff against its WS4 source run and the
MKRF retention profile grid.

## Checks

| Check | Result |
| --- | --- |
| Blocks | 1,763 |
| Scheduled blocks | 1,219 |
| Schedule events | 1,395 |
| Managed area + unmanaged area | 4,120.674 + 690.176 = **4,810.850 ha** |
| Retention targets | **10 of 10 met** |
| Target statuses | **44 met / 2 below / 1 above** |
| Retained BA, schedule/profile sum | 12,669.836 m² |
| Retained BA, matrix account sum | 12,669.832 m² |
| Retained volume | 192,029.805 m³ |
| Retained log value | CAD 41,286,444 |
| Public run | `/fhops/?run=mkrf-vr-policy` returns 200 |
| Public brief | `/briefs/MKRF_VR_POLICY.pdf` returns 200 |
| Portal links | present on `/forests/` and `/` |
| Contract tests | pass |

The schedule/profile retained-BA sum and the matrix retention account agree to
rounding.

## Correction found

The first issue of the summary and brief used `report_accounts.mean × 100` for
the sparsely populated retention accounts. Those accounts have 99 annual records,
not a complete 100-year ladder, so `mean × 100` overstates the total.

Corrected totals:

| Metric | Corrected |
| --- | ---: |
| Retained BA | **12,669.832 m²** |
| Retained volume | **192,029.805 m³** |
| Retained log value | **CAD 41.286M** |
| Sawlog butt | **24,610 m³ / CAD 7.061M** |
| Sawlog upper | **166,805 m³ / CAD 34.169M** |
| Pulp | **615 m³ / CAD 0.057M** |

The public summary, README, brief and portal card have been updated.

## Policy result

The published scenario is a **policy seed**, not a fully re-optimized target
search:

- 400 m² retained BA per 10-year period;
- CC / VR10 / VR20 / VR30 choice grid;
- full managed area;
- retained DF carried in the composite next-rotation track;
- no residual area moved to unmanaged.

All ten retention targets are met. The two remaining misses are even-flow
yield checks; one even-flow check is above the band.

## Remaining limits

- Coastal grade products D/F/H/I/J/U/X/Y are still aggregate-scaled.
- The bucked ledger carries sawlog butt/upper/pulp, not a calibrated coastal
  grade mapping.
- The composite retained-overstory curve is additive, not a two-cohort
  competition/mortality model.
- The R+50 anchor is a regional PSP estimate from 13 sites.
- The 400 m² floor is a scenario policy, not a legal requirement.
- This is a public WS4 screen, not an approved AAC, budget or legal plan.

## Conclusion

The public scenario is suitable as a **draft retention policy screen**. It is
not yet a decision-grade coastal-grade implementation.
