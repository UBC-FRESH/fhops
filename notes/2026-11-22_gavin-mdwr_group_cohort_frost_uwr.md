> Public project-note copy. See the matching instance planning note.

# Gavin MDWR repaired-layout cohort state — 2026-11-22

Status: **cohort-state diagnostic, not a phase result**

## Inputs

- Repaired layout: `2026-11-22_gavin-mdwr_groups_frost_uwr.csv`,
  27,110 groups / 2,722.37 ha.
- Frost/UWR repair note: `2026-11-22_gavin-mdwr_layout_repair.md`.
- Existing group matrix: `ws4/runtime/gavin-mdwr-group-matrix-legal-s40`.
- Existing legal block entry schedule:
  `ws4/runtime/gavin-mdwr-40-schedule-official-ba-temporal-s40-legal.csv`.
- Cohort state script: `build_gavin_mdwr_group_cohort_state_legal_s40.py`.

## Mapping

- Each repaired group maps to its source group's matrix track using
  `source_group_id`.
- 27 source groups (0.54 ha) have no matrix group because the old s40 mapping
  excluded them. They are all unassigned and are dropped from the cohort state.
- Cohort input: **27,083 groups / 2,721.83 ha** in **1,427 blocks**.
- 4,671 groups are the assigned layout openings; the cohort script uses all
  groups, not just assigned openings. This is inherited from the existing
  cohort model.

## Result

| Metric | Repaired layout | Old legal s40 cohort |
| --- | ---: | ---: |
| Groups in cohort state | 27,083 | 25,759 |
| Blocks | 1,427 | 1,443 |
| Cut events | 12,534 | 11,910 |
| Cut area | 1,684.06 ha | 1,760.20 ha |
| Harvested volume | **629,809 m³** | 658,199 m³ |
| Final state volume | **1,111,922 m³** | 1,141,775 m³ |
| Final BA | **180,249 m²** | 184,534 m² |
| BA-gate failures | 0 | 0 |

The repaired-layout cohort harvest is **4.3% lower** than the old legal s40
cohort. The cut area is 4.3% lower; the volume response is therefore primarily
an area effect, not a yield-curve change.

## Pass-area check

- Assigned layout openings: **1,386.43 ha**.
- Cohort cut area: **1,684.06 ha**.
- Difference: **+297.63 ha** because the cohort script cuts all groups, not only
  the assigned openings.
- Assigned area lost in the repair: **46.36 ha** (42.58 ha outside UWR plus
  3.78 ha dropped small pieces).
- No rebalancing was done to restore pass targets after clipping.

This means the cohort state is internally consistent with the old cohort
method, but it is **not** a legal-opening-only cut ledger. The existing cohort
script must be changed if the model is to cut only the assigned group layout.

## Outputs

- `2026-11-22_gavin-mdwr_groups_frost_uwr_cohort.csv`
- `2026-11-22_gavin-mdwr_group_matrix_frost_uwr_map.csv`
- `2026-11-22_gavin-mdwr_group_cohort_frost_uwr_cuts.csv`
- `2026-11-22_gavin-mdwr_group_cohort_frost_uwr_state.csv` (35 MB
  intermediate, not committed)
- `2026-11-22_gavin-mdwr_group_cohort_frost_uwr.json`

## Limits

- This is a cohort state, not the regrown phase schedule.
- The frozen `assigned` flag is not used by the cohort script.
- Unassigned groups are cut by the cohort model, so the result overstates the
  legal opening footprint.
- 16 blocks with only unmapped tiny groups are absent.
- No target framework or public replacement decision is changed.
- The public group result remains the old-layout **0.679M m³ / 26-of-30**
  regrown phase diagnostic.

## Next

Build the group schedule from the new cut rows, rerun the regrown phase
optimizer, and compare the result with the old 0.679M m³ / 26-of-30 diagnostic.
