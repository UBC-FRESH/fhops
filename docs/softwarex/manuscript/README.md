# FHOPS SoftwareX Manuscript Workspace

This directory houses the working sources for the SoftwareX submission. It is intentionally separate from `reference/` (snapshots) and `assets/` (shared figures/data) so we can script builds without touching upstream artifacts.

```
manuscript/
├── outline.md               # Living section-by-section plan (mirrors SoftwareX template)
├── sections/                # Individual content files (LaTeX or include-ready snippets)
├── elsarticle/              # Stock CTAN elsarticle class + sample manuscript (unzipped 2025-11-23)
├── README.md                # (this file) build + workflow notes
└── Makefile (planned)       # TBD: wrapper around latexmk / tectonic / pandoc
```

## Template snapshot
- Source: https://mirrors.ctan.org/macros/latex/contrib/elsarticle.zip (mirrors the official Elsevier `elsarticle` bundle).
- Retrieved: 2025-11-23 via `curl -L -o docs/softwarex/reference/templates/elsarticle-template.zip …`.
- Contents live under `elsarticle/`. Keep upstream files pristine; place FHOPS-specific adjustments (title page, macros, includes) in `sections/` or a sibling folder so we can diff against the CTAN baseline easily.

## Planned workflow
1. **Template adaptation:** Use `elsarticle/template.tex` (or the sample `model1-num-names.tex`) as the seed for `fhops-softx.tex`. Keep custom includes inside `sections/` and add a thin wrapper file in the root that stitches everything together.
2. **Single-source content:** Draft prose in `sections/` (probably LaTeX include files) so we can reuse snippets inside Sphinx later via shared sources.
3. **Build command:** Introduce a Makefile (or `hatch` target) that runs `latexmk`/`tectonic` to produce PDF + bbl files. The command should also copy generated PDF into `docs/softwarex/assets/` for archival.
4. **Automation hooks:** Once figures/tables scripts exist, wire them into the Makefile so `make manuscript` regenerates everything end-to-end.

> TODO: Decide between `latexmk` + TeX Live (likely already available on CI) vs. `tectonic` (self-contained) and document the exact toolchain requirements below once chosen.

## Immediate todos
- [x] Unpack the `elsarticle` template locally, commit only the files we customize (class files can live under `elsarticle/`).
- [ ] Fill in `outline.md` with the initial section scaffolding and ownership notes.
- [ ] Decide on the LaTeX toolchain (likely `latexmk` + TeXLive) and document dependency versions here.
