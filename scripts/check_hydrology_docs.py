"""Check the hydrology docs for stale links, schemas, and quickstart behavior."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = (
    Path("docs/howto/hydrology_quickstart.rst"),
    Path("docs/reference/femic_hydrology.rst"),
    Path("docs/reference/hydrology_contract_index.rst"),
    Path("docs/index.rst"),
)
DOC_REF = re.compile(r":doc:`([^`]+)`")
SCHEMA = re.compile(r"`((?:fhops|ws4|femic)\.hydrology\.[A-Za-z0-9_.]+)`")
URL = re.compile(r"https://github\.com/UBC-FRESH/[^\s`<>)]+")


def check_doc_references(root: Path, files: tuple[Path, ...] = DOC_FILES) -> list[str]:
    """Return stale local ``:doc:`` references.

    Parameters
    ----------
    root : Path
        Repository root.
    files : tuple of Path, optional
        Documentation files to scan, relative to ``root``.

    Returns
    -------
    list of str
        Error messages; empty when every local reference resolves.
    """
    errors: list[str] = []
    for relative in files:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing docs page: {relative}")
            continue
        for target in DOC_REF.findall(path.read_text(encoding="utf-8")):
            resolved = _resolve_doc(root, path, target)
            if resolved is None:
                errors.append(f"{relative}: unresolved :doc: target {target!r}")
    return errors


def check_schema_mentions(root: Path) -> list[str]:
    """Return stale FHOPS-owned schema mentions in the contract index.

    Parameters
    ----------
    root : Path
        Repository root.

    Returns
    -------
    list of str
        Error messages for documented FHOPS schemas that are absent from source.
    """
    index = root / "docs/reference/hydrology_contract_index.rst"
    if not index.is_file():
        return [f"missing contract index: {index.relative_to(root)}"]
    text = index.read_text(encoding="utf-8")
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted((root / "src").rglob("*.py"))
    )
    errors: list[str] = []
    for schema in sorted(set(SCHEMA.findall(text))):
        if schema.startswith("fhops.hydrology.") or schema == "ws4.hydrology.exposure.v1":
            if schema not in source_text:
                errors.append(f"contract index names {schema!r}, absent from src/")
    return errors


def check_quickstart(root: Path) -> list[str]:
    """Build and run the synthetic quickstart's FHOPS path."""
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="fhops-hydro-docs-") as temp:
        out = Path(temp) / "quickstart"
        env = {"PYTHONPATH": str(root / "src")}
        try:
            build = subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts/build_hydrology_quickstart.py"),
                    "--out",
                    str(out),
                ],
                cwd=root,
                env=_merged_env(env),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [f"quickstart generator failed: {exc}"]
        if build.returncode != 0:
            return [f"quickstart generator failed: {build.stderr.strip()}"]
        payload = json.loads((out / "quickstart.json").read_text(encoding="utf-8"))
        expected = payload["expected"]
        scenario = out / "fhops/scenario/scenario.yaml"
        bundle = out / "bundle"
        mapping = out / "fhops/mapping"
        screen = out / "fhops/screen"
        commands = [
            (
                "register",
                [
                    sys.executable,
                    "-m",
                    "fhops.cli.main",
                    "scenario",
                    "hydrology",
                    "register",
                    str(scenario),
                    str(bundle),
                ],
            ),
            (
                "map",
                [
                    sys.executable,
                    "-m",
                    "fhops.cli.main",
                    "scenario",
                    "hydrology",
                    "map",
                    str(scenario),
                    str(bundle),
                    str(out / "fhops/crosswalk.csv"),
                    "--metadata",
                    str(out / "fhops/crosswalk.meta.json"),
                    "--out",
                    str(mapping),
                ],
            ),
            (
                "screen",
                [
                    sys.executable,
                    "-m",
                    "fhops.cli.main",
                    "scenario",
                    "hydrology",
                    "screen",
                    str(scenario),
                    str(bundle),
                    str(mapping),
                    str(out / "fhops/screen_schedule.csv"),
                    str(out / "fhops/exposure.json"),
                    "--out",
                    str(screen),
                ],
            ),
            (
                "constraint-check",
                [
                    sys.executable,
                    "-m",
                    "fhops.cli.main",
                    "scenario",
                    "hydrology",
                    "constraint-check",
                    str(scenario),
                    str(mapping),
                    str(out / "fhops/hazard_schedule.csv"),
                    str(out / "fhops/hazard.json"),
                    "--assets",
                    str(out / "fhops/assets.json"),
                    "--no-fail-on-closure",
                ],
            ),
        ]
        for name, command in commands:
            result = subprocess.run(
                command,
                cwd=root,
                env=_merged_env(env),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                errors.append(f"{name} failed: {result.stderr.strip() or result.stdout.strip()}")
        if errors:
            return errors
        screened = json.loads((screen / "hydrology_screen.json").read_text(encoding="utf-8"))
        if screened.get("row_count") != expected["fhops_screen_rows"]:
            errors.append("FHOPS screen row count does not match quickstart.json")
        if not (out / "ws4/dataset/fragments.parquet").is_file():
            errors.append("quickstart did not create the WS4 dataset")
    return errors


def check_external_links(root: Path, files: tuple[Path, ...] = DOC_FILES) -> list[str]:
    """Return unreachable external GitHub documentation links.

    Parameters
    ----------
    root : Path
        Repository root.
    files : tuple of Path, optional
        Documentation files to scan.

    Returns
    -------
    list of str
        Error messages; empty when every URL responds.
    """
    urls = sorted(
        {
            url.rstrip(".,;:")
            for relative in files
            if (root / relative).is_file()
            for url in URL.findall((root / relative).read_text(encoding="utf-8"))
        }
    )
    errors: list[str] = []
    for url in urls:
        request = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=20):
                pass
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"unreachable docs URL {url}: {exc}")
    return errors


def _resolve_doc(root: Path, source: Path, target: str) -> Path | None:
    candidate = Path(target)
    if candidate.is_absolute():
        candidate = root / "docs" / str(candidate).lstrip("/")
    else:
        candidate = source.parent / candidate
    if candidate.suffix != ".rst":
        candidate = candidate.with_suffix(".rst")
    if candidate.is_file():
        return candidate
    index = candidate.with_name(candidate.stem) / "index.rst"
    return index if index.is_file() else None


def _merged_env(extra: dict[str, str]) -> dict[str, str]:
    import os

    env = os.environ.copy()
    env.update(extra)
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-external", action="store_true")
    args = parser.parse_args(argv)
    errors = [
        *check_doc_references(REPO_ROOT),
        *check_schema_mentions(REPO_ROOT),
        *check_quickstart(REPO_ROOT),
    ]
    if args.check_external:
        errors.extend(check_external_links(REPO_ROOT))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("hydrology docs check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
