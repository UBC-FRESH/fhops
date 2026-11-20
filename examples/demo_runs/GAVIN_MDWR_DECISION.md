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

The public `gavin-mdwr-group` scenario now exposes the full **2,797.5 ha**
group-cohort state.

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

## Compliance status matrix

| Requirement | Current state |
| --- | --- |
| No clearcut in MDWR | retained as a stricter policy choice; FSP Table 7 allows clearcut on fresh/wetter sites |
| Table 30 pass intensity | **not the legal mapping** — current model uses MWP Table 30 High 33 / Moderate 25 / Low 20; the 2007 GAR order Table 2 uses Low 33 / Moderate 25 / High 20 |
| Stand-level BA | current gate uses 40 m²/ha for all BEC; legal order requires **45 m²/ha in ICH** and 40 m²/ha elsewhere |
| Opening size | maximum 0.4/0.7 implemented; **minimum 0.1 ha and frost-prone 0.1–0.3 ha are not implemented** |
| 3–5 cohorts | represented in the cohort state |
| Minimum group size | not implemented |
| Preparatory thinning | not implemented |
| Adjusted Appendix 9 compartment map | not reconciled |
| 2007 GAR order / current UWR boundary | not independently reviewed |
| Group target framework | not implemented |
| Full group area | 2,797.5 ha of 2,799.3 ha |
| Public group scenario | full 34,512-group cohort state, diagnostic only |

## Legal order conflict

The exact 2007 Transition and Deep Snowpack GAR order (Amendment
TransDeep_Feb07_ord.pdf) was reviewed on 20 November 2026. It establishes
parameters that differ from the MWP #3 Table 30 assumptions used by the current
public screen:

- **GWM 6:** group selection requires ≥45 m²/ha in ICH and ≥40 m²/ha elsewhere;
- **Table 2:** Low 33% / 120-year rotation / 3 patches; Moderate 25% / 160 / 4;
  High 20% / 200 / 5;
- **GWM 10 / Table 3:** openings 0.1–0.4 ha warm aspect, 0.1–0.7 ha other, and
  0.1–0.3 ha on frost-prone sites.

The current screen uses the MWP #3 Table 30 mapping (High 33, Moderate 25, Low
20) and a 40 m²/ha gate everywhere. It is therefore **not compliant with the
2007 GAR order** and must not be presented as such. A legal-order rebuild is
required before any replacement decision.

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
