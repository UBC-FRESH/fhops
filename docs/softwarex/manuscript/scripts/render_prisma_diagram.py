#!/usr/bin/env python3
"""Render the PRISMA-style FHOPS workflow diagram into PDF/PNG/SVG assets."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({' '.join(cmd)}):\n{result.stdout}"
        )


def build_pdf(tex_path: Path, build_dir: Path, texinputs: str | None) -> Path:
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("latexmk") is None:
        raise RuntimeError("latexmk is required to render the PRISMA diagram.")
    cmd = [
        "latexmk",
        "-lualatex",
        "-halt-on-error",
        "-interaction=nonstopmode",
        "-file-line-error",
        "-synctex=0",
        "-output-directory=" + str(build_dir),
        str(tex_path),
    ]
    env = None
    if texinputs:
        env = os.environ.copy()
        env["TEXINPUTS"] = texinputs
    run(cmd, env=env)
    pdf_path = build_dir / f"{tex_path.stem}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    return pdf_path


def _enforce_png_dpi(png_path: Path, dpi: int = 300) -> None:
    """Ensure the PNG advertises the requested DPI if Pillow is available."""
    if Image is None:
        return
    with Image.open(png_path) as img:
        img.save(png_path, dpi=(dpi, dpi))


def convert_pdf_to_png(pdf_path: Path, png_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("magick"):
        cmd = [
            "magick",
            "-density",
            "300",
            str(pdf_path),
            "-quality",
            "95",
            str(png_path),
        ]
        run(cmd)
        _enforce_png_dpi(png_path)
    elif shutil.which("pdftoppm"):
        tmp_prefix = png_path.with_suffix("")
        cmd = [
            "pdftoppm",
            "-r",
            "300",
            "-singlefile",
            "-png",
            str(pdf_path),
            str(tmp_prefix),
        ]
        run(cmd)
        generated = png_path
        if not generated.exists():
            raise FileNotFoundError(generated)
        _enforce_png_dpi(generated)
    else:
        raise RuntimeError("Neither ImageMagick (magick) nor pdftoppm is available for PDF→PNG conversion.")


def convert_pdf_to_svg(pdf_path: Path, svg_path: Path) -> None:
    if shutil.which("pdf2svg"):
        run(["pdf2svg", str(pdf_path), str(svg_path)])
    else:
        # Optional output; warn but do not fail.
        print("[prisma] pdf2svg not available; skipping SVG export.", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="Path to the FHOPS repository root.",
    )
    parser.add_argument(
        "--tex",
        type=Path,
        default=None,
        help="Path to the PRISMA LaTeX source (defaults to sections/includes/prisma_overview.tex).",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=None,
        help="Directory for intermediate latexmk outputs.",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help="Output directory for rendered figures (defaults to docs/softwarex/assets/figures).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    tex_path = (
        args.tex
        if args.tex is not None
        else repo_root
        / "docs"
        / "softwarex"
        / "manuscript"
        / "sections"
        / "includes"
        / "prisma_overview_standalone.tex"
    ).resolve()
    build_dir = (
        args.build_dir
        if args.build_dir is not None
        else repo_root / "docs" / "softwarex" / "manuscript" / "build" / "prisma"
    ).resolve()
    assets_dir = (
        args.assets_dir
        if args.assets_dir is not None
        else repo_root / "docs" / "softwarex" / "assets" / "figures"
    ).resolve()

    if not tex_path.exists():
        raise SystemExit(f"PRISMA source not found: {tex_path}")

    includes_dir = tex_path.parent
    existing = os.environ.get("TEXINPUTS", "")
    texinputs = f"{includes_dir}{os.pathsep}"
    if existing:
        texinputs += existing

    print(f"[prisma] Rendering {tex_path.relative_to(repo_root)}")
    pdf_path = build_pdf(tex_path, build_dir, texinputs)
    pdf_target = assets_dir / "prisma_overview.pdf"
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_path, pdf_target)
    print(f"[prisma] PDF -> {pdf_target.relative_to(repo_root)}")

    png_target = assets_dir / "prisma_overview.png"
    convert_pdf_to_png(pdf_path, png_target)
    print(f"[prisma] PNG -> {png_target.relative_to(repo_root)}")

    svg_target = assets_dir / "prisma_overview.svg"
    convert_pdf_to_svg(pdf_path, svg_target)
    if svg_target.exists():
        print(f"[prisma] SVG -> {svg_target.relative_to(repo_root)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
