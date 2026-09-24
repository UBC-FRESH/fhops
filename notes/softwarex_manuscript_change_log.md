# SoftwareX Manuscript Change Log (local)

Track local manuscript edits/text debt without polluting the main project CHANGE_LOG. Update this before each writing push.

## 2026-09-10 — Editorial Manager preview audit and replacement files
- Final reproducibility check ran `build_tables.py` and exposed stale med42 manuscript-ready rows. Regenerated Table 4/Table 5 from the actual shipped inputs, updated prose and the response letter, and verified a second clean regeneration matches the canonical CSV outputs exactly. Final values: med42 Table 4 SA −27271.22/1245.04 s, ILS −33452.28/1791.73 s, Tabu −46063.73/7391.10 s; Table 5 Bayes −35485.30, Δ −8214.08, 5.29 s.
- Added the two additional EM documents: one-page `cover-letter.pdf` and five-page `response-to-reviewers.pdf`, copied to `/home/gep/projects/fhops-manuscript/manuscript/build/`. The response PDF contains E1–E3 and R1.1–R1.7, uses manuscript number SOFTX-D-26-00697R1, and was checked for missing glyphs, Markdown leakage, and margin overflow.
- The first EM preview converted all uploads successfully, but exposed two real submission defects: Table 5 described a signed delta while its med42 cell remained positive `11454.66`, and the latexdiff PDF displayed unresolved old-key citations as `[?][8]` plus interleaved deleted/replacement prose.
- Corrected `build_tables.py` med42 sense from `minimize` to `maximize`. The underlying comparison consequently selects Bayes (−35485.30, 5.29 s), not Random (−39725.88), with signed Δ −7214.08 against the manuscript SA baseline −28271.22; synchronized the generated CSV/TeX, standalone asset mirrors, and prose.
- Regenerated the marked manuscript as additions-only highlighting (`latexdiff --type=CFONT --no-del --disable-citation-markup --math-markup=off`), eliminating unresolved old citations and garbled replacement text while retaining 1471 blue insertion spans.
- Aligned the manuscript competing-interest statement with the separately uploaded declaration (Rosalia Jaffray reports NSERC support; other authors report no known competing interests) and removed the redundant bibliography note that rendered as `Forest EngineeringPublished online`.
- Replacement artifacts: `/home/gep/projects/fhops-manuscript/manuscript/build/fhops-softx-em-flat.zip` (33-page standalone smoke build, 15 refs, no `[?]`/`??`) and `fhops-softx-marked.pdf` (33 pages, clean blue additions). The current 76-page EM preview must be regenerated after replacing both manuscript uploads; it is not the final approved preview.

## 2026-09-08 — Scope resolution + port to authoritative fhops-manuscript repo
- **Discovery:** the local `docs/softwarex/manuscript/` tree is a DIVERGED copy. The actual round-1 submission (`SOFTX-D-26-00697.pdf`) was built from the standalone repo `UBC-FRESH/fhops-manuscript` (`main` @ `cc12710`; local clone at `/home/gep/projects/fhops-manuscript`), which has a different abstract, highlights, keywords, 9-ref bibliography, and single-author front matter. All prior R1 edits in this repo landed on the wrong base.
- **Action taken:** ported the reviewer-driven fixes onto the standalone repo's own `revision/softx-r1` branch (that repo's `CHANGE_LOG.md` now records the full port). The submitted base text (abstract/highlights/keywords/authors/addresses) was preserved; edits are merge targets, not wholesale copies of the divergent tree.
- **Correction while porting:** the earlier ω-weights note in the local draft claimed tiny7/small21 overrides `1.0/0.2/0.1/0.05`, which does NOT match shipped data. All shipped scenarios set `objective_weights: production=1.0, mobilisation=0.5` (transitions/landing_surplus default 0.0). The ported note uses the verified weights.
- **Numbering shift:** with the comparative table inserted in `introduction.tex`, the submitted Table 3 (solver performance) becomes Table 1 in the revised manuscript; the response letter's Table numbering references must be re-checked against the ported build (30 pp, 15 refs).
- Local tree position: leave in place as reference text (some phrases reused verbatim), but no further manuscript edits here. Typesetting sweeps (enumerate list, `---` dashes, `\resizebox` tables, `\path` tokens) applied to the local tree are NOT R1-required for the submitted base — that base already uses `enumerate`, `\resizebox`, and `\breakpath`. Do not port formatting un-asked.

## 2026-09-07 – Round-1 revision (SOFTX-D-26-00697): review responses + benchmark-table prose fixes
- Branch `revision/softx-r1` created from `main` to carry all round-1 revision edits; nothing committed to `main`.
- **Published review reference.** `references.bib` `jaffray2025systematic` → `@article{jaffray2026systematic}` (IJFE, 2026, pp. 1–16, DOI 10.1080/14942119.2026.2662184, note: published online 2026-06-13). In-text "2025 / submitted to IJFE" language updated in `abstract.tex`, `introduction.tex`, `impact.tex`, `sections/includes/motivation_story.{md,tex}` (pandoc absent → mirrored `.tex` manually).
- **Comparative table + references.** Added comparative table (`tab:comparison`, Table 3 in revision) in `introduction.tex` rows: FHOPS, FPInterface, Woodstock/Tactical Optimisation (Remsoft), PRISM, research prototypes. New bib entries: `blouin2012fpinterface` (IJFE 23(1):64–69, 2012), `volpe2011fpinterface` (Volpé, ADVANCE 13(1), May 2011; corroborates member-only access), `ronnqvist2003optimization` (Math Programming 97:267–284, 2003), `segura2014dss` (Comput Electron Agric 101:55–67, 2014). FPInterface row scoped to publicly verifiable facts (simulation scope, member access); "OptiFor" NOT included (only a stand-level silvicultural thesis tool, Cao 2010, Dissertationes Forestales 103 — deferred to response letter).
- **COI/self-citation disclosure** added in `introduction.tex` (all three present authors co-author the cited review). Corrected earlier "two of three" wording: the review author list is Jaffray/Coupland/Paradis, so R.J., K.C., and G.P. are all co-authors (R1.5).
- **Objective-weight/sign-convention note.** Added `\subsubsection{Objective weights and sign convention}` + `Eq.~\eqref{eq:objective-weights}` in `software_description.tex` (score always maximised; default weights 1.0/1.0/0.0/0.0; tiny7/small21 overrides 1.0/0.2/0.1/0.05; negative values = penalty-dominated, not a change of sense).
- **Table 3 (original numbering) prose fixes** in `illustrative_example.tex`, numbers kept as-submitted:
  - Synthetic-small bullet: corrected "objective 39.79" → −75039.79, production 0.00 m³, staged 39.79 m³, runtimes 62.5/96.5/584.5 s (ILS/SA/Tabu), all solvers identical score (penalty-dominated, no improving move).
  - Med42 bullet: SA least-negative (best) −28271.2; ILS more volume but lower score −41581.7; Tabu −46063.7; no change of optimisation sense.
  - Table caption: "(lower objective is better for Med42)" → sign-convention note referencing `sec:objective-weights`.
  - Tuning paragraph: Med42 leaderboard row reframed as trailing the SA default (−28271.2) by 11454.7 units under maximisation convention.
- **Limitation** made explicit in `impact.tex` §Project maturity: not yet validated on other harvesting systems (single BC ground-based CTL archetype); scenario contract allows extension w/o solver changes.
- **Companion thesis cited.** Added `@mastersthesis{jaffray2026thesis}` (Jaffray, *Development and Evaluation of an Open-Source Tool for Machine Scheduling in Forest Operational Planning*, UBC MASc thesis, Apr 2026) to `references.bib`. Chapter 4 of the thesis is the third paper in the logical sequence (review → FHOPS → rolling-horizon evaluation): it tests FHOPS rolling-horizon design across 3 BC operating contexts (North-Island, Kamloops, Prince-George TSAs) × 3 problem sizes (6/6, 18/12, 40/24 blocks/machines) × θ∈{2,4,8,16} wk × f_roll∈{1,7,14} d = 108 deterministic runs (FHOPS v1.0.0, HiGHS v1.13.1, Pyomo v6.10.0, 1800 s MIP limit, SA 500 iter, fixed seeds; finding: re-optimization frequency dominates performance, diminishing returns beyond ~8 wk). Cited in `abstract.tex`, `introduction.tex`, `illustrative_example.tex`, `impact.tex`, `conclusions.tex`.
- **Refs/labels hygiene**: "Figures and tables referenced" uses `\ref{}`; added `sec:positioning` label in `introduction.tex`. Static check: 0 unresolved refs, 27/27 cite keys renderable, all 3 non-`sections/` labels (`tab:code-metadata`, `tab:current-code-version`, `fig:fhops-prisma-overview`) resolve to `metadata/`/`includes/`. Reference count in response letter updated 26 → 27.
- **Response letter** drafted at `docs/softwarex/tmp/response-letter.md` (editor + reviewer point-by-point; E1–E3, R1.1–R1.7).
- **Verification**: PDF build NOT run in this environment (no TeX; apt install blocked by libc dependency conflict). Must run `cd docs/softwarex/manuscript && make pdf` before push.

### 2026-09-08 — Typesetting pass: list formatting, dash hygiene, table fitting, faculty name
- **Contributions as a list.** Converted the "three contributions" paragraph in `introduction.tex` from inline numbered prose (`1. / 2. / 3.` glued into the paragraph) into a proper `enumerate` list; item labels terminated with full stops (`Architecture + data contract.` etc.). Renders as `1. 2. 3.` with indented continuation on the expected page.
- **Em-dash hygiene.** Replaced all 28 spaced en-dash separators (` – `) used as label/description connectors in `software_description.tex` and `illustrative_example.tex` with unspaced TeX em dashes (`---`). PDF audit: 0 spaced em/en dashes (remaining `–` glyphs are legit ranges: pagenums, year spans, verbatim publication titles); the pre-existing `—` glyph usages were already unspaced and untouched.
- **Wide auto-generated tables fit.** The 7-column `solver_performance.tex` and 6-column `tuning_leaderboard.tex` inputs (raw `tabular`) overhung the right margin by ~12–36 pt on the appendix page(s). Wrapped both `\input`s in `\resizebox{\linewidth}{!}{\input{...}}` inside `illustrative_example.tex` — no regeneration, no data change, numbers identical.
- **Overflowing bare path token.** Wrapped `tuning/playback/costing/scaling` (reproducibility/`benchmark_runs.log` paragraph, `illustrative_example.tex`) in `\path{...}` so it gains break points; previously the unbreakable token pushed past the margin at 590 pt.
- **Faculty name.** `metadata/code_metadata.tex` updated to "Faculty of Forestry \& Environmental Stewardship, UBC" (was stale "Faculty of Forestry"); `fhops-softx.tex:37` already used the current name. Verified in rendered PDF.
- **Verification (Tectonic mirror workflow).** Rebuilt via `/tmp/opencode/tex/tectonic -p -c minimal -o build fhops-softx.tex`; result 45 pages, 0 markdown artifacts, 0 spans ≥577 pt past the right margin, all paths LMMono12, `<slug>` intact. `docs/softwarex/tmp/fhops-softx-revision.pdf` refreshed.
- **Divergence note.** `sections/includes/cli_pipeline.tex` and `fhops_operational_formulation.tex` were hand-edited to `\path{}` in `.tex` ONLY; their `.md` primaries still carry markdown backticks and cannot express `\path` (would break Sphinx HTML). If `export_docs_assets.py` is ever run again, the `.tex` mirrors will be regenerated from `.md` and must be re-patched.

## 2025-12-03 – Table escaping + latexmk verification
- Added `_escape_latex` handling to `docs/softwarex/manuscript/scripts/build_tables.py` so the tuning leaderboard’s “Key Settings” column escapes underscores/percent signs/etc. before emitting LaTeX, preventing the `Missing $` errors we saw during the latest PDF build.
- Regenerated the solver/tuning tables and reran the latexmk→bibtex→latexmk cycle; `docs/softwarex/manuscript/build/fhops-softx.pdf` now compiles cleanly with all citations resolved.
- Logged the outcome in the planning note (Phase 3 sync task) so the remaining action is to run the paired Sphinx build once the next prose pass lands.
- Corrected the Med42 label in the table builder to “ground-based” (all four reference datasets share the same system) and rebuilt the tables/PDF so the manuscript no longer claims it is a skyline/tethered case.

## 2025-12-03 – Focus reset + branch kickoff
- Spun up `feature/softwarex-phase3` from `main` now that the MIP formulation branch is merged, keeping manuscript edits on a clean baseline aligned with the reproducibility assets.
- Added a Detailed Next Steps entry in `ROADMAP.md` calling out the renewed SoftwareX push and the requirement to sync note/changelog updates as work proceeds on the new branch.
- Inserted a “SoftwareX focus reset” block in `notes/softwarex_manuscript_plan.md` that documents the branch reset and tracks the open action to define the first sprint scope (Phase 2 polish + Phase 3 validation dry run).
- Recorded the need to reframe Section~2/3 narratives around the updated dataset ladder (tiny7/small21/med42 as reproducible ground-based cases, large84 deferred), call out the current status of warm-start MIP plumbing, incremental heuristics (parallel multistart OK, batched neighbours GIL-locked), the WIP nature of both formulations, and the rolling-horizon + BC deployment roadmap (cite the Jaffray literature review rather than in-progress thesis chapters).
- Updated Sections~\ref{sec:software-description} and \ref{sec:illustrative-example} to reflect the tiny7→small21→med42 ladder, defer large84 until rolling-horizon runs land, document the warm-start/heurstic caveats, and mention the rolling-horizon + BC deployment roadmap. Section~3 now references small21 in the benchmark/tuning narrative and explains why large84 is omitted.
- Regenerated the SoftwareX assets (fast mode) so Tables~1–2 and Figures~2–3 now consume the updated benchmark/tuning/playback/costing/scaling data for tiny7/small21/med42 + synthetic tiers. Logged the run in `docs/softwarex/assets/benchmark_runs.log` (fast=1 manual regeneration).

## 2025-11-24 – Pending text work
- **Section 5 – Conclusions.** Need a proper summary paragraph (recap FHOPS contributions, automation pipeline) plus future work sentence (BC deployments, forwarder/helper backlog). Currently a placeholder.
- **Metadata narrative.** Introduce the metadata tables in Section 1 or 2 (one paragraph explaining release/version, reproducibility log) so reviewers see context before Table refs.
- **Impact metrics references.** Once GitHub/PyPI stats are pulled, add citations/links to show adoption numbers (stars, downloads) rather than qualitative statements.

## 2025-11-27 – Phase 2 asset + reproducibility updates
- Enforced 300 dpi PNG generation inside `scripts/render_prisma_diagram.py` (adds Pillow-backed DPI tagging even when ImageMagick is unavailable) and regenerated `docs/softwarex/assets/figures/prisma_overview.(pdf|png)`; assets now satisfy the SoftwareX resolution requirement.
- Added a “Reproducibility log and environment” subsection to Section~3, tying every benchmark/tuning/playback artefact to its directory, the benchmark log (`docs/softwarex/assets/benchmark_runs.log`), and the recorded hardware/software context (72-core EPYC host, Ubuntu 24.04, Python 3.12.3, Pyomo 6.9.4, HiGHS 1.11.0, FHOPS 1.0.0a2).
- Documented the shared snippet workflow for Sphinx consumers in `docs/includes/softwarex/README.md`, updated the includes README checklist, and re-ran `export_docs_assets.py` so `.tex`/`.rst` outputs stayed in sync.
- Added a reusable CLI pipeline snippet (`sections/includes/cli_pipeline.md` → `.tex/.rst`) that Section~3 now `\input`s, and the same content is included in `docs/howto/benchmarks.rst` to keep manuscript + Sphinx instructions identical.
- Phase 2 close-out checklist added to the planning doc: highlights/abstract/metadata re-proofed, `GH-SWX-Phase2` marked complete, Phase 3 validation/submission bundle/metadata tasks staged with concrete commands and directory requirements.
- Section~\ref{sec:software-description} now includes the exact FHOPS MIP formulation (objective, decision variables, constraints, set/parameter definitions), satisfying the request to document the mathematical model reviewers will evaluate.

## 2025-11-24 – Section polish
- Added CLI/asset-path references in Section 1 and Section 3 so every table/figure cites its source directory (e.g., `docs/softwarex/assets/data/benchmarks/<slug>/summary.csv`, `docs/softwarex/assets/data/tuning`).
- Expanded Section 2 automation notes with concrete command examples and asset destinations.
- Rewrote Section 4 to highlight how FHOPS addresses Jaffray et al. gaps, emphasising BC focus today with extensibility for other regions/currencies later.
- Section 5 now references the backlog in `notes/softwarex_manuscript_change_log.md` so future work is tied to an actionable list.
- Added explicit CLI/source references after Tables~\ref{tab:benchmarks}--\ref{tab:tuning} and in the playback/costing paragraph so readers know which directories (\texttt{docs/softwarex/assets/...}) contain each artefact; noted CAD currency assumption and path to alternative machine-rate files.

---

## Imported entries from legacy manuscript CHANGELOG

### 2025-11-26 — PRISMA automation + shared figure embed
- Rebuilt `prisma_overview.tex` using plain TikZ (no external packages) and added a standalone driver so the figure can compile independently of the manuscript.
- Added `scripts/render_prisma_diagram.py` and wired it into `scripts/generate_assets.sh`; running `make assets` now regenerates `docs/softwarex/assets/figures/prisma_overview.(pdf|png)` automatically (SVG generated opportunistically when `pdf2svg` is installed).
- Updated `docs/overview.rst` to embed the PNG alongside the narrative include, ensuring the user guide displays the exact same visual as the manuscript.
- Documented the automated workflow in `docs/softwarex/manuscript/README.md` and `sections/includes/README.md`, and marked the Phase 1 PRISMA task complete inside `notes/softwarex_manuscript_plan.md` / `notes/submission_readiness_dashboard.md`.
- Introduced `FHOPS_ASSETS_FAST` handling inside `scripts/generate_assets.sh` (cuts benchmark/tuning budgets for quick iterations) and captured the manual verification checklist + env-var guidance in `docs/softwarex/manuscript/README.md`. The submission readiness dashboard now references the canonical figure assets.
- Added `scripts/run_manuscript_benchmarks.sh` plus new Makefile targets (`make manuscript-benchmarks`, `make manuscript-benchmarks-fast`) so we can rerun the entire asset pipeline on demand, log runtimes + asset hashes to `docs/softwarex/assets/benchmark_runs.log`, and satisfy the reproducibility checklist captured in `notes/submission_readiness_dashboard.md`.

### 2025-11-25 — PRISMA workflow figure wiring
- Inserted the PRISMA-style workflow include (`\input{sections/includes/prisma_overview}`) into `sections/software_description.tex`, anchoring the architecture narrative around the same figure used in the WS3 EI manuscript pattern.
- Created `docs/includes/softwarex/prisma_overview.rst`, an interim narrative-only include so the Sphinx Overview can cite the same pipeline until we export a PNG version of the diagram.
- Updated `docs/overview.rst` to include the new snippet under an “Automation pipeline” section, keeping the user guide aligned with the manuscript narrative ahead of the future PNG/SVG export workflow.
- Updated `docs/softwarex/manuscript/sections/includes/README.md` with maintenance notes for the PRISMA figure (package requirements, manual regeneration steps, future PNG workflow) and tracked the work inside `notes/softwarex_manuscript_plan.md`.
- Expanded `notes/thesis_alignment.md` with explicit Chapter 2 case-study definitions (coastal skyline/tethered, interior community forest, salvage/MPB) plus checkpoint dates (dataset freeze, scenario cartridge export, solver alignment, KPI drafting, thesis submission) so we can reference a single source when validating SoftwareX scope boundaries.

### 2025-11-24 — Shared content exporter & dataset summaries
- Introduced `scripts/export_docs_assets.py` and wired it into `generate_assets.sh` so all Markdown snippets under `sections/includes/` render automatically into LaTeX + Sphinx-ready `.rst` files during `make assets`.
- Added the first shared narrative (`motivation_story.md`) and included it in both the manuscript and `docs/overview.rst`, ensuring the docs and paper stay synchronized on the FHOPS motivation text.
- Implemented `scripts/run_dataset_inspection.py`, which inspects `examples/tiny7`, `examples/med42`, and a freshly generated `synth --tier small` bundle; outputs JSON summaries + an index under `docs/softwarex/assets/data/datasets/`, and snapshots the synthetic scenario for reproducibility.
- Updated the Phase 1 plan to reflect the completed scenario-ingest automation, keeping the assets checklist aligned with the new scripts.
- Expanded `scripts/generate_assets.sh` so `make assets` now benchmarks `tiny7`, `med42`, and the synthetic tier across SA/ILS/Tabu (with compare presets) and writes per-scenario summaries/telemetry plus an aggregated `benchmarks/index.json`.
- Added a shared heuristic solver matrix/notes pair (`heuristics_matrix.csv`, `heuristics_notes.md`) that the exporter converts into LaTeX/RST so both the manuscript and `docs/howto/heuristic_presets.rst` present identical solver guidance.
- Wired `scripts/run_tuner.py` into the asset pipeline so condensed tuning studies run via `scripts/run_tuning_benchmarks.py` and drop comparison/leaderboard/difficulty tables inside `docs/softwarex/assets/data/tuning/`.
- Added `benchmark_kpis.csv` + `benchmark_kpis_notes.md` and wired them through the exporter so both the manuscript and `docs/howto/benchmarks.rst` can reuse the same SA/ILS/Tabu KPI table.
- Added `scripts/run_playback_analysis.py` plus pipeline hooks that replay the best SA/ILS schedules (deterministic + stochastic) for tiny7, med42, and the synthetic tier, writing shift/day summaries + metrics under `docs/softwarex/assets/data/playback/` for manuscript robustness figures.
- Added `scripts/run_costing_demo.py`, which exercises `fhops dataset estimate-cost` for representative med42 machines, logs telemetry JSONL, and emits `cost_summary.csv/json` under `docs/softwarex/assets/data/costing/` for the machine-rate discussion.
- Added `scripts/run_synthetic_sweep.py` so we can regenerate synthetic small/medium/large tiers, benchmark SA runtimes, and capture `scaling_summary.csv/json` plus `runtime_vs_blocks.png` under `docs/softwarex/assets/data/scaling/`.

### 2025-11-23 — Workspace scaffolding & exemplar analysis
- Created the `docs/softwarex/` workspace with dedicated `reference/`, `manuscript/`, `assets/`, and `submissions/` folders plus a top-level README describing ownership and next steps.
- Logged provenance for all reference artifacts (Guide for Authors snapshot, elsarticle template bundle, Crossref most-cited dump, nine exemplar PDFs) via `docs/softwarex/reference/README.md`.
- Seeded the manuscript working area: added `manuscript/README.md` outlining the build workflow and `manuscript/outline.md` mirroring the SoftwareX section structure with FHOPS source notes.
- Expanded `notes/softwarex_exemplar_analysis.md` with takeaways + citation-ready cues for all nine exemplar papers to guide drafting and readiness criteria.
- Downloaded the CTAN `elsarticle` template, extracted it into `docs/softwarex/manuscript/elsarticle/`, and updated the manuscript README to record the template snapshot plus next actions.
- Added an initial `fhops-softx.tex` wrapper and a `Makefile` that runs `latexmk -pdf` into `build/`, establishing the traditional TeX Live toolchain for future drafts.
- Added placeholder section includes under `docs/softwarex/manuscript/sections/` (`introduction.tex`, `software_description.tex`, etc.) plus highlights/abstract files, and rewired `fhops-softx.tex` to `\input` them so future drafting is modular.
- Documented the latexmk workflow and TeX Live requirements in `docs/softwarex/manuscript/README.md`.
