"""Extract tables from Arnvik (2024) appendices into CSV dumps."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import pdfplumber

PDF_PATH = Path("notes/reference/arnvik-w-20240926.pdf")
OUT_DIR = Path("notes/reference/arnvik_tables")

TABLE_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
}

SECTIONS = [
    ("appendix8", "Appendix 8. Models"),
    ("appendix9", "Appendix 9. Independent variables"),
    ("appendix10", "Appendix 10. Parameters in models"),
    ("appendix11", "Appendix 11. Statistical significance and observational units"),
]


def find_section_ranges(pdf: pdfplumber.PDF) -> dict[str, tuple[int, int]]:
    markers: dict[str, list[int]] = {name: [] for name, _ in SECTIONS}
    for index, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        for name, marker in SECTIONS:
            if marker in text:
                markers[name].append(index)
    ranges: dict[str, tuple[int, int]] = {}
    ranges: dict[str, tuple[int, int]] = {}
    prev_start = -1
    for idx, (name, _) in enumerate(SECTIONS):
        positions = [pos for pos in markers[name] if pos > prev_start]
        if not positions:
            positions = markers[name]
        if not positions:
            raise SystemExit(f"{name} not found in PDF")
        start = positions[0]
        prev_start = start
        end = len(pdf.pages)
        for other_name, _ in SECTIONS[idx + 1 :]:
            others = markers.get(other_name) or []
            for pos in others:
                if pos > start:
                    end = pos
                    break
            if end != len(pdf.pages):
                break
        ranges[name] = (start, end)
    return ranges


def write_table(path: Path, rows: Iterable[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow(row)


def extract_section(name: str, start: int, end: int, pdf: pdfplumber.PDF) -> None:
    section_dir = OUT_DIR / name
    section_dir.mkdir(parents=True, exist_ok=True)
    aggregated: list[list[str]] = []
    for page_index in range(start, end):
        page = pdf.pages[page_index]
        tables = page.extract_tables(table_settings=TABLE_SETTINGS)
        if not tables:
            continue
        for table_idx, table in enumerate(tables, start=1):
            cleaned = [[cell.strip() if cell else "" for cell in row] for row in table]
            out_path = section_dir / f"{name}_page{page_index+1:03d}_table{table_idx}.csv"
            write_table(out_path, cleaned)
            for row in cleaned:
                aggregated.append([str(page_index + 1), str(table_idx), *row])
            print(
                f"  {name}: page {page_index+1} -> table {table_idx} ({len(cleaned)} rows)"
            )
    write_table(section_dir / f"{name}_aggregate.csv", aggregated)


def main() -> None:
    if not PDF_PATH.exists():
        raise SystemExit(f"Missing PDF: {PDF_PATH}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with pdfplumber.open(PDF_PATH) as pdf:
        ranges = find_section_ranges(pdf)
        for name, _ in SECTIONS:
            start, end = ranges[name]
            print(f"Extracting {name} pages {start+1}-{end}...")
            extract_section(name, start, end, pdf)


if __name__ == "__main__":
    main()
