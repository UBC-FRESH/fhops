from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Iterable

import typer

telemetry_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Telemetry maintenance utilities.")


def _read_run_lines(path: Path) -> Iterable[tuple[str, dict[str, object] | None]]:
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line:
                yield raw, None
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                yield raw, None
            else:
                yield raw, payload if isinstance(payload, dict) else None


@telemetry_app.command("prune")
def prune(
    telemetry_log: Path = typer.Argument(
        Path("telemetry/runs.jsonl"),
        exists=False,
        dir_okay=False,
        writable=True,
        help="Telemetry JSONL file to prune.",
    ),
    keep: int = typer.Option(
        5000,
        "--keep",
        "-k",
        min=1,
        help="Number of most-recent run records to retain.",
    ),
    steps_dir: Path | None = typer.Option(
        None,
        "--steps-dir",
        help="Directory holding step logs (defaults to <log>/../steps).",
        dir_okay=True,
        file_okay=False,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the prune operation without modifying any files.",
    ),
) -> None:
    """Trim run telemetry JSONL and delete matching step logs."""
    if not telemetry_log.exists():
        typer.echo(f"No telemetry log found at {telemetry_log}. Nothing to prune.")
        raise typer.Exit(0)

    lines = list(_read_run_lines(telemetry_log))
    if len(lines) <= keep:
        typer.echo(
            f"Telemetry log contains {len(lines)} record(s); nothing to prune (keep={keep})."
        )
        raise typer.Exit(0)

    kept_entries = deque(lines, maxlen=keep)
    removed_entries = lines[:-keep]

    kept_run_ids = {
        payload.get("run_id")
        for _, payload in kept_entries
        if isinstance(payload, dict) and payload.get("run_id")
    }
    removed_run_ids = {
        payload.get("run_id")
        for _, payload in removed_entries
        if isinstance(payload, dict) and payload.get("run_id")
    }

    steps_root = steps_dir or telemetry_log.parent / "steps"
    if dry_run:
        typer.echo(
            f"[dry-run] Would keep {len(kept_entries)} record(s) and prune "
            f"{len(removed_entries)}."
        )
        if removed_run_ids:
            typer.echo(
                f"[dry-run] Would remove {len(removed_run_ids)} step log(s) in {steps_root}."
            )
        raise typer.Exit(0)

    tmp_path = telemetry_log.with_suffix(telemetry_log.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for raw_line, _ in kept_entries:
            # raw_line already includes newline representation from original file
            if raw_line.endswith("\n"):
                handle.write(raw_line)
            else:
                handle.write(raw_line + "\n")
    tmp_path.replace(telemetry_log)

    steps_removed = 0
    if steps_root.exists():
        for run_id in removed_run_ids:
            if not isinstance(run_id, str):
                continue
            step_path = steps_root / f"{run_id}.jsonl"
            if step_path.exists():
                step_path.unlink()
                steps_removed += 1
    typer.echo(
        f"Pruned {len(removed_entries)} record(s); kept {len(kept_entries)}. "
        f"Removed {steps_removed} step log(s)."
    )
