> Public project-note copy. See the matching instance planning note.

# Gavin Lake MDWR — block vs group decision brief

Status: **decision gate, not a new model result**

Date: 2026-11-20

## Bottom line

The **block-level MDWR screen remains the public policy result**. The complete
group state is a spatial diagnostic and does **not** replace it.

| Result | Harvested volume | Area basis | Status |
| --- | ---: | --- | --- |
| Full-estate block screen | **4.154M m³ / 300 yr** | 5,663.7 ha estate | public policy screen |
| MDWR-only block screen | **0.594M m³ / 300 yr** | 2,799.3 ha MDWR | comparison baseline |
| Complete group state | **0.533M m³ / 300 yr** | 2,797.5 ha groups | diagnostic prototype |

The group/block MDWR ratio is **0.90**: **190 m³/ha** for the group state versus
**212 m³/ha** for the block screen.

## Group-state facts

- **34,512 groups** on **1,443 blocks**
- **2,797.5 ha** represented of 2,799.3 ha MDWR
- **1.8 ha** polygon residue across 22 blocks, maximum 0.02 ha
- **9,674 assigned groups / 1,430.3 ha**
- **24,838 standing groups**
- **9,674 cuts**
- final standing yield **1,274,641 m³**
- initial BA **102,863 m²**; final BA **255,737 m²**

The public `gavin-mdwr-group` scenario currently exposes the **2,586.8 ha**
cut/standing subset. The full 34,512-group state is in the instance matrix.

## Why the block screen stays public

1. The group model is still a schematic 10 m cell layout.
2. Minimum group size, cohort regeneration, and windthrow are not modelled.
3. The adjusted Appendix 9 compartment map has not been reconciled.
4. The 2007 GAR order and current UWR boundary have not been independently
   reviewed.
5. The group run has no policy target framework comparable to the block
   screen’s 13/37/11 status.
6. The group state is 1.8 ha short of the MDWR and uses a VRI cross-sectional
   BA fit, not a plantation BA model.

## Replacement gate

The group state can replace the block-level public result only after all of the
following are true:

- full 2,799.3 ha group coverage;
- reconciled adjusted Appendix 9 compartment boundaries;
- independently reviewed 2007 GAR order and current UWR boundary;
- minimum group size and 0.4/0.7 ha maximum enforced;
- 40 m²/ha pre-harvest BA tested at every entry;
- 3–5 cohort structure and plantation regeneration modelled;
- group and block target frameworks compared on the same area and schedule;
- a group-state public scenario whose geometry is small enough to use.

## Decision

- Keep `gavin-mdwr` as the public policy screen.
- Keep `gavin-mdwr-group` as a diagnostic prototype.
- Do not present the 0.533M m³ group result as a replacement or as a
  compliance-grade MDWR plan.

## Evidence

- `MKRF`/`GAVIN_MDWR_SCENARIO.pdf` — current block/group brief
- `notes/2026-11-19_gavin-mdwr-legal-review.md` — legal and map review
- `planning/2026-11-19_gavin-mdwr-mdwr-only-comparison.json`
- `planning/2026-11-19_gavin-mdwr_group_matrix_ba_summary.json`
- `planning/2026-11-19_gavin-mdwr_group_area_gap.json`
