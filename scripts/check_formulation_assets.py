#!/usr/bin/env python3
"""Check that generated formulation assets are synchronized with Markdown/CSV primaries.

The check copies source files into a temporary directory, invokes
``docs/softwarex/manuscript/scripts/export_docs_assets.py`` against that copy, and compares the
freshly generated TeX/RST files with the checked-in generated assets. It exits non-zero and prints
the drifted paths when any output is stale.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PANDOC_VERSION = "3.1.3"


def _pandoc_version(path: str) -> str | None:
    try:
        output = subprocess.run(
            [path, "--version"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()[0]
    except Exception:
        return None
    parts = output.split()
    return parts[1] if len(parts) > 1 and parts[0].lower() == "pandoc" else None


def _pandoc_path() -> str | None:
    candidates: list[str] = []
    found = shutil.which("pandoc")
    if found:
        candidates.append(found)
    try:
        import pypandoc

        candidates.append(str(pypandoc.get_pandoc_path()))
    except Exception:
        pass
    for candidate in candidates:
        if _pandoc_version(candidate) == PANDOC_VERSION:
            return candidate
    return None


def pandoc_available() -> bool:
    """Return True when the pinned Pandoc version is available."""
    return _pandoc_path() is not None


def _copy_sources(includes_dir: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.md", "*.csv"):
        for path in includes_dir.glob(pattern):
            if path.name.lower() == "readme.md":
                continue
            shutil.copy2(path, target / path.name)


def _compare_trees(generated_root: Path, expected_root: Path) -> list[Path]:
    drifted: list[Path] = []
    for generated in sorted(generated_root.rglob("*")):
        if not generated.is_file():
            continue
        relative = generated.relative_to(generated_root)
        expected = expected_root / relative
        if not expected.exists() or not filecmp.cmp(generated, expected, shallow=False):
            drifted.append(relative)
    return drifted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="FHOPS repository root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    includes_dir = repo_root / "docs" / "softwarex" / "manuscript" / "sections" / "includes"
    expected_rst_dir = repo_root / "docs" / "includes" / "softwarex"
    exporter = repo_root / "docs" / "softwarex" / "manuscript" / "scripts" / "export_docs_assets.py"

    pandoc = _pandoc_path()
    if pandoc is None:
        print(
            f"[formulation-check] Pandoc {PANDOC_VERSION} not found; install that version "
            "or use the CI workflow environment.",
            file=sys.stderr,
        )
        return 2

    with tempfile.TemporaryDirectory(prefix="fhops-formulation-check-") as tmp:
        tmp_root = Path(tmp)
        source_copy = tmp_root / "includes"
        generated_rst = tmp_root / "rst"
        _copy_sources(includes_dir, source_copy)
        env = os.environ.copy()
        env["PATH"] = str(Path(pandoc).parent) + os.pathsep + env.get("PATH", "")
        subprocess.run(
            [
                sys.executable,
                str(exporter),
                "--repo-root",
                str(repo_root),
                "--includes-dir",
                str(source_copy),
                "--rst-out-dir",
                str(generated_rst),
            ],
            check=True,
            env=env,
        )

        drifted: list[Path] = []
        drifted.extend(_compare_trees(source_copy, includes_dir))
        drifted.extend(_compare_trees(generated_rst, expected_rst_dir))

    if drifted:
        print("[formulation-check] Generated assets are out of sync:", file=sys.stderr)
        for path in drifted:
            print(f"  - {path}", file=sys.stderr)
        print(
            "[formulation-check] Run `python docs/softwarex/manuscript/scripts/export_docs_assets.py` "
            "with pandoc on PATH and commit the regenerated files.",
            file=sys.stderr,
        )
        return 1

    print("[formulation-check] Formulation assets are synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
