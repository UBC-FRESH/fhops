#!/usr/bin/env python
"""Execute analytics notebooks and capture metadata.

Usage:
    python scripts/run_analytics_notebooks.py [--light] [--keep-going]
                                               [--timeout SECONDS]
                                               [--notebook PATH ...]

By default the script executes the curated analytics notebooks under
``docs/examples/analytics/`` using ``jupyter nbconvert`` and records per-notebook
runtime/status metadata to ``docs/examples/analytics/data/notebook_metadata.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_NOTEBOOKS = [
    "docs/examples/analytics/playback_walkthrough.ipynb",
    "docs/examples/analytics/stochastic_robustness.ipynb",
    "docs/examples/analytics/what_if_analysis.ipynb",
    "docs/examples/analytics/landing_congestion.ipynb",
    "docs/examples/analytics/system_mix.ipynb",
    "docs/examples/analytics/kpi_decomposition.ipynb",
    "docs/examples/analytics/telemetry_diagnostics.ipynb",
    "docs/examples/analytics/ensemble_resilience.ipynb",
    "docs/examples/analytics/operator_sweep.ipynb",
    "docs/examples/analytics/benchmark_summary.ipynb",
]

DATA_DIR = Path("docs/examples/analytics/data")
METADATA_PATH = DATA_DIR / "notebook_metadata.json"


def run_notebook(
    path: Path, *, light: bool, timeout: int | None, env: dict[str, str]
) -> tuple[str, float, str]:
    """Execute the notebook and return (status, runtime_seconds, message)."""
    cmd = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        str(path),
        "--output",
        path.name,
        "--output-dir",
        str(path.parent),
    ]
    start = time.perf_counter()
    status = "ok"
    message = ""
    try:
        subprocess.run(cmd, check=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        status = "timeout"
        message = f"Timeout after {timeout}s"
    except subprocess.CalledProcessError as exc:
        status = "error"
        message = f"Exited with return code {exc.returncode}"
    duration = time.perf_counter() - start
    return status, duration, message


def normalise_paths(notebooks: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for entry in notebooks:
        path = Path(entry)
        if not path.exists():
            raise FileNotFoundError(f"Notebook not found: {entry}")
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--light", action="store_true", help="Run in light mode (fewer stochastic samples)."
    )
    parser.add_argument(
        "--keep-going", action="store_true", help="Continue executing notebooks even if one fails."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Optional timeout (seconds) per notebook execution.",
    )
    parser.add_argument(
        "--notebook",
        dest="notebooks",
        action="append",
        help="Specific notebook(s) to execute (default: curated list).",
    )
    args = parser.parse_args()

    notebooks = args.notebooks or DEFAULT_NOTEBOOKS
    paths = normalise_paths(notebooks)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    if args.light:
        env["FHOPS_ANALYTICS_LIGHT"] = "1"

    results = []
    overall_status = 0

    for path in paths:
        print(f"Executing {path}...")
        status, duration, message = run_notebook(
            path, light=args.light, timeout=args.timeout, env=env
        )
        results.append(
            {
                "notebook": str(path),
                "status": status,
                "runtime_seconds": round(duration, 2),
                "message": message,
            }
        )
        if status != "ok" and not args.keep_going:
            overall_status = 1
            break
        if status != "ok":
            overall_status = 1

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "light_mode": bool(args.light),
        "notebooks": results,
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Metadata written to {METADATA_PATH}")

    if overall_status:
        print("One or more notebooks failed.", file=sys.stderr)
    return overall_status


if __name__ == "__main__":
    sys.exit(main())
