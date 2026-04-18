"""Product Analytics — ABC classification and product-channel fit analysis.

Business context: A toy distributor needs to know (1) which products drive revenue
(ABC classification), and (2) which products sell well in which channels
(product-channel fit matrix) to optimize allocation and channel strategy.
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
    """Deduplicate sales by (DocEntry, ItemCode, Period, GroupName)."""
    df = df_sale_prepared.copy()
    df["DocDate"] = pd.to_datetime(df["DocDate"], errors="coerce")
    df = df.dropna(subset=["DocDate"])
    df["Period"] = df["DocDate"].dt.to_period("M").dt.start_time
    return df.drop_duplicates(subset=["DocEntry", "ItemCode", "Period", "GroupName"])


# ---------------------------------------------------------------------------
# F-034: ABC Classification
# ---------------------------------------------------------------------------

def compute_abc_classification(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    year: Optional[int] = None,
    dimension: str = "item",
    a_threshold: float = 80.0,
    b_threshold: float = 95.0,
) -> dict[str, Any]:
    """Classify items or brands into A/B/C tiers by revenue contribution.

    ABC classification is fundamental for inventory management:
    - A items: top products generating ~80% of revenue (~20% of SKUs) — protect and prioritize
    - B items: next ~15% of revenue — manage normally
    - C items: bottom ~5% of revenue — candidates for reduction or liquidation

    Parameters
    ----------
    dimension : "item" or "brand"
        Group sales at item or brand level.
    year : optional int
        Filter to a specific year, or None for all time.
    a_threshold : float
        Cumulative revenue % cutoff for A class (default 80).
    b_threshold : float
        Cumulative revenue % cutoff for B class (default 95). Remainder = C.

    Returns dict with:
        rows: list of dicts with classification details
        summary: counts and revenue by class
        thresholds: {a, b} used
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale)

    if d.empty:
        return {"rows": [], "summary": {}, "thresholds": {"a": a_threshold, "b": b_threshold}, "year": year, "dimension": dimension}

    # Optional year filter
    if year is not None:
        d = d[d["DocDate"].dt.year == int(year)]
        if d.empty:
            return {"rows": [], "summary": {}, "thresholds": {"a": a_threshold, "b": b_threshold}, "year": year, "dimension": dimension}

    # Aggregate by dimension
    if dimension == "brand":
        group_col = "Brand"
        name_col = "Brand"
    else:
        group_col = "ItemCode"
        name_col = "ItemCode"

    agg = d.groupby(group_col, as_index=False).agg(
        revenue_thb=("LineTotal", "sum"),
        sold_qty=("Quantity", "sum"),
        transaction_count=("DocEntry", "nunique"),
    )

    # Add description for items
    if dimension == "item":
        desc_map = d.drop_duplicates("ItemCode").set_index("ItemCode")
        agg["description"] = agg["ItemCode"].map(
            desc_map.get("ItemName", pd.Series(dtype=str))
            if "ItemName" in desc_map.columns
            else pd.Series(dtype=str)
        ).fillna("")
        agg["brand"] = agg["ItemCode"].map(
            desc_map["Brand"] if "Brand" in desc_map.columns else pd.Series(dtype=str)
        ).fillna("Unknown")

    # Sort by revenue descending
    agg = agg.sort_values("revenue_thb", ascending=False).reset_index(drop=True)
    total_revenue = agg["revenue_thb"].sum()

    if total_revenue == 0:
        return {"rows": [], "summary": {}, "thresholds": {"a": a_threshold, "b": b_threshold}, "year": year, "dimension": dimension}

    # Cumulative % and classification
    agg["revenue_pct"] = (agg["revenue_thb"] / total_revenue * 100)
    agg["cumulative_pct"] = agg["revenue_pct"].cumsum()

    def classify(cum_pct, idx):
        if idx == 0 or cum_pct <= a_threshold:
            return "A"
        elif cum_pct <= b_threshold:
            return "B"
        else:
            return "C"

    agg["abc_class"] = [classify(cp, i) for i, cp in enumerate(agg["cumulative_pct"])]

    # On-hand data for items
    oh_by_item = df_onhand.groupby("ItemCode", as_index=False).agg(
        onhand_qty=("OnHand", "sum"),
    )
    oh_by_item["OnHand"] = pd.to_numeric(oh_by_item["onhand_qty"], errors="coerce").fillna(0)

    # Build rows
    rows = []
    for _, r in agg.iterrows():
        row = {
            "rank": len(rows) + 1,
            "abc_class": r["abc_class"],
            "revenue_thb": round(float(r["revenue_thb"]), 2),
            "revenue_pct": round(float(r["revenue_pct"]), 2),
            "cumulative_pct": round(float(r["cumulative_pct"]), 2),
            "sold_qty": int(r["sold_qty"]),
            "transaction_count": int(r["transaction_count"]),
        }
        if dimension == "item":
            row["item_code"] = str(r["ItemCode"])
            row["description"] = str(r.get("description", ""))
            row["brand"] = str(r.get("brand", "Unknown"))
            # Add on-hand info
            oh_match = oh_by_item[oh_by_item["ItemCode"] == r["ItemCode"]]
            row["onhand_qty"] = int(oh_match["OnHand"].sum()) if len(oh_match) > 0 else 0
        else:
            row["brand"] = str(r[group_col])
            # Aggregate on-hand for brand
            brand_items = d[d["Brand"] == r[group_col]]["ItemCode"].unique()
            oh_match = oh_by_item[oh_by_item["ItemCode"].isin(brand_items)]
            row["onhand_qty"] = int(oh_match["OnHand"].sum()) if len(oh_match) > 0 else 0
            row["sku_count"] = int(d[d["Brand"] == r[group_col]]["ItemCode"].nunique())

        rows.append(row)

    # Summary by class
    summary = {}
    for cls in ["A", "B", "C"]:
        cls_rows = [r for r in rows if r["abc_class"] == cls]
        summary[cls] = {
            "count": len(cls_rows),
            "revenue_thb": round(sum(r["revenue_thb"] for r in cls_rows), 2),
            "revenue_pct": round(sum(r["revenue_pct"] for r in cls_rows), 2),
            "sold_qty": sum(r["sold_qty"] for r in cls_rows),
        }

    return {
        "rows": rows,
        "summary": summary,
        "thresholds": {"a": a_threshold, "b": b_threshold},
        "year": year,
        "dimension": dimension,
        "total_revenue_thb": round(float(total_revenue), 2),
        "total_skus": len(rows),
    }


# ---------------------------------------------------------------------------
# F-035: Product-Channel Fit Matrix
# ---------------------------------------------------------------------------

def compute_product_channel_fit(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    year: Optional[int] = None,
    year_list: Optional[list[int]] = None,
    dimension: str = "brand",
    top_n: int = 50,
) -> dict[str, Any]:
    """Build product-channel fit matrix showing what sells where.

    This answers: "For each brand (or item), which channels generate revenue?"
    and "For each channel, which brands are the top sellers?"

    Parameters
    ----------
    dimension : "brand" or "item"
        Group products at brand or item level.
    year : optional int
        Filter to a specific year, or None for all time. Ignored if year_list is set.
    year_list : optional list of int
        Filter to multiple years. Takes precedence over year.
    top_n : int
        Limit to top N products by total revenue.

    Returns dict with:
        matrix: list of dicts, each product with per-channel revenue
        channels: list of channel names (column headers)
        top_per_channel: dict mapping channel -> top 10 products
        summary: overall channel revenue totals
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale)

    # Resolve year filter: year_list takes precedence
    effective_years = year_list if year_list else ([int(year)] if year is not None else None)
    empty_result = {"matrix": [], "channels": [], "top_per_channel": {}, "summary": {}, "year_list": effective_years, "dimension": dimension}

    if d.empty:
        return empty_result

    # Optional year filter
    if effective_years is not None:
        d = d[d["DocDate"].dt.year.isin(effective_years)]
        if d.empty:
            return empty_result

    # GroupName on sale = sales channel
    channel_col = "GroupName"
    channels = sorted(d[channel_col].dropna().unique().tolist())

    if dimension == "item":
        group_col = "ItemCode"
    else:
        group_col = "Brand"

    # Total revenue per product
    product_total = d.groupby(group_col, as_index=False).agg(
        total_revenue=("LineTotal", "sum"),
        total_qty=("Quantity", "sum"),
    ).sort_values("total_revenue", ascending=False).head(top_n)

    top_products = product_total[group_col].tolist()
    d_filtered = d[d[group_col].isin(top_products)]

    # Pivot: product x channel → revenue
    pivot_rev = d_filtered.pivot_table(
        index=group_col,
        columns=channel_col,
        values="LineTotal",
        aggfunc="sum",
        fill_value=0,
    )

    # Pivot: product x channel → quantity
    pivot_qty = d_filtered.pivot_table(
        index=group_col,
        columns=channel_col,
        values="Quantity",
        aggfunc="sum",
        fill_value=0,
    )

    # Build matrix rows
    matrix = []
    for prod in top_products:
        if prod not in pivot_rev.index:
            continue
        prod_match = product_total[product_total[group_col] == prod]
        row = {
            "product": str(prod),
            "total_revenue": round(float(prod_match["total_revenue"].iloc[0]), 2) if not prod_match.empty else 0.0,
            "total_qty": int(prod_match["total_qty"].iloc[0]) if not prod_match.empty else 0,
            "channel_count": 0,
            "channels": {},
        }

        if dimension == "item":
            desc_match = d_filtered[d_filtered["ItemCode"] == prod]
            row["description"] = str(desc_match["ItemName"].iloc[0]) if len(desc_match) > 0 and "ItemName" in desc_match.columns else ""
            row["brand"] = str(desc_match["Brand"].iloc[0]) if len(desc_match) > 0 and "Brand" in desc_match.columns else "Unknown"

        active_channels = 0
        for ch in channels:
            rev = float(pivot_rev.loc[prod, ch]) if ch in pivot_rev.columns else 0
            qty = int(pivot_qty.loc[prod, ch]) if ch in pivot_qty.columns else 0
            if rev > 0:
                active_channels += 1
            row["channels"][ch] = {"revenue": round(rev, 2), "qty": qty}

        row["channel_count"] = active_channels
        matrix.append(row)

    # Top products per channel
    top_per_channel = {}
    for ch in channels:
        ch_data = d_filtered[d_filtered[channel_col] == ch]
        if ch_data.empty:
            top_per_channel[ch] = []
            continue
        ch_agg = ch_data.groupby(group_col, as_index=False).agg(
            revenue=("LineTotal", "sum"),
            qty=("Quantity", "sum"),
        ).sort_values("revenue", ascending=False).head(10)
        top_per_channel[ch] = [
            {"product": str(r[group_col]), "revenue": round(float(r["revenue"]), 2), "qty": int(r["qty"])}
            for _, r in ch_agg.iterrows()
        ]

    # Channel summary
    ch_summary = d.groupby(channel_col, as_index=False).agg(
        revenue=("LineTotal", "sum"),
        qty=("Quantity", "sum"),
        product_count=(group_col, "nunique"),
    ).sort_values("revenue", ascending=False)
    total_rev = ch_summary["revenue"].sum()
    summary = {
        str(r[channel_col]): {
            "revenue": round(float(r["revenue"]), 2),
            "revenue_pct": round(float(r["revenue"]) / total_rev * 100, 2) if total_rev > 0 else 0,
            "qty": int(r["qty"]),
            "product_count": int(r["product_count"]),
        }
        for _, r in ch_summary.iterrows()
    }

    return {
        "matrix": matrix,
        "channels": channels,
        "top_per_channel": top_per_channel,
        "summary": summary,
        "year_list": effective_years,
        "dimension": dimension,
        "total_products": len(matrix),
    }
