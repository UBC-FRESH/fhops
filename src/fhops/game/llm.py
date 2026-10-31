"""Prompt/response helpers for the optional debrief LLM."""

from __future__ import annotations

import json
from typing import Any

__all__ = [
    "DEEPSEEK_GAME_MODEL",
    "build_debrief_prompt",
    "parse_debrief_response",
]

DEEPSEEK_GAME_MODEL = "opencode-go/deepseek-v4.1-flash"


def build_debrief_prompt(facts: dict[str, Any]) -> str:
    """Build a strict JSON-only explanation prompt from deterministic facts."""
    return (
        "You are the FHOPS serious-game debrief agent. Explain the result using "
        "ONLY the facts in the JSON below. Do not add new numeric claims, do not "
        "change the optimal choice, and do not give operational advice beyond "
        "the supplied facts. Return ONLY one JSON object with exactly these keys:\n"
        '{"why_optimal": "concise explanation", "parameter_costs": {"parameter": "explanation"}}\n'
        "Facts:\n" + json.dumps(facts, sort_keys=True, separators=(",", ":"))
    )


def parse_debrief_response(text: str) -> dict[str, Any]:
    """Extract a JSON object from an agent response."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError("Debrief agent did not return valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Debrief agent response must be a JSON object.")
    if not isinstance(payload.get("why_optimal"), str):
        raise ValueError("Debrief agent response needs why_optimal.")
    if not isinstance(payload.get("parameter_costs"), dict):
        raise ValueError("Debrief agent response needs parameter_costs.")
    return payload
