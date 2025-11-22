"""Summarise FNCY12 monthly productivity with/without supports and derive support ratios."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "fpinnovations" / "fncy12_tmy45_mini_mak.json"


@dataclass
class Bucket:
    months: list[str]
    shifts: float = 0.0
    smh: float = 0.0
    volume: float = 0.0

    def add(self, month: str, shifts: float, smh_per_shift: float, volume: float) -> None:
        self.months.append(month)
        self.shifts += shifts
        self.smh += shifts * smh_per_shift
        self.volume += volume

    def summary(self, label: str) -> dict[str, float | str | Sequence[str]]:
        avg_shift = self.volume / self.shifts if self.shifts else 0.0
        avg_smh = self.volume / self.smh if self.smh else 0.0
        return {
            "label": label,
            "months": list(self.months),
            "productive_shifts": self.shifts,
            "productive_smh": self.smh,
            "volume_m3": self.volume,
            "avg_shift_m3": avg_shift,
            "avg_smh_m3": avg_smh,
        }


def _derive_support_ratios() -> dict[str, float]:
    """Derive Cat D8 / Timberjack ratios from crew delta + support share."""

    # Table 3 indicates Thunderbird crew size 5.5 vs. 3.0 for comparable Skylead systems.
    crew_with_support = 5.5
    crew_baseline = 3.0
    extra_man_days = crew_with_support - crew_baseline

    # FNCY12 text: 23% of the area/shift required intermediate supports.
    support_area_fraction = 0.23

    # TN-157 backspar share ≈ 58% of support effort; remaining 42% assigned to trail support (Timberjack).
    cat_d8_share = 0.58
    timberjack_share = 1.0 - cat_d8_share

    effective_man_days = extra_man_days * support_area_fraction
    cat_d8_ratio = effective_man_days * cat_d8_share
    timberjack_ratio = effective_man_days * timberjack_share
    return {
        "extra_man_days": extra_man_days,
        "support_area_fraction": support_area_fraction,
        "cat_d8_smhr_per_yarder_smh": cat_d8_ratio,
        "timberjack450_smhr_per_yarder_smh": timberjack_ratio,
    }


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    months = data["productivity"]["volumes_m3_per_month"]
    shift_hours = float(data["productivity"]["shift_hours"])

    with_support = Bucket(months=[])
    without_support = Bucket(months=[])

    for entry in months:
        bucket = with_support if entry["month"] in {"August", "September", "October"} else without_support
        bucket.add(
            month=entry["month"],
            shifts=float(entry["productive_shifts"]),
            smh_per_shift=shift_hours,
            volume=float(entry["volume_m3"]),
        )

    print("Productivity split:")
    for summary in (
        without_support.summary("without_support"),
        with_support.summary("with_support"),
    ):
        print(summary)

    ratios = _derive_support_ratios()
    print("\\nDerived support utilisation ratios (per yarder SMH):")
    print(
        {
            "cat_d8_smhr_per_yarder_smh": round(ratios["cat_d8_smhr_per_yarder_smh"], 4),
            "timberjack450_smhr_per_yarder_smh": round(
                ratios["timberjack450_smhr_per_yarder_smh"], 4
            ),
            "assumptions": {
                "extra_man_days": ratios["extra_man_days"],
                "support_area_fraction": ratios["support_area_fraction"],
                "backspar_share": 0.58,
            },
        }
    )


if __name__ == "__main__":
    main()
