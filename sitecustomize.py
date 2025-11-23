"""Project-level sitecustomize to keep Typer CLI tests stable."""

from fhops._typer_cli_runner import patch_typer_cli_runner

patch_typer_cli_runner()
