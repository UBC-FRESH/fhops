#!/usr/bin/env python3
"""Rewrite absolute paths recorded in the SoftwareX assets to repository-relative paths.

Path rule (#144): every path recorded in ``docs/softwarex/assets`` (scenario paths in benchmark,
scaling, costing and tuning summaries/telemetry, ``scenario_path.txt``, ``index.json``, dataset
summaries) is a POSIX path relative to the repository root, e.g. ``examples/med42/scenario.yaml``.
The asset scripts run the FHOPS CLI from the repository root with repo-relative arguments, and
FHOPS records the paths as given. This tool is the safety net at the end of ``generate_assets.sh``
(for writers that resolve paths themselves, e.g. ``fhops dataset estimate-cost``) and the one-off
normaliser for assets written by older pipelines.

* default mode: replace ``<repo-root>/`` and every ``--prefix`` (e.g. a removed worktree) with the
  empty string in text assets (also the JSON-escaped ``\\/`` form) and in the text columns of
  SQLite files;
* ``--check``: rewrite nothing, list remaining absolute paths, exit 1 if there are any.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections.abc import Iterable
from pathlib import Path

SQLITE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}
BINARY_SUFFIXES = {".png", ".pdf", ".svg", ".gz", ".zip", ".parquet"}

# An absolute POSIX path under a typical root, or a Windows drive path, that is not part of a
# longer relative path (``assets/data/x`` does not match because ``s`` precedes the slash).
ABSOLUTE_PATH_RE = re.compile(
    r"(?<![\w.~-])(?:/|\\/)"
    r"(?:home|Users|tmp|root|mnt|media|opt|private|var|srv|scratch|workspace|builds|github)"
    r"(?:/|\\/)[^\s\"',;)]*"
    r"|(?<![\w])[A-Za-z]:\\\\?[^\s\"',;)]+"
)


def repo_relative(path: Path | str, repo_root: Path) -> str:
    """Return ``path`` relative to ``repo_root`` (POSIX) when it lies inside it, else unchanged.

    Relative inputs are interpreted relative to ``repo_root``.
    """
    candidate = Path(path)
    absolute = candidate if candidate.is_absolute() else repo_root / candidate
    try:
        return absolute.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _prefix_forms(prefixes: Iterable[str]) -> list[str]:
    forms: list[str] = []
    for prefix in prefixes:
        clean = prefix.rstrip("/") + "/"
        for form in (clean, clean.replace("/", "\\/")):
            if form not in forms:
                forms.append(form)
    # Longest first so a nested prefix never leaves a partial path behind.
    return sorted(forms, key=len, reverse=True)


def relativize_text(text: str, prefixes: Iterable[str]) -> str:
    for form in _prefix_forms(prefixes):
        text = text.replace(form, "")
    return text


def _is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() not in SQLITE_SUFFIXES | BINARY_SUFFIXES


def _sqlite_text_columns(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    columns: list[tuple[str, str]] = []
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    for table in tables:
        for _, name, col_type, *_ in conn.execute(f'PRAGMA table_info("{table}")'):
            if col_type.upper() in {"TEXT", ""}:
                columns.append((table, name))
    return columns


def rewrite_sqlite(path: Path, prefixes: Iterable[str]) -> int:
    forms = _prefix_forms(prefixes)
    changed = 0
    conn = sqlite3.connect(path)
    try:
        for table, column in _sqlite_text_columns(conn):
            for form in forms:
                cur = conn.execute(
                    f'UPDATE "{table}" SET "{column}" = replace("{column}", ?, \'\') '
                    f'WHERE instr("{column}", ?) > 0',
                    (form, form),
                )
                changed += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return changed


def scan_sqlite(path: Path) -> list[str]:
    hits: list[str] = []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for table, column in _sqlite_text_columns(conn):
            for (value,) in conn.execute(f'SELECT "{column}" FROM "{table}"'):
                if isinstance(value, str):
                    hits.extend(
                        f"{table}.{column}: {m.group(0)}" for m in ABSOLUTE_PATH_RE.finditer(value)
                    )
    finally:
        conn.close()
    return hits


def iter_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def rewrite(root: Path, prefixes: list[str]) -> list[Path]:
    changed: list[Path] = []
    for path in iter_files(root):
        if path.suffix.lower() in SQLITE_SUFFIXES:
            if rewrite_sqlite(path, prefixes):
                changed.append(path)
            continue
        if not _is_text_candidate(path):
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        fixed = relativize_text(text, prefixes)
        if fixed != text:
            path.write_bytes(fixed.encode("utf-8"))
            changed.append(path)
    return changed


def check(root: Path) -> dict[Path, list[str]]:
    findings: dict[Path, list[str]] = {}
    for path in iter_files(root):
        if path.suffix.lower() in SQLITE_SUFFIXES:
            hits = scan_sqlite(path)
        elif _is_text_candidate(path):
            try:
                text = path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                continue
            hits = [m.group(0) for m in ABSOLUTE_PATH_RE.finditer(text)]
        else:
            continue
        if hits:
            findings[path] = hits
    return findings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("assets_root", type=Path, help="Asset directory to rewrite or check.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="Repository root whose absolute path is stripped (default: this checkout).",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="Additional absolute checkout root to strip (repeatable), e.g. a removed worktree.",
    )
    parser.add_argument(
        "--check", action="store_true", help="Only report remaining absolute paths (exit 1)."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.assets_root
    if not args.check:
        prefixes = [str(args.repo_root.resolve()), *args.prefix]
        changed = rewrite(root, prefixes)
        print(f"[assets] Relativised recorded paths in {len(changed)} file(s) under {root}")
    findings = check(root)
    for path, hits in findings.items():
        shown = ", ".join(sorted(set(hits))[:3])
        print(f"[assets] absolute path in {path}: {shown}", file=sys.stderr)
    if findings:
        print(f"[assets] {len(findings)} file(s) still record absolute paths", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
