"""Build structured regression metadata for FPInnovations TR-127 Appendix VII."""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path("data/reference/fpinnovations/tr127_regressions.json")

MODELS = [
    {
        "block": 1,
        "description": "Block 1",
        "intercept_minutes": 6.3285,
        "std_error_minutes": 1.71,
        "observations": 269,
        "r_squared": 0.15,
        "predictors": [
            {
                "name": "latd",
                "description": "Lateral distance",
                "units": "m",
                "range": [0, 8],
                "coefficient": 0.0438,
            }
        ],
    },
    {
        "block": 2,
        "description": "Block 2",
        "intercept_minutes": 1.1646,
        "std_error_minutes": 2.19,
        "observations": 134,
        "r_squared": 0.49,
        "predictors": [
            {
                "name": "sd",
                "description": "Slope distance",
                "units": "m",
                "range": [225, 770],
                "coefficient": 0.0175,
            }
        ],
    },
    {
        "block": 3,
        "description": "Block 3",
        "intercept_minutes": 8.0878,
        "std_error_minutes": 2.16,
        "observations": 46,
        "r_squared": 0.29,
        "predictors": [
            {
                "name": "latd",
                "description": "Lateral distance",
                "units": "m",
                "range": [0, 65],
                "coefficient": 0.0935,
            }
        ],
    },
    {
        "block": 4,
        "description": "Block 4",
        "intercept_minutes": 3.3702,
        "std_error_minutes": 0.87,
        "observations": 125,
        "r_squared": 0.45,
        "predictors": [
            {
                "name": "latd",
                "description": "Lateral distance",
                "units": "m",
                "range": [0, 40],
                "coefficient": 0.0288,
            }
        ],
    },
    {
        "block": 5,
        "description": "Block 5",
        "intercept_minutes": 2.3296,
        "std_error_minutes": 1.64,
        "observations": 300,
        "r_squared": 0.34,
        "predictors": [
            {
                "name": "sd",
                "description": "Slope distance",
                "units": "m",
                "range": [70, 650],
                "coefficient": 0.0073,
            },
            {
                "name": "latd",
                "description": "Lateral distance",
                "units": "m",
                "range": [0, 80],
                "coefficient": 0.0350,
            },
            {
                "name": "logs",
                "description": "Number of logs",
                "units": "count",
                "range": [1, 10],
                "coefficient": 0.2791,
            },
        ],
    },
    {
        "block": 6,
        "description": "Block 6",
        "intercept_minutes": 3.6724,
        "std_error_minutes": 1.92,
        "observations": 99,
        "r_squared": 0.33,
        "predictors": [
            {
                "name": "sd",
                "description": "Slope distance",
                "units": "m",
                "range": [265, 716],
                "coefficient": 0.0052,
            },
            {
                "name": "latd",
                "description": "Lateral distance",
                "units": "m",
                "range": [0, 75],
                "coefficient": 0.0305,
            },
            {
                "name": "logs",
                "description": "Number of logs",
                "units": "count",
                "range": [1, 7],
                "coefficient": 0.4465,
            },
        ],
    },
]


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(MODELS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(MODELS)} regression entries -> {OUTPUT}")


if __name__ == "__main__":
    main()
