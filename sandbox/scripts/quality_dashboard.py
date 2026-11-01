"""Run the Tree Lab quality gates and print a green/red dashboard.

Checks
------
1. ``ruff format --check`` over ``src``, ``tests``, and ``sandbox``.
2. ``ruff check`` over the same paths.
3. ``mypy src`` (the repository gate).
4. ``MYPYPATH=src mypy sandbox`` (the sandbox gate).
5. ``pytest tests/tree_lab``.
6. ``pytest`` (the full suite).
7. ``node --check`` on the SPA modules when Node.js is available.
8. ``sphinx-build -b html docs _build/html -W`` when Sphinx is installed.

Results are printed as a table and written to ``sandbox/runs/quality.json``.
The process exits non-zero if any gate fails.

Usage
-----
``python -m sandbox.scripts.quality_dashboard``
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BIN = Path(sys.executable).parent


@dataclass(slots=True)
class Gate:
    """One quality gate definition and result.

    Attributes
    ----------
    name : str
        Short gate name shown in the dashboard.
    command : list[str]
        Command to execute.
    env : dict[str, str]
        Extra environment variables.
    required : bool
        When ``False`` a missing tool is reported as skipped, not failed.
    """

    name: str
    command: list[str]
    env: dict[str, str]
    required: bool = True
    status: str = "pending"
    duration_s: float = 0.0
    detail: str = ""


def _gates(include_docs: bool) -> list[Gate]:
    python = sys.executable
    gates = [
        Gate(
            "ruff format",
            [str(BIN / "ruff"), "format", "--check", "src", "tests", "sandbox"],
            {},
        ),
        Gate(
            "ruff check",
            [str(BIN / "ruff"), "check", "src", "tests", "sandbox"],
            {},
        ),
        Gate("mypy src", [str(BIN / "mypy"), "src"], {}),
        Gate("mypy sandbox", [str(BIN / "mypy"), "sandbox"], {"MYPYPATH": "src"}),
        Gate(
            "pytest tree_lab",
            [python, "-m", "pytest", "tests/tree_lab", "-q", "-p", "no:warnings"],
            {},
        ),
        Gate("pytest full", [python, "-m", "pytest", "-q", "-p", "no:warnings"], {}),
    ]
    node = shutil.which("node")
    if node:
        gates.append(
            Gate(
                "js syntax",
                [
                    "bash",
                    "-lc",
                    "cd sandbox/tree_lab/static && for f in app.js viewer.js; do "
                    'node --input-type=module --check < "$f" || exit 1; done',
                ],
                {},
            )
        )
    sphinx = BIN / "sphinx-build"
    if include_docs and sphinx.is_file():
        gates.append(
            Gate("sphinx docs", [str(sphinx), "-b", "html", "docs", "_build/html", "-W"], {})
        )
    pre_commit = BIN / "pre-commit"
    if pre_commit.is_file():
        gates.append(
            Gate("pre-commit", [str(pre_commit), "run", "--all-files"], {}, required=False)
        )
    return gates


def _run(gate: Gate, timeout_s: float) -> None:
    env = os.environ.copy()
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH', '')}"
    env.update(gate.env)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            gate.command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        gate.status = "skipped" if not gate.required else "failed"
        gate.detail = f"tool not found: {gate.command[0]}"
    except subprocess.TimeoutExpired:
        gate.status = "failed"
        gate.detail = f"timed out after {timeout_s:g}s"
    else:
        gate.status = "passed" if completed.returncode == 0 else "failed"
        lines = (completed.stdout or "").strip().splitlines() + (
            completed.stderr or ""
        ).strip().splitlines()
        summary = [
            line
            for line in lines
            if " passed" in line or " failed" in line or "error" in line.lower()
        ]
        if summary:
            gate.detail = summary[-1].strip()
        elif gate.status == "passed":
            gate.detail = f"exit {completed.returncode}"
        else:
            gate.detail = lines[-1].strip() if lines else ""
    gate.duration_s = round(time.monotonic() - started, 2)


def main(argv: list[str] | None = None) -> int:
    """Run every gate and print the dashboard."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout", type=float, default=3600.0, help="Per-gate timeout in seconds."
    )
    parser.add_argument("--no-docs", action="store_true", help="Skip the Sphinx build.")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "sandbox" / "runs" / "quality.json",
        help="Dashboard JSON output path.",
    )
    args = parser.parse_args(argv)

    gates = _gates(include_docs=not args.no_docs)
    for gate in gates:
        print(f"… {gate.name}", flush=True)
        _run(gate, args.timeout)

    width = max(len(gate.name) for gate in gates)
    print()
    for gate in gates:
        icon = {"passed": "GREEN", "failed": "RED  ", "skipped": "SKIP "}[gate.status]
        print(f"{icon}  {gate.name:<{width}}  {gate.duration_s:>7.2f}s  {gate.detail}")

    failed = [gate.name for gate in gates if gate.status == "failed"]
    payload = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "green": not failed,
        "gates": [
            {
                "name": gate.name,
                "status": gate.status,
                "duration_s": gate.duration_s,
                "detail": gate.detail,
                "command": gate.command,
            }
            for gate in gates
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nDashboard: {'GREEN' if not failed else 'RED (' + ', '.join(failed) + ')'}")
    print(f"Written to {args.out}")
    return 0 if not failed else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
