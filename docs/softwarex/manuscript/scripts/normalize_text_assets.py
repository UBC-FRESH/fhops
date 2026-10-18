#!/usr/bin/env python3
"""Normalise generated text assets the way the repository's pre-commit hooks would.

The ``trailing-whitespace`` and ``end-of-file-fixer`` hooks rewrite text files when they are
committed (e.g. JSON written without a final newline). Running the same normalisation at the end
of ``generate_assets.sh`` makes the files on disk, the ``assets_hash`` recorded in
``benchmark_runs.log`` and the committed files byte-identical. Binary assets (PNG, PDF, SQLite)
are left untouched.
"""

from __future__ import annotations

import argparse
from pathlib import Path

TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".tex", ".txt", ".yaml", ".yml", ".log"}


def strip_trailing_whitespace(data: bytes) -> bytes:
    """``trailing-whitespace``: strip whitespace before each line ending (CRLF/LF kept)."""
    fixed: list[bytes] = []
    lines = [part + b"\n" for part in data.split(b"\n")]
    lines[-1] = lines[-1][:-1]
    for line in lines:
        if not line:
            continue
        if line.endswith(b"\r\n"):
            body, eol = line[:-2], b"\r\n"
        elif line.endswith(b"\n"):
            body, eol = line[:-1], b"\n"
        else:
            body, eol = line, b""
        fixed.append(body.rstrip() + eol)
    return b"".join(fixed)


def fix_end_of_file(data: bytes) -> bytes:
    """``end-of-file-fixer``: exactly one final line ending (an all-newline file becomes empty)."""
    if not data:
        return data
    if data[-1:] not in (b"\n", b"\r"):
        return data + b"\n"
    body = data.rstrip(b"\r\n")
    if not body:
        return b""
    remaining = data[len(body) :]
    for sequence in (b"\n", b"\r\n", b"\r"):
        if remaining.startswith(sequence):
            return body + sequence
    return data


def normalise(data: bytes) -> bytes:
    """Apply both hooks; the result is a fixpoint of each."""
    return fix_end_of_file(strip_trailing_whitespace(data))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="Asset directory to normalise in place.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed = 0
    for path in sorted(args.root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        data = path.read_bytes()
        fixed = normalise(data)
        if fixed != data:
            path.write_bytes(fixed)
            changed += 1
    print(f"[assets] Normalised {changed} text file(s) under {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
