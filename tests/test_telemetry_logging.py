from __future__ import annotations

import json
from pathlib import Path

from fhops.telemetry import append_jsonl


def test_append_jsonl(tmp_path: Path):
    path = tmp_path / "telemetry.jsonl"
    record1 = {"id": 1, "value": "alpha"}
    record2 = {"id": 2, "value": "beta"}

    append_jsonl(path, record1)
    append_jsonl(path, record2)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == record1
    assert json.loads(lines[1]) == record2
