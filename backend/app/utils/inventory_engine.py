"""
Historical On-Hand Reconstruction Engine.

Reconstructs stock levels at past dates by working backwards from the current
OnHand snapshot using stock movement documents (Sales, GRPO, TR IN, TR OUT).

Algorithm:
    OnHand(item, location, end_of_month_M) =
        OnHand(item, location, file_date)
        + Sales(item, location, after M through file_date)       # sold items were in stock
        - GRPO(item, location, after M through file_date)        # purchased items weren't there
        - TR_IN(item, location, after M through file_date)       # transferred-in items weren't there
        - TR_OUT(item, location, after M through file_date)      # TR Out has negative qty → subtracting negative = adding

See CLAUDE_ADDITIONS.md §B.1 for full specification.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd


def compute_historical_onhand(
    df_raw_onhand: pd.DataFrame,
    df_raw_sale: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame],
    df_tr_in: Optional[pd.DataFrame],
    df_tr_out: Optional[pd.DataFrame],
    file_date: date,
    period_type: str = "monthly",
) -> pd.DataFrame:
    """
    Reconstruct historical on-hand quantities at item × location × period grain.

    Parameters
    ----------
    df_raw_onhand : DataFrame
        Current snapshot: ItemCode, WhsCode, OnHand
    df_raw_sale : DataFrame
        Sales history: DocDate, ItemCode, WhsCode, Quantity
    df_grpo_detail : DataFrame or None
        Purchase receipts: DocDate, ItemCode, WhsCode, Quantity
    df_tr_in : DataFrame or None
        Transfer IN: DocDate, ItemCode, WhsCode, Quantity (positive)
    df_tr_out : DataFrame or None
        Transfer OUT: DocDate, ItemCode, WhsCode, Quantity (negative)
    file_date : date
        Date of the on-hand snapshot (from filename)
    period_type : str
        "monthly" or "weekly"

    Returns
    -------
    DataFrame indexed by (ItemCode, WhsCode) with columns:
        {period_str}_OnHand_QTY for each period end
    Latest period equals current snapshot on-hand.
    """
    # --- Step 1: Build current on-hand at item × location grain ---
    oh = df_raw_onhand.copy()
    oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0.0)
    # Keep raw per-warehouse granularity (do NOT aggregate across warehouses here)
    current_oh = (
        oh.groupby(["ItemCode", "WhsCode"], as_index=False)["OnHand"]
        .sum()
    )

    # --- Step 2: Build movement aggregates per period at item × location ---
    file_ts = pd.Timestamp(file_date)

    # Determine all periods from sales dates
    sale = df_raw_sale.copy()
    sale["DocDate"] = pd.to_datetime(sale["DocDate"], errors="coerce")
    sale = sale.dropna(subset=["DocDate"])

    if sale.empty:
        return pd.DataFrame()

    if period_type == "monthly":
        sale["Period"] = sale["DocDate"].dt.to_period("M").dt.start_time
    else:
        sale["Period"] = sale["DocDate"].dt.to_period("W-MON").dt.start_time

    all_periods = sorted(sale["Period"].unique())
    if not all_periods:
        return pd.DataFrame()

    # Aggregate sales by item × location × period
    sale_agg = (
        sale.groupby(["ItemCode", "WhsCode", "Period"], as_index=False)["Quantity"]
        .sum()
        .rename(columns={"Quantity": "Sold_QTY"})
    )

    # Aggregate GRPO by item × location × period
    grpo_agg = _aggregate_movement(df_grpo_detail, period_type, "GRPO_QTY")

    # Aggregate TR IN by item × location × period
    tr_in_agg = _aggregate_movement(df_tr_in, period_type, "TR_IN_QTY")

    # Aggregate TR OUT by item × location × period (quantities are NEGATIVE)
    tr_out_agg = _aggregate_movement(df_tr_out, period_type, "TR_OUT_QTY")

    # --- Step 3: Reconstruct historical on-hand working backwards ---
    # For each (item, location), start from current on-hand and work backwards
    # through periods from newest to oldest.
    #
    # OnHand(end_of_M) = OnHand(end_of_M+1)
    #     + Sold_QTY(M+1)       # items that were sold in M+1 were in stock at end of M
    #     - GRPO_QTY(M+1)       # items received in M+1 weren't in stock at end of M
    #     - TR_IN_QTY(M+1)      # items transferred in during M+1 weren't there at end of M
    #     - TR_OUT_QTY(M+1)     # TR OUT qty is negative, so -(-X) = +X (items that left in M+1 were there at end of M)

    # Build a full index: all (ItemCode, WhsCode) pairs from on-hand + sales
    all_item_loc = set()
    for _, r in current_oh.iterrows():
        all_item_loc.add((r["ItemCode"], r["WhsCode"]))
    for _, r in sale_agg.iterrows():
        all_item_loc.add((r["ItemCode"], r["WhsCode"]))

    # Create lookup dicts for fast access
    oh_lookup = current_oh.set_index(["ItemCode", "WhsCode"])["OnHand"].to_dict()

    def _movement_lookup(agg_df, col_name):
        if agg_df is None or agg_df.empty:
            return {}
        return agg_df.set_index(["ItemCode", "WhsCode", "Period"])[col_name].to_dict()

    sold_lookup = _movement_lookup(sale_agg, "Sold_QTY")
    grpo_lookup = _movement_lookup(grpo_agg, "GRPO_QTY")
    tr_in_lookup = _movement_lookup(tr_in_agg, "TR_IN_QTY")
    tr_out_lookup = _movement_lookup(tr_out_agg, "TR_OUT_QTY")

    # Reconstruct: work backwards from newest period to oldest
    periods_desc = sorted(all_periods, reverse=True)  # newest first
    result_rows = []

    for item, wh in sorted(all_item_loc):
        current_qty = oh_lookup.get((item, wh), 0.0)
        period_values = {}

        # Latest period = current on-hand
        # Then each earlier period reverses the movements of the NEXT period
        for i, period in enumerate(periods_desc):
            if i == 0:
                # Latest period: on-hand equals current snapshot
                period_values[period] = current_qty
            else:
                # Reverse movements of the previous (more recent) period
                next_period = periods_desc[i - 1]
                sold = sold_lookup.get((item, wh, next_period), 0.0)
                grpo = grpo_lookup.get((item, wh, next_period), 0.0)
                tr_in = tr_in_lookup.get((item, wh, next_period), 0.0)
                tr_out = tr_out_lookup.get((item, wh, next_period), 0.0)

                # Reverse: add back sold, subtract received, subtract transferred in,
                # subtract transferred out (which is already negative → adds back)
                prev_oh = period_values[next_period] + sold - grpo - tr_in - tr_out
                # Clamp at zero: negative on-hand is physically impossible — it
                # means stock movements before our data window are incomplete.
                period_values[period] = max(0.0, prev_oh)

        row = {"ItemCode": item, "WhsCode": wh}
        for p in sorted(all_periods):
            key = p.strftime("%Y-%m-%d")
            row[f"{key}_OnHand_QTY"] = period_values.get(p, 0.0)

        result_rows.append(row)

    if not result_rows:
        return pd.DataFrame()

    result = pd.DataFrame(result_rows)
    result = result.set_index(["ItemCode", "WhsCode"])
    return result


def compute_historical_onhand_org(
    df_raw_onhand: pd.DataFrame,
    df_raw_sale: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame],
    df_tr_in: Optional[pd.DataFrame],
    df_tr_out: Optional[pd.DataFrame],
    file_date: date,
    period_type: str = "monthly",
) -> pd.DataFrame:
    """
    Like compute_historical_onhand but aggregated to item level (all locations summed).
    Returns DataFrame indexed by ItemCode with {period}_OnHand_QTY columns.
    """
    detail = compute_historical_onhand(
        df_raw_onhand, df_raw_sale, df_grpo_detail,
        df_tr_in, df_tr_out, file_date, period_type,
    )
    if detail.empty:
        return detail

    # Sum across WhsCode for each ItemCode
    return detail.groupby(level="ItemCode").sum()


def _aggregate_movement(
    df: Optional[pd.DataFrame],
    period_type: str,
    qty_col_name: str,
) -> Optional[pd.DataFrame]:
    """
    Aggregate a movement DataFrame (GRPO, TR IN, or TR OUT) by ItemCode × WhsCode × Period.
    Returns None if input is None or empty.
    """
    if df is None or df.empty:
        return None

    d = df.copy()
    d["DocDate"] = pd.to_datetime(d["DocDate"], errors="coerce")
    d = d.dropna(subset=["DocDate"])

    if d.empty:
        return None

    if "Quantity" not in d.columns:
        return None

    d["Quantity"] = pd.to_numeric(d["Quantity"], errors="coerce").fillna(0.0)

    if period_type == "monthly":
        d["Period"] = d["DocDate"].dt.to_period("M").dt.start_time
    else:
        d["Period"] = d["DocDate"].dt.to_period("W-MON").dt.start_time

    # Ensure WhsCode column exists
    if "WhsCode" not in d.columns:
        return None

    agg = (
        d.groupby(["ItemCode", "WhsCode", "Period"], as_index=False)["Quantity"]
        .sum()
        .rename(columns={"Quantity": qty_col_name})
    )
    return agg
