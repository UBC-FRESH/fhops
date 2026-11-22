> Public project-note copy. See the matching instance planning note.

# Gavin MDWR assigned entry-offset ledger — 2026-11-22

Status: **one-cut legal-opening ledger, not a phase result**

## Purpose

The assigned-only cohort left 928 openings uncut because the cohort script
ignores the layout's `entry_offset`. This ledger fixes that by cutting every
assigned opening exactly once at its layout entry.

## Result

| Metric | Value |
| --- | ---: |
| Assigned openings | 4,671 |
| Blocks | 875 |
| Cut events | 4,671 |
| Cut area | **1,386.43 ha** |
| Harvested volume | **504,601 m³** |
| Mean cut BA | 82.2 m²/ha |
| Minimum 10-year volume | 0 m³ |
| Maximum 10-year volume | **148,505 m³** |
| Mean 10-year volume | 16,820 m³ |

All 4,671 assigned openings are cut. The ledger uses the existing group matrix
curves at `initial_age + entry_offset` and a single cut per opening.

## What this fixes

- The assigned-only cohort cut only 3,743 groups and left 279.64 ha uncut.
- The entry-offset ledger cuts all 4,671 groups and exactly the assigned
  1,386.43 ha.
- It is still a **one-cut ledger**: there is no second entry, regrowth after a
  cut, or final standing stock.

## Caveats

- The cut-year distribution is very uneven: 1,491 openings cut at year 0 and
  148,505 m³ in the first decade. Phase shifting will be required.
- 612 openings (174.9 ha) have BA below 40 m²/ha at their entry. GWM 6 is
  applied at the stand/block level in this model, not as a per-group gate.
- Some group BA values are implausible for small groups; the group matrix BA
  curve is a screening proportional fit, not a calibrated per-group BA model.
- No phase shift, cohort re-entry, windthrow, target framework, or final-stock
  account is included.
- The public group result remains the old-layout **0.679M m³ / 26-of-30**
  regrown phase diagnostic.

## Outputs

- `2026-11-22_gavin-mdwr_assigned_entry_cuts.csv`
- `2026-11-22_gavin-mdwr_assigned_entry_cuts_summary.json`

## Next

Run the regrown phase optimizer on these one-cut rows, then check whether the
phase can flatten the first-decade spike without pushing events past year 300.
