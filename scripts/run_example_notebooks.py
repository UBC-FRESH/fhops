#!/usr/bin/env python3
"""Execute the FHOPS onboarding notebook series.

Runs only the five onboarding notebooks (00-04) into an untracked tmp output
directory. Never overwrites source notebooks.

Usage:
    python scripts/run_example_notebooks.py                     # all 5 notebooks
    python scripts/run_example_notebooks.py --light             # skip heavy steps
    python scripts/run_example_notebooks.py --notebook 01       # shorthand alias
    python scripts/run_example_notebooks.py --notebook 00 --notebook 01  # repeatable selection
    python scripts/run_example_notebooks.py --notebook 01_fhops_operations_simulation  # full name
    python scripts/run_example_notebooks.py --timeout 300       # per-notebook timeout
    python scripts/run_example_notebooks.py --keep-going        # continue on failure
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

DEFAULT_NOTEBOOKS = [
    "00_fhops_orientation",
    "01_fhops_operations_simulation",
    "02_fhops_solve_compare",
    "03_fhops_playback_kpis",
    "04_fhops_stochastic_what_if",
]

ALL_NOTEBOOKS = DEFAULT_NOTEBOOKS[:]
_NOTEBOOK_ALIASES = {f"{index:02d}": notebook for index, notebook in enumerate(DEFAULT_NOTEBOOKS)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run FHOPS onboarding notebooks.")
    p.add_argument(
        "--notebook",
        "-n",
        action="append",
        default=None,
        help="Notebook name(s) to run (default: all five onboarding notebooks).",
    )
    p.add_argument("--light", "-l", action="store_true", help="Skip heavy/heuristic steps.")
    p.add_argument(
        "--keep-going",
        "-k",
        action="store_true",
        help="Continue executing remaining notebooks after a failure.",
    )
    p.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=600,
        help="Per-notebook timeout in seconds (default: 600).",
    )
    p.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Output directory for executed notebooks (untracked tmp by default).",
    )
    p.add_argument(
        "--notebooks-dir",
        type=Path,
        default=None,
        help="Directory containing source notebooks (default: examples/).",
    )
    return p.parse_args(argv)


def normalize_notebook_name(name: str) -> str:
    """Resolve a numeric onboarding alias to its canonical notebook name."""

    alias = name.removesuffix(".ipynb")
    return _NOTEBOOK_ALIASES.get(alias, name)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def find_repo_root(start: Path | None = None) -> Path | None:
    probe = (start or Path.cwd()).resolve()
    while True:
        candidate = probe / "pyproject.toml"
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                probe = probe.parent
                continue
            if 'name = "fhops"' in text or "name='fhops'" in text:
                return probe
        parent = probe.parent
        if parent == probe:
            return None
        probe = parent


def execute_notebook(
    notebook_name: str,
    notebooks_dir: Path,
    output_dir: Path,
    light: bool = False,
    timeout: int = 600,
) -> dict[str, Any]:
    """Execute a single notebook and write the executed version to output_dir.

    Returns a result dict with ``ok``, ``notebook``, ``elapsed_seconds``,
    ``notebook_path``, and on failure ``error`` plus ``traceback``.
    """
    import traceback

    import nbformat

    notebook_path = notebooks_dir / f"{notebook_name}.ipynb"
    if not notebook_path.is_file():
        return {"ok": False, "notebook": notebook_name, "error": f"not found: {notebook_path}"}

    nb = nbformat.read(notebook_path, as_version=4)

    # Compute PYTHONPATH for the kernel environment.
    # Preserve any existing PYTHONPATH so user/site packages survive.
    existing_py = os.environ.get("PYTHONPATH", "")
    extra_paths = [str(notebooks_dir)]
    repo_root = find_repo_root()
    if repo_root is not None:
        extra_paths.append(str(repo_root / "src"))
    new_py = ":".join(extra_paths)
    if existing_py:
        combined_py = new_py + ":" + existing_py
    else:
        combined_py = new_py

    # Inject PYTHONPATH via the kernel env, not notebook metadata.
    nb.metadata["execution"] = {
        "interpreter": {"hash": sys.version},
        "PYTHONPATH": combined_py,
    }

    # Strip existing outputs so we get fresh execution
    for cell in nb.cells:
        cell.outputs = []
        cell.execution_count = None

    # Build the setup cell source with a concrete resolved path.
    examples_abs = str(notebooks_dir.resolve())
    setup_source = (
        f"import sys\n"
        f"from pathlib import Path\n"
        f"sys.path.insert(0, '{examples_abs}')\n"
        f"print('Examples dir:', '{examples_abs}')\n"
        f"try:\n"
        f"    import fhops\n"
        f"    print(f'fhops {{fhops.__version__}}')\n"
        f"except ImportError:\n"
        f"    print('fhops not importable; CLI path will be used')\n"
    )
    setup_cell = nbformat.v4.new_code_cell(
        source=setup_source,
        metadata={"language": "python"},
    )
    nb.cells.insert(0, setup_cell)

    # Optionally set light-mode flag as a notebook variable
    if light:
        flag_cell = nbformat.v4.new_code_cell(
            source="LIGHT_MODE = True\nprint('Light mode enabled')",
            metadata={"language": "python"},
        )
        nb.cells.insert(1, flag_cell)

    # Execute all cells
    from nbconvert.preprocessors import ExecutePreprocessor

    ep = ExecutePreprocessor(timeout=timeout, kernel_name="python3")
    try:
        ep.preprocess(nb, {"metadata": {"path": str(notebooks_dir)}})
    except Exception as exc:
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tb = "".join(tb_lines)[-2000:]  # last 2000 chars for diagnostics
        return {
            "ok": False,
            "notebook": notebook_name,
            "error": str(exc),
            "traceback": tb,
        }

    # Write executed notebook to output_dir
    out_path = output_dir / f"{notebook_name}.ipynb"
    nbformat.write(nb, str(out_path))
    return {"ok": True, "notebook": notebook_name, "notebook_path": str(out_path)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    notebooks_dir = args.notebooks_dir
    if notebooks_dir is None:
        if find_repo_root() is not None:
            notebooks_dir = find_repo_root() / "examples"
        else:
            notebooks_dir = Path.cwd() / "examples"

    if args.output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="fhops_onboarding_"))
    else:
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

    if args.notebook:
        selected = [normalize_notebook_name(name) for name in args.notebook]
        unknown = [name for name in selected if name not in DEFAULT_NOTEBOOKS]
        if unknown:
            valid_aliases = ", ".join([*(_NOTEBOOK_ALIASES), *DEFAULT_NOTEBOOKS])
            print(
                f"Error: unknown notebook selection(s): {', '.join(unknown)}",
                file=sys.stderr,
            )
            print(f"Choose from: {valid_aliases}", file=sys.stderr)
            return 2
    else:
        selected = DEFAULT_NOTEBOOKS[:]

    results: list[dict[str, Any]] = []
    failures = 0

    for name in selected:
        print(f"\n{'=' * 60}")
        print(f"Executing: {name}")
        print(f"{'=' * 60}")
        t0 = time.time()
        result = execute_notebook(
            name, notebooks_dir, output_dir, light=args.light, timeout=args.timeout
        )
        elapsed = time.time() - t0
        result["elapsed_seconds"] = round(elapsed, 1)
        results.append(result)
        status = "OK" if result["ok"] else "FAILED"
        print(
            f"  {status} in {result['elapsed_seconds']}s -> {result.get('notebook_path', 'no output')}"
        )
        if not result["ok"]:
            print(f"    Error: {result.get('error', '<unknown>')}")
            tb = result.get("traceback", "")
            if tb:
                print("    Traceback (last 10 lines):")
                for line in tb.strip().splitlines()[-10:]:
                    print(f"      {line}")
            failures += 1
            if not args.keep_going:
                print("Aborting (not --keep-going).")
                break

    print(f"\n{'=' * 60}")
    print(f"Results: {len(results)} executed, {failures} failed")
    print(f"Output directory: {output_dir}")

    # Write a summary JSON (untracked)
    summary = {
        "notebooks": [r["notebook"] for r in results],
        "failures": failures,
        "output_dir": str(output_dir),
    }
    (output_dir / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
