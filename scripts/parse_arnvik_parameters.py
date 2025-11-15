"""Parse Appendix 10 parameter tables into JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

APPENDIX10_DIR = Path("notes/reference/arnvik_tables/appendix10")
OUTPUT = APPENDIX10_DIR / "parameters.json"


def iter_rows(path: Path) -> Iterable[list[str]]:
    import csv

    with path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if any(cell.strip() for cell in row):
                yield [cell.strip() for cell in row]


def parse_parameters() -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    current_pub = ""
    current_nr = ""
    files = sorted(APPENDIX10_DIR.glob("appendix10_page*_table1.csv"))
    for file in files:
        for row in iter_rows(file):
            if row[0] and not row[0].isdigit():
                current_pub = row[0]
                continue
            if row[0].isdigit():
                current_nr = row[0]
                params = {f"col_{idx}": cell for idx, cell in enumerate(row[1:], start=1) if cell}
                data[f"{current_pub} model {current_nr}"] = params
    return data


def main() -> None:
    data = parse_parameters()
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"Captured {len(data)} parameter rows -> {OUTPUT}")


if __name__ == "__main__":
    main()
