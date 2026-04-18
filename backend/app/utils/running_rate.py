"""
Running-rate helper for the latest (possibly partial) month.

The data snapshot is taken on an arbitrary day of the month (e.g. April 9,
2026 means April has only 9 days of sales). If we display April's revenue
next to March's 30-day revenue without adjustment, April looks like a
collapse when it's just incomplete.

This module provides:

  - get_data_as_of_date(df_sale): detect the snapshot date from Sale.DocDate
  - compute_running_rate(actual, days_elapsed, days_in_month): scale up
  - annotate_monthly_series(months, as_of): mark the last month as partial
    and compute its running rate

The output format adds three keys per month when relevant:
    is_partial : bool          — true only for the latest partial month
    days_elapsed : int         — days of data present in that month
    days_in_month : int        — full month length
    running_rate_* : float     — projected full-month value

Charts use `running_rate_*` for the last data point when `is_partial=True`,
and render it with a different style (dashed, pale, or explicitly labelled)
so viewers know it's a projection.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Optional

import pandas as pd


def get_data_as_of_date(df_sale: pd.DataFrame) -> Optional[date]:
    """Return the most recent DocDate in the Sale sheet (data snapshot date)."""
    if df_sale is None or df_sale.empty or "DocDate" not in df_sale.columns:
        return None
    d = pd.to_datetime(df_sale["DocDate"], errors="coerce").dropna()
    if d.empty:
        return None
    return d.max().date()


def compute_running_rate(
    actual_value: float, days_elapsed: int, days_in_month: int
) -> float:
    """Scale a partial-month value up to a full-month projection.

    running_rate = actual * (days_in_month / days_elapsed)

    Returns actual_value unchanged when days_elapsed <= 0 or >= days_in_month.
    """
    if days_elapsed <= 0 or days_in_month <= 0:
        return float(actual_value)
    if days_elapsed >= days_in_month:
        return float(actual_value)
    return float(actual_value) * (days_in_month / days_elapsed)


def annotate_monthly_series(
    months: list[dict],
    as_of_date: Optional[date],
    numeric_fields: Optional[list[str]] = None,
    period_key: str = "period",
) -> list[dict]:
    """Add is_partial / running_rate_* to the latest month if it's partial.

    Parameters
    ----------
    months : list of dicts, each representing a month. Must contain a
        period string in "%Y-%m" format under the given period_key.
    as_of_date : the data snapshot date. If None, nothing is annotated.
    numeric_fields : which keys to compute running_rate_ for. Defaults to
        every numeric-looking key in the dict.
    period_key : the key containing the period string. Default "period".

    The input list is mutated AND returned for convenience.
    """
    if as_of_date is None or not months:
        return months

    # Find the latest month entry
    latest_idx = None
    latest_period = None
    for i, m in enumerate(months):
        per = m.get(period_key)
        if not per:
            continue
        try:
            # Accept "YYYY-MM" or "YYYY-MM-DD"
            dt = datetime.strptime(per[:7], "%Y-%m").date()
        except ValueError:
            continue
        if latest_period is None or dt > latest_period:
            latest_period = dt
            latest_idx = i

    if latest_idx is None or latest_period is None:
        return months

    # Is the latest month the same as the as_of month AND partial?
    if latest_period.year != as_of_date.year or latest_period.month != as_of_date.month:
        return months

    days_in_month = calendar.monthrange(latest_period.year, latest_period.month)[1]
    days_elapsed = as_of_date.day
    if days_elapsed >= days_in_month:
        return months

    m = months[latest_idx]
    m["is_partial"] = True
    m["days_elapsed"] = days_elapsed
    m["days_in_month"] = days_in_month

    if numeric_fields is None:
        numeric_fields = [
            k for k, v in m.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in (
                "days_elapsed", "days_in_month"
            )
        ]

    for f in numeric_fields:
        val = m.get(f)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            m[f"running_rate_{f}"] = round(
                compute_running_rate(val, days_elapsed, days_in_month), 2
            )

    return months
