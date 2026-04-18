"""Purchase Cost Tracking & Vendor Analysis — FOB trends, purchase vs. sold, working capital.

Business context: A toy distributor needs to know (1) are purchase costs going up or down?
(2) are we buying more than we sell for any brand? (3) how much cash is tied up in
inventory and is it growing? These functions turn GRPO purchase data + sales + on-hand
into actionable procurement and working-capital insights.
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


# ---------------------------------------------------------------------------
# 1. Purchase Cost Trends
# ---------------------------------------------------------------------------

def compute_purchase_cost_trends(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    brand: Optional[str] = None,
    year: Optional[int] = None,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """FOB cost per unit over time by brand, with currency impact analysis.

    Returns:
        brand_trends: list of {brand, periods: [{period, avg_fob_thb, total_qty, total_fob_thb, currency_mix}]}
        overall_trend: list of {period, avg_fob_thb, total_qty, total_fob_thb}
        currency_impact: list of {currency, total_qty, avg_rate, total_fob_thb, share_pct}
        summary: {total_purchased_thb, unique_brands, unique_items, period_count}
    """
    if df_grpo_detail is None or df_grpo_detail.empty:
        return {
            "brand_trends": [],
            "overall_trend": [],
            "currency_impact": [],
            "summary": {"total_purchased_thb": 0, "unique_brands": 0, "unique_items": 0, "period_count": 0},
        }

    g = df_grpo_detail.copy()
    g["DocDate"] = pd.to_datetime(g["DocDate"], errors="coerce")
    g = g.dropna(subset=["DocDate"])
    g["Price"] = pd.to_numeric(g["Price"], errors="coerce").fillna(0)
    g["Rate"] = pd.to_numeric(g["Rate"], errors="coerce").fillna(0)
    g["Quantity"] = pd.to_numeric(g["Quantity"], errors="coerce").fillna(0)
    g = g[g["Quantity"] > 0].copy()
    g["FOB_THB_Unit"] = g["Price"] * g["Rate"]
    g["FOB_THB_Total"] = g["FOB_THB_Unit"] * g["Quantity"]
    g["Period"] = g["DocDate"].dt.to_period("M").dt.start_time

    # Map brand from Item Master
    brand_map = df_item_master.drop_duplicates(subset=["ItemCode"]).set_index("ItemCode")["GroupName"]
    g["Brand"] = g["ItemCode"].map(brand_map).fillna("Unknown")

    _years = year_list if year_list else ([year] if year is not None else None)
    if _years:
        g = g[g["DocDate"].dt.year.isin(_years)].copy()
    if brand is not None:
        g = g[g["Brand"] == brand].copy()

    if g.empty:
        return {
            "brand_trends": [],
            "overall_trend": [],
            "currency_impact": [],
            "summary": {"total_purchased_thb": 0, "unique_brands": 0, "unique_items": 0, "period_count": 0},
        }

    # --- Overall trend (monthly) ---
    overall = (
        g.groupby("Period", as_index=False)
        .agg(total_qty=("Quantity", "sum"), total_fob_thb=("FOB_THB_Total", "sum"))
    )
    overall["avg_fob_thb"] = overall["total_fob_thb"] / overall["total_qty"].replace(0, np.nan)
    overall = overall.sort_values("Period")
    overall_trend = [
        {
            "period": str(r["Period"].date()),
            "avg_fob_thb": round(float(r["avg_fob_thb"]), 2) if pd.notna(r["avg_fob_thb"]) else 0,
            "total_qty": int(r["total_qty"]),
            "total_fob_thb": round(float(r["total_fob_thb"]), 2),
        }
        for _, r in overall.iterrows()
    ]

    # --- Brand trends (monthly per brand, top 20 brands by total spend) ---
    brand_totals = g.groupby("Brand")["FOB_THB_Total"].sum().sort_values(ascending=False)
    top_brands = brand_totals.head(20).index.tolist()
    brand_trends = []
    for b in top_brands:
        bg = g[g["Brand"] == b]
        bperiods = (
            bg.groupby("Period", as_index=False)
            .agg(total_qty=("Quantity", "sum"), total_fob_thb=("FOB_THB_Total", "sum"))
        )
        bperiods["avg_fob_thb"] = bperiods["total_fob_thb"] / bperiods["total_qty"].replace(0, np.nan)
        bperiods = bperiods.sort_values("Period")
        periods_list = [
            {
                "period": str(r["Period"].date()),
                "avg_fob_thb": round(float(r["avg_fob_thb"]), 2) if pd.notna(r["avg_fob_thb"]) else 0,
                "total_qty": int(r["total_qty"]),
                "total_fob_thb": round(float(r["total_fob_thb"]), 2),
            }
            for _, r in bperiods.iterrows()
        ]
        brand_trends.append({
            "brand": str(b),
            "total_spend_thb": round(float(brand_totals[b]), 2),
            "periods": periods_list,
        })

    # --- Currency impact ---
    if "Currency" in g.columns:
        curr = g.groupby("Currency", as_index=False).agg(
            total_qty=("Quantity", "sum"),
            avg_rate=("Rate", "mean"),
            total_fob_thb=("FOB_THB_Total", "sum"),
        )
        grand = curr["total_fob_thb"].sum()
        curr["share_pct"] = (curr["total_fob_thb"] / grand * 100) if grand > 0 else 0
        currency_impact = [
            {
                "currency": str(r["Currency"]),
                "total_qty": int(r["total_qty"]),
                "avg_rate": round(float(r["avg_rate"]), 4),
                "total_fob_thb": round(float(r["total_fob_thb"]), 2),
                "share_pct": round(float(r["share_pct"]), 1),
            }
            for _, r in curr.sort_values("total_fob_thb", ascending=False).iterrows()
        ]
    else:
        currency_impact = []

    summary = {
        "total_purchased_thb": round(float(g["FOB_THB_Total"].sum()), 2),
        "unique_brands": int(g["Brand"].nunique()),
        "unique_items": int(g["ItemCode"].nunique()),
        "period_count": int(g["Period"].nunique()),
    }

    return {
        "brand_trends": brand_trends,
        "overall_trend": overall_trend,
        "currency_impact": currency_impact,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 2. Purchase vs. Sold Analysis
# ---------------------------------------------------------------------------

def compute_purchase_vs_sold(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    year: Optional[int] = None,
    top_n: int = 30,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Compare purchased qty/THB vs. sold qty/THB by brand.

    Identifies brands where we buy more than we sell (inventory build-up risk)
    and brands where we sell more than we buy (potential stockout risk).

    Returns:
        brands: list of {brand, purchased_qty, purchased_thb, sold_qty, sold_thb,
                         purchase_sold_ratio, inventory_build_up, onhand_qty, onhand_thb}
        summary: {total_purchased_thb, total_sold_thb, overall_ratio, build_up_brands, draw_down_brands}
    """
    # --- Sold side ---
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale)
    _years = year_list if year_list else ([year] if year is not None else None)
    if _years:
        d = d[d["DocDate"].dt.year.isin(_years)].copy()
    d["Quantity"] = pd.to_numeric(d["Quantity"], errors="coerce").fillna(0)
    d["LineTotal"] = pd.to_numeric(d["LineTotal"], errors="coerce").fillna(0)
    d["Brand"] = d["Brand"].fillna("Unknown")

    sold_agg = d.groupby("Brand", as_index=False).agg(
        sold_qty=("Quantity", "sum"),
        sold_thb=("LineTotal", "sum"),
    )

    # --- Purchased side ---
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        g = df_grpo_detail.copy()
        g["DocDate"] = pd.to_datetime(g["DocDate"], errors="coerce")
        g = g.dropna(subset=["DocDate"])
        g["Price"] = pd.to_numeric(g["Price"], errors="coerce").fillna(0)
        g["Rate"] = pd.to_numeric(g["Rate"], errors="coerce").fillna(0)
        g["Quantity"] = pd.to_numeric(g["Quantity"], errors="coerce").fillna(0)
        g = g[g["Quantity"] > 0].copy()
        g["FOB_THB_Total"] = g["Price"] * g["Rate"] * g["Quantity"]

        brand_map = df_item_master.drop_duplicates(subset=["ItemCode"]).set_index("ItemCode")["GroupName"]
        g["Brand"] = g["ItemCode"].map(brand_map).fillna("Unknown")

        if _years:
            g = g[g["DocDate"].dt.year.isin(_years)].copy()

        purch_agg = g.groupby("Brand", as_index=False).agg(
            purchased_qty=("Quantity", "sum"),
            purchased_thb=("FOB_THB_Total", "sum"),
        )
    else:
        purch_agg = pd.DataFrame(columns=["Brand", "purchased_qty", "purchased_thb"])

    # --- On-hand side ---
    oh = df_onhand.copy()
    oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0)
    oh["Master Price"] = pd.to_numeric(oh.get("Master Price", pd.Series(dtype=float)), errors="coerce").fillna(0)
    oh["onhand_thb"] = oh["OnHand"] * oh["Master Price"]
    oh["Brand"] = oh.get("Brand", pd.Series(dtype=str))
    if "Brand" not in oh.columns or oh["Brand"].isna().all():
        oh["Brand"] = "Unknown"
    oh["Brand"] = oh["Brand"].fillna("Unknown")
    oh_agg = oh.groupby("Brand", as_index=False).agg(
        onhand_qty=("OnHand", "sum"),
        onhand_thb=("onhand_thb", "sum"),
    )

    # --- Merge ---
    merged = sold_agg.merge(purch_agg, on="Brand", how="outer").merge(oh_agg, on="Brand", how="outer")
    for col in ["sold_qty", "sold_thb", "purchased_qty", "purchased_thb", "onhand_qty", "onhand_thb"]:
        merged[col] = merged[col].fillna(0)

    # Purchase/Sold ratio: >1 means buying more than selling
    merged["purchase_sold_ratio"] = merged.apply(
        lambda r: round(float(r["purchased_thb"]) / float(r["sold_thb"]), 2)
        if float(r["sold_thb"]) > 0 else (float("inf") if float(r["purchased_thb"]) > 0 else 0),
        axis=1,
    )
    merged["inventory_build_up"] = merged["purchased_thb"] > merged["sold_thb"]

    # Sort by total activity (purchased + sold), top N
    merged["total_activity"] = merged["purchased_thb"] + merged["sold_thb"]
    merged = merged.sort_values("total_activity", ascending=False).head(top_n)

    brands = []
    for _, r in merged.iterrows():
        brands.append({
            "brand": str(r["Brand"]),
            "purchased_qty": int(r["purchased_qty"]),
            "purchased_thb": round(float(r["purchased_thb"]), 2),
            "sold_qty": int(r["sold_qty"]),
            "sold_thb": round(float(r["sold_thb"]), 2),
            "purchase_sold_ratio": float(r["purchase_sold_ratio"]) if not np.isinf(r["purchase_sold_ratio"]) else None,
            "inventory_build_up": bool(r["inventory_build_up"]),
            "onhand_qty": int(r["onhand_qty"]),
            "onhand_thb": round(float(r["onhand_thb"]), 2),
        })

    total_purchased = float(merged["purchased_thb"].sum())
    total_sold = float(merged["sold_thb"].sum())
    overall_ratio = round(total_purchased / total_sold, 2) if total_sold > 0 else None

    summary = {
        "total_purchased_thb": round(total_purchased, 2),
        "total_sold_thb": round(total_sold, 2),
        "overall_ratio": overall_ratio,
        "build_up_brands": int(merged["inventory_build_up"].sum()),
        "draw_down_brands": int((~merged["inventory_build_up"]).sum()),
    }

    return {"brands": brands, "summary": summary}


# ---------------------------------------------------------------------------
# 3. Working Capital & Inventory Efficiency Trends
# ---------------------------------------------------------------------------

def compute_working_capital_trends(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    df_tr_in: Optional[pd.DataFrame] = None,
    df_tr_out: Optional[pd.DataFrame] = None,
    file_date: Optional[Any] = None,
    window_months: int = 12,
) -> dict[str, Any]:
    """Working capital (inventory value) and efficiency metrics trending over time.

    Uses historical on-hand reconstruction to show inventory value over time,
    and compares to monthly revenue to compute turnover and stock-to-sales ratio.

    Returns:
        monthly_trends: list of {period, onhand_thb, revenue_thb, stock_to_sales,
                                 turnover_rate, avg_days_cover}
        summary: {current_onhand_thb, current_revenue_monthly, current_turnover,
                  trend_direction, months_analyzed}
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale)

    if d.empty:
        return {
            "monthly_trends": [],
            "summary": {
                "current_onhand_thb": 0, "current_revenue_monthly": 0,
                "current_turnover": 0, "trend_direction": "flat", "months_analyzed": 0,
            },
        }

    # Monthly revenue
    d["Quantity"] = pd.to_numeric(d["Quantity"], errors="coerce").fillna(0)
    d["LineTotal"] = pd.to_numeric(d["LineTotal"], errors="coerce").fillna(0)
    rev_monthly = d.groupby("Period", as_index=False).agg(
        revenue_thb=("LineTotal", "sum"),
        sold_qty=("Quantity", "sum"),
    ).sort_values("Period")

    # Limit to last N months
    if len(rev_monthly) > window_months:
        rev_monthly = rev_monthly.tail(window_months).copy()

    # Current on-hand value
    oh = df_onhand.copy()
    oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0)
    oh["Master Price"] = pd.to_numeric(oh.get("Master Price", pd.Series(dtype=float)), errors="coerce").fillna(0)
    current_onhand_thb = float((oh["OnHand"] * oh["Master Price"]).sum())

    # Try historical on-hand reconstruction for trend
    try:
        from app.utils.inventory_engine import compute_historical_onhand_org
        # Determine file_date: use parameter, or infer from latest sale date
        from datetime import date as _date_type
        if file_date is not None:
            fd = file_date if isinstance(file_date, _date_type) else pd.Timestamp(file_date).date()
        else:
            # Fallback: use the latest DocDate in sales as proxy for snapshot date
            fd = d["DocDate"].max().date() if not d.empty else pd.Timestamp.now().date()
        hist_oh = compute_historical_onhand_org(
            df_raw_onhand=df_raw_onhand,
            df_raw_sale=df_raw_sale,
            df_grpo_detail=df_grpo_detail,
            df_tr_in=df_tr_in,
            df_tr_out=df_tr_out,
            file_date=fd,
            period_type="monthly",
        )
        # hist_oh: rows=ItemCode, cols like "2024-01-01_OnHand_QTY", values=on-hand qty
        # Multiply by master price to get THB value per period
        price_map = df_item_master.drop_duplicates(subset=["ItemCode"]).set_index("ItemCode")["Price"]
        price_map = pd.to_numeric(price_map, errors="coerce").fillna(0)

        # Normalize index of hist_oh so ItemCode lookup matches price_map
        price_map_str = price_map.copy()
        price_map_str.index = price_map_str.index.astype(str).str.strip()
        hist_oh_idx_str = hist_oh.index.astype(str).str.strip()

        # Prices aligned with hist_oh rows (falls back to 0 for unknown items)
        aligned_prices = pd.Series(
            hist_oh_idx_str.map(price_map_str).values,
            index=hist_oh.index,
        ).fillna(0.0)

        # Key by "YYYY-MM-DD" string on BOTH sides to avoid Timestamp/datetime64
        # hashing inconsistencies that caused the Working Capital tab to fall
        # back to the current snapshot every month.
        oh_thb_by_period: dict[str, float] = {}
        for col in hist_oh.columns:
            col_str = str(col)
            if "_OnHand_QTY" in col_str:
                period_key = col_str.replace("_OnHand_QTY", "")  # e.g. "2025-01-01"
                qty = hist_oh[col].fillna(0).clip(lower=0)  # floor at 0
                oh_thb_by_period[period_key] = float((qty * aligned_prices).sum())
        has_historical = len(oh_thb_by_period) > 0
    except Exception:
        has_historical = False
        oh_thb_by_period = {}

    # Build monthly trend rows
    monthly_trends = []
    for _, r in rev_monthly.iterrows():
        period = r["Period"]
        rev = float(r["revenue_thb"])

        # Normalize Period to "YYYY-MM-DD" string for dict lookup
        try:
            period_key = pd.Timestamp(period).strftime("%Y-%m-%d")
        except Exception:
            period_key = str(period)

        # Get on-hand THB for this period
        if has_historical and period_key in oh_thb_by_period:
            oh_val = oh_thb_by_period[period_key]
        else:
            oh_val = current_onhand_thb  # fallback: use current snapshot

        stock_to_sales = round(oh_val / rev, 2) if rev > 0 else None
        # Annualized turnover: (monthly revenue * 12) / on-hand value
        turnover = round((rev * 12) / oh_val, 2) if oh_val > 0 else None

        monthly_trends.append({
            "period": str(period.date()) if hasattr(period, "date") else str(period),
            "onhand_thb": round(oh_val, 2),
            "revenue_thb": round(rev, 2),
            "stock_to_sales": stock_to_sales,
            "turnover_rate": turnover,
        })

    # Summary
    if len(monthly_trends) >= 2:
        first_rev = monthly_trends[0]["revenue_thb"]
        last_rev = monthly_trends[-1]["revenue_thb"]
        if first_rev > 0 and last_rev > first_rev:
            trend_dir = "improving"
        elif first_rev > 0 and last_rev < first_rev:
            trend_dir = "declining"
        else:
            trend_dir = "flat"
    else:
        trend_dir = "flat"

    latest_rev = monthly_trends[-1]["revenue_thb"] if monthly_trends else 0
    current_turnover = round((latest_rev * 12) / current_onhand_thb, 2) if current_onhand_thb > 0 else 0

    summary = {
        "current_onhand_thb": round(current_onhand_thb, 2),
        "current_revenue_monthly": round(latest_rev, 2),
        "current_turnover": current_turnover,
        "trend_direction": trend_dir,
        "months_analyzed": len(monthly_trends),
    }

    return {"monthly_trends": monthly_trends, "summary": summary}
