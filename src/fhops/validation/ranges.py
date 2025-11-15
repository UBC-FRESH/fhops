"""Schema validators leveraging Lahrsen (2025) ranges."""

from __future__ import annotations

from typing import Iterable, List, Mapping

from fhops.productivity import load_lahrsen_ranges

RangeEntry = Mapping[str, float]


def _within(entry: RangeEntry, value: float) -> bool:
    lo = entry.get("min")
    hi = entry.get("max")
    if lo is None or hi is None:
        return True
    return lo <= value <= hi


def validate_block_ranges(
    *,
    block_id: str,
    stem_size: float | None,
    volume_per_ha: float | None,
    stem_density: float | None,
    ground_slope: float | None,
    section: str = "daily",
) -> list[str]:
    """Return warnings when block metrics fall outside observed ranges."""

    ranges = load_lahrsen_ranges()[section]
    warnings: List[str] = []
    if stem_size is not None and not _within(ranges["avg_stem_size_m3"], stem_size):
        warnings.append(
            f"Block {block_id}: avg_stem_size={stem_size} outside [{ranges['avg_stem_size_m3']['min']}, {ranges['avg_stem_size_m3']['max']}]"
        )
    if volume_per_ha is not None and not _within(ranges["volume_per_ha_m3"], volume_per_ha):
        warnings.append(
            f"Block {block_id}: volume_per_ha={volume_per_ha} outside [{ranges['volume_per_ha_m3']['min']}, {ranges['volume_per_ha_m3']['max']}]"
        )
    if stem_density is not None and not _within(ranges["stem_density_per_ha"], stem_density):
        warnings.append(
            f"Block {block_id}: stem_density={stem_density} outside [{ranges['stem_density_per_ha']['min']}, {ranges['stem_density_per_ha']['max']}]"
        )
    if ground_slope is not None and not _within(ranges["ground_slope_percent"], ground_slope):
        warnings.append(
            f"Block {block_id}: slope={ground_slope} outside [{ranges['ground_slope_percent']['min']}, {ranges['ground_slope_percent']['max']}]"
        )
    return warnings


__all__ = ["validate_block_ranges"]
