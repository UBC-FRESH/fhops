# FHOPS SoftwareX Manuscript Workspace

This directory houses the working sources for the SoftwareX submission. It is intentionally separate from `reference/` (snapshots) and `assets/` (shared figures/data) so we can script builds without touching upstream artifacts.

```
manuscript/
├── outline.md           # Living section-by-section plan (mirrors SoftwareX template)
├── sections/            # Individual content files (LaTeX or include-ready snippets)
├── README.md            # (this file) build + workflow notes
└── Makefile (planned)   # TBD: wrapper around latexmk / tectonic / pandoc
```

## Planned workflow
1. **Template adaptation:** Copy `elsarticle` class + sample manuscript from `../reference/templates/elsarticle-template.zip` into `manuscript/` (next action). We’ll keep our modifications tracked in git so diffs vs. upstream are obvious.
2. **Single-source content:** Draft prose in `sections/` (probably LaTeX include files) so we can reuse snippets inside Sphinx later via shared sources.
3. **Build command:** Introduce a Makefile (or `hatch` target) that runs `latexmk`/`tectonic` to produce PDF + bbl files. The command should also copy generated PDF into `docs/softwarex/assets/` for archival.
4. **Automation hooks:** Once figures/tables scripts exist, wire them into the Makefile so `make manuscript` regenerates everything end-to-end.

## Immediate todos
- [ ] Unpack the `elsarticle` template locally, commit only the files we customize (class files can live under `template/`).
- [ ] Fill in `outline.md` with the initial section scaffolding and ownership notes.
- [ ] Decide on the LaTeX toolchain (likely `latexmk` + TeXLive) and document dependency versions here.
