"""Compatibility helpers for Typer CLI tests."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from types import ModuleType

_PATCH_FLAG = "_fhops_stdout_mirrored"


def _iter_modules() -> Iterable[ModuleType]:
    for module in sys.modules.values():
        if isinstance(module, ModuleType):
            yield module


def _swap_in_module(
    module: ModuleType, original: type, patched: type
) -> None:  # pragma: no cover - tiny helper
    candidate = getattr(module, "CliRunner", None)
    if candidate is original:
        setattr(module, "CliRunner", patched)


def patch_typer_cli_runner() -> None:
    """Mirror stderr into stdout for typer.testing.CliRunner."""

    try:
        import typer.testing as typer_testing  # type: ignore
    except Exception:  # pragma: no cover - Typer missing in some toolchains
        return

    current = getattr(typer_testing, "CliRunner", None)
    if current is None or getattr(current, _PATCH_FLAG, False):
        return

    original_runner = current

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
    for module in _iter_modules():
        _swap_in_module(module, original_runner, StdoutCliRunner)
