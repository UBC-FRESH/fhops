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

### Reserved content checklist
- [ ] Real BC scenario YAMLs, block/machine productivity data, and KPIs stay in Rosalia’s repos until Chapter 2 is submitted.
- [ ] Case-specific figures (e.g., skyline corridor trade-off curves, mobilisation cost comparisons between licensees) appear only after Chapter 2 defence.
- [ ] Policy text around Indigenous/community-forest governance remains thesis-only unless Rosalia signs off on a short teaser paragraph.
- [ ] Any machine/tuning presets derived from BC partners (versus public FPInnovations data) must be redacted or anonymised before inclusion in SoftwareX assets.

## Action Items
- [ ] Keep Section 1 (Motivation) in the SoftwareX paper high-level; cite the thesis literature but avoid case-specific insights reserved for the thesis.
- [ ] Limit Section 3 (Illustrative example) to synthetic or anonymised demos; reference forthcoming thesis work for real BC case studies.
- [ ] Coordinate with Rosalia when planning figures/tables to ensure nothing conflicts with her Chapter 2 storyline.
- [ ] Update this note whenever the thesis plan shifts (e.g., if Rosalia adds/removes case studies).

## References
- `tmp/jaffray-rosalia-masc-proposal/` (see Chapter 2 + Table 1.1 for case-study roadmap).
- `tmp/jaffray-rosalia-masc-thesis/` (full thesis draft once Chapter 2 is written).
