#!/usr/bin/env python3
"""Generate a pre-saved optimal 3D replay for a game level."""

from __future__ import annotations

import argparse
from pathlib import Path

from fhops.game.replay import generate_replay
from fhops.game.stand_precompute import load_stand_precompute


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("level", type=Path)
    parser.add_argument("--precompute", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = load_stand_precompute(args.precompute)
    choices = dict(payload["bounds"]["best_choices"])
    print(generate_replay(args.level, choices, args.out))


if __name__ == "__main__":
    main()
