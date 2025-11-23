# SoftwareX Exemplar Analysis Log

Targeted readings from the nine-paper exemplar set. Each section captures structure, readiness cues, and concrete takeaways we should mirror (file references point to the local PDFs under `docs/softwarex/reference/examples/`).

## PyLESA (SoftwareX 14, 2021) — `pylesa/pylesa.pdf`
- **Structural cues:** Opens with SoftwareX “Code metadata” and “Software metadata” tables that spell out repository, license, dependency stack, and contact info, immediately anchoring the reproducibility story (`docs/softwarex/reference/examples/pylesa/pylesa.pdf`, first two pages).
- **Architecture evidence:** Section 2 walks through the object-oriented architecture with Fig. 1 showing the Excel-to-Python workflow, control scripts (`fixed_order.py`, `mpc.py`), and automated parametric runs, grounding claims about modularity.
- **Benchmarking:** Section 3 supplies an illustrative district-heating sizing study plus 3D KPI plots (levelized cost vs. heat-pump/tank sizes) and a detailed MPC vs. fixed-order comparison.
- **FHOPS takeaway:** We need an equally explicit architecture figure, a reproducible control strategy narrative, and KPI plots tied to configurable experiments to convince SoftwareX reviewers we cover planning + optimisation rigor.
- **Citation-ready nuggets:** Quote-worthy text includes the gap analysis (Section 1) highlighting limits of existing planning tools (lack of temperature-dependent HP models, tariff modeling, MPC) and the “Impact” section enumerating how PyLESA fills those gaps. Capture those phrases verbatim for context when defining FHOPS differentiators.
- **Key refs to pull:** Section 1 (pp. 1–2) gap list; Fig. 1 (pp. 2–3) architecture; Section 3 (pp. 3–4) KPI plots; “Impact” section (p. 4).

## pycity_scheduling (SoftwareX 16, 2021) — `pycity_scheduling/pycity_scheduling.pdf`
- **Structural cues:** Code/Software metadata tables plus explicit dependency list (Pyomo, Shapely, pytest) and Docker install instructions demonstrate ready-to-run packaging.
- **Framework story:** Section 1 describes the multi-energy “energy hub” motivation and enumerates the gaps in existing tools (data processing, extensibility, coordination); later sections show how pycity_scheduling’s object model, hierarchy of actors, and optimisation workflows answer those gaps.
- **Governance & docs:** Links to a published user manual and dedicated support email build confidence that the project is maintained beyond a research prototype.
- **FHOPS takeaway:** Mirror the explicit dependency/Docker story, list the optimisation hierarchy we support, and make sure our user-facing docs are referenced directly from the manuscript.
- **Citation-ready nuggets:** Fig. 1 (power dispatch coordination approach) + the textual description of centralised vs. distributed optimisation in Section 1.2 can inform our explanation of FHOPS multi-agent scheduling capabilities.
- **Key refs to pull:** Section 1.1–1.3 for problem framing; Fig. 1 (p.~3) for coordination diagram; Section 4 for experimental validation narrative.

## cashocs v2.0 (SoftwareX 24, 2023) — `cashocs/cashocs.pdf`
- **Structural cues:** Titled as a “Software update” with cross-reference to the v1.0 SoftwareX publication, signalling long-term maintenance.
- **Release discipline:** Code metadata highlights GNU GPL licensing, FEniCS/PETSc/MPI dependencies, and rich release notes (hosted on ReadTheDocs); sections 2–3 detail major additions (space mapping framework, topology optimisation via level sets, MPI backend, constraint handling).
- **FHOPS takeaway:** Document our release cadence, changelog links, and “what’s new” table so reviewers see FHOPS as a living project with governed updates.
- **Citation-ready nuggets:** Section 2.1 (space mapping framework) and Section 2.3 (topology optimisation workflow) provide concrete examples of how to describe new capabilities succinctly; emulate their “Problem → Addition → Benefit” pattern for FHOPS release notes.
- **Key refs to pull:** Section 2’s bullet lists describing new functionality; Section 3’s performance comparisons; concluding remarks that highlight future roadmap.

## PyDDRBG (SoftwareX 17, 2022) — `pydrdbg/pydrdbg.pdf`
- **Benchmark strength:** Focuses on supplying a tunable benchmark generator for multimodal optimisation, including static + dynamic cases, robust mean peak ratio metric, and hooks for arbitrary algorithms (Section 2).
- **Usability signals:** Highlights compatibility with Python 3.7.9, minimal dependencies, and an example-driven tutorial flow.
- **FHOPS takeaway:** We should provide an equally clear benchmark manifest plus metrics guidance (e.g., how to compute convergence KPIs) so reviewers can compare FHOPS heuristics objectively.
- **Citation-ready nuggets:** The definition of the robust mean peak ratio (Section 2.3) and the explanation of how dynamic scenarios shift optima offer direct language for our benchmarking appendix.
- **Key refs to pull:** Section 2.1 dataset generator description; Fig. 1 parameter diagram; Section 3 evaluation procedure; Appendix tables listing benchmark configurations.

## GROMACS (SoftwareX 1–2, 2015) — `gromacs/gromacs.pdf`
- **Impact framing:** Emphasises scale (“from laptops to supercomputers”), multi-level parallelism (SIMD, CPU/GPU co-processing, domain decomposition, ensemble-level replica exchange), and feature breadth (free-energy workflows, compressed trajectory format).
- **Evidence:** Discusses performance gains in version 5 and references external frameworks (Copernicus), demonstrating ecosystem integration.
- **FHOPS takeaway:** Position FHOPS similarly around scalability tiers (laptop prototyping → cluster-scale runs) and highlight concrete performance improvements alongside integration points.
- **Citation-ready nuggets:** Section 3 (parallelisation strategy) includes quotable statements about “multi-level parallelism” that we can paraphrase when discussing FHOPS solver stacking.

## libxc (SoftwareX 7, 2018) — `libxc/libxc.pdf`
- **API stability story:** Paper states the library ships ∼400 functionals covering 50+ years of research and is used by 20+ downstream codes, underscoring backward compatibility requirements.
- **Governance:** Discusses collaborative maintenance across physics & quantum chemistry codes, implying strong contributor workflows.
- **FHOPS takeaway:** We must articulate our public API promises, downstream dependants, and test matrices that protect compatibility between releases.
- **Citation-ready nuggets:** Use their description of cross-community adoption (Section 1) as a model for communicating FHOPS’ multi-domain consumer list.

## MOOSE (SoftwareX 11, 2020) — `moose/moose.pdf`
- **Framework narrative:** Section 1 highlights MOOSE’s interface abstractions (PDE, boundary conditions, materials) and automatic handling of parallel, adaptive, nonlinear finite-element solves.
- **Ecosystem:** Lists diverse scientific domains already using MOOSE and stresses reusability/composability via interfaces and inheritance.
- **FHOPS takeaway:** Showcase FHOPS’ plugin interfaces and list real applications/teams to prove there is already an ecosystem depending on the framework.
- **Citation-ready nuggets:** Their explanation of “simultaneous execution of multiple sub-applications with data transfers between scales” mirrors FHOPS’ multi-stage optimisation loops—adapt the prose when discussing orchestrated heuristic passes.

## TSFEL (SoftwareX 11, 2020) — `tsfel/tsfel.pdf`
- **User-centric design:** Abstract emphasises >60 time-series features across temporal/statistical/spectral domains, with both GUI and Python package entry points plus computational cost evaluation.
- **Documentation:** Metadata points to licence (CC BY-NC-ND) and highlights how users can customise feature extraction via online interface or config files.
- **FHOPS takeaway:** Provide dual entry points (CLI + API/notebooks) and emphasise onboarding aids (wizards, presets) that align with our docs; include resource-usage notes for transparency.
- **Citation-ready nuggets:** Section 2’s breakdown of feature families is a template for how we can present FHOPS’ solver library taxonomy.

## Advanced LIGO/Virgo Open Data (SoftwareX 13, 2021) — `ligo_open_data/ligo_open_data.pdf`
- **Artifact packaging:** Massive author list and title focus on publishing full open data from observing runs, setting expectations for how SoftwareX papers describe data governance, checksum trails, and community access instructions.
- **Impact:** Paper positions the software/data release as infrastructure for the scientific community, underscoring the need for traceable data management plans.
- **FHOPS takeaway:** Plan to mirror their artifact section—document storage locations, persistent identifiers (DOIs), validation checksums, and community support routes for FHOPS datasets/models.
- **Citation-ready nuggets:** Lift the structure of their “Data release logistics” section (portal description + verification steps) to inform our artifact-packaging paragraph.
- **Key refs to pull:** Section 3 (data products), Section 4 (access instructions), and the appendix describing validation tools/checksums.

---

Next steps for analysis:
1. Deep-read PyLESA, pycity_scheduling, cashocs, and PyDDRBG to extract direct quotes/figures (with page numbers) we can reuse as benchmarks for FHOPS KPIs.
2. Expand this log with granular page/section references as we annotate the PDFs (architecture figures, validation tables, governance text).
3. Feed the extracted criteria—especially the Key refs above—back into `notes/submission_readiness_dashboard.md` so each indicator lists the FHOPS artifact or exemplar mapping that satisfies it.
4. When drafting sections in LaTeX, cite the specific pages/figures noted here to maintain traceability.
