"""Parse Appendix 11 statistical metadata into JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

APPENDIX11_DIR = Path("notes/reference/arnvik_tables/appendix11")
OUTPUT = APPENDIX11_DIR / "statistics.json"


def iter_rows(path: Path) -> Iterable[list[str]]:
    import csv

    with path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if any(cell.strip() for cell in row):
                yield [cell.strip() for cell in row]


def parse_statistics() -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    current_pub = ""
    files = sorted(APPENDIX11_DIR.glob("appendix11_page*_table1.csv"))
    for file in files:
        for row in iter_rows(file):
            if row[0] and not row[0].isdigit():
                current_pub = row[0]
                continue
            if row[0].isdigit():
                model_nr = row[0]
                entry = {
                    "observational_unit": row[1],
                    "observations": row[2],
                    "structure": row[3],
                    "r_squared": row[4],
                    "r_squared_adj": row[5],
                    "significance": row[6],
                    "f_stat": row[7] if len(row) > 7 else "",
                }
                data[f"{current_pub} model {model_nr}"] = entry
    return data


def main() -> None:
    data = parse_statistics()
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"Captured {len(data)} statistical rows -> {OUTPUT}")


if __name__ == "__main__":
    main()
