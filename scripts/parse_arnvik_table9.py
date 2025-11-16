"""Parse Arnvik (2024) Table 9 machine counts via Camelot."""

from __future__ import annotations

import csv
from pathlib import Path

import camelot

PDF_PATH = Path("notes/reference/arnvik-w-20240926.pdf")
OUT_PATH = Path("notes/reference/arnvik_tables/table9_machine_counts.csv")
TABLE_REGION = "40,720,560,80"
PAGE = 34


def main() -> None:
    if not PDF_PATH.exists():
        raise SystemExit(f"Missing PDF: {PDF_PATH}")
    tables = camelot.read_pdf(
        str(PDF_PATH),
        pages=str(PAGE),
        flavor="stream",
        table_regions=[TABLE_REGION],
        strip_text="\n",
    )
    if len(tables) < 2:
        raise SystemExit("Unable to locate Table 9 with Camelot; adjust region")
    df = tables[1].df
    header = df.iloc[4].tolist()
    rows = df.iloc[5:-1].values.tolist()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"Wrote Table 9 counts -> {OUT_PATH}")


if __name__ == "__main__":
    main()
