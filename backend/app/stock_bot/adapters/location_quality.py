"""Per-location quality metrics — revenue, on-hand, percentile rank.

Builds the inputs the location classifier needs:
  - annual revenue at the location (trailing 12 months)
  - on-hand value at master price
  - percentile rank of the location's revenue against all locations
    (smaller = better; top 10% = 0.0 to 0.10)

We don't reuse ``location_analytics.compute_location_performance()`` directly
because it filters to specific years and applies its own deduplication. The
bot wants the raw "what's this location worth to us" signal across the most
recent year of data.
"""
from __future__ import annotations

import pandas as pd

from app.utils.sales_dedup import dedup_sale_lines


def build_location_quality(
    df_sale_prepared: pd.DataFrame,
    df_onhand_with_state: pd.DataFrame,
    window_days: int = 365,
) -> pd.DataFrame:
    """Per-location revenue + on-hand + percentile rank.

    Args:
        df_sale_prepared: Prepared sale frame with DocDate, WhsCode, LineTotal,
            Quantity. Same input as ``velocity.build_item_location_velocity()``.
        df_onhand_with_state: Output of
            ``stock_state.build_item_location_onhand()`` — has WhsCode and
            on_hand_thb_master per (item, location).
        window_days: Look-back for annual revenue. Default 365.

    Returns:
        DataFrame, one row per WhsCode, with columns:
          WhsCode, annual_revenue_thb, on_hand_thb_master,
          percentile_rank, WhsName.
    """
    if df_sale_prepared.empty:
        rev = pd.DataFrame(columns=["WhsCode", "annual_revenue_thb"])
    else:
        d = df_sale_prepared.copy()
        d["DocDate"] = pd.to_datetime(d["DocDate"], errors="coerce")
        d = d.dropna(subset=["DocDate"])
        d["WhsCode"] = d["WhsCode"].astype(str).str.strip()
        as_of_ts = d["DocDate"].max()
        start = as_of_ts - pd.Timedelta(days=window_days - 1)
        recent = d[(d["DocDate"] >= start) & (d["DocDate"] <= as_of_ts)]

        subset = [
            c for c in ["DocEntry", "ItemCode", "Period", "GroupName", "WhsCode"]
            if c in recent.columns
        ]
        recent = dedup_sale_lines(recent, subset)

        rev = (
            recent.groupby("WhsCode", as_index=False)
            .agg(annual_revenue_thb=("LineTotal", "sum"))
        )
        rev["annual_revenue_thb"] = pd.to_numeric(
            rev["annual_revenue_thb"], errors="coerce"
        ).fillna(0.0)

    if df_onhand_with_state.empty:
        onhand = pd.DataFrame(columns=["WhsCode", "on_hand_thb_master", "WhsName"])
    else:
        onhand = (
            df_onhand_with_state.groupby("WhsCode", as_index=False)
            .agg(
                on_hand_thb_master=("on_hand_thb_master", "sum"),
                WhsName=("WhsName", "first"),
            )
        )

    merged = onhand.merge(rev, on="WhsCode", how="outer")
    merged["annual_revenue_thb"] = pd.to_numeric(
        merged["annual_revenue_thb"], errors="coerce"
    ).fillna(0.0)
    merged["on_hand_thb_master"] = pd.to_numeric(
        merged["on_hand_thb_master"], errors="coerce"
    ).fillna(0.0)
    if "WhsName" not in merged.columns:
        merged["WhsName"] = merged["WhsCode"]
    merged["WhsName"] = merged["WhsName"].fillna(merged["WhsCode"])
    # Catch "nan" strings that survived fillna.
    merged["WhsName"] = merged.apply(
        lambda r: r["WhsCode"] if (
            r["WhsName"] is None
            or str(r["WhsName"]).strip().lower() in ("nan", "")
        ) else r["WhsName"],
        axis=1,
    )

    # Percentile rank: smaller = higher revenue. Top 10% revenue = rank 0.0-0.10.
    # ``pct=True, ascending=False`` returns 0.0 for the largest value, 1.0 for
    # the smallest — exactly the convention classify_location_class expects.
    if len(merged) > 0:
        merged["percentile_rank"] = merged["annual_revenue_thb"].rank(
            pct=True, ascending=False
        )
    else:
        merged["percentile_rank"] = 0.5

    return merged[[
        "WhsCode", "WhsName", "annual_revenue_thb",
        "on_hand_thb_master", "percentile_rank",
    ]]
