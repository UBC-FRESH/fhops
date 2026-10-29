"""Run a bounded sensitivity grid for a ground-based tree-scale system.

The script is intentionally narrow: it exercises processor rate, truck fleet,
shift length, truck capacity/cycle, and landing capacity for one scenario.
Outputs CSV and JSON under ``--out``. Demo inputs are external to the repo.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from fhops.ground_system import (
    GroundSystemError,
    ProcessorSpec,
    simulate_ground_system,
)


def _variants() -> list[tuple[str, dict[str, object]]]:
    variants: list[tuple[str, dict[str, object]]] = [("baseline", {})]
    for rate in (20.0, 35.0, 50.0, 70.0):
        variants.append(
            (
                f"processor_rate_{rate:g}",
                {"processor_spec": ProcessorSpec("PROC", seconds_per_m3=3600.0 / rate)},
            )
        )
    for count in (1, 2, 3, 4, 6):
        variants.append((f"trucks_{count}", {"truck_count": count}))
    for shifts, hours in ((1, 8), (2, 8), (1, 10), (2, 10), (2, 12)):
        variants.append(
            (f"shift_{shifts}x{hours}", {"shifts_per_day": shifts, "hours_per_shift": hours})
        )
    for capacity, cycle in ((20, 3600), (30, 1800), (30, 5400), (40, 3600)):
        variants.append(
            (
                f"truck_{capacity}m3_{cycle}s",
                {"truck_capacity_m3": capacity, "truck_cycle_time_s": cycle},
            )
        )
    for capacity in (60, 120, 240):
        variants.append((f"landing_{capacity}", {"landing_capacity_m3": capacity}))
    return variants


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--block", required=True)
    parser.add_argument("--feller", default="H1")
    parser.add_argument("--skidder", action="append", default=["H2", "H3"])
    parser.add_argument("--processor", default="H5")
    parser.add_argument("--loader", default="H4")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    base: dict[str, object] = {
        "feller_machine_id": args.feller,
        "skidder_machine_ids": tuple(args.skidder),
        "processor_machine_id": args.processor,
        "loader_machine_id": args.loader,
        "bunch_volume_m3": 8.0,
        "rate_model": "calibrated",
        "shift_days": 21,
        "shifts_per_day": 2,
        "hours_per_shift": 10.0,
        "truck_capacity_m3": 30.0,
        "truck_cycle_time_s": 3600.0,
        "truck_count": 3,
        "truck_load_time_s": 300.0,
        "landing_capacity_m3": 120.0,
    }
    rows: list[dict[str, object]] = []
    for label, overrides in _variants():
        params = {**base, **overrides}
        if params.get("processor_spec") is not None:
            spec = params["processor_spec"]
            assert isinstance(spec, ProcessorSpec)
            params["processor_spec"] = ProcessorSpec(
                args.processor, seconds_per_m3=spec.seconds_per_m3
            )
        try:
            result = simulate_ground_system(args.scenario, block_id=args.block, **params)
            rows.append(
                {
                    "variant": label,
                    "status": "ok",
                    "makespan_h": round(result.makespan_s / 3600.0, 3),
                    "processor_h": round(
                        result.machine_summaries[args.processor]["busy_s"] / 3600.0, 3
                    ),
                    "fb_h": round(result.machine_summaries[args.feller]["busy_s"] / 3600.0, 3),
                    "loader_h": round(result.machine_summaries[args.loader]["busy_s"] / 3600.0, 3),
                    "truck_loads": result.truck_summary.get("dispatched_loads")
                    if result.truck_summary
                    else 0,
                    "landing_max_m3": round(result.landing_inventory_max_m3, 3),
                    "landing_final_m3": round(result.landing_inventory_final_m3, 3),
                    "warnings": "; ".join(result.warnings),
                }
            )
        except GroundSystemError as exc:
            rows.append({"variant": label, "status": "error", "error": str(exc)})
        print(rows[-1])

    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "tree_system_sensitivity.json"
    json_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    csv_path = args.out / "tree_system_sensitivity.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {json_path} and {csv_path}")


if __name__ == "__main__":
    main()
