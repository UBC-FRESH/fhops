#!/usr/bin/env python3
"""Precompute exact bounds for serious-game levels."""

from __future__ import annotations

import argparse
from pathlib import Path

from fhops.game import check_precompute, load_levels, precompute_level
from fhops.game.precompute import load_precompute, write_precompute


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels-dir", type=Path, default=Path("examples/game/levels"))
    parser.add_argument("--output-dir", type=Path, default=Path("examples/game/precomputed"))
    parser.add_argument("--level", action="append", default=None)
    parser.add_argument("--solver", default="highs")
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run or verify the precompute."""
    args = parse_args()
    levels = load_levels(args.levels_dir)
    if args.level:
        wanted = set(args.level)
        levels = tuple(level for level in levels if level.level_id in wanted)
        if not levels:
            raise SystemExit("No matching level ids")
    for level in levels:
        path = args.output_dir / f"{level.level_id}.json"
        if args.check:
            payload = load_precompute(path)
            check_precompute(level, payload)
            print(f"{level.level_id}: precompute complete")
            continue
        payload = precompute_level(
            level,
            solver=args.solver,
            time_limit=args.time_limit,
        )
        write_precompute(payload, path)
        bounds = payload["bounds"]
        print(
            f"{level.level_id}: {payload['completeness']['variant_count']} variants, "
            f"best={bounds['best_adjusted_objective']:.3f}, "
            f"worst={bounds['worst_adjusted_objective']:.3f}"
        )


if __name__ == "__main__":
    main()
