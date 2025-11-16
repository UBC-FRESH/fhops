"""Parse Appendix 10 parameter tables into structured JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber

PDF_PATH = Path("notes/reference/arnvik-w-20240926.pdf")
OUTPUT = Path("notes/reference/arnvik_tables/appendix10/parameters.json")

PAGE_RANGE = range(123, 137)  # zero-based indexes covering pages 124-137

HEADER_PREFIX = "Author(s)"
PUBLICATION_RE = re.compile(r"^(.*?\(\d{4}[a-z]?\))\s+(.*)$")


def iter_lines() -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(PDF_PATH) as pdf:
        for idx in PAGE_RANGE:
            text = pdf.pages[idx].extract_text() or ""
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("Appendix 10"):
                    continue
                if line.startswith("Parameters in models") or line.startswith(
                    "values of productivity"
                ):
                    continue
                if line.startswith("At a certain threshold"):
                    continue
                if line.isdigit():
                    continue
                lines.append(line)
    return lines


def parse_parameters() -> dict[str, dict[str, str]]:
    lines = iter_lines()
    columns: list[str] | None = None
    current_pub: str | None = None
    data: dict[str, dict[str, str]] = {}

    for line in lines:
        if line.startswith(HEADER_PREFIX):
            parts = line.split()
            columns = parts[2:]
            continue
        if columns is None:
            continue
        match = PUBLICATION_RE.match(line)
        if match:
            current_pub = match.group(1)
            remainder = match.group(2)
        else:
            if current_pub is None:
                continue
            remainder = line
        tokens = remainder.split()
        if not tokens:
            continue
        nr = tokens[0]
        values = tokens[1:]
        row = {col: (values[idx] if idx < len(values) else "") for idx, col in enumerate(columns)}
        data[f"{current_pub} model {nr}"] = row
    return data


def main() -> None:
    data = parse_parameters()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"Captured {len(data)} parameter rows -> {OUTPUT}")


if __name__ == "__main__":
    main()
