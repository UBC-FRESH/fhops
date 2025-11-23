#!/usr/bin/env python3
"""Render shared manuscript/doc snippets from Markdown primaries.

Each `*.md` file inside `sections/includes/` is treated as source-of-truth.
This script emits:
  * `<name>.tex` next to the Markdown file for LaTeX `\\input`.
  * `<rst_out_dir>/<name>.rst` for inclusion inside the Sphinx docs.

Conversion relies on `pandoc`, which is available in the Codex CLI image.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def run_pandoc(src: Path, target: Path, pandoc_format: str) -> None:
    """Invoke pandoc to convert `src` Markdown into `target`."""
    cmd = [
        "pandoc",
        "-f",
        "markdown",
        "-t",
        pandoc_format,
        str(src),
        "-o",
        str(target),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"pandoc failed for {src} -> {target} ({pandoc_format}):\n"
            f"{result.stdout}\n{result.stderr}"
        )


def convert_include(md_path: Path, rst_dir: Path) -> list[Path]:
    """Render a single Markdown include into .tex and .rst outputs."""
    generated: list[Path] = []

    # LaTeX output sits next to the Markdown file.
    tex_path = md_path.with_suffix(".tex")
    tex_header = "% AUTO-GENERATED from {} -- do not edit directly.\n".format(
        md_path.name
    )
    run_pandoc(md_path, tex_path, "latex")
    tex_content = tex_path.read_text(encoding="utf-8")
    tex_path.write_text(tex_header + tex_content, encoding="utf-8")
    generated.append(tex_path)

    # ReStructuredText output feeds Sphinx includes.
    rst_dir.mkdir(parents=True, exist_ok=True)
    rst_path = rst_dir / f"{md_path.stem}.rst"
    rst_header = (
        ".. AUTO-GENERATED from {} -- do not edit directly.\n\n".format(
            md_path.name
        )
    )
    run_pandoc(md_path, rst_path, "rst")
    rst_content = rst_path.read_text(encoding="utf-8")
    rst_path.write_text(rst_header + rst_content, encoding="utf-8")
    generated.append(rst_path)

    return generated


def find_markdown_files(root: Path) -> Iterable[Path]:
    """Yield Markdown files (excluding README) under `root`."""
    for path in sorted(root.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        yield path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render shared manuscript/doc snippets."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="Path to the FHOPS repository root.",
    )
    parser.add_argument(
        "--includes-dir",
        type=Path,
        default=None,
        help="Directory containing Markdown source snippets.",
    )
    parser.add_argument(
        "--rst-out-dir",
        type=Path,
        default=None,
        help="Output directory for generated .rst files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root: Path = args.repo_root.resolve()
    includes_dir = (
        args.includes_dir
        if args.includes_dir is not None
        else repo_root
        / "docs"
        / "softwarex"
        / "manuscript"
        / "sections"
        / "includes"
    ).resolve()
    rst_dir = (
        args.rst_out_dir
        if args.rst_out_dir is not None
        else repo_root / "docs" / "includes" / "softwarex"
    ).resolve()

    if not includes_dir.exists():
        raise SystemExit(f"Includes directory not found: {includes_dir}")

    print(
        f"[export-docs] Rendering Markdown snippets from {includes_dir} "
        f"into .tex and .rst (RST dir: {rst_dir})"
    )

    generated: list[Path] = []
    for md_path in find_markdown_files(includes_dir):
        generated.extend(convert_include(md_path, rst_dir))

    if not generated:
        print("[export-docs] No Markdown snippets found.")
    else:
        for path in generated:
            print(f"[export-docs] Wrote {path.relative_to(repo_root)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
