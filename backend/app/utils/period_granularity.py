"""Shared helpers for monthly-vs-weekly time-series grouping.

All trend endpoints accept a ``granularity`` query parameter — either
``"monthly"`` (default) or ``"weekly"``. The two helpers below ensure the
grouping rule and the display-label format stay consistent across every
trend function in the app.

Week semantics
--------------
Weekly mode uses ISO weeks: weeks run Monday → Sunday and the week number
follows ``isocalendar()``. Display labels are formatted as
``"YYYY-Www (Mmm DD)"`` where the bracketed date is the Monday that starts
the week, e.g. ``"2026-W17 (Apr 20)"``.

Monthly mode keeps the existing format: ``"YYYY-MM"``.
"""

from __future__ import annotations

import pandas as pd

VALID_GRANULARITIES = ("monthly", "weekly")


def normalize_granularity(value: str | None) -> str:
    """Coerce any input to a valid granularity. Defaults to ``"monthly"``."""
    if value is None:
        return "monthly"
    v = str(value).strip().lower()
    if v in ("week", "weekly", "w"):
        return "weekly"
    return "monthly"


def period_start_series(date_series: pd.Series, granularity: str) -> pd.Series:
    """Return a Series of period-start timestamps for the given dates.

    For ``"monthly"`` the start is the 1st of the month. For ``"weekly"`` the
    start is the Monday of the ISO week containing the date.
    """
    if granularity == "weekly":
        # to_period("W") defaults to W-SUN ("week ending Sunday") which makes
        # start_time a Monday — exactly the ISO/Monday convention we want.
        return date_series.dt.to_period("W").dt.start_time
    return date_series.dt.to_period("M").dt.start_time


def format_period_label(ts: pd.Timestamp, granularity: str) -> str:
    """Format a period-start timestamp as the user-facing axis/label string.

    Monthly: ``"2026-04"``
    Weekly:  ``"2026-W17 (Apr 20)"``
    """
    ts = pd.Timestamp(ts)
    if granularity == "weekly":
        iso = ts.isocalendar()
        # iso is a 3-tuple (year, week, weekday) on older pandas / a NamedTuple
        # on newer pandas; both are indexable by position.
        iso_year = iso[0] if not hasattr(iso, "year") else iso.year
        iso_week = iso[1] if not hasattr(iso, "week") else iso.week
        return f"{iso_year}-W{int(iso_week):02d} ({ts.strftime('%b %d')})"
    return ts.strftime("%Y-%m")


def iter_period_starts(start: pd.Timestamp, end: pd.Timestamp, granularity: str):
    """Yield every period-start timestamp from ``start`` to ``end`` inclusive.

    Used to fill gaps with zeros so missing periods still appear in the chart.
    """
    start_p = period_start_series(pd.Series([pd.Timestamp(start)])).iloc[0] if False else (
        pd.Timestamp(start).to_period("W" if granularity == "weekly" else "M").start_time
    )
    end_p = pd.Timestamp(end).to_period("W" if granularity == "weekly" else "M").start_time

    cur = start_p
    step = pd.Timedelta(days=7) if granularity == "weekly" else None
    while cur <= end_p:
        yield cur
        if granularity == "weekly":
            cur = cur + step
        else:
            # Use period arithmetic to handle month-length variation
            cur = (cur.to_period("M") + 1).start_time
