"""Per-(item × location) sales velocity over a trailing window.

Distinct from ``inventory_alerts._build_item_velocity()``, which is global per
item. The bot needs per-location velocity because shelf cap depends on what
each specific store actually sells, not the SKU's company-wide average.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.utils.sales_dedup import dedup_sale_lines


def build_item_location_velocity(
    df_sale_prepared: pd.DataFrame,
    window_days: int = 90,
    as_of: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Aggregate sales by (ItemCode, WhsCode) over a trailing window.

    Args:
        df_sale_prepared: Output of ``nichi_stock.prepare_sales_and_onhand_data``
            (the first frame in the tuple) — has DocDate, ItemCode, WhsCode,
            Quantity, LineTotal, with Period column.
        window_days: Look-back window. Default 90 (~3 months).
        as_of: Anchor date. Defaults to the latest DocDate in the data.

    Returns:
        DataFrame with one row per (ItemCode, WhsCode) and columns:
          - sold_qty: total units sold in window
          - sold_thb: revenue in window (actual sales price)
          - avg_daily_qty: sold_qty / window_days
          - monthly_velocity: sold_qty / (window_days / 30.0)
          - velocity_basis: "observed" if the location had this SKU in stock
            recently, "no_history" otherwise (caller decides how to handle).
    """
    if df_sale_prepared.empty or "DocDate" not in df_sale_prepared.columns:
        return pd.DataFrame(columns=[
            "ItemCode", "WhsCode", "sold_qty", "sold_thb",
            "avg_daily_qty", "monthly_velocity", "velocity_basis",
        ])

    d = df_sale_prepared.copy()
    d["DocDate"] = pd.to_datetime(d["DocDate"], errors="coerce")
    d = d.dropna(subset=["DocDate"])
    d["WhsCode"] = d["WhsCode"].astype(str).str.strip()

    if as_of is None:
        as_of_ts = d["DocDate"].max()
    else:
        as_of_ts = pd.to_datetime(as_of)
    start = as_of_ts - pd.Timedelta(days=window_days - 1)

    recent = d[(d["DocDate"] >= start) & (d["DocDate"] <= as_of_ts)]

    # Deduplicate by (DocEntry, ItemCode, Period, GroupName, WhsCode) — same
    # convention as stock_allocation._channel_dedup_sale to avoid double-counting
    # consignment settlement docs.
    subset = [
        c for c in ["DocEntry", "ItemCode", "Period", "GroupName", "WhsCode"]
        if c in recent.columns
    ]
    recent = dedup_sale_lines(recent, subset)

    agg = (
        recent.groupby(["ItemCode", "WhsCode"], as_index=False)
        .agg(sold_qty=("Quantity", "sum"), sold_thb=("LineTotal", "sum"))
    )
    agg["sold_qty"] = pd.to_numeric(agg["sold_qty"], errors="coerce").fillna(0.0)
    agg["sold_thb"] = pd.to_numeric(agg["sold_thb"], errors="coerce").fillna(0.0)
    agg["avg_daily_qty"] = agg["sold_qty"] / float(window_days)
    agg["monthly_velocity"] = agg["sold_qty"] / (float(window_days) / 30.0)
    agg["velocity_basis"] = "observed"

    return agg


def build_item_location_lifetime_sales(
    df_sale_prepared: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate ALL-TIME sales by (ItemCode, WhsCode) — no window filter.

    Same dedup convention as :func:`build_item_location_velocity` so the
    numbers reconcile with the windowed velocity. Used by the UI to show
    "lifetime sold at this location" on every transfer row, which is the
    long-run product-market-fit signal a manager wants alongside the
    short-window velocity.

    Returns:
        DataFrame indexed by (ItemCode, WhsCode) with:
          - sold_qty_lifetime: total units sold all-time at this location
          - sold_thb_lifetime: total revenue all-time at this location
    """
    if df_sale_prepared.empty or "DocDate" not in df_sale_prepared.columns:
        return pd.DataFrame(columns=[
            "ItemCode", "WhsCode", "sold_qty_lifetime", "sold_thb_lifetime",
        ])

    d = df_sale_prepared.copy()
    d["WhsCode"] = d["WhsCode"].astype(str).str.strip()

    subset = [
        c for c in ["DocEntry", "ItemCode", "Period", "GroupName", "WhsCode"]
        if c in d.columns
    ]
    d = dedup_sale_lines(d, subset)

    agg = (
        d.groupby(["ItemCode", "WhsCode"], as_index=False)
        .agg(
            sold_qty_lifetime=("Quantity", "sum"),
            sold_thb_lifetime=("LineTotal", "sum"),
        )
    )
    agg["sold_qty_lifetime"] = pd.to_numeric(
        agg["sold_qty_lifetime"], errors="coerce"
    ).fillna(0.0)
    agg["sold_thb_lifetime"] = pd.to_numeric(
        agg["sold_thb_lifetime"], errors="coerce"
    ).fillna(0.0)
    return agg
