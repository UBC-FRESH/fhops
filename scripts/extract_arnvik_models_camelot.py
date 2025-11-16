"""Extract Appendix 8 tables using Camelot for tougher layouts."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import camelot

PDF_PATH = Path("notes/reference/arnvik-w-20240926.pdf")
OUT_DIR = Path("notes/reference/arnvik_tables/appendix8_camelot")

# Bounding box tuned for Appendix 8 layout (x1,y1,x2,y2 in PDF points)
TABLE_REGION = "40,795,590,40"
PAGES = list(range(101, 117))  # can extend once other ranges identified

HEADERS = [
    "page",
    "table",
    "author",
    "model",
    "harvest_method",
    "machine_type",
    "base_machine",
    "propulsion",
    "dv_type",
    "units",
    "formula",
]


HARVEST_TOKENS = {
    "CTL",
    "FT",
    "B (FT)",
    "*FT",
    "B",
    "*CTL",
    "B(FT)",
}


def split_author(cell: str) -> tuple[str, str | None]:
    match = re.match(r"(.+?\(\d{4}[a-z]?\))\s*(\d+)?$", cell)
    if match:
        author = match.group(1).strip()
        model = match.group(2)
        return author, model
    return cell, None


def normalize_table(df, page: int, table_idx: int) -> list[list[str]]:
    rows: list[list[str]] = []
    current_author = ""
    for raw in df.values.tolist():
        cells = [cell.strip() for cell in raw]
        if not any(cells):
            continue
        if len(cells) < 7:
            continue
        first = cells[0]
        if "Author" in first or "Propulsion" in first or "built;" in first:
            continue
        author = current_author
        model = ""
        remainder = cells[1:]
        if first:
            if any(ch.isalpha() for ch in first):
                author_candidate, inline_model = split_author(first)
                author = author_candidate or author
                current_author = author
                if inline_model:
                    model = inline_model
            elif first.isdigit():
                model = first
            else:
                author = first or author
        if not remainder and model:
            continue
        if remainder:
            first_data = remainder[0]
            if not model and first_data.isdigit():
                model = first_data
                remainder = remainder[1:]
            elif not model:
                match = re.match(r"(\d+)\s+(.*)", first_data)
                if match:
                    model = match.group(1)
                    remainder[0] = match.group(2)
            else:
                match = re.match(rf"{model}\\s+(.*)", first_data)
                if match:
                    remainder[0] = match.group(1)
        if not author or not model:
            continue
        if author == current_author == "":
            continue
        # Ensure remainder still has enough slots; pad with blanks if needed
        while len(remainder) < 7:
            remainder.append("")
        hm = remainder[0]
        # Clean potential harvest token joined with next entry
        if hm and hm.strip() not in HARVEST_TOKENS and " " in hm:
            parts = hm.split()
            if parts[0] in HARVEST_TOKENS:
                hm = parts[0]
                remainder[0] = hm
                remainder.insert(1, " ".join(parts[1:]))
        if len(remainder) < 7:
            continue
        machine = remainder[1]
        base = remainder[2]
        prop = remainder[3]
        dv_type = remainder[4]
        units = remainder[5]
        formula = remainder[6]
        rows.append(
            [
                str(page),
                str(table_idx),
                author,
                model,
                hm,
                machine,
                base,
                prop,
                dv_type,
                units,
                formula,
            ]
        )
    return rows


def extract() -> None:
    if not PDF_PATH.exists():
        raise SystemExit(f"Missing PDF: {PDF_PATH}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    aggregated: list[list[str]] = []
    for page in PAGES:
        tables = camelot.read_pdf(
            str(PDF_PATH),
            pages=str(page),
            flavor="stream",
            table_regions=[TABLE_REGION],
            strip_text="\n",
        )
        if not tables:
            print(f"No tables detected on page {page}")
            continue
        for idx, table in enumerate(tables, start=1):
            normalized = normalize_table(table.df, page, idx)
            if not normalized:
                continue
            out_path = OUT_DIR / f"appendix8_page{page:03d}_table{idx}.csv"
            with out_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(HEADERS)
                writer.writerows(normalized)
            aggregated.extend(normalized)
            print(f"Camelot: page {page} table {idx} -> {len(normalized)} rows")
    agg_path = OUT_DIR / "appendix8_camelot_aggregate.csv"
    with agg_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADERS)
        writer.writerows(aggregated)
    print(f"Wrote Camelot aggregate -> {agg_path}")


if __name__ == "__main__":
    extract()
