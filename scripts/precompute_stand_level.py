#!/usr/bin/env python3
"""Precompute a stand-scale serious-game level."""

from __future__ import annotations

import argparse
from pathlib import Path

from fhops.game.stand_precompute import (
    check_stand_precompute,
    load_stand_precompute,
    precompute_stand_level,
    write_stand_precompute,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("level", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run or verify a stand precompute."""
    args = parse_args()
    if args.check:
        payload = load_stand_precompute(args.out)
        check_stand_precompute(args.level, payload)
        print(f"{payload['level_id']}: precompute complete")
        return
    payload = precompute_stand_level(args.level)
    write_stand_precompute(payload, args.out)
    print(
        f"{payload['level_id']}: {payload['completeness']['combination_count']} combinations, "
        f"best={payload['bounds']['best_net_profit']:.2f}, "
        f"worst={payload['bounds']['worst_net_profit']:.2f}"
    )


if __name__ == "__main__":
    main()
