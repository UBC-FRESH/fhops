"""Utilities for appending structured telemetry records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd


def append_jsonl(path: str | Path, record: Mapping[str, Any]) -> None:
    """Append a JSON record as a single line to the given path."""
    path = Path(path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def load_jsonl(path: str | Path, *, record_type: str | None = None) -> pd.DataFrame:
    """Load JSONL records into a Pandas DataFrame.

    Parameters
    ----------
    path:
        Path to the JSONL file.
    record_type:
        When provided, filters records to those whose ``record_type`` field matches.

    Returns
    -------
    pandas.DataFrame
        DataFrame containing the decoded records (each record remains a dict column-wise).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Telemetry JSONL not found: {path}")

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if record_type is not None and payload.get("record_type") != record_type:
                continue
            records.append(payload)
    return pd.DataFrame.from_records(records)


__all__ = ["append_jsonl", "load_jsonl"]
