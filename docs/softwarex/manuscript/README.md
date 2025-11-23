# FHOPS SoftwareX Manuscript Workspace

This directory houses the working sources for the SoftwareX submission. It is intentionally separate from `reference/` (snapshots) and `assets/` (shared figures/data) so we can script builds without touching upstream artifacts.

```
manuscript/
├── outline.md               # Living section-by-section plan (mirrors SoftwareX template)
├── sections/                # Individual content files (LaTeX include snippets)
├── elsarticle/              # Stock CTAN elsarticle class + sample manuscript (unzipped 2025-11-23)
├── fhops-softx.tex          # Wrapper that stitches sections/includes together
├── references.bib           # Manuscript BibTeX database (exemplar entries + FHOPS cites)
├── Makefile                 # latexmk-based build entry point
├── README.md                # (this file) build + workflow notes
└── build/ (generated)       # latexmk output directory (ignored)
```

## Template snapshot
- Source: https://mirrors.ctan.org/macros/latex/contrib/elsarticle.zip (mirrors the official Elsevier `elsarticle` bundle).
- Retrieved: 2025-11-23 via `curl -L -o docs/softwarex/reference/templates/elsarticle-template.zip …`.
- Contents live under `elsarticle/`. Keep upstream files pristine; place FHOPS-specific adjustments (title page, macros, includes) in `sections/` or sibling files so we can diff against the CTAN baseline.

## Build workflow (`latexmk` + TeX Live)
We use the standard TeX Live toolchain (preferred by SoftwareX) orchestrated through `latexmk`.

```
# Build PDF into build/fhops-softx.pdf
make          # equivalent to `make default`

# Clean auxiliary files + build directory
make clean
```

`latexmk` will automatically run pdflatex/bibtex as needed. You’ll need a TeX Live installation that includes common packages (`latexmk`, `hyperref`, `lineno`, etc.). On Debian/Ubuntu, `sudo apt-get install texlive-full latexmk` is the quickest path; we can revisit a lighter scheme/tectonic later if build times become an issue.

## Planned workflow
1. **Template adaptation:** `fhops-softx.tex` pulls the elsarticle class and `\input`s the files under `sections/`, with citations managed via `references.bib`. Section files are intended to be reusable (shared with Sphinx via includes later).
2. **Single-source content:** Draft prose in `sections/*.tex`. When content stabilises, we can symlink or otherwise share snippets with the Sphinx docs.
3. **Automation hooks:** Once figure/table scripts exist, wire them into the Makefile (e.g., `make assets`) so `make` regenerates everything end-to-end before `latexmk` runs.

## Immediate todos
- [x] Unpack the `elsarticle` template locally, commit only the files we customise.
- [x] Decide on the LaTeX toolchain (latexmk + TeX Live) and document it here.
- [ ] Flesh out each section file with real FHOPS content and tie in shared snippets/figures.
