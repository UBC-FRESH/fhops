"""Extract Arnvik (2024) Appendices 4 & 5 tables using Camelot."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import camelot

PDF_PATH = Path("notes/reference/arnvik-w-20240926.pdf")
OUT_DIR = Path("notes/reference/arnvik_tables")
TABLE_REGION = "40,795,575,40"
APPENDICES = {
    "appendix4_machines": range(80, 88),  # Appendix 4 pages 80-87
    "appendix5_stands": range(88, 98),    # Appendix 5 pages 88-97
}


def pad_row(row: list[str], width: int) -> list[str]:
    if len(row) >= width:
        return row
    return row + [""] * (width - len(row))


def extract_appendix(name: str, pages: Iterable[int]) -> None:
    all_rows: list[list[str]] = []
    max_cols = 0
    for page in pages:
        tables = camelot.read_pdf(
            str(PDF_PATH),
            pages=str(page),
            flavor="stream",
            table_regions=[TABLE_REGION],
            strip_text="\n",
        )
        if not tables:
            print(f"[{name}] no table detected on page {page}")
            continue
        table = tables[0]
        for idx, row in enumerate(table.df.values.tolist()):
            cleaned = [cell.strip() for cell in row]
            all_rows.append([str(page), str(idx + 1), *cleaned])
            max_cols = max(max_cols, len(cleaned))
        print(f"[{name}] page {page}: captured {table.shape[0]} rows")
    if not all_rows:
        print(f"[{name}] no rows captured")
        return
    header = ["page", "row"] + [f"c{i}" for i in range(max_cols)]
    out_path = OUT_DIR / f"{name}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in all_rows:
            page, row_idx, *cells = row
            writer.writerow([page, row_idx, *pad_row(cells, max_cols)])
    print(f"[{name}] wrote {len(all_rows)} rows -> {out_path}")


def main() -> None:
    if not PDF_PATH.exists():
        raise SystemExit(f"Missing PDF: {PDF_PATH}")
    for name, pages in APPENDICES.items():
        extract_appendix(name, pages)


if __name__ == "__main__":
    main()
