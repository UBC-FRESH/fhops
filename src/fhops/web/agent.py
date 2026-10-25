"""Optional local assistant bridge.

The assistant is disabled unless the service is started with ``--allow-agent``. When enabled it
runs the installed ``opencode`` CLI as a subprocess in the configured workspace; the service never
reads provider keys and never supplies a shell.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["AgentError", "AgentRequest", "run_agent"]


class AgentRequest(BaseModel):
    """A single assistant prompt."""

    message: str = Field(min_length=1, max_length=4000)
    model: str | None = Field(default=None, max_length=200)


class AgentError(RuntimeError):
    """The assistant subprocess failed."""


def run_agent(
    request: AgentRequest,
    *,
    workspace: Path,
    command: tuple[str, ...],
    timeout: float,
) -> dict[str, Any]:
    """Run the assistant CLI and return its textual response."""
    argv = list(command)
    if request.model:
        argv.extend(["--model", request.model])
    argv.append(request.message)
    try:
        completed = subprocess.run(
            argv,
            cwd=workspace,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AgentError(f"Assistant command not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AgentError(f"Assistant timed out after {timeout:g} s") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-2000:]
        raise AgentError(detail or f"Assistant exited with code {completed.returncode}")
    response = _extract_response(completed.stdout)
    return {
        "response": response,
        "returncode": completed.returncode,
        "command": argv[0],
    }


def _extract_response(stdout: str) -> str:
    text = stdout.strip()
    if not text:
        return ""
    # ``opencode run --format json`` emits one JSON object per line; keep the last assistant text.
    lines = text.splitlines()
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict):
            for key in ("text", "content", "message"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            part = payload.get("part")
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"].strip()
    return text[-12000:]
