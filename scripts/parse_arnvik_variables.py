"""Parse Appendix 9 variable definitions into JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path

APPENDIX9_DIR = Path("notes/reference/arnvik_tables/appendix9")
OUTPUT = APPENDIX9_DIR / "variables.json"

CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9₀-₉]*$")


def iter_rows(path: Path):
    import csv

    with path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            yield [cell.strip() for cell in row]


def parse_variables() -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    current_code: str | None = None
    current_unit: str = ""
    current_desc: list[str] = []

    files = sorted(APPENDIX9_DIR.glob("appendix9_page*_table1.csv"))
    for file in files:
        for row in iter_rows(file):
            if not any(row):
                continue
            code_candidate = row[0]
            if code_candidate and CODE_RE.match(code_candidate):
                if current_code:
                    mapping[current_code] = {
                        "unit": current_unit,
                        "description": " ".join(current_desc).strip(),
                    }
                current_code = code_candidate
                current_unit = row[1] if len(row) > 1 else ""
                current_desc = [" ".join(cell for cell in row[2:] if cell)]
                continue
            if current_code:
                current_desc.append(" ".join(cell for cell in row if cell))
    if current_code and current_code not in mapping:
        mapping[current_code] = {
            "unit": current_unit,
            "description": " ".join(current_desc).strip(),
        }
    return mapping


def main() -> None:
    mapping = parse_variables()
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump(mapping, fh, indent=2, ensure_ascii=False)
    print(f"Captured {len(mapping)} variable definitions -> {OUTPUT}")


if __name__ == "__main__":
    main()
