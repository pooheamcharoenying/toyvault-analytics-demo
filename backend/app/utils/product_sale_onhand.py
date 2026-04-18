"""
Product Sale Vs. OnHand analytics.

Two features:
1. generate_product_sale_vs_onhand(): Item × Month table with Sold_QTY, Sold_THB, OnHand_QTY, Sale_Ratio
2. generate_product_sale_vs_onhand_locations(): Same but with per-location breakdown

See CLAUDE_ADDITIONS.md §B.2 and §B.3 for specifications.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from app.utils import nichi_stock as nstk
from app.utils.inventory_engine import compute_historical_onhand, compute_historical_onhand_org


def generate_product_sale_vs_onhand(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame],
    df_tr_in: Optional[pd.DataFrame],
    df_tr_out: Optional[pd.DataFrame],
    brand_name: str,
    file_date: date,
    period_type: str = "monthly",
    year_list: Optional[list[int]] = None,
) -> pd.DataFrame:
    """
    B.2: Product Sale Vs. OnHand — Item × Month table.

    Rows: Product items belonging to `brand_name`
    Columns per month: Sold_QTY, Sold_THB, OnHand_QTY, Sale_Ratio
    Plus a Total row.

    OnHand_QTY is org-wide (summed across all locations) since this view
    doesn't break down by location.
    """
    # --- Prepare sales with brand fill ---
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )

    # --- Filter to brand ---
    df_sale["Brand"] = df_sale["Brand"].fillna("Unknown")
    brand_sale = df_sale[df_sale["Brand"] == brand_name].copy()

    if brand_sale.empty:
        return pd.DataFrame()

    # --- Period assignment ---
    brand_sale["DocDate"] = pd.to_datetime(brand_sale["DocDate"], errors="coerce")
    brand_sale = brand_sale.dropna(subset=["DocDate"])

    if period_type == "monthly":
        brand_sale["Period"] = brand_sale["DocDate"].dt.to_period("M").dt.start_time
    else:
        brand_sale["Period"] = brand_sale["DocDate"].dt.to_period("W-MON").dt.start_time

    # --- Year filter ---
    if year_list:
        brand_sale = brand_sale[brand_sale["DocDate"].dt.year.isin(year_list)].copy()

    if brand_sale.empty:
        return pd.DataFrame()

    # --- Dedup (same as channel matrix: DocEntry + ItemCode + Period + GroupName) ---
    brand_sale = brand_sale.drop_duplicates(
        subset=["DocEntry", "ItemCode", "Period", "GroupName"]
    )

    # --- Aggregate sales by Item × Period ---
    sale_agg = (
        brand_sale.groupby(["ItemCode", "Period"], as_index=False)
        .agg(Sold_QTY=("Quantity", "sum"), Sold_THB=("LineTotal", "sum"))
    )

    # --- Get item descriptions ---
    item_desc = (
        brand_sale[["ItemCode", "ItemName"]]
        .drop_duplicates(subset=["ItemCode"])
        .set_index("ItemCode")["ItemName"]
        .to_dict()
    )

    # --- Get historical on-hand (org-wide) ---
    hist_oh = compute_historical_onhand_org(
        df_raw_onhand, df_raw_sale, df_grpo_detail,
        df_tr_in, df_tr_out, file_date, period_type,
    )

    # --- Build output table ---
    items = sorted(sale_agg["ItemCode"].unique())
    periods = sorted(sale_agg["Period"].unique())

    # Create pivot for sales
    qty_pivot = sale_agg.pivot(index="ItemCode", columns="Period", values="Sold_QTY").fillna(0)
    thb_pivot = sale_agg.pivot(index="ItemCode", columns="Period", values="Sold_THB").fillna(0)

    # Build final columns
    final_data = {"ItemName": pd.Series({item: item_desc.get(item, "") for item in items})}

    for period in periods:
        key = period.strftime("%Y-%m-%d")

        sold_qty = qty_pivot[period] if period in qty_pivot.columns else pd.Series(0, index=items)
        sold_thb = thb_pivot[period] if period in thb_pivot.columns else pd.Series(0, index=items)

        # Get on-hand for each item from reconstruction
        oh_col = f"{key}_OnHand_QTY"
        oh_values = {}
        for item in items:
            if not hist_oh.empty and item in hist_oh.index and oh_col in hist_oh.columns:
                oh_values[item] = float(hist_oh.loc[item, oh_col])
            else:
                oh_values[item] = 0.0

        oh_series = pd.Series(oh_values)

        # Sale ratio = Sold_QTY / OnHand_QTY
        ratio = pd.Series(index=items, dtype=float)
        for item in items:
            sq = float(sold_qty.get(item, 0))
            oq = oh_series.get(item, 0)
            if oq > 0:
                ratio[item] = sq / oq
            elif sq > 0:
                ratio[item] = float("inf")
            else:
                ratio[item] = 0.0

        final_data[f"{key}_Sold_QTY"] = sold_qty
        final_data[f"{key}_Sold_THB"] = sold_thb
        final_data[f"{key}_OnHand_QTY"] = oh_series
        final_data[f"{key}_Sale_Ratio"] = ratio

    final_df = pd.DataFrame(final_data, index=items)
    final_df.index.name = "ItemCode"

    # Sort columns: ItemName first, then by period
    metric_order = {"Sold_QTY": 0, "Sold_THB": 1, "OnHand_QTY": 2, "Sale_Ratio": 3}
    other_cols = [c for c in final_df.columns if c != "ItemName"]

    def sort_key(col_name: str):
        parts = col_name.split("_", 1)
        if len(parts) == 2:
            return (parts[0], metric_order.get(parts[1], 99))
        return (col_name, 99)

    sorted_cols = ["ItemName"] + sorted(other_cols, key=sort_key)
    final_df = final_df[sorted_cols]

    # --- Total row ---
    total_row = final_df.select_dtypes(include=[np.number]).sum()
    total_row["ItemName"] = "Total"
    # Recalculate ratio for total row
    for period in periods:
        key = period.strftime("%Y-%m-%d")
        total_sold = total_row.get(f"{key}_Sold_QTY", 0)
        total_oh = total_row.get(f"{key}_OnHand_QTY", 0)
        if total_oh > 0:
            total_row[f"{key}_Sale_Ratio"] = total_sold / total_oh
        elif total_sold > 0:
            total_row[f"{key}_Sale_Ratio"] = float("inf")
        else:
            total_row[f"{key}_Sale_Ratio"] = 0.0

    total_row.name = "Total"
    final_df = pd.concat([final_df, total_row.to_frame().T])

    return final_df


def generate_product_sale_vs_onhand_locations(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame],
    df_tr_in: Optional[pd.DataFrame],
    df_tr_out: Optional[pd.DataFrame],
    df_whs_code: pd.DataFrame,
    brand_name: str,
    file_date: date,
    period_type: str = "monthly",
    year_list: Optional[list[int]] = None,
) -> pd.DataFrame:
    """
    B.3: Product Sale Vs. OnHand by Locations.

    Same as B.2 but each month group has:
    1. Summary (Total_Sold_QTY, Total_Sold_THB, Total_OnHand_QTY, Total_Sale_Ratio)
    2. Per-location breakdown (Sold_QTY, Sold_THB, OnHand_QTY, Sale_Ratio per WhsName)
    """
    # --- Prepare sales with brand fill ---
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )

    # --- Build WhsCode → WhsName mapping ---
    whs_map = df_whs_code.set_index("WhsCode")["WhsName"].to_dict()

    # --- Filter to brand ---
    df_sale["Brand"] = df_sale["Brand"].fillna("Unknown")
    brand_sale = df_sale[df_sale["Brand"] == brand_name].copy()

    if brand_sale.empty:
        return pd.DataFrame()

    # --- Period assignment ---
    brand_sale["DocDate"] = pd.to_datetime(brand_sale["DocDate"], errors="coerce")
    brand_sale = brand_sale.dropna(subset=["DocDate"])

    if period_type == "monthly":
        brand_sale["Period"] = brand_sale["DocDate"].dt.to_period("M").dt.start_time
    else:
        brand_sale["Period"] = brand_sale["DocDate"].dt.to_period("W-MON").dt.start_time

    if year_list:
        brand_sale = brand_sale[brand_sale["DocDate"].dt.year.isin(year_list)].copy()

    if brand_sale.empty:
        return pd.DataFrame()

    # Dedup
    brand_sale = brand_sale.drop_duplicates(
        subset=["DocEntry", "ItemCode", "Period", "GroupName"]
    )

    # --- Aggregate sales by Item × WhsCode × Period ---
    sale_loc_agg = (
        brand_sale.groupby(["ItemCode", "WhsCode", "Period"], as_index=False)
        .agg(Sold_QTY=("Quantity", "sum"), Sold_THB=("LineTotal", "sum"))
    )

    # Also aggregate at item × period for summary
    sale_total_agg = (
        brand_sale.groupby(["ItemCode", "Period"], as_index=False)
        .agg(Sold_QTY=("Quantity", "sum"), Sold_THB=("LineTotal", "sum"))
    )

    # --- Item descriptions ---
    item_desc = (
        brand_sale[["ItemCode", "ItemName"]]
        .drop_duplicates(subset=["ItemCode"])
        .set_index("ItemCode")["ItemName"]
        .to_dict()
    )

    # --- Historical on-hand at item × location level ---
    hist_oh = compute_historical_onhand(
        df_raw_onhand, df_raw_sale, df_grpo_detail,
        df_tr_in, df_tr_out, file_date, period_type,
    )

    # --- Determine dimensions ---
    items = sorted(sale_loc_agg["ItemCode"].unique())
    periods = sorted(sale_loc_agg["Period"].unique())
    # Locations that have any activity for this brand
    active_whs = sorted(sale_loc_agg["WhsCode"].unique())

    # --- Build output table ---
    final_data = {"ItemName": pd.Series({item: item_desc.get(item, "") for item in items})}

    for period in periods:
        key = period.strftime("%Y-%m-%d")
        oh_col = f"{key}_OnHand_QTY"

        # --- Summary columns (all locations combined) ---
        total_slice = sale_total_agg[sale_total_agg["Period"] == period].set_index("ItemCode")
        summary_sold_qty = total_slice["Sold_QTY"].reindex(items, fill_value=0)
        summary_sold_thb = total_slice["Sold_THB"].reindex(items, fill_value=0)

        # Org-wide on-hand per item
        summary_oh = pd.Series(0.0, index=items)
        for item in items:
            if not hist_oh.empty and oh_col in hist_oh.columns:
                # Sum across all locations for this item
                try:
                    summary_oh[item] = float(hist_oh.xs(item, level="ItemCode")[oh_col].sum())
                except KeyError:
                    pass

        summary_ratio = _compute_ratio_series(summary_sold_qty, summary_oh, items)

        final_data[f"{key}_Total_Sold_QTY"] = summary_sold_qty
        final_data[f"{key}_Total_Sold_THB"] = summary_sold_thb
        final_data[f"{key}_Total_OnHand_QTY"] = summary_oh
        final_data[f"{key}_Total_Sale_Ratio"] = summary_ratio

        # --- Per-location columns ---
        loc_slice = sale_loc_agg[sale_loc_agg["Period"] == period]

        for wh in active_whs:
            wh_name = whs_map.get(wh, wh)
            wh_data = loc_slice[loc_slice["WhsCode"] == wh].set_index("ItemCode")

            loc_sold_qty = wh_data["Sold_QTY"].reindex(items, fill_value=0) if not wh_data.empty else pd.Series(0.0, index=items)
            loc_sold_thb = wh_data["Sold_THB"].reindex(items, fill_value=0) if not wh_data.empty else pd.Series(0.0, index=items)

            # Per-location on-hand
            loc_oh = pd.Series(0.0, index=items)
            for item in items:
                if not hist_oh.empty and oh_col in hist_oh.columns:
                    try:
                        loc_oh[item] = float(hist_oh.loc[(item, wh), oh_col])
                    except KeyError:
                        pass

            loc_ratio = _compute_ratio_series(loc_sold_qty, loc_oh, items)

            safe_name = wh_name.replace(" ", "_")
            final_data[f"{key}_{safe_name}_Sold_QTY"] = loc_sold_qty
            final_data[f"{key}_{safe_name}_Sold_THB"] = loc_sold_thb
            final_data[f"{key}_{safe_name}_OnHand_QTY"] = loc_oh
            final_data[f"{key}_{safe_name}_Sale_Ratio"] = loc_ratio

    final_df = pd.DataFrame(final_data, index=items)
    final_df.index.name = "ItemCode"

    # --- Total row ---
    total_row = final_df.select_dtypes(include=[np.number]).sum()
    total_row["ItemName"] = "Total"
    # Recalculate all ratios for total row
    for col in total_row.index:
        if col.endswith("_Sale_Ratio"):
            prefix = col.rsplit("_Sale_Ratio", 1)[0]
            sold_col = f"{prefix}_Sold_QTY"
            oh_col = f"{prefix}_OnHand_QTY"
            ts = total_row.get(sold_col, 0)
            to = total_row.get(oh_col, 0)
            if to > 0:
                total_row[col] = ts / to
            elif ts > 0:
                total_row[col] = float("inf")
            else:
                total_row[col] = 0.0

    total_row.name = "Total"
    final_df = pd.concat([final_df, total_row.to_frame().T])

    # Ensure ItemName is first column
    cols = ["ItemName"] + [c for c in final_df.columns if c != "ItemName"]
    final_df = final_df[cols]

    return final_df


def _compute_ratio_series(
    sold_qty: pd.Series, onhand_qty: pd.Series, items: list
) -> pd.Series:
    """Compute sale ratio with proper inf/zero handling."""
    ratio = pd.Series(0.0, index=items, dtype=float)
    for item in items:
        sq = float(sold_qty.get(item, 0))
        oq = float(onhand_qty.get(item, 0))
        if oq > 0:
            ratio[item] = sq / oq
        elif sq > 0:
            ratio[item] = float("inf")
        else:
            ratio[item] = 0.0
    return ratio
