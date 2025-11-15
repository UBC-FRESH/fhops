"""Extract raw tables from Arnvik (2024) Appendix 8 into CSV dumps.

This is a first pass that simply exports each detected table into
``notes/reference/arnvik_tables/`` for manual/automated cleaning later.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import pdfplumber

PDF_PATH = Path("notes/reference/arnvik-w-20240926.pdf")
OUT_DIR = Path("notes/reference/arnvik_tables")
AGG_CSV = OUT_DIR / "appendix8_raw.csv"

TABLE_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
}


def find_appendix_range(pdf: pdfplumber.PDF) -> tuple[int, int]:
    start_candidates: list[int] = []
    appendix9_indices: list[int] = []
    for index, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if "Appendix 8. Models" in text:
            start_candidates.append(index)
        if "Appendix 9" in text:
            appendix9_indices.append(index)
    if not start_candidates:
        raise SystemExit("Appendix 8 not found in PDF")
    start = start_candidates[-1]
    end = len(pdf.pages)
    for idx in appendix9_indices:
        if idx > start:
            end = idx
            break
    return start, end


def write_table(path: Path, rows: Iterable[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow(row)


def main() -> None:
    if not PDF_PATH.exists():
        raise SystemExit(f"Missing PDF: {PDF_PATH}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    aggregated: list[list[str]] = []
    with pdfplumber.open(PDF_PATH) as pdf:
        start, end = find_appendix_range(pdf)
        print(f"Extracting tables from pages {start+1} to {end}...")
        for page_index in range(start, end):
            page = pdf.pages[page_index]
            tables = page.extract_tables(table_settings=TABLE_SETTINGS)
            if not tables:
                continue
            for table_idx, table in enumerate(tables, start=1):
                cleaned = [[cell.strip() if cell else "" for cell in row] for row in table]
                out_path = OUT_DIR / f"appendix8_page{page_index+1:03d}_table{table_idx}.csv"
                write_table(out_path, cleaned)
                for row in cleaned:
                    aggregated.append([str(page_index + 1), str(table_idx), *row])
                print(f"  page {page_index+1}: wrote table {table_idx} with {len(cleaned)} rows")
    write_table(AGG_CSV, aggregated)
    print(f"Wrote aggregate CSV to {AGG_CSV}")


if __name__ == "__main__":
    main()
