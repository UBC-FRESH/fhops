> Public project-note copy. See the matching instance planning note.

# Gavin MDWR tail-limit decision — 2026-11-22

Status: **decision recorded**

## Decision

Option 1 is adopted: accept the **26/30 tail limit** and keep the legal-order
block screen public.

- `gavin-mdwr` remains the public policy screen.
- `gavin-mdwr-group` remains a diagnostic prototype.
- The entry-offset phase is recorded as **0.580M m³**, 26/30 periods in band,
  with late-period volumes of 6,603 / 3,944 / 3,841 / 3,474 m³.
- The old all-group regrown phase remains **0.679M m³ / 26-of-30**, also a
  diagnostic.
- No further phase restarts will be run on the current one-cut ledger.
- No group result is a replacement or compliance determination.

## Why

The phase optimizer can shift each block by at most 119 years and cannot move a
cut beyond year 299. The assigned entries are concentrated early. After the
phase cap, the eligible late-entry pool is too small to fill periods 260–290.
The four-period tail deficit is therefore structural for the current one-cut,
300-year, 1,386.4 ha assigned ledger.

It is not a local optimizer failure, and another restart is not justified.

## Reopening triggers

Revisit the replacement question only if one of these is approved:

1. a wider or asymmetric target band;
2. a longer horizon with additional legal entries;
3. a legal later-entry/re-entry model that adds cuts to the late periods.

Until then, the block screen remains public and the group screens remain
diagnostics.

## Evidence

- `planning/2026-11-22_gavin-mdwr_entry_phase.md`
- `planning/2026-11-22_gavin-mdwr_group_phase_entry_opt.csv`
- `planning/2026-11-22_gavin-mdwr_group_phase_entry_regrown_cuts.csv`
- `examples/demo_runs/GAVIN_MDWR_DECISION.md`
- `examples/demo_runs/GAVIN_MDWR_SCENARIO.md`
