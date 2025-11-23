"""Shared CLI testing utilities."""

from __future__ import annotations

from typer.testing import CliRunner as _TyperCliRunner

from fhops._typer_cli_runner import patch_typer_cli_runner

patch_typer_cli_runner()


class CliRunner(_TyperCliRunner):
    """CLI runner that keeps stderr/text assertions stable."""

    def invoke(self, *args, **kwargs):  # type: ignore[override]
        result = super().invoke(*args, **kwargs)
        stderr_bytes = getattr(result, "stderr_bytes", b"")
        if stderr_bytes:
            stdout_bytes = getattr(result, "stdout_bytes", b"")
            result.stdout_bytes = stdout_bytes + stderr_bytes
        return result


__all__ = ["CliRunner"]
