#!/usr/bin/env python3
"""Detect and optionally remove duplicate chunks from a text log.

This script is tailored for conversation logs where entire transcripts may be
pasted multiple times. It scans for repeated multi-line chunks using hashed
windows, reports the duplicates it finds, and can rewrite the file with the
later copies removed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class DuplicateChunk:
    """Represents a duplicate chunk (keeping the first copy, removing the later)."""

    original_start: int
    duplicate_start: int
    length: int

    @property
    def original_range(self) -> tuple[int, int]:
        return self.original_start, self.original_start + self.length

    @property
    def duplicate_range(self) -> tuple[int, int]:
        return self.duplicate_start, self.duplicate_start + self.length


def detect_duplicate_chunks(
    lines: Sequence[str], window: int, min_lines: int
) -> List[DuplicateChunk]:
    """Return duplicate chunks found in ``lines`` using a rolling window."""

    if window < 1:
        raise ValueError("window must be >= 1")
    if min_lines < window:
        min_lines = window

    seen: dict[tuple[str, ...], int] = {}
    chunks: List[DuplicateChunk] = []
    i = 0
    skip_until = -1

    while i <= len(lines) - window:
        if i < skip_until:
            i += 1
            continue

        window_slice = tuple(lines[i : i + window])
        first_idx = seen.get(window_slice)

        if first_idx is None:
            seen[window_slice] = i
            i += 1
            continue

        start_a, start_b = first_idx, i

        # Extend backwards in case we matched mid-way through a chunk.
        while (
            start_a > 0
            and start_b > 0
            and lines[start_a - 1] == lines[start_b - 1]
            and start_a - 1 < start_b - 1
        ):
            start_a -= 1
            start_b -= 1

        # Extend forwards while the regions match (stop if regions would overlap).
        idx_a, idx_b = start_a, start_b
        match_len = 0
        while idx_b < len(lines) and lines[idx_a] == lines[idx_b]:
            idx_a += 1
            idx_b += 1
            match_len += 1
            if idx_a == start_b:
                break

        if match_len >= min_lines:
            chunks.append(DuplicateChunk(start_a, start_b, match_len))
            skip_until = start_b + match_len
            i = skip_until
        else:
            # Treat the current index as the better reference point and continue.
            seen[window_slice] = i
            i += 1

    return chunks


def remove_ranges(lines: Sequence[str], chunks: Iterable[DuplicateChunk]) -> List[str]:
    """Return ``lines`` without the duplicate ranges specified in ``chunks``."""

    cleaned: List[str] = []
    chunk_iter = iter(sorted(chunks, key=lambda c: c.duplicate_start))
    current = next(chunk_iter, None)

    for idx, line in enumerate(lines):
        while current and idx >= current.duplicate_start + current.length:
            current = next(chunk_iter, None)
        if current and current.duplicate_start <= idx < current.duplicate_start + current.length:
            continue
        cleaned.append(line)

    return cleaned


def format_chunk_summary(chunk: DuplicateChunk) -> str:
    orig_start = chunk.original_start + 1
    orig_end = chunk.original_start + chunk.length
    dup_start = chunk.duplicate_start + 1
    dup_end = chunk.duplicate_start + chunk.length
    return (
        f"Original lines {orig_start}-{orig_end} duplicated at lines {dup_start}-{dup_end} "
        f"({chunk.length} lines)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find and remove duplicate chunks in a conversation log."
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to the log file (e.g., notes/coding-agent-conversation-log.txt).",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=32,
        help="Number of consecutive lines used to detect duplicates (default: 32).",
    )
    parser.add_argument(
        "--min-lines",
        type=int,
        default=80,
        help="Minimum number of matching lines required before a chunk is removed.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="File encoding (default: utf-8).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite the file with duplicate chunks removed.",
    )
    parser.add_argument(
        "--show-snippet",
        action="store_true",
        help="Print the first non-empty line from each duplicate chunk for context.",
    )

    args = parser.parse_args()
    path: Path = args.path
    if not path.exists():
        raise SystemExit(f"{path} does not exist")

    content = path.read_text(encoding=args.encoding)
    lines = content.splitlines(keepends=True)

    chunks = detect_duplicate_chunks(lines, window=args.window, min_lines=args.min_lines)

    if not chunks:
        print("No duplicate chunks detected.")
        return

    print(f"Detected {len(chunks)} duplicate chunk(s):")
    for chunk in chunks:
        print(f"  - {format_chunk_summary(chunk)}")
        if args.show_snippet:
            dup_lines = lines[chunk.duplicate_start : chunk.duplicate_start + chunk.length]
            snippet = next((ln.strip() for ln in dup_lines if ln.strip()), "")
            if snippet:
                print(f"      snippet: {snippet[:120]}")

    if args.apply:
        cleaned = remove_ranges(lines, chunks)
        path.write_text("".join(cleaned), encoding=args.encoding)
        removed_lines = sum(chunk.length for chunk in chunks)
        print(f"Removed {removed_lines} line(s). Updated file written to {path}.")
    else:
        print("Run again with --apply to rewrite the file.")


if __name__ == "__main__":
    main()
