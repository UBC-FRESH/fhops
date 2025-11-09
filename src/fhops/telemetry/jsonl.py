"""Utilities for appending structured telemetry records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def append_jsonl(path: str | Path, record: Mapping[str, Any]) -> None:
    """Append a JSON record as a single line to the given path."""
    path = Path(path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


__all__ = ["append_jsonl"]
