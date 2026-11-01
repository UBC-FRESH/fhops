"""Bootstrap the Tree Lab sandbox: generate cases, pin inventories, build runs.

Usage
-----
``python -m sandbox.scripts.bootstrap``

The script is idempotent: existing case inputs are left untouched unless
``--force`` is passed, and each case receives a deterministic ``demo`` run that
the web UI can open immediately.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from sandbox.scripts.generate_cases import case_specs, generate_case
from sandbox.tree_lab.cases import discover_cases, ensure_pinned, validate_case
from sandbox.tree_lab.runner import run_case

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = REPO_ROOT / "sandbox" / "cases"
DEFAULT_RUNS = REPO_ROOT / "sandbox" / "runs"


def main(argv: list[str] | None = None) -> int:
    """Generate and build every demo case."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--force", action="store_true", help="Regenerate case inputs from scratch.")
    parser.add_argument("--skip-runs", action="store_true", help="Only generate and pin cases.")
    args = parser.parse_args(argv)

    if args.force:
        for spec in case_specs():
            shutil.rmtree(args.cases / spec.case_id, ignore_errors=True)

    summaries = []
    for spec in case_specs():
        case_dir = args.cases / spec.case_id
        if not (case_dir / "case.json").is_file():
            print(f"[generate] {spec.case_id}")
            generate_case(spec, args.cases)
        else:
            print(f"[keep]     {spec.case_id}")

    for case in discover_cases(args.cases):
        pin = ensure_pinned(case)
        report = validate_case(case)
        if not report["valid"]:
            raise SystemExit(f"{case.case_id} is invalid: {report['errors']}")
        print(f"[pin]      {case.case_id}: {pin['inventory_id']} (changed={pin['changed']})")
        if args.skip_runs:
            continue
        print(f"[run]      {case.case_id}")
        record = run_case(case, args.runs / case.case_id, run_id="demo")
        summaries.append(
            {
                "case_id": case.case_id,
                "run_id": record["run_id"],
                "status": record["status"],
                "trees": record["kpis"]["tree_count"],
                "volume_m3": round(record["kpis"]["processed_volume_m3"], 3),
                "makespan_h": round(record["kpis"]["makespan_s"] / 3600.0, 2),
                "events": record["event_count"],
            }
        )

    args.runs.mkdir(parents=True, exist_ok=True)
    status = {"cases": summaries}
    (args.runs / "status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
