# Jaffray Thesis Alignment Checklist

> Track how the SoftwareX manuscript (FHOPS platform paper) stays aligned with Rosalia Jaffray’s MASc thesis. Goal: publish FHOPS as a tooling/architecture paper without pre-empting the thesis’ Chapter 2 case-study contributions.

## Ownership Split
- **SoftwareX manuscript (FHOPS tooling):**
  - Platform architecture (scenario contract, optimiser stack, telemetry).
  - Reproducible workflow + benchmark scripts.
  - High-level synthetic/illustrative examples showing capability (no deep BC case studies).
  - Pointers to the open datasets/templates Rosalia will later use.
- **Jaffray Chapter 2 (BC case studies):**
  - Detailed deployment of FHOPS on 2–3 BC-based scenarios (initial plan per `tmp/jaffray-masc-review-paper` + thesis repo notes: (i) skyline corridor/steep tethered harvest in Coastal BC, (ii) community-forest ground-based plan in the Interior, (iii) beetle/salvage recovery block near Prince George).
  - Analysis answering the “open questions” from the thesis intro/lit review (trade-off mapping, solution quality vs. operations context).
  - Policy/management discussion tied to real data (inventory, productivity, costs) from BC partners.
  - Deliverables aligned with `tmp/jaffray-rosalia-masc-proposal` Table 1.1 (Ch.1 methodology + Ch.2 validation roadmap).

### Chapter 2 deliverables (from thesis repos)
- **Case Study A – Coastal skyline/tethered corridor (Northern Vancouver Island):**
  - Focus: skyline corridor layouts + winch-assist transitions raised in `chap_1/chap_1.tex` (harvest system table + FRPA discussion).
  - Data: skyline productivity logs, partial-retention prescriptions, mobilisation/low-bedding rules (stored under Rosalia’s private data dirs; **never** ingest into FHOPS repo until thesis submission).
  - FHOPS tie-in: demonstrate cable + tethered presets, but keep KPI tables/plots in Rosalia’s repo.
- **Case Study B – Community-forest ground-based package (BC Interior):**
  - Focus: multi-block scheduling for a small tenure (mix of buncher/skidder + hoe-chucking) responding to governance questions from Chapter 1 §§“Forest Operations in British Columbia”.
  - Data: community-forest block inventory, operator roster, mobilisation costs; these remain private while we publish only synthetic analogues.
  - FHOPS tie-in: we can mention that FHOPS supports small-tenure planning but defer all real KPI/value plots to Chapter 2.
- **Case Study C – Salvage / MPB recovery near Prince George:**
  - Focus: salvage corridors, helicopter-vs-ground trade-offs, policy hooks tied to FRPA updates (Chap. 1 lines 95ff.).
  - Data: wildfire/MPB inventory + productivity calibrations; again, embargoed until the thesis chapter is submitted.
- If Rosalia narrows to two scenarios, Case Study A (coast) and B (interior community forest) are mandatory; Case C is optional stretch.

### Reserved content checklist
- [ ] Real BC scenario YAMLs, block/machine productivity data, and KPIs stay in Rosalia’s repos until Chapter 2 is submitted.
- [ ] Case-specific figures (e.g., skyline corridor trade-off curves, mobilisation cost comparisons between licensees) appear only after Chapter 2 defence.
- [ ] Policy text around Indigenous/community-forest governance remains thesis-only unless Rosalia signs off on a short teaser paragraph.
- [ ] Any machine/tuning presets derived from BC partners (versus public FPInnovations data) must be redacted or anonymised before inclusion in SoftwareX assets.

### Chapter 2 checkpoints (working timeline)
1. **C2-CP0 – Dataset freeze (2025-12-05):** Rosalia locks the raw block/machine datasets in `tmp/jaffray-rosalia-masc-thesis/data/` so FHOPS synthetic analogues can be generated without referencing private data.
2. **C2-CP1 – FHOPS scenario cartridge (2025-12-15):** Rosalia exports internal YAML bundles; we verify loader compatibility privately but do not commit them.
3. **C2-CP2 – Solver/tuning alignment (2026-01-10):** Rosalia runs SA/ILS/Tabu + tuning harness on the BC datasets; we only consume summary statistics for cross-checking heuristics, no raw telemetry in FHOPS repo.
4. **C2-CP3 – KPI + trade-off drafting (2026-01-24):** Thesis Chapter 2 figures/tables drafted; we review to ensure SoftwareX manuscript does not pre-empt them.
5. **C2-CP4 – Thesis submission freeze (2026-02-07):** Once Rosalia files Chapter 2, we can reference high-level outcomes (e.g., “validated on three BC case studies”) in FHOPS release notes but still avoid data dumps until publication.

For each checkpoint, add a short note here once completed plus a link to Rosalia’s repo commit/Overleaf snapshot (kept private).

## Action Items
- [ ] Keep Section 1 (Motivation) in the SoftwareX paper high-level; cite the thesis literature but avoid case-specific insights reserved for the thesis.
- [ ] Limit Section 3 (Illustrative example) to synthetic or anonymised demos; reference forthcoming thesis work for real BC case studies.
- [ ] Coordinate with Rosalia when planning figures/tables to ensure nothing conflicts with her Chapter 2 storyline.
- [ ] Update this note whenever the thesis plan shifts (e.g., if Rosalia adds/removes case studies or checkpoint dates slip).

## References
- `tmp/jaffray-rosalia-masc-proposal/` (see Chapter 2 + Table 1.1 for case-study roadmap).
- `tmp/jaffray-rosalia-masc-thesis/` (full thesis draft once Chapter 2 is written).
