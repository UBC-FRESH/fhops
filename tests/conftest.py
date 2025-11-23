"""Test configuration and shared fixtures."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from types import ModuleType

import typer.testing as typer_testing

OriginalCliRunner = typer_testing.CliRunner


class StdoutCliRunner(OriginalCliRunner):
    """CliRunner that mirrors stderr into stdout for Typer/Click>=8.1."""

    def invoke(self, *args, **kwargs):  # type: ignore[override]
        result = super().invoke(*args, **kwargs)
        stderr_bytes = getattr(result, "stderr_bytes", b"")
        if stderr_bytes:
            stdout_bytes = getattr(result, "stdout_bytes", b"")
            result.stdout_bytes = stdout_bytes + stderr_bytes
        return result


def _patch_existing_modules(modules: Iterable[ModuleType]) -> None:
    """Swap any already-imported CliRunner references."""

    for module in modules:
        if module is None:
            continue
        runner = getattr(module, "CliRunner", None)
        if runner is OriginalCliRunner:
            setattr(module, "CliRunner", StdoutCliRunner)


# Ensure all tests importing `CliRunner` get the merged-stdout behavior,
# even if they imported typer.testing before this module executed.
typer_testing.CliRunner = StdoutCliRunner
_patch_existing_modules(sys.modules.values())
