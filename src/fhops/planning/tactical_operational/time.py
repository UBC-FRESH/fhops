"""Period templates and hierarchy helpers for tactical–operational planning."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from fhops.planning.tactical_operational.models import PeriodLevel, PlanningPeriod


def _discount_factor(start_date: date, base_date: date, annual_rate: float) -> float:
    """Return the effective discount factor for a period start date."""
    if annual_rate <= 0:
        return 1.0
    elapsed_years = (start_date - base_date).days / 365.25
    return 1.0 / ((1.0 + annual_rate) ** elapsed_years)


def four_week_periods(
    year: int,
    *,
    start_month: int = 1,
    start_day: int = 1,
    periods: int = 13,
    discount_rate_per_year: float = 0.0,
) -> list[PlanningPeriod]:
    """Build thirteen (or a custom count of) four-week planning periods for a calendar year.

    The final period is truncated at December 31 when the accounting calendar overflows the year.
    Discount factors are assigned at each period start using an effective annual rate.
    """
    if periods < 1:
        raise ValueError("periods must be >= 1")
    first_start = date(year, start_month, start_day)
    end_of_year = date(year, 12, 31)
    rows: list[PlanningPeriod] = []
    for index in range(periods):
        start = first_start + timedelta(days=28 * index)
        if start > end_of_year:
            break
        end = min(start + timedelta(days=27), end_of_year)
        rows.append(
            PlanningPeriod(
                period_id=f"Y{year}-P{index + 1:02d}",
                level=PeriodLevel.FOUR_WEEK,
                sequence=index + 1,
                start_date=start,
                end_date=end,
                discount_factor=_discount_factor(start, first_start, discount_rate_per_year),
            )
        )
    return rows


def seasonal_periods(
    year: int,
    *,
    discount_rate_per_year: float = 0.0,
) -> list[PlanningPeriod]:
    """Build a conventional four-season calendar-year period template."""
    first_start = date(year, 1, 1)
    specs = [
        ("WINTER", date(year, 1, 1), date(year, 3, 31), ["winter"]),
        ("SPRING", date(year, 4, 1), date(year, 6, 30), ["spring", "breakup"]),
        ("SUMMER", date(year, 7, 1), date(year, 9, 30), ["summer", "fire_season"]),
        ("FALL", date(year, 10, 1), date(year, 12, 31), ["fall"]),
    ]
    return [
        PlanningPeriod(
            period_id=f"Y{year}-{name}",
            level=PeriodLevel.SEASON,
            sequence=index + 1,
            start_date=start,
            end_date=end,
            discount_factor=_discount_factor(start, first_start, discount_rate_per_year),
            season_tags=tags,
        )
        for index, (name, start, end, tags) in enumerate(specs)
    ]


def validate_period_hierarchy(periods: list[PlanningPeriod]) -> None:
    """Validate uniqueness, parent references, and chronological ordering of a period set."""
    ids = [period.period_id for period in periods]
    if len(ids) != len(set(ids)):
        raise ValueError("PlanningPeriod identifiers must be unique")
    sequences = [period.sequence for period in periods]
    if len(sequences) != len(set(sequences)):
        raise ValueError("PlanningPeriod sequence values must be unique")
    known = set(ids)
    for period in periods:
        if period.parent_period_id and period.parent_period_id not in known:
            raise ValueError(
                f"Period {period.period_id} references unknown parent {period.parent_period_id}"
            )
    ordered = sorted(periods, key=lambda item: item.sequence)
    if any(
        current.start_date > current.end_date
        or (previous.end_date >= current.start_date and previous.level == current.level)
        for previous, current in zip(ordered, ordered[1:], strict=True)
    ):
        raise ValueError(
            "Same-level planning periods must be chronologically ordered and non-overlapping"
        )


def children_by_parent(periods: list[PlanningPeriod]) -> dict[str, list[PlanningPeriod]]:
    """Group child periods by parent period ID for roll-up reporting."""
    children: dict[str, list[PlanningPeriod]] = defaultdict(list)
    for period in periods:
        if period.parent_period_id:
            children[period.parent_period_id].append(period)
    return dict(children)


__all__ = [
    "children_by_parent",
    "four_week_periods",
    "seasonal_periods",
    "validate_period_hierarchy",
]
