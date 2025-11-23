"""Helpers to keep Typer CLI tests stable across Click/Typer upgrades."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from types import ModuleType

import typer.testing as typer_testing

_PATCH_FLAG = "_fhops_stdout_mirrored"


def _needs_patch() -> bool:
    """Check whether typer.testing already exposes the patched runner."""

    current_runner = getattr(typer_testing, "CliRunner", None)
    return not getattr(current_runner, _PATCH_FLAG, False)


def _swap_in_module(module: ModuleType, original: type, patched: type) -> None:
    """Replace references to the original runner within a module namespace."""

    candidate = getattr(module, "CliRunner", None)
    if candidate is original:
        setattr(module, "CliRunner", patched)


def patch_cli_runner() -> None:
    """Mirror stderr into stdout so CLI tests can assert on rich errors."""

    if not _needs_patch():
        return

    original_runner = typer_testing.CliRunner

    class StdoutCliRunner(original_runner):  # type: ignore[misc,valid-type]
        _fhops_stdout_mirrored = True

        def invoke(self, *args, **kwargs):  # type: ignore[override]
            result = super().invoke(*args, **kwargs)
            stderr_bytes = getattr(result, "stderr_bytes", b"")
            if stderr_bytes:
                stdout_bytes = getattr(result, "stdout_bytes", b"")
                result.stdout_bytes = stdout_bytes + stderr_bytes
            return result

    typer_testing.CliRunner = StdoutCliRunner
    modules: Iterable[ModuleType | None] = sys.modules.values()
    for module in modules:
        if module is not None:
            _swap_in_module(module, original_runner, StdoutCliRunner)
