"""Stable cache for post-level explanation payloads."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["ExplanationCache", "explanation_key"]


class ExplanationCache:
    """JSON-backed cache keyed by level and finite choice combination."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._payload: dict[str, Any] = {}
        if self.path.is_file():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("Explanation cache must be a JSON object.")
            self._payload = loaded

    def get(self, key: str) -> dict[str, Any] | None:
        """Return a cached explanation, if present."""
        value = self._payload.get(key)
        return dict(value) if isinstance(value, dict) else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        """Store and persist one explanation."""
        self._payload[key] = dict(value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def explanation_key(level_id: str, choices: dict[str, Any]) -> str:
    """Return a stable level+choice cache key."""
    material = json.dumps(
        {"level_id": level_id, "choices": choices},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
