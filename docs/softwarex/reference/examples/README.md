# SoftwareX Exemplar Library

Curated set of high-quality SoftwareX publications we will mine for structure, tone, and readiness indicators. Each entry lists why it is relevant to FHOPS and any immediate follow-ups (for example, downloading the PDF once we work around Elsevier's automated download restrictions).

> **Note on PDFs:** ScienceDirect currently serves Cloudflare-protected HTML when requested from the CLI, so the actual PDF assets still need to be downloaded through an authenticated browser session. Each entry below includes the DOI/PII so we can fetch the definitive copy manually and store it alongside these notes.

## Targeted Optimization & Planning Exemplars

### PyLESA — Local Energy Planning Toolkit
- **Citation:** Lyden et al., SoftwareX 14 (2021), DOI `10.1016/j.softx.2021.100699`, PII `S2352711021000443`.
- **Why it matters:** Demonstrates how to position a planning-oriented Python framework with modular scenarios, validation studies, and documented reproducibility (data packages + configuration templates).
- **Key signals to emulate:** Explicit success metrics for case studies, scenario library architecture diagrams, integration between CLI tooling and notebooks, and a metadata table that ties software features to policy context.
- **Next action:** Manual PDF download + highlight extraction for our reference quotes.

### pycity_scheduling — Multi-Energy Scheduling Framework
- **Citation:** Kather et al., SoftwareX 14 (2021), DOI `10.1016/j.softx.2021.100839`, PII `S2352711021001230`.
- **Why it matters:** Focuses on optimization/scheduling workflows similar to FHOPS, with emphasis on modular problem definitions, KPIs, and validation across multiple district energy scenarios.
- **Key signals to emulate:** Benchmark suite description, configuration inheritance patterns, rigorous reproducibility narrative (input data provenance + solver settings), and cross-references to GitHub CI for experiments.
- **Next action:** Pull PDF + copy their KPI framing for our readiness dashboard.

### cashocs — Adjoint-Based Shape Optimization
- **Citation:** Blauth et al., SoftwareX 26 (2024), DOI `10.1016/j.softx.2023.101577`, PII `S235271102300273X`.
- **Why it matters:** Modern SoftwareX paper that highlights automation hooks, tutorial-driven documentation, semantic versioning, and automated validation for optimization codebases.
- **Key signals to emulate:** Release governance narrative (semantic tags + DOI-minted artifacts), end-to-end tutorial gallery, explicit mention of CI hardware specs, and impact section quantifying downstream adoption.
- **Next action:** Capture PDF figures showing workflow + include their release governance checklist in our plan.

### PyDDRBG — Benchmarking Optimization Methods
- **Citation:** Arora et al., SoftwareX 15 (2021), DOI `10.1016/j.softx.2021.100961`, PII `S2352711021001850`.
- **Why it matters:** Provides a reproducible benchmarking harness for multimodal optimization—close to FHOPS’ narrative around evaluating heuristics and search strategies.
- **Key signals to emulate:** Dataset/benchmark manifest, plug-in design discussion, automated result dashboards, and guidance for extending the framework.
- **Next action:** Download PDF + extract their benchmark manifest template for our submission readiness dashboard.

## High-Impact (Top-Cited) Exemplars
Sourced via Crossref (`docs/softwarex/reference/softwarex_top_cited_crossref.json`, sorted by `is-referenced-by-count`). These papers shape editor expectations for polish, reproducibility, and community impact.

### GROMACS — HPC Molecular Simulation
- **Citation:** Abraham et al., SoftwareX 1–2 (2015), DOI `10.1016/j.softx.2015.06.001`, PII `S2352711015000059`.
- **Signals:** Mature governance model, explicit multi-platform benchmark tables, and a strong “impact and reuse” story (industrial + academic uptake).
- **Takeaway for FHOPS:** Quantify adoption (downloads, institutions, benchmarks) and include performance scaling figures, not just qualitative claims.

### libxc — Functional Library for DFT
- **Citation:** Lehtola et al., SoftwareX 7 (2018), DOI `10.1016/j.softx.2018.11.002`, PII `S2352711017300602`.
- **Signals:** Highlights API stability guarantees, contribution workflow, and backwards compatibility testing—useful for our discussion on FHOPS’ public API freeze.

### MOOSE — Multiphysics Framework
- **Citation:** Permann et al., SoftwareX 11 (2020), DOI `10.1016/j.softx.2020.100430`, PII `S2352711019302973`.
- **Signals:** Clear separation of core architecture vs. application ecosystem, and a reproducibility matrix (compilers, MPI stacks, OS targets). Editors reward that level of operational detail.

### TSFEL — Time-Series Feature Extraction Library
- **Citation:** Barandas et al., SoftwareX 11 (2020), DOI `10.1016/j.softx.2020.100456`, PII `S2352711020300017`.
- **Signals:** Demonstrates how to connect tutorials, API docs, and benchmark leaderboards into one cohesive narrative—ideal reference for integrating FHOPS manuscript + Sphinx docs.

### Open Data from Advanced LIGO/Virgo
- **Citation:** Abbott et al., SoftwareX 13 (2021), DOI `10.1016/j.softx.2021.100658`, PII `S2352711021000030`.
- **Signals:** Exemplifies artifact packaging (DOIs, checksums, portal instructions) and an impact statement framed around community data reuse—relevant to our planned artifact bundle.

> **To do:** Each folder under `docs/softwarex/reference/examples/` contains DOI/PII stubs. Replace the “PDF pending” note after downloading the definitive PDFs via a browser session.
