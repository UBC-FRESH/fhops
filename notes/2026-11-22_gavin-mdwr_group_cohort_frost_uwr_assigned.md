> Public project-note copy. See the matching instance planning note.

# Gavin MDWR assigned-openings-only cohort — 2026-11-22

Status: **cohort diagnostic, not a phase result**

## Purpose

The all-group repaired cohort cut 1,684.06 ha because the cohort model includes
unassigned standing groups. This run restricts the cohort to the **4,671
assigned openings / 1,386.43 ha** in the repaired layout.

## Result

| Metric | Value |
| --- | ---: |
| Assigned groups | 4,671 |
| Blocks | 875 |
| Groups cut at least once | 3,743 |
| Unique cut area | 1,106.79 ha |
| Uncut assigned groups | **928** |
| Uncut assigned area | **279.64 ha** |
| Cut events | 4,530 |
| Event area (double-counts re-entries) | 1,350.13 ha |
| Harvested volume | **499,597 m³** |
| Final state | **554,774 m³** |
| Final BA | **96,950 m²** |
| BA-gate failures | 0 |

## Why 928 openings are uncut

The cohort script assigns each group to a cohort index and cuts it only on
entries whose index matches that cohort modulo the number of cohorts. Blocks
with fewer accepted entries than cohorts leave some cohorts without a cut.
The script does **not** use the layout's `entry_offset`, which already assigns
each opening to an entry.

This means the assigned-only cohort is not yet a complete legal-opening cut
ledger. The final state covers only the 1,386.43 ha assigned area, not the full
2,722.37 ha repaired estate, so it cannot be compared directly with the
whole-estate 1,000,000 m³ final-stock floor or 150,000 m² BA floor.

## Comparison

| Run | Cut events | Unique cut area | Harvested | Final stock | Final BA |
| --- | ---: | ---: | ---: | ---: | ---: |
| All repaired groups | 12,534 | 1,424.60 ha | 629,809 m³ | 1,111,922 m³ | 180,249 m² |
| Assigned openings only | 4,530 | 1,106.79 ha | 499,597 m³ | 554,774 m³ | 96,950 m² |
| Old legal s40 cohort | 11,910 | not recomputed | 658,199 m³ | 1,141,775 m³ | 184,534 m² |

The assigned-only run is not the public group result. The old-layout regrown
phase result remains **0.679M m³ / 26-of-30**.

## Outputs

- `2026-11-22_gavin-mdwr_groups_frost_uwr_assigned.csv`
- `2026-11-22_gavin-mdwr_group_matrix_frost_uwr_assigned_map.csv`
- `2026-11-22_gavin-mdwr_group_cohort_frost_uwr_assigned_cuts.csv`
- `2026-11-22_gavin-mdwr_group_cohort_frost_uwr_assigned.json`
- `2026-11-22_gavin-mdwr_group_cohort_frost_uwr_assigned_state.csv`
  (6.2 MB intermediate, not committed)

## Next

Build a one-cut entry-offset ledger for all 4,671 assigned openings, then run
the regrown phase schedule on those cuts. Do not compare the assigned-only
final state with whole-estate floors unless the unassigned standing area is
added to the account.
