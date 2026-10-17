# FHOPS SoftwareX Manuscript Workspace

> **Superseded draft — the canonical manuscript lives in
> [UBC-FRESH/fhops-manuscript](https://github.com/UBC-FRESH/fhops-manuscript).**
> The LaTeX prose in this directory (`fhops-softx.tex`, `sections/*.tex`, `outline.md`) is an
> early draft that is no longer maintained: its numbers and wording predate the FHOPS 1.0.1
> assets and must not be quoted. Numbers come from the generated tables and figures under
> `docs/softwarex/assets/` (the source of record), which the canonical manuscript imports.
>
> What remains maintained here, because FHOPS itself uses it:
> - `scripts/` — the asset pipeline (`generate_assets.sh`, `run_manuscript_benchmarks.sh`,
>   `build_tables.py`, `audit_asset_consistency.py`, `asset_hash.py`, …) that writes
>   `docs/softwarex/assets/**`;
> - `sections/includes/*.md|csv` — shared snippets exported to the Sphinx docs
>   (`docs/includes/softwarex/*.rst`) by `scripts/export_docs_assets.py`;
> - `metadata/*.tex` — the code-metadata tables (kept factually correct for the release).

This directory houses the working sources for the SoftwareX submission. It is intentionally separate from the private `reference-documents/` submodule (full-text snapshots) and `assets/` (shared figures/data) so we can script builds without touching upstream artifacts.

```
manuscript/
├── outline.md               # Living section-by-section plan (mirrors SoftwareX template)
├── sections/                # Individual content files (LaTeX include snippets)
├── elsarticle/              # Stock CTAN elsarticle class + sample manuscript (unzipped 2025-11-23)
├── fhops-softx.tex          # Wrapper that stitches sections/includes together
├── references.bib           # Manuscript BibTeX database (exemplar + forestry cites + FHOPS refs)
├── scripts/                 # Asset-generation hooks (call FHOPS benchmarks etc.)
├── Makefile                 # `make all` orchestrates assets + PDF build
├── README.md                # (this file) build + workflow notes
└── build/ (generated)       # latexmk output directory (ignored)
```

## Template snapshot
- Source: https://mirrors.ctan.org/macros/latex/contrib/elsarticle.zip (mirrors the official Elsevier `elsarticle` bundle).
- Retrieved: 2025-11-23 via `curl -L -o reference-documents/docs/softwarex/reference/templates/elsarticle-template.zip …`.
- Contents live under `elsarticle/`. Keep upstream files pristine; place FHOPS-specific adjustments (title page, macros, includes) in `sections/` or sibling files so we can diff against the CTAN baseline.

## Build workflow (`latexmk` + TeX Live)
We use the standard TeX Live toolchain (preferred by SoftwareX) orchestrated through `latexmk`. The Makefile also provides an `all` target so we can regenerate FHOPS assets + PDF in a single command.

```
# Rebuild everything (clean → assets → PDF)
make all

# Just build the PDF
make pdf    # or simply `make`

# Clean auxiliary files + build directory
make clean
```

`scripts/generate_assets.sh` is the one-stop entry point for reproducible artifacts. It now:

- Runs the shared Markdown/CSV exporter (`export_docs_assets.py`).
- Invokes `render_prisma_diagram.py`, which compiles the TikZ workflow figure via `latexmk` and drops PDF/PNG assets into `docs/softwarex/assets/figures/` (skipped with a warning when `latexmk` is not installed; the committed figure is kept).
- Executes dataset inspection, benchmark suites (SA/ILS/Tabu; the four scenarios run one after another so `runtime_s` is not inflated by concurrent runs), tuning harness, playback robustness, costing demo, and scaling sweeps so every referenced CSV/JSON/PNG is fresh.
- Rewrites any absolute checkout path left in the assets to its repo-relative form and fails if one remains (`relativize_asset_paths.py`, see *Recorded paths* below).
- Finishes with `normalize_text_assets.py`, which applies the repository's `trailing-whitespace` / `end-of-file-fixer` rules so the generated files, the logged assets hash and the committed files are byte-identical.

Environment knobs:

- `FHOPS_ASSETS_FAST=1 make assets` trims benchmark budgets (shorter iterations) so you can sanity-check the pipeline without waiting for the full runs. Use the default (`0`) for submission-quality artifacts. The tuning harness uses the published budgets (120 SA iterations per configuration, 8 Bayesian trials, ILS 160 / Tabu 900 iterations) in both modes.
- `FHOPS_ASSETS_NOTE="…"` (optional) adds a `note:` line to the `benchmark_runs.log` entry written by `run_manuscript_benchmarks.sh`.
- A full run takes about 3.8 h on an idle host (med42 Tabu alone about 2 h).
- All scripts respect the current Python interpreter (`python`); set `PYTHONPATH`/virtualenv as usual. `render_prisma_diagram.py` requires `latexmk`, `lualatex`, and either ImageMagick (`magick`) or `pdftoppm` for PNG export (optional `pdf2svg` for SVG).

Manual verification checklist (run after `make assets`):

1. **Datasets:** `docs/softwarex/assets/data/datasets/` contains `index.json` plus per-scenario summaries (`*_summary.json`).
2. **Benchmarks:** Each scenario folder under `docs/softwarex/assets/data/benchmarks/` has `summary.(csv|json)` + `telemetry.jsonl`; `index.json` lists all runs.
3. **Tuning:** `docs/softwarex/assets/data/tuning/` includes `softwarex_summary.*` plus tuner-specific reports; `telemetry/steps/*.jsonl` remains git-ignored by design.
4. **Playback:** `docs/softwarex/assets/data/playback/<scenario>/` holds `day.csv`, `shift.csv`, `metrics.json`, and rendered Markdown summaries.
5. **Costing:** `docs/softwarex/assets/data/costing/cost_summary.(csv|json)` present with matching telemetry logs.
6. **Scaling:** `docs/softwarex/assets/data/scaling/` contains `scaling_summary.(csv|json)` and `runtime_vs_blocks.png`.
7. **Figures/snippets:** `docs/softwarex/assets/figures/prisma_overview.(pdf|png)` regenerates, and `docs/includes/softwarex/*.rst` mirror the Markdown snippets.
8. **Consistency:** `python scripts/audit_asset_consistency.py` reports 0 failing checks (summaries vs assignment CSVs, tables vs `build_tables.py`, playback, scaling, tuning, repo-relative paths), and after `make manuscript-benchmarks` `make verify-assets-hash` passes.

If any directory is missing or stale, re-run `FHOPS_ASSETS_FAST=0 make assets` to produce the canonical versions, then `make pdf` to rebuild the manuscript. `latexmk` will automatically run when the manuscript PDF is built. You’ll need a TeX Live installation that includes common packages (`latexmk`, `tikz`, `hyperref`, `lineno`, etc.). On Debian/Ubuntu, `sudo apt-get install texlive-full latexmk` is still the quickest path; we can revisit a lighter scheme/tectonic later if build times become an issue.

### Benchmark-only runs & logging

- `make manuscript-benchmarks` runs `scripts/run_manuscript_benchmarks.sh`, which in turn executes the full asset pipeline and appends a log entry (UTC start time, commit hash, fast mode, runtime seconds, `hash_recipe: v2`, `assets_hash`, optional `note:`) to `docs/softwarex/assets/benchmark_runs.log`.
- `make manuscript-benchmarks-fast` does the same but sets `FHOPS_ASSETS_FAST=1` for quick sanity checks (shorter benchmark budgets; the tuning harness uses the published budgets in both modes).
- `make verify-assets-hash` (= `python scripts/asset_hash.py verify`) recomputes the hash and checks it against the last log entry.
- Use these targets before major milestones or submissions so we have a reproducibility audit trail without forcing a full PDF build each time.

### Assets hash (recipe v2, #144)

`assets_hash` identifies exactly the asset files that are committed, so anyone can recompute it
from a git checkout or from an unpacked sdist (which ships the tracked files):

1. **Files:** every file under `docs/softwarex/assets/` that git would commit —
   `git ls-files --cached --others --exclude-standard -- docs/softwarex/assets` (tracked files plus
   new, not git-ignored files, so freshly regenerated assets are covered before they are committed;
   git-ignored files such as `data/tuning/telemetry/steps/*.jsonl` are excluded) — minus files
   deleted from the working tree, minus `docs/softwarex/assets/benchmark_runs.log` itself.
   Without `.git` (sdist): every file under `docs/softwarex/assets/` except the log.
2. **Lines:** `sha256sum` output per file (`<digest>  <repo-relative path>`), sorted by path bytes
   (`LC_ALL=C`).
3. **Hash:** SHA-256 of those lines.

From the repository root:

```bash
# git checkout
git ls-files -z --cached --others --exclude-standard -- docs/softwarex/assets \
  | grep -zv '^docs/softwarex/assets/benchmark_runs.log$' \
  | LC_ALL=C sort -zu | xargs -0 sha256sum | sha256sum
# unpacked sdist (no .git)
find docs/softwarex/assets -type f ! -path docs/softwarex/assets/benchmark_runs.log -print0 \
  | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum
# same rule in Python, plus the check against the last log entry
python docs/softwarex/manuscript/scripts/asset_hash.py compute
python docs/softwarex/manuscript/scripts/asset_hash.py verify
```

Entries without `hash_recipe` used the legacy recipe (v1): `find docs/softwarex/assets -type f
-print0 | sort -z | xargs -0 sha256sum | sha256sum`, run before the entry was appended. It
hashed every file on disk — including the git-ignored tuning step logs and the log itself as it
stood before the entry — in the locale's sort order, so v1 values cannot be recomputed from the
repository or the sdist. In particular, the entry `run_started: 2026-10-07T06:53:41Z` (commit
35c38d9, merged as 0463fd5) logs
`bcf65f3126ce329267e48aa1cb3ae332a5ee5a2e88ffe03ea44953aa93fe223f`, which includes the ignored
`data/tuning/telemetry/steps/*.jsonl`; the same v1 recipe over the files committed in 0463fd5
(log without that entry, `LC_ALL=C`) gives
`16a4def731b7f560b29f4229904b1e5315d20d8f321055822cab523643e4d96a` (`en_US.UTF-8` ordering:
`66b49529677ad20a8a463a921d9f715db25ff283664bc42b434d9dc8069362f6`). Log history is never
rewritten; corrections are appended as `audit_note:` entries (same fields, no solver run).

### Recorded paths (#144)

Paths recorded inside the assets (scenario paths in benchmark/scaling `summary.csv|json`,
`telemetry.jsonl`, `scenario_path.txt`, `benchmarks/index.json`, dataset summaries and table paths,
costing telemetry, tuning `runs.jsonl`/`runs.sqlite`) are POSIX paths relative to the repository
root, e.g. `examples/med42/scenario.yaml`. FHOPS writes paths as given on the command line, so the
pipeline runs the CLI from the repository root with repo-relative arguments;
`scripts/relativize_asset_paths.py` strips any remaining `<repo-root>/` prefix at the end of
`generate_assets.sh` (and `--check` fails on any absolute path), and `audit_asset_consistency.py`
reports absolute paths as failures. To normalise assets written elsewhere, pass the other checkout
root: `python scripts/relativize_asset_paths.py ../../assets --prefix /old/checkout`.

### Table 5 (tuning leaderboard)

`build_tables.py` writes `data/tables/tuning_leaderboard.{csv,tex}` with a *Budget* column for every
row, read from the tuning runs (`tuner_meta.budget` in `data/tuning/telemetry/runs.jsonl`, e.g.
`8 trials × 120 iters` for Bayes, `1 run × 160 iters` for ILS), and *Key settings* for every row
(ILS/Tabu rows show their tuner settings). The `.tex` ends with a note: Δ is the best tuned
objective minus the SA default benchmark objective, and the SA default budgets (8000 / 4000 /
20000 / 6000 iterations for Tiny7 / Small21 / Med42 / Synthetic-small, read from the benchmark
summaries) are far larger than the tuning budgets; ties are named. The `.tex` uses `booktabs` and
`array` and is about one text width wide with `\tabcolsep` = 4 pt.

## Metadata tables & reproducibility log
- `metadata/code_metadata.tex` and `metadata/current_code_version.tex` store the journal-required tables (version, licence, supported platforms, installation method, benchmark log path). Update them whenever release naming, contact info, or reproducibility evidence changes.
- The introduction references Tables~\ref{tab:code-metadata}–\ref{tab:current-code-version}, so keep those entries aligned with the text and the actual reproducibility log at `docs/softwarex/assets/benchmark_runs.log`.

## History
The draft was written here first (`fhops-softx.tex` + `sections/*.tex`, elsarticle template,
latexmk build) and moved to UBC-FRESH/fhops-manuscript for submission and revision. The section
files are kept for reference only; the stale numbers in `sections/illustrative_example.tex` were
replaced by references to the generated tables and figures (#144) instead of being updated again,
because every regeneration changes them and the canonical manuscript quotes them from the assets.
