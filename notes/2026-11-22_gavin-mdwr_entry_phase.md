> Public project-note copy. See the matching instance planning note.

# Gavin MDWR entry-offset phase result — 2026-11-22

Status: **phase diagnostic on the one-cut assigned ledger, not a policy result**

## Inputs

- `2026-11-22_gavin-mdwr_assigned_entry_cuts.csv`: 4,671 cuts, 875 blocks,
  1,386.43 ha, 504,601 m³ at the original entry ages.
- Group matrix: `gavin-mdwr-group-matrix-legal-s40`.
- Phase optimizer: `optimize_gavin_mdwr_group_phase_regrown.py`, eight
  coordinate-descent restarts.
- Phase range: 0–119 years; mean 51.4 years.

## Result

| Metric | Value |
| --- | ---: |
| Cut events | 4,671 |
| Blocks | 875 |
| Total volume | **579,763 m³** |
| Mean 10-year volume | 19,325 m³ |
| Min 10-year volume | **3,474 m³** |
| Max 10-year volume | **30,950 m³** |
| Periods in band | **26/30** |
| Objective | 143,169,355 |

| Period | Volume |
| ---: | ---: |
| 0 | 30,171 m³ |
| 10 | 20,638 m³ |
| 20 | 22,024 m³ |
| 30 | 14,077 m³ |
| 40 | 28,626 m³ |
| 50 | 30,950 m³ |
| 60 | 30,035 m³ |
| 70 | 29,174 m³ |
| 80 | 27,983 m³ |
| 90 | 28,981 m³ |
| 100 | 29,381 m³ |
| 110 | 24,135 m³ |
| 120 | 26,101 m³ |
| 130 | 20,640 m³ |
| 140 | 28,651 m³ |
| 150 | 17,158 m³ |
| 160 | 14,988 m³ |
| 170 | 21,191 m³ |
| 180 | 15,011 m³ |
| 190 | 15,317 m³ |
| 200 | 19,613 m³ |
| 210 | 16,540 m³ |
| 220 | 12,463 m³ |
| 230 | 11,537 m³ |
| 240 | 14,713 m³ |
| 250 | 11,805 m³ |
| 260 | 6,603 m³ |
| 270 | 3,944 m³ |
| 280 | 3,841 m³ |
| 290 | 3,474 m³ |

There are no ceiling violations; the four late periods are below the
10,316.89 m³ floor.

## Why the tail does not close

- The phase optimizer can shift each block by at most 119 years, and also not
  beyond year 299.
- The assigned entries are concentrated early; after the phase cap, only a
  small number of openings remain available for periods 260–290.
- Filling the four late periods would require moving about 23,000 m³ into the
  tail. The eligible late-entry pool is too small.
- This is a structural limit of the one-cut, 300-year assigned ledger, not a
  local optimizer failure.

## Limits

- One cut per assigned opening; no 40-year re-entry, later-entry cohort, or
  final-standing-stock account.
- The cut volume is regrown at the shifted first-cut age; no second entry is
  invented.
- The result is not comparable to the old all-group 0.679M m³ / 26-of-30
  regrown phase diagnostic.
- The public block screen remains the policy result.

## Outputs

- `2026-11-22_gavin-mdwr_group_phase_entry_opt.csv`
- `2026-11-22_gavin-mdwr_group_phase_entry_opt.json`
- `2026-11-22_gavin-mdwr_group_phase_entry_regrown_cuts.csv`
- `2026-11-22_gavin-mdwr_group_phase_entry_regrown.json`

## Next decision

Choose one:

1. accept the 26/30 tail-feasibility limit and keep the block public;
2. approve a wider/asymmetric target band;
3. approve a horizon or later-entry model that adds legal entries beyond the
   current assigned schedule.

No further phase restart is recommended.
