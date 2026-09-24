# Tactical–Operational Expansion Provenance

Date: 2026-09-24
Issues: #36, #37

## Purpose

This note records the public provenance trail for the TOPM-inspired FHOPS expansion without
redistributing restricted thesis, commercial, or publisher documents. It complements
`notes/reference_log.md`, which remains focused primarily on FPInnovations/FERIC productivity and
cost references.

## Source policy

- Public repository content is limited to bibliographic records, short summaries, and design
  implications.
- Full-text documents stay in the private `reference-documents` vault or with their original
  publishers/institutions.
- No TOPM, OperMAX, thesis appendix, or commercial dataset values are copied into public FHOPS
  fixtures. Acceptance scenarios must be newly synthesized and copyright-safe.

## Historical lineage

| Source | Public status | What FHOPS takes from it |
|---|---|---|
| Oborn, R. M. R. (1996), *A Mathematical Programming Application with Semi-Continuous Variables for Multi-Faceted Forest Operations Planning*, MScFE thesis, University of New Brunswick | Cite bibliographically; do not redistribute PDF or appendices | Direct TOPM formulation reference: multi-year/multi-season periods, harvest-system alternatives, semi-continuous harvest quantities, products/mills, transport, inventory, purchases, roads, silviculture, fleet economics, discounting, and scenario comparison. |
| Richard and Gunn (1996), tactical planning model/software conference paper | Bibliographic reference only | Early software-system framing for tactical harvest/transport planning. |
| Barrett (1997), Canadian Wood Fibre Centre technology delivery | Bibliographic reference only | Context for the research-to-practice pipeline around TOPM-era decision support. |
| Gunn (1998), Atlantic Canada forest-products policy/modelling perspective | Bibliographic reference only | Policy and industrial context for the TOPM/MAXPLAN/OperMAX family. |
| Feller and Richards (1999), *MAXPLAN: A Forest Operations Planning System* | Bibliographic reference only | Commercial planning-system predecessor/spinoff context. |
| Robak (1999), *OperMAX: A Forest Operations Planning System* | Bibliographic reference only | Commercial TOPM-like planning shell context. |
| Lehoux, Marier, D’Amours, Ouellet, and Beaulieu (2012), *Le réseau de création de valeur de la fibre de bois canadienne*, CIRRELT-2012-33 | Public CIRRELT PDF: https://www.cirrelt.ca/documentstravail/cirrelt-2012-33.pdf | Confirms OperMAX as a Force/Robak multi-year operations-planning optimizer spanning harvest, transport, silviculture, road construction, purchases, mill-yard inventories, roadside/sublicensed sales, and inter-mill deliveries. |
| Jaffray, Coupland, and Paradis (2026), *Forest harvesting operational planning tools: a systematic review...* IJFE | Published article; cite DOI 10.1080/14942119.2026.2662184 | Modern tool-design criteria: parameterized site specificity, documented assumptions, validation, uncertainty/re-planning support, reproducibility, adoption checklist, and open artifacts. |

## OperMAX/RoadOpt design lessons for FHOPS

The public TOPM/OperMAX lineage suggests five implementation lessons:

1. **Scenario shell matters.** Users need to store, validate, compare, and rerun scenario variants
   without manually editing solver matrices.
2. **Validation must happen before solve.** Stand-alone contract checks should catch missing roads,
   invalid yields, inconsistent units, infeasible system eligibility, and inventory imbalance risks.
3. **Planning is broader than harvest allocation.** Roads, silviculture, product flows, purchases,
   inventories, and fleet capacity must share one economic/time model when enabled.
4. **Solver independence is essential.** TOPM’s MIPIII-specific semi-continuous implementation is
   historically important, but FHOPS should express the semantics portably and use native solver
   features only as optional optimizations.
5. **Reports are part of the model.** Decision vectors, objective decomposition, inventory balances,
   road/fleet state, and infeasibility diagnostics must be first-class outputs.

## Relationship to existing FHOPS artifacts

- `notes/tactical_operational_expansion_plan.md` — functional scope and delivery plan.
- `notes/adr/0001-tactical-operational-architecture.md` — architecture decision record.
- `tests/fixtures/tactical_operational/topm-mini/specification.yaml` — copyright-safe executable
  acceptance specification.
- `notes/tactical_operational_compatibility_baseline.md` — current operational behavior that Phase 6
  must preserve.
