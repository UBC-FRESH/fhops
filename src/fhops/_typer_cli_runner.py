"""Compatibility helpers for Typer CLI tests."""

from __future__ import annotations

from typing import Any, Callable, Type, cast

_PATCH_FLAG = "_fhops_stdout_mirrored"


def patch_typer_cli_runner() -> None:
    """Mirror stderr into stdout for typer.testing.CliRunner."""

    try:
        import typer.testing as typer_testing
    except Exception:  # pragma: no cover - Typer missing in some toolchains
        return

    runner = getattr(typer_testing, "CliRunner", None)
    if runner is None or getattr(runner, _PATCH_FLAG, False):
        return

    cli_runner_type = cast(Type[Any], runner)
    original_invoke = cast(Callable[..., Any], cli_runner_type.invoke)

    def invoke_with_merged_stdout(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_invoke(self, *args, **kwargs)
        stderr_bytes = getattr(result, "stderr_bytes", b"")
        if stderr_bytes:
            stdout_bytes = getattr(result, "stdout_bytes", b"")
            result.stdout_bytes = stdout_bytes + stderr_bytes
        return result

    setattr(cli_runner_type, "invoke", invoke_with_merged_stdout)
    setattr(cli_runner_type, _PATCH_FLAG, True)
