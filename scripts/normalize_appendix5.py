"""Normalize Appendix 5 stand metadata into structured JSON."""

from __future__ import annotations

import csv
import json
from pathlib import Path

RAW = Path("notes/reference/arnvik_tables/appendix5_stands.csv")
OUT = Path("notes/reference/arnvik_tables/appendix5_stands_normalized.json")

COLUMNS = {
    "tree_species": "c1",
    "stand_age": "c2",
    "stem_volume": "c3",
    "dbh": "c4",
    "ground_condition": "c5",
    "ground_roughness": "c6",
    "slope": "c7",
    "num_operators": ("c8", "c9"),
}


def _clean(cell: str | None) -> str:
    if not cell:
        return ""
    return cell.strip().strip('"').rstrip(",").strip()


def _append_field(record: dict[str, str], field: str, value: str) -> None:
    if not value:
        return
    existing = record.get(field, "")
    record[field] = value if not existing else f"{existing} {value}".strip()


def normalize() -> None:
    if not RAW.exists():
        raise SystemExit(f"Missing source file: {RAW}")

    records: list[dict] = []
    current: dict | None = None

    def flush_current() -> None:
        nonlocal current
        if not current:
            return
        data_fields = [
            current.get("tree_species"),
            current.get("stand_age"),
            current.get("stem_volume"),
            current.get("dbh"),
            current.get("ground_condition"),
            current.get("ground_roughness"),
            current.get("slope"),
            current.get("num_operators"),
        ]
        if any(field for field in data_fields):
            current["pages"] = sorted(set(current.get("pages", [])))
            records.append(current)
        current = None

    with RAW.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            page = int(row["page"])
            author_cell = _clean(row.get("c0"))
            row_payload = any(_clean(row.get(col)) for col in [f"c{i}" for i in range(1, 10)])

            if author_cell:
                lower = author_cell.lower()
                if lower.startswith("author"):
                    continue
                if lower.startswith("mean values"):
                    continue
                if lower.startswith("operators"):
                    continue
                if row_payload:
                    flush_current()
                    current = {
                        "author": author_cell,
                        "tree_species": "",
                        "stand_age": "",
                        "stem_volume": "",
                        "dbh": "",
                        "ground_condition": "",
                        "ground_roughness": "",
                        "slope": "",
                        "num_operators": "",
                        "notes": "",
                        "pages": [page],
                    }
                else:
                    if current:
                        _append_field(current, "notes", author_cell)
                    continue

            if not current:
                continue

            current.setdefault("pages", []).append(page)

            for field, col in COLUMNS.items():
                if isinstance(col, tuple):
                    value = next((_clean(row.get(c)) for c in col if _clean(row.get(c))), "")
                else:
                    value = _clean(row.get(col))
                _append_field(current, field, value)

            misc_note = _clean(row.get("c0"))
            if misc_note and misc_note.lower() not in ("", current["author"].lower()):
                _append_field(current, "notes", misc_note)

    flush_current()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, ensure_ascii=False)
    print(f"Normalized {len(records)} stand entries -> {OUT}")


if __name__ == "__main__":
    normalize()
