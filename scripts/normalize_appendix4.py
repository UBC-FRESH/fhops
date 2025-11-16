"""Normalize Appendix 4 machine specs into structured JSON."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

RAW = Path("notes/reference/arnvik_tables/appendix4_machines.csv")
OUT = Path("notes/reference/arnvik_tables/appendix4_machines_normalized.json")

FLAG_RE = re.compile(r"^(?P<head>.+?)\s+(?P<deb>Yes|No|-)\s+(?P<mtc>Yes|No|-)$")
TIME_UNITS = (
    "months",
    "month",
    "hours",
    "hour",
    "mins",
    "min",
    "days",
    "day",
)


def parse_head(value: str) -> tuple[str, str | None, str | None]:
    value = value.strip()
    if not value:
        return "", None, None
    match = FLAG_RE.match(value)
    if match:
        return match.group("head"), match.group("deb"), match.group("mtc")
    return value, None, None


def parse_pr_machine(value: str) -> tuple[str | None, str]:
    value = value.strip()
    if not value:
        return None, ""
    parts = value.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def parse_hm_machine(value: str) -> tuple[str, str | None]:
    value = value.strip()
    if not value:
        return "", None
    tokens = value.split()
    harvest_method = tokens[0]
    machine_type = " ".join(tokens[1:]) if len(tokens) > 1 else None
    return harvest_method, machine_type or None


def parse_time_operation(value: str) -> tuple[str | None, str | None]:
    value = value.strip()
    if not value or value == "-":
        return None, None
    lower = value.lower()
    for unit in TIME_UNITS:
        idx = lower.find(unit)
        if idx != -1:
            end = idx + len(unit)
            time_part = value[:end].strip()
            operation = value[end:].strip() or None
            return time_part, operation
    if value.startswith("-"):
        op = value.lstrip("- ") or None
        return None, op
    return None, value


def normalize() -> None:
    if not RAW.exists():
        raise SystemExit(f"Missing source file: {RAW}")
    records: list[dict] = []
    current_author = None
    note_buffer = ""
    with RAW.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            author_cell = (row.get("c0") or "").strip()
            note_cell = (row.get("c1") or "").strip()
            data_cells = [
                (row.get(col) or "").strip() for col in ("c2", "c3", "c4", "c5", "c6", "c7")
            ]
            has_data = any(data_cells)
            if author_cell:
                if author_cell.lower() == "authors":
                    current_author = None
                    note_buffer = ""
                    continue
                current_author = author_cell
                if not has_data:
                    note_buffer = " ".join(filter(None, [note_buffer, author_cell])).strip()
                    continue
            if note_cell and not has_data:
                note_buffer = " ".join(filter(None, [note_buffer, note_cell])).strip()
                continue
            if not has_data:
                continue
            author = current_author or ""
            N = (row.get("c2") or "").strip()
            hm_value = (row.get("c3") or "").strip()
            base_machine = (row.get("c4") or "").strip()
            pr_value = (row.get("c5") or "").strip()
            head_value = (row.get("c6") or "").strip()
            time_value = (row.get("c7") or "").strip()
            harvest_method, machine_type = parse_hm_machine(hm_value)
            propulsion, machine_model = parse_pr_machine(pr_value)
            head_model, debarking, mtc = parse_head(head_value)
            time_recorded, operation = parse_time_operation(time_value)
            records.append(
                {
                    "author": author,
                    "note": note_buffer or note_cell,
                    "n_machines": None if not N or N == "-" else N,
                    "harvest_method": harvest_method,
                    "machine_type": machine_type,
                    "base_machine": base_machine,
                    "propulsion": propulsion,
                    "machine_model": machine_model,
                    "head_model": head_model,
                    "debarking": debarking,
                    "multi_tree_cut": mtc,
                    "time_recorded": time_recorded,
                    "operation": operation,
                    "page": int(row["page"]),
                }
            )
            note_buffer = ""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, ensure_ascii=False)
    print(f"Normalized {len(records)} machine entries -> {OUT}")


if __name__ == "__main__":
    normalize()
