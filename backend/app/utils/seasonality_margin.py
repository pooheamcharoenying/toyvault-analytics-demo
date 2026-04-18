"""Seasonality analysis & margin mix/waterfall — monthly patterns, YoY seasonal
comparison, blended margin trends, and brand-level margin contribution.

Business context: A toy distributor needs to know (1) which months are peak vs.
trough for sales — overall and by brand/channel, (2) whether this year is tracking
above or below the historical seasonal pattern, (3) whether overall gross margin
is healthy and which brands are dragging it down or lifting it up.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from app.utils import nichi_stock as nstk


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _channel_dedup_sale(df_sale_prepared: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate sales by (DocEntry, ItemCode, Period, GroupName) using monthly periods."""
    df = df_sale_prepared.copy()
    df["DocDate"] = pd.to_datetime(df["DocDate"], errors="coerce")
    df = df.dropna(subset=["DocDate"])
    df["Period"] = df["DocDate"].dt.to_period("M").dt.start_time
    return df.drop_duplicates(subset=["DocEntry", "ItemCode", "Period", "GroupName"])


def _safe_json(val):
    """Convert numpy/pandas types to Python-native for JSON serialization."""
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    return val


# ---------------------------------------------------------------------------
# 1. Seasonality Analysis
# ---------------------------------------------------------------------------

def compute_seasonality_analysis(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    dimension: str = "overall",
    filter_value: Optional[str] = None,
) -> dict[str, Any]:
    """Analyze monthly sales patterns across years for seasonal insights.

    Args:
        dimension: "overall", "brand", or "channel"
        filter_value: specific brand/channel to filter when dimension is brand/channel

    Returns:
        monthly_patterns: list of {month, month_name, avg_revenue, avg_qty, years_data: [{year, revenue, qty}]}
        yearly_totals: list of {year, total_revenue, total_qty}
        seasonal_index: list of {month, month_name, index} — 100 = average month
        current_vs_pattern: list of {month, month_name, historical_avg, current_year, pct_vs_avg}
        yoy_growth: list of {year, revenue, growth_pct}
        summary: {peak_month, trough_month, seasonality_strength, years_analyzed}
    """
    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale)

    if d.empty:
        return _empty_seasonality()

    # Apply dimension filter
    if dimension == "brand" and filter_value:
        d = d[d["Brand"] == filter_value]
    elif dimension == "channel" and filter_value:
        d = d[d["GroupName"] == filter_value]

    if d.empty:
        return _empty_seasonality()

    d["Year"] = d["DocDate"].dt.year
    d["Month"] = d["DocDate"].dt.month

    # Monthly aggregation by year
    monthly = (
        d.groupby(["Year", "Month"], as_index=False)
        .agg(revenue=("LineTotal", "sum"), qty=("Quantity", "sum"))
    )

    years = sorted(monthly["Year"].unique())
    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    # 1. Monthly patterns with per-year breakdown
    monthly_patterns = []
    for m in range(1, 13):
        month_data = monthly[monthly["Month"] == m]
        years_data = []
        for y in years:
            ym = month_data[month_data["Year"] == y]
            if not ym.empty:
                years_data.append({
                    "year": int(y),
                    "revenue": _safe_json(ym["revenue"].iloc[0]),
                    "qty": _safe_json(ym["qty"].iloc[0]),
                })
        monthly_patterns.append({
            "month": m,
            "month_name": month_names[m - 1],
            "avg_revenue": _safe_json(month_data["revenue"].mean()) if not month_data.empty else 0,
            "avg_qty": _safe_json(month_data["qty"].mean()) if not month_data.empty else 0,
            "years_data": years_data,
        })

    # 2. Yearly totals
    yearly_totals = []
    for y in years:
        yd = monthly[monthly["Year"] == y]
        yearly_totals.append({
            "year": int(y),
            "total_revenue": _safe_json(yd["revenue"].sum()),
            "total_qty": _safe_json(yd["qty"].sum()),
        })

    # 3. Seasonal index (100 = average month)
    avg_monthly_rev = sum(p["avg_revenue"] or 0 for p in monthly_patterns) / 12.0 if monthly_patterns else 1
    seasonal_index = []
    for p in monthly_patterns:
        idx = (p["avg_revenue"] / avg_monthly_rev * 100.0) if avg_monthly_rev > 0 else 0
        seasonal_index.append({
            "month": p["month"],
            "month_name": p["month_name"],
            "index": round(idx, 1),
        })

    # 4. Current year vs. historical average
    current_year = max(years) if years else None
    historical_years = [y for y in years if y != current_year] if current_year else []
    current_vs_pattern = []
    for m in range(1, 13):
        hist = monthly[(monthly["Month"] == m) & (monthly["Year"].isin(historical_years))]
        curr = monthly[(monthly["Month"] == m) & (monthly["Year"] == current_year)]
        hist_avg = float(hist["revenue"].mean()) if not hist.empty else None
        curr_val = float(curr["revenue"].iloc[0]) if not curr.empty else None
        pct = None
        if hist_avg and hist_avg > 0 and curr_val is not None:
            pct = round((curr_val - hist_avg) / hist_avg * 100.0, 1)
        current_vs_pattern.append({
            "month": m,
            "month_name": month_names[m - 1],
            "historical_avg": _safe_json(hist_avg),
            "current_year": _safe_json(curr_val),
            "pct_vs_avg": _safe_json(pct),
        })

    # 5. Year-over-year growth
    yoy_growth = []
    for i, yt in enumerate(yearly_totals):
        growth = None
        if i > 0 and yearly_totals[i - 1]["total_revenue"] and yearly_totals[i - 1]["total_revenue"] > 0:
            growth = round(
                (yt["total_revenue"] - yearly_totals[i - 1]["total_revenue"])
                / yearly_totals[i - 1]["total_revenue"] * 100.0,
                1,
            )
        yoy_growth.append({
            "year": yt["year"],
            "revenue": yt["total_revenue"],
            "growth_pct": _safe_json(growth),
        })

    # 6. Summary
    peak = max(seasonal_index, key=lambda x: x["index"]) if seasonal_index else None
    trough = min(seasonal_index, key=lambda x: x["index"]) if seasonal_index else None
    indices = [s["index"] for s in seasonal_index]
    strength = round(max(indices) - min(indices), 1) if indices else 0

    return {
        "monthly_patterns": monthly_patterns,
        "yearly_totals": yearly_totals,
        "seasonal_index": seasonal_index,
        "current_vs_pattern": current_vs_pattern,
        "yoy_growth": yoy_growth,
        "summary": {
            "peak_month": peak["month_name"] if peak else None,
            "trough_month": trough["month_name"] if trough else None,
            "seasonality_strength": strength,
            "years_analyzed": len(years),
            "current_year": int(current_year) if current_year else None,
        },
    }


def _empty_seasonality():
    return {
        "monthly_patterns": [],
        "yearly_totals": [],
        "seasonal_index": [],
        "current_vs_pattern": [],
        "yoy_growth": [],
        "summary": {
            "peak_month": None,
            "trough_month": None,
            "seasonality_strength": 0,
            "years_analyzed": 0,
            "current_year": None,
        },
    }


# ---------------------------------------------------------------------------
# 2. Margin Mix / Waterfall Analysis
# ---------------------------------------------------------------------------

def compute_margin_mix_analysis(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    year: Optional[int] = None,
    top_n: int = 15,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Blended gross margin trends and brand-level margin contribution analysis.

    Returns:
        margin_trend: list of {period, revenue, fob_cost, gross_margin, margin_pct}
        brand_contributions: list of {brand, revenue, fob_cost, gross_margin, margin_pct, revenue_share_pct, margin_contribution_pct}
        waterfall: list of {brand, margin_contribution_thb, cumulative} — ordered by contribution
        margin_drivers: {positive: [{brand, impact}], negative: [{brand, impact}]} — what lifts/drags margin
        summary: {blended_margin_pct, total_revenue, total_fob_cost, total_gross_margin, brand_count}
    """
    if df_grpo_detail is None or df_grpo_detail.empty:
        return _empty_margin_mix()

    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale)

    if d.empty:
        return _empty_margin_mix()

    # Prepare GRPO data for FOB costs
    g = df_grpo_detail.copy()
    g["DocDate"] = pd.to_datetime(g["DocDate"], errors="coerce")
    g = g.dropna(subset=["DocDate"])

    # Ensure Price and Rate columns exist for FOB calculation
    for col in ["Price", "Rate"]:
        if col not in g.columns:
            g[col] = 0.0
    g["Price"] = pd.to_numeric(g["Price"], errors="coerce").fillna(0)
    g["Rate"] = pd.to_numeric(g["Rate"], errors="coerce").fillna(0)
    g["FOB_THB"] = g["Price"] * g["Rate"]

    # Map brands from item master
    brand_map = df_item_master.set_index("ItemCode")["GroupName"].to_dict() if "GroupName" in df_item_master.columns else {}
    g["Brand"] = g["ItemCode"].map(brand_map).fillna("Unknown")

    # Compute average FOB cost per item (weighted by quantity)
    g["Quantity"] = pd.to_numeric(g.get("Quantity", pd.Series(dtype=float)), errors="coerce").fillna(0)
    g["FOB_Total"] = g["FOB_THB"] * g["Quantity"].abs()

    item_fob = (
        g[g["Quantity"].abs() > 0]
        .groupby("ItemCode", as_index=False)
        .agg(total_fob=("FOB_Total", "sum"), total_qty=("Quantity", lambda x: x.abs().sum()))
    )
    item_fob["avg_fob"] = item_fob["total_fob"] / item_fob["total_qty"]
    fob_map = item_fob.set_index("ItemCode")["avg_fob"].to_dict()

    # Apply FOB to sales
    d["FOB_Unit"] = d["ItemCode"].map(fob_map).fillna(0)
    d["FOB_Total"] = d["FOB_Unit"] * d["Quantity"].abs()

    # GP Commission for consignment sales
    d["GP_Commission_THB"] = nstk.compute_gp_commission(d)

    # Year filter (year_list takes precedence over year)
    d["Year"] = d["DocDate"].dt.year
    _years = year_list if year_list else ([year] if year else None)
    if _years:
        d = d[d["Year"].isin(_years)]

    if d.empty:
        return _empty_margin_mix()

    d["Period"] = d["DocDate"].dt.to_period("M").dt.start_time

    # 1. Margin trend over time
    trend_agg = (
        d.groupby("Period", as_index=False)
        .agg(
            revenue=("LineTotal", "sum"),
            fob_cost=("FOB_Total", "sum"),
            gp_commission=("GP_Commission_THB", "sum"),
        )
        .sort_values("Period")
    )
    # Gross margin = Revenue − FOB Cost − GP Commission
    trend_agg["gross_margin"] = trend_agg["revenue"] - trend_agg["fob_cost"] - trend_agg["gp_commission"]
    trend_agg["margin_pct"] = np.where(
        trend_agg["revenue"] > 0,
        trend_agg["gross_margin"] / trend_agg["revenue"] * 100.0,
        0,
    )
    margin_trend = [
        {
            "period": _safe_json(row["Period"]),
            "revenue": _safe_json(row["revenue"]),
            "fob_cost": _safe_json(row["fob_cost"]),
            "gp_commission": _safe_json(row["gp_commission"]),
            "gross_margin": _safe_json(row["gross_margin"]),
            "margin_pct": round(float(row["margin_pct"]), 1),
        }
        for _, row in trend_agg.iterrows()
    ]

    # 2. Brand contributions
    brand_agg = (
        d.groupby("Brand", as_index=False)
        .agg(
            revenue=("LineTotal", "sum"),
            fob_cost=("FOB_Total", "sum"),
            gp_commission=("GP_Commission_THB", "sum"),
        )
        .sort_values("revenue", ascending=False)
    )
    # Gross margin = Revenue − FOB Cost − GP Commission
    brand_agg["gross_margin"] = brand_agg["revenue"] - brand_agg["fob_cost"] - brand_agg["gp_commission"]
    total_rev = brand_agg["revenue"].sum()
    total_margin = brand_agg["gross_margin"].sum()
    brand_agg["margin_pct"] = np.where(
        brand_agg["revenue"] > 0,
        brand_agg["gross_margin"] / brand_agg["revenue"] * 100.0,
        0,
    )
    brand_agg["revenue_share_pct"] = np.where(
        total_rev > 0,
        brand_agg["revenue"] / total_rev * 100.0,
        0,
    )
    brand_agg["margin_contribution_pct"] = np.where(
        total_margin != 0,
        brand_agg["gross_margin"] / abs(total_margin) * 100.0,
        0,
    )

    brand_contributions = [
        {
            "brand": row["Brand"],
            "revenue": _safe_json(row["revenue"]),
            "fob_cost": _safe_json(row["fob_cost"]),
            "gp_commission": _safe_json(row["gp_commission"]),
            "gross_margin": _safe_json(row["gross_margin"]),
            "margin_pct": round(float(row["margin_pct"]), 1),
            "revenue_share_pct": round(float(row["revenue_share_pct"]), 1),
            "margin_contribution_pct": round(float(row["margin_contribution_pct"]), 1),
        }
        for _, row in brand_agg.head(top_n).iterrows()
    ]

    # 3. Waterfall (ordered by margin contribution, cumulative)
    wf = brand_agg.head(top_n).sort_values("gross_margin", ascending=False).copy()
    waterfall = []
    cumulative = 0
    for _, row in wf.iterrows():
        cumulative += float(row["gross_margin"])
        waterfall.append({
            "brand": row["Brand"],
            "margin_contribution_thb": _safe_json(row["gross_margin"]),
            "cumulative": round(cumulative, 2),
        })

    # 4. Margin drivers — positive and negative contributors
    positive = [
        {"brand": r["Brand"], "impact": _safe_json(r["gross_margin"])}
        for _, r in brand_agg[brand_agg["gross_margin"] > 0]
        .head(10)
        .iterrows()
    ]
    negative = [
        {"brand": r["Brand"], "impact": _safe_json(r["gross_margin"])}
        for _, r in brand_agg[brand_agg["gross_margin"] <= 0]
        .sort_values("gross_margin")
        .head(10)
        .iterrows()
    ]

    # 5. Summary
    total_fob = brand_agg["fob_cost"].sum()
    total_gp = brand_agg["gp_commission"].sum()
    blended_pct = round(float(total_margin / total_rev * 100.0), 1) if total_rev > 0 else 0

    return {
        "margin_trend": margin_trend,
        "brand_contributions": brand_contributions,
        "waterfall": waterfall,
        "margin_drivers": {"positive": positive, "negative": negative},
        "summary": {
            "blended_margin_pct": blended_pct,
            "total_revenue": _safe_json(total_rev),
            "total_fob_cost": _safe_json(total_fob),
            "total_gp_commission": _safe_json(total_gp),
            "total_gross_margin": _safe_json(total_margin),
            "brand_count": len(brand_agg),
        },
    }


def _empty_margin_mix():
    return {
        "margin_trend": [],
        "brand_contributions": [],
        "waterfall": [],
        "margin_drivers": {"positive": [], "negative": []},
        "summary": {
            "blended_margin_pct": 0,
            "total_revenue": 0,
            "total_fob_cost": 0,
            "total_gross_margin": 0,
            "brand_count": 0,
        },
    }
