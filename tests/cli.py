"""Shared CLI testing utilities."""

from __future__ import annotations

from typer.testing import CliRunner as _TyperCliRunner

from fhops._typer_cli_runner import patch_typer_cli_runner

patch_typer_cli_runner()

CliRunner = _TyperCliRunner

__all__ = ["CliRunner"]
