"""Shared CLI testing utilities."""

from __future__ import annotations

import re
from typing import Any

from typer.testing import CliRunner as _TyperCliRunner

from fhops._typer_cli_runner import patch_typer_cli_runner

patch_typer_cli_runner()

_ANSI_RE = re.compile(r"\x1B\[[0-9;?]*[ -/]*[@-~]")


class CliRunner(_TyperCliRunner):
    """Thin wrapper that ensures Typer's patched runner is imported."""

    def invoke(self, *args, **kwargs):  # type: ignore[override]
        result = super().invoke(*args, **kwargs)
        merged = _coalesce_output(result, strip_ansi=True)
        if merged:
            try:
                encoded = merged.encode("utf-8")
            except Exception:  # pragma: no cover - fallback for exotic encodings
                encoded = merged.encode("utf-8", errors="replace")
            result.stdout_bytes = encoded
            result.output_bytes = encoded
        # Drop stderr so downstream helpers do not append duplicates.
        if getattr(result, "stderr_bytes", None):
            result.stderr_bytes = b""
        return result


def _decode(chunk: bytes | str | None) -> str:
    if not chunk:
        return ""
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8", errors="replace")
    return chunk


def _strip_ansi(value: str) -> str:
    return _ANSI_RE.sub("", value)


def _coalesce_output(result: Any, *, strip_ansi: bool) -> str:
    text = ""
    stdout_bytes = getattr(result, "stdout_bytes", b"")
    if stdout_bytes:
        text = _decode(stdout_bytes)
    elif result.stdout:
        text = _decode(result.stdout)

    stderr_bytes = getattr(result, "stderr_bytes", b"")
    if stderr_bytes:
        stderr_text = _decode(stderr_bytes)
        if stderr_text and stderr_text not in text:
            text += stderr_text

    if not text:
        try:
            stderr_value = getattr(result, "stderr", "")
        except ValueError:
            stderr_value = ""
        text = _decode(result.stdout) or _decode(stderr_value)

    if strip_ansi:
        text = _strip_ansi(text)
    return text


def cli_text(result: Any, *, strip_ansi: bool = True) -> str:
    """Return combined CLI output (stdout + stderr) for assertions."""

    return _coalesce_output(result, strip_ansi=strip_ansi)


__all__ = ["CliRunner", "cli_text"]
