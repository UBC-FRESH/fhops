"""Test configuration and shared fixtures."""

from __future__ import annotations

import typer.testing as typer_testing


class StdoutCliRunner(typer_testing.CliRunner):
    """CliRunner that mirrors stderr into stdout for older Click versions."""

    def invoke(self, *args, **kwargs):  # type: ignore[override]
        result = super().invoke(*args, **kwargs)
        stderr_bytes = getattr(result, "stderr_bytes", b"")
        if stderr_bytes:
            stdout_bytes = getattr(result, "stdout_bytes", b"")
            result.stdout_bytes = stdout_bytes + stderr_bytes
        return result


# Ensure all tests importing `CliRunner` get the merged-stdout behavior.
typer_testing.CliRunner = StdoutCliRunner
