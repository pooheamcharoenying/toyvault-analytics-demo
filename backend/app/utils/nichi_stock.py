from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Shared GP Commission Helper
# ---------------------------------------------------------------------------

def compute_gp_commission(df_sales: pd.DataFrame) -> pd.Series:
    """Compute per-row GP commission (THB) for consignment sales.

    GP Commission = LineTotal × U_ACT_GP / 100  for Consignment rows.
    Credit sales (and rows missing U_ACT_GP) get 0.

    Parameters
    ----------
    df_sales : DataFrame
        Sales DataFrame that may contain 'U_ACT_GP' and 'Sale Type' columns.

    Returns
    -------
    pd.Series  — same index as df_sales, float64, GP commission per row in THB.
    """
    if df_sales.empty:
        return pd.Series(0.0, index=df_sales.index, dtype=float)

    gp = pd.Series(0.0, index=df_sales.index, dtype=float)

    if "U_ACT_GP" not in df_sales.columns:
        return gp

    u_act = pd.to_numeric(df_sales["U_ACT_GP"], errors="coerce").fillna(0.0)
    line_total = pd.to_numeric(df_sales["LineTotal"], errors="coerce").fillna(0.0)

    if "Sale Type" in df_sales.columns:
        consignment_mask = df_sales["Sale Type"] == "Consignment"
    else:
        # Fallback: treat non-zero U_ACT_GP as consignment
        consignment_mask = u_act > 0

    gp[consignment_mask] = (line_total[consignment_mask] * u_act[consignment_mask] / 100.0)
    return gp


def compute_retailer_cut_components(df_sales: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (discount_thb, gp_commission_thb) as separate components.

    discount_thb is only the credit-channel implicit-discount piece (Master
    price minus actual LineTotal); gp_commission_thb is only the consignment
    GP piece. Their sum equals the total Retailer Cut.
    """
    if df_sales.empty:
        empty = pd.Series(0.0, index=df_sales.index, dtype=float)
        return empty, empty
    line_total = pd.to_numeric(df_sales.get("LineTotal", 0), errors="coerce").fillna(0.0)
    if "Price Master" in df_sales.columns:
        price_master = pd.to_numeric(df_sales["Price Master"], errors="coerce").fillna(0.0)
        discount = (price_master - line_total).clip(lower=0.0)
    else:
        discount = pd.Series(0.0, index=df_sales.index, dtype=float)
    gp = compute_gp_commission(df_sales)
    return discount, gp


def prepare_sales_and_onhand_data(df_raw_sale, df_raw_onhand, df_item_master, dept_store_data: Optional[defaultdict[str, list[str]]] = None):
        
    """
    Processes raw sales and on-hand inventory data to return:
    - cleaned df_sale copy (with Month-Year; Brand filled from Item Master when missing on lines)
    - df_onhand aggregated by ItemCode with merged details, including 'Master Price'
    - df_item_month grouped summary of monthly sales

    Always works on copies — does not mutate GLOBAL_DF frames in place.
    """
    if df_item_master is None or df_item_master.empty:
        raise ValueError("df_item_master is required and cannot be empty")

    df_raw_sale = df_raw_sale.copy()
    df_raw_onhand = df_raw_onhand.copy()

    # Normalize column name: raw Excel uses "Dscription" (SAP spelling),
    # rename to "ItemName" at the data boundary for consistency downstream.
    if 'Dscription' in df_raw_sale.columns and 'ItemName' not in df_raw_sale.columns:
        df_raw_sale = df_raw_sale.rename(columns={'Dscription': 'ItemName'})

    # Ensure DocDate is datetime
    df_raw_sale['DocDate'] = pd.to_datetime(df_raw_sale['DocDate'], errors='coerce')

    # Create Month-Year column
    df_raw_sale['Month-Year'] = df_raw_sale['DocDate'].dt.to_period('M').astype(str)

    # Product brand on sale lines: prefer line Brand; fill from Item Master GroupName (vendor brand)
    _mb = df_item_master[['ItemCode', 'GroupName']].drop_duplicates(subset=['ItemCode']).rename(
        columns={'GroupName': '_BrandFromMaster'}
    )
    df_raw_sale = df_raw_sale.merge(_mb, on='ItemCode', how='left')
    df_raw_sale['Brand'] = df_raw_sale['Brand'].fillna(df_raw_sale['_BrandFromMaster'])
    df_raw_sale = df_raw_sale.drop(columns=['_BrandFromMaster'])

    if 'Price' in df_raw_onhand.columns:
        df_raw_onhand = df_raw_onhand.drop(columns=['Price'])
        
    if 'SALETEAM' in df_raw_onhand.columns:
        df_raw_onhand = df_raw_onhand.drop(columns=['SALETEAM'])

    if 'GroupName' in df_raw_onhand.columns:
        df_raw_onhand = df_raw_onhand.drop(columns=['GroupName'])

    # Merge price, brand, and item name into on-hand data
    df_raw_onhand = df_raw_onhand.merge(
        df_item_master[['ItemCode', 'GroupName', 'ItemName', 'Price']],
        on='ItemCode',
        how='left'
    )

    # Rename for consistency
    df_raw_onhand = df_raw_onhand.rename(columns={
        'GroupName': 'Brand',
        'Price': 'Master Price'
    })

    # Fallback: for items NOT in Item Master (Master Price is NaN), derive
    # the unit master price from the Sale sheet's "Price Master" column
    # (= line-level Quantity × unit master price). This recovers ~76% of
    # items missing from the master without overriding any real master prices.
    # Cached per df_raw_sale identity so we don't rescan 600K+ rows on every
    # request. See app/utils/price_recovery.py for the full tiered logic.
    try:
        from app.utils.price_recovery import _sale_unit_master_price_map
        _fallback = _sale_unit_master_price_map(df_raw_sale)
        if not _fallback.empty:
            _needs_fallback = df_raw_onhand['Master Price'].isna()
            if _needs_fallback.any():
                df_raw_onhand.loc[_needs_fallback, 'Master Price'] = (
                    df_raw_onhand.loc[_needs_fallback, 'ItemCode'].map(_fallback)
                )
    except Exception:
        pass  # Never break data prep if the recovery helper fails

    # Brand fallback: for items NOT in Item Master, fill Brand from (a)
    # Sale.Brand if populated, else (b) item-code prefix inference.
    # See app/utils/brand_recovery.py for the full tiered logic.
    try:
        from app.utils.brand_recovery import build_brand_map
        _needs_brand_fallback = df_raw_onhand['Brand'].isna()
        if _needs_brand_fallback.any():
            _all_codes = df_raw_onhand.loc[_needs_brand_fallback, 'ItemCode']
            _brand_map = build_brand_map(
                df_item_master,
                df_sale=df_raw_sale,
                all_item_codes=_all_codes,
            )
            df_raw_onhand.loc[_needs_brand_fallback, 'Brand'] = (
                df_raw_onhand.loc[_needs_brand_fallback, 'ItemCode'].map(_brand_map)
            )
    except Exception:
        pass  # Never break data prep if the recovery helper fails

    # Aggregate on-hand data by ItemCode
    df_raw_onhand = (
        df_raw_onhand
        .groupby('ItemCode', as_index=False)
        .agg({
            'OnHand': 'sum',
            'Brand': 'first',
            'ItemName': 'first',
            'Master Price': 'first'
        })
    )

    # Reorder columns: Brand, ItemName, ItemCode first
    first_cols = ['Brand', 'ItemName', 'ItemCode']
    other_cols = [col for col in df_raw_onhand.columns if col not in first_cols]
    df_raw_onhand = df_raw_onhand[first_cols + other_cols]

    # Group sales by item and month
    df_item_month = (
        df_raw_sale.groupby(['ItemCode', 'ItemName', 'Brand', 'Price', 'Month-Year'])
        .agg({'Quantity': 'sum', 'LineTotal': 'sum'})
        .reset_index()
    )
    
    return df_raw_sale, df_raw_onhand, df_item_month

def generate_sales_onhand_by_channel(df_sale, df_onhand, period_type='monthly'):
    assert period_type in ['weekly', 'monthly'], "period_type must be either 'weekly' or 'monthly'"

    df_sale = df_sale.copy()
    df_sale['DocDate'] = pd.to_datetime(df_sale['DocDate'])

    if period_type == 'weekly':
        df_sale['Period'] = df_sale['DocDate'].dt.to_period('W-MON').dt.start_time
    elif period_type == 'monthly':
        df_sale['Period'] = df_sale['DocDate'].dt.to_period('M').dt.start_time

    # Step 1: Drop duplicates to avoid over-counting
    df_sale = df_sale.drop_duplicates(subset=['DocEntry', 'ItemCode', 'Period', 'GroupName'])

    # Step 2: Aggregate
    df_agg = df_sale.groupby(['GroupName', 'Period']).agg({
        'Quantity': 'sum',
        'LineTotal': 'sum'
    }).reset_index()

    if df_agg.empty:
        return pd.DataFrame()

    # Step 3: Pivot
    qty_pivot = df_agg.pivot(index='GroupName', columns='Period', values='Quantity').fillna(0)
    thb_pivot = df_agg.pivot(index='GroupName', columns='Period', values='LineTotal').fillna(0)

    # On-hand by *sales channel* (GroupName) is not in the export — stock is by item/warehouse.
    # Do not repeat organisation-wide stock on every channel row (misleading). Sales columns stay granular.
    df_onhand_filtered = df_onhand.dropna(subset=['OnHand', 'Master Price']).copy()
    df_onhand_filtered['OnHand_THB'] = df_onhand_filtered['OnHand'] * df_onhand_filtered['Master Price']
    total_onhand_units = float(df_onhand_filtered['OnHand'].sum())
    total_onhand_thb = float(df_onhand_filtered['OnHand_THB'].sum())

    periods = sorted(qty_pivot.columns)[::-1]
    if not periods:
        return pd.DataFrame()

    periods_asc = sorted(periods)
    latest_period = periods_asc[-1]
    latest_key = latest_period.strftime('%Y-%m-%d')

    # Step 6: Combine into a single-level header
    final_data = {}
    for period in periods_asc:
        key = period.strftime('%Y-%m-%d')
        final_data[f"{key}_Sold_QTY"] = qty_pivot[period]
        final_data[f"{key}_Sold_THB"] = thb_pivot[period]
        # Per-channel on-hand unknown without allocation rules — leave NaN
        final_data[f"{key}_OnHand_QTY"] = pd.Series(np.nan, index=qty_pivot.index, dtype=float)
        final_data[f"{key}_OnHand_THB"] = pd.Series(np.nan, index=qty_pivot.index, dtype=float)

    final_df = pd.DataFrame(final_data)

    metric_order = {"Sold_QTY": 0, "Sold_THB": 1, "OnHand_QTY": 2, "OnHand_THB": 3}
    def sort_key(col_name: str):
        date_part, metric_part = col_name.split("_", 1)
        return (date_part, metric_order.get(metric_part, 99), metric_part)

    final_df = final_df.reindex(columns=sorted(final_df.columns, key=sort_key))

    # Total row: sum sales; org-wide on-hand only on latest period columns (single snapshot)
    total_row = final_df.sum(numeric_only=True)
    for period in periods_asc:
        key = period.strftime('%Y-%m-%d')
        total_row[f"{key}_OnHand_QTY"] = total_onhand_units if period == latest_period else np.nan
        total_row[f"{key}_OnHand_THB"] = total_onhand_thb if period == latest_period else np.nan
    total_row.name = 'Total'
    final_df = pd.concat([final_df, total_row.to_frame().T])

    # Rename index from raw "GroupName" to semantic "Channel" for display
    final_df.index.name = "Channel"

    # Debug consistency check
    original_total = df_sale['LineTotal'].sum()
    agg_total = df_agg['LineTotal'].sum()
    if not np.isclose(original_total, agg_total):
        logger.warning("Channel aggregated sales (%s) != original total (%s)", agg_total, original_total)

    return final_df

def generate_sales_onhand_by_brand(
    df_sale,
    df_onhand,
    period_type='monthly',
    df_raw_onhand=None,
    df_grpo_detail=None,
    df_tr_in=None,
    df_tr_out=None,
    file_date=None,
    df_item_master=None,
):
    """
    Brand × Period matrix with Sold QTY/THB and reconstructed OnHand QTY/THB.

    When df_raw_onhand and file_date are provided, uses the full inventory engine
    (GRPO, TR IN, TR OUT) for accurate historical on-hand reconstruction.
    Falls back to sales-only reversal when those params are missing.
    """
    assert period_type in ['weekly', 'monthly'], "period_type must be either 'weekly' or 'monthly'"

    df_sale = df_sale.copy()
    df_sale['DocDate'] = pd.to_datetime(df_sale['DocDate'])

    # 🔧 Fix missing Brand
    df_sale['Brand'] = df_sale['Brand'].fillna('Unknown')

    if period_type == 'weekly':
        df_sale['Period'] = df_sale['DocDate'].dt.to_period('W-MON').dt.start_time
    elif period_type == 'monthly':
        df_sale['Period'] = df_sale['DocDate'].dt.to_period('M').dt.start_time

    # 🧼 Remove duplicates to prevent overcounting
    df_sale = df_sale.drop_duplicates(subset=['DocEntry', 'ItemCode', 'Period', 'Brand'])

    # 🔄 Aggregate sales
    df_agg = df_sale.groupby(['Brand', 'Period']).agg({
        'Quantity': 'sum',
        'LineTotal': 'sum'
    }).reset_index()

    if df_agg.empty:
        return pd.DataFrame()

    # Pivot to Brand vs Period
    qty_pivot = df_agg.pivot(index='Brand', columns='Period', values='Quantity').fillna(0)
    thb_pivot = df_agg.pivot(index='Brand', columns='Period', values='LineTotal').fillna(0)

    periods = sorted(qty_pivot.columns)
    if not periods:
        return pd.DataFrame()

    # 📦 OnHand info — current snapshot for THB calculation
    df_onhand_filtered = df_onhand.dropna(subset=['Brand', 'OnHand', 'Master Price']).copy()
    df_onhand_filtered['OnHand_THB'] = df_onhand_filtered['OnHand'] * df_onhand_filtered['Master Price']

    # Build item→brand and item→master_price mappings for engine output aggregation
    item_brand_map = df_onhand_filtered.set_index('ItemCode')['Brand'].to_dict()
    item_price_map = df_onhand_filtered.set_index('ItemCode')['Master Price'].to_dict()

    # If item_master is available, supplement the mappings
    if df_item_master is not None and not df_item_master.empty:
        for _, row in df_item_master.iterrows():
            ic = row.get('ItemCode')
            gn = row.get('GroupName')
            pr = row.get('Price')
            if ic and gn and ic not in item_brand_map:
                item_brand_map[ic] = gn
            if ic and pr and ic not in item_price_map:
                item_price_map[ic] = pr

    # 🧮 Historical OnHand reconstruction
    use_engine = (df_raw_onhand is not None and file_date is not None)

    if use_engine:
        from app.utils.inventory_engine import compute_historical_onhand_org
        from datetime import date as _date_type

        fd = file_date if isinstance(file_date, _date_type) else pd.Timestamp(file_date).date()

        # Get item-level historical on-hand from full engine
        item_onhand = compute_historical_onhand_org(
            df_raw_onhand=df_raw_onhand,
            df_raw_sale=df_sale,  # already deduped
            df_grpo_detail=df_grpo_detail,
            df_tr_in=df_tr_in,
            df_tr_out=df_tr_out,
            file_date=fd,
            period_type=period_type,
        )

        if item_onhand.empty:
            use_engine = False  # fall back

    if use_engine:
        # Aggregate item-level onhand to brand level
        # item_onhand is indexed by ItemCode with columns like "2024-01-01_OnHand_QTY"
        item_onhand = item_onhand.copy()
        item_onhand['Brand'] = item_onhand.index.map(lambda ic: item_brand_map.get(ic, 'Unknown'))
        brand_onhand = item_onhand.groupby('Brand').sum()

        # Also compute THB: for each item, multiply onhand_qty by master_price then aggregate
        item_onhand_thb = item_onhand.drop(columns=['Brand']).copy()
        for col in item_onhand_thb.columns:
            item_onhand_thb[col] = item_onhand_thb[col].astype(float) * item_onhand_thb.index.map(
                lambda ic: float(item_price_map.get(ic, 0))
            )
        item_onhand_thb['Brand'] = item_onhand.index.map(lambda ic: item_brand_map.get(ic, 'Unknown'))
        brand_onhand_thb = item_onhand_thb.groupby('Brand').sum()

        # Build onhand unit and THB DataFrames aligned with periods
        onhand_units_df = pd.DataFrame(index=qty_pivot.index, columns=periods, dtype=float).fillna(0)
        onhand_thb_df = pd.DataFrame(index=qty_pivot.index, columns=periods, dtype=float).fillna(0)

        for period in periods:
            key = period.strftime('%Y-%m-%d') + "_OnHand_QTY"
            if key in brand_onhand.columns:
                for brand in qty_pivot.index:
                    if brand in brand_onhand.index:
                        onhand_units_df.at[brand, period] = float(brand_onhand.at[brand, key])
                    if brand in brand_onhand_thb.index:
                        thb_key = key  # same column name, different DF
                        onhand_thb_df.at[brand, period] = float(brand_onhand_thb.at[brand, thb_key])
    else:
        # Fallback: simple sales-only reversal (original algorithm)
        onhand_agg = df_onhand_filtered.groupby('Brand')[['OnHand', 'OnHand_THB']].sum()

        periods_desc = sorted(periods, reverse=True)
        onhand_units = {}
        onhand_thb = {}

        for i, period in enumerate(periods_desc):
            if i == 0:
                onhand_units[period] = onhand_agg['OnHand']
                onhand_thb[period] = onhand_agg['OnHand_THB']
            else:
                prev = periods_desc[i - 1]
                onhand_units[period] = onhand_units[prev] + qty_pivot[prev]
                onhand_thb[period] = onhand_thb[prev] + thb_pivot[prev]

        onhand_units_df = pd.DataFrame(onhand_units)
        onhand_thb_df = pd.DataFrame(onhand_thb)

    # Build flat columns: "<YYYY-MM-DD>_<Metric>"
    final_data = {}
    for period in periods:
        key = period.strftime('%Y-%m-%d')
        final_data[f"{key}_Sold_QTY"] = qty_pivot[period]
        final_data[f"{key}_Sold_THB"] = thb_pivot[period]
        final_data[f"{key}_OnHand_QTY"] = onhand_units_df[period]
        final_data[f"{key}_OnHand_THB"] = onhand_thb_df[period]

    final_df = pd.DataFrame(final_data)

    # Ensure consistent metric ordering within each date
    metric_order = {"Sold_QTY": 0, "Sold_THB": 1, "OnHand_QTY": 2, "OnHand_THB": 3}
    def sort_key(col_name: str):
        date_part, metric_part = col_name.split("_", 1)
        return (date_part, metric_order.get(metric_part, 99), metric_part)

    final_df = final_df.reindex(columns=sorted(final_df.columns, key=sort_key))

    # ➕ Add total row
    total_row = final_df.sum(numeric_only=True)
    total_row.name = 'Total'
    final_df = pd.concat([final_df, total_row.to_frame().T])

    # 🧪 Debug check
    original_total = df_sale['LineTotal'].sum()
    agg_total = df_agg['LineTotal'].sum()
    if not np.isclose(original_total, agg_total):
        logger.warning("Brand aggregated sales (%s) != original total (%s)", agg_total, original_total)

    return final_df

def generate_sales_onhand_by_brand_channel(
    df_sale,
    df_onhand,
    brand_name,
    period_type='monthly',
    current_date=None,
    year_list=None
):

    assert period_type in ['weekly', 'monthly'], "period_type must be either 'weekly' or 'monthly'"

    now = pd.Timestamp.now() if current_date is None else pd.to_datetime(current_date)

    df_sale = df_sale.copy()
    df_sale['DocDate'] = pd.to_datetime(df_sale['DocDate'])

    # Brand filter
    if brand_name == 'None':
        df_sale_brand = df_sale[df_sale['Brand'].isna()].copy()
        df_onhand_brand = df_onhand[df_onhand['Brand'].isna()].copy()
        display_brand_name = 'None (NaN values)'
    else:
        df_sale['Brand'] = df_sale['Brand'].fillna('Unknown')
        df_sale_brand = df_sale[df_sale['Brand'] == brand_name].copy()
        df_onhand_brand = df_onhand[df_onhand['Brand'] == brand_name].copy()
        display_brand_name = brand_name

    if df_sale_brand.empty:
        logger.warning("No sales data found for brand: %s", display_brand_name)
        return pd.DataFrame()

    # Periods
    if period_type == 'weekly':
        df_sale_brand['Period'] = df_sale_brand['DocDate'].dt.to_period('W-MON').dt.start_time
        current_period_start = now.to_period('W-MON').start_time
        def _is_fully_elapsed(p): return p < current_period_start
    else:  # monthly
        df_sale_brand['Period'] = df_sale_brand['DocDate'].dt.to_period('M').dt.start_time
        current_month_start = pd.Timestamp(now.year, now.month, 1)
        def _is_fully_elapsed(p): return p < current_month_start

    # ===== CRITICAL FIX: Filter data by year_list BEFORE aggregation =====
    if year_list:
        df_sale_brand = df_sale_brand[df_sale_brand['Period'].dt.year.isin(year_list)].copy()
        if df_sale_brand.empty:
            logger.warning("No sales data found for brand %s in years %s", display_brand_name, year_list)
            return pd.DataFrame()

    # De-dup and aggregate
    df_sale_brand = df_sale_brand.drop_duplicates(subset=['DocEntry', 'ItemCode', 'Period', 'GroupName'])
    df_agg = df_sale_brand.groupby(['GroupName', 'Period']).agg(
        Quantity=('Quantity', 'sum'),
        LineTotal=('LineTotal', 'sum')
    ).reset_index()
    if df_agg.empty:
        return pd.DataFrame()

    qty_pivot = df_agg.pivot(index='GroupName', columns='Period', values='Quantity').fillna(0)
    thb_pivot = df_agg.pivot(index='GroupName', columns='Period', values='LineTotal').fillna(0)

    # ----- OnHand snapshot (no summing; carry-forward) -----
    df_onhand_filtered = df_onhand_brand.dropna(subset=['OnHand', 'Master Price']).copy()
    if df_onhand_filtered.empty:
        onhand_units_snapshot = 0.0
        onhand_thb_snapshot = 0.0
    else:
        df_onhand_filtered['OnHand_THB'] = df_onhand_filtered['OnHand'] * df_onhand_filtered['Master Price']
        onhand_units_snapshot = float(df_onhand_filtered['OnHand'].sum())
        onhand_thb_snapshot = float(df_onhand_filtered['OnHand_THB'].sum())

    # Build onhand matrices with carry-forward across periods
    periods_sorted_asc = sorted(qty_pivot.columns)
    if not periods_sorted_asc:
        return pd.DataFrame()

    # Choose the first fully elapsed period to anchor the snapshot (so we don't place into partial month/week)
    fully_elapsed_periods = [p for p in periods_sorted_asc if _is_fully_elapsed(p)]
    if fully_elapsed_periods:
        anchor_period = fully_elapsed_periods[-1]  # most recent fully elapsed period
    else:
        # If nothing is fully elapsed yet, we won't place onhand into the timeline;
        # Tot_OnHand_* will still use the snapshot values.
        anchor_period = None

    onhand_units_df = pd.DataFrame(index=qty_pivot.index, columns=periods_sorted_asc, dtype=float)
    onhand_thb_df = pd.DataFrame(index=qty_pivot.index, columns=periods_sorted_asc, dtype=float)
    onhand_units_df[:] = np.nan
    onhand_thb_df[:] = np.nan

    if anchor_period is not None:
        # Put snapshot at anchor and carry forward to the right (later periods)
        put_idx = periods_sorted_asc.index(anchor_period)
        for i in range(put_idx, len(periods_sorted_asc)):
            p = periods_sorted_asc[i]
            onhand_units_df[p] = onhand_units_snapshot
            onhand_thb_df[p] = onhand_thb_snapshot
    # (Left of anchor stays NaN; no historical backfill guesses.)

    # ----- Build flat columns -----
    final_data = {}
    for p in periods_sorted_asc:
        key = p.strftime('%Y-%m-%d')
        final_data[f"{key}_Sold_QTY"]   = qty_pivot[p]
        final_data[f"{key}_Sold_THB"]   = thb_pivot[p]
        final_data[f"{key}_OnHand_QTY"] = onhand_units_df[p]
        final_data[f"{key}_OnHand_THB"] = onhand_thb_df[p]

    final_df = pd.DataFrame(final_data, index=qty_pivot.index)

    metric_order = {"Sold_QTY": 0, "Sold_THB": 1, "OnHand_QTY": 2, "OnHand_THB": 3}
    def _sort_key(c):
        date_part, metric_part = c.split("_", 1)
        return (date_part, metric_order.get(metric_part, 99), metric_part)
    final_df = final_df.reindex(columns=sorted(final_df.columns, key=_sort_key))

    # ---------- YEAR FILTERING FOR TOTALS AND AVERAGES ----------
    # Now periods_sorted_asc already contains only year_list periods due to filtering above
    all_keys = [p.strftime('%Y-%m-%d') for p in periods_sorted_asc]
    fully_elapsed_keys = [p.strftime('%Y-%m-%d') for p in fully_elapsed_periods]

    # For Prev2_Avg: Use the 2 most recent fully elapsed periods
    prev2_periods = fully_elapsed_periods[-2:] if len(fully_elapsed_periods) >= 2 else fully_elapsed_periods
    prev2_keys = [p.strftime('%Y-%m-%d') for p in prev2_periods]

    def _sold_cols_for(keys):
        qty_cols = [f"{k}_Sold_QTY" for k in keys if f"{k}_Sold_QTY" in final_df.columns]
        thb_cols = [f"{k}_Sold_THB" for k in keys if f"{k}_Sold_THB" in final_df.columns]
        return qty_cols, thb_cols

    # Sales totals across ALL periods (which are now filtered to year_list only)
    all_qty_cols, all_thb_cols = _sold_cols_for(all_keys)
    final_df['Tot_Sold_QTY'] = final_df[all_qty_cols].sum(axis=1) if all_qty_cols else 0.0
    final_df['Tot_Sold_THB'] = final_df[all_thb_cols].sum(axis=1) if all_thb_cols else 0.0

    # Current OnHand per row = latest non-NA across onhand timeline (no summing)
    onhand_qty_cols = [f"{k}_OnHand_QTY" for k in all_keys]
    onhand_thb_cols = [f"{k}_OnHand_THB" for k in all_keys]
    final_df['Tot_OnHand_QTY'] = final_df[onhand_qty_cols].bfill(axis=1).iloc[:, -1] if onhand_qty_cols else np.nan
    final_df['Tot_OnHand_THB'] = final_df[onhand_thb_cols].bfill(axis=1).iloc[:, -1] if onhand_thb_cols else np.nan

    # Lifetime averages (ALL fully elapsed periods)
    lt_qty_cols, lt_thb_cols = _sold_cols_for(fully_elapsed_keys)
    final_df['LT_Avg_Sold_QTY'] = final_df[lt_qty_cols].mean(axis=1) if lt_qty_cols else np.nan
    final_df['LT_Avg_Sold_THB'] = final_df[lt_thb_cols].mean(axis=1) if lt_thb_cols else np.nan

    # Previous 2 fully elapsed periods average
    prev2_qty_cols, prev2_thb_cols = _sold_cols_for(prev2_keys)
    final_df['Prev2_Avg_Sold_QTY'] = final_df[prev2_qty_cols].mean(axis=1) if prev2_qty_cols else np.nan
    final_df['Prev2_Avg_Sold_THB'] = final_df[prev2_thb_cols].mean(axis=1) if prev2_thb_cols else np.nan

    # Put the new columns in front
    front_cols = [
        'Tot_Sold_QTY', 'Tot_Sold_THB', 'Tot_OnHand_QTY', 'Tot_OnHand_THB',
        'LT_Avg_Sold_QTY', 'LT_Avg_Sold_THB',
        'Prev2_Avg_Sold_QTY', 'Prev2_Avg_Sold_THB'
    ]
    remaining_cols = [c for c in final_df.columns if c not in front_cols]
    final_df = final_df[front_cols + remaining_cols]

    # ----- Custom Total row -----
    total_row = {}
    # Sales totals = sum across channels
    total_row['Tot_Sold_QTY'] = final_df['Tot_Sold_QTY'].sum()
    total_row['Tot_Sold_THB'] = final_df['Tot_Sold_THB'].sum()
    # OnHand total = sum of current onhand across channels (no summing across periods)
    total_row['Tot_OnHand_QTY'] = final_df['Tot_OnHand_QTY'].sum(min_count=1)
    total_row['Tot_OnHand_THB'] = final_df['Tot_OnHand_THB'].sum(min_count=1)

    # Period columns: sum sales; onhand = sum across channels
    for p in periods_sorted_asc:
        key = p.strftime('%Y-%m-%d')
        # Sales
        qcol, tcol = f"{key}_Sold_QTY", f"{key}_Sold_THB"
        total_row[qcol] = final_df[qcol].sum(min_count=1)
        total_row[tcol] = final_df[tcol].sum(min_count=1)
        # OnHand: NOT a sum across time; but summing across channels is okay
        ohq, oht = f"{key}_OnHand_QTY", f"{key}_OnHand_THB"
        total_row[ohq] = final_df[ohq].sum(min_count=1)
        total_row[oht] = final_df[oht].sum(min_count=1)
    
    # Averages for Total row: Calculate from total period sums
    # LT_Avg should be: sum of all fully elapsed periods / number of fully elapsed periods
    num_fully_elapsed = len(fully_elapsed_periods)
    if num_fully_elapsed > 0:
        # Sum across all fully elapsed period columns for total row
        lt_qty_sum = sum(total_row[f"{p.strftime('%Y-%m-%d')}_Sold_QTY"] 
                        for p in fully_elapsed_periods)
        lt_thb_sum = sum(total_row[f"{p.strftime('%Y-%m-%d')}_Sold_THB"] 
                        for p in fully_elapsed_periods)
        total_row['LT_Avg_Sold_QTY'] = lt_qty_sum / num_fully_elapsed
        total_row['LT_Avg_Sold_THB'] = lt_thb_sum / num_fully_elapsed
    else:
        total_row['LT_Avg_Sold_QTY'] = np.nan
        total_row['LT_Avg_Sold_THB'] = np.nan
    
    # Prev2_Avg: average of last 2 fully elapsed periods for total
    num_prev2 = len(prev2_periods)
    if num_prev2 > 0:
        prev2_qty_sum = sum(total_row[f"{p.strftime('%Y-%m-%d')}_Sold_QTY"] 
                           for p in prev2_periods)
        prev2_thb_sum = sum(total_row[f"{p.strftime('%Y-%m-%d')}_Sold_THB"] 
                           for p in prev2_periods)
        total_row['Prev2_Avg_Sold_QTY'] = prev2_qty_sum / num_prev2
        total_row['Prev2_Avg_Sold_THB'] = prev2_thb_sum / num_prev2
    else:
        total_row['Prev2_Avg_Sold_QTY'] = np.nan
        total_row['Prev2_Avg_Sold_THB'] = np.nan

    final_df.loc['Total'] = total_row

    # Rename index from raw "GroupName" to semantic "Channel" for display
    final_df.index.name = "Channel"

    # Debug - validate totals
    original_total = df_sale_brand['LineTotal'].sum()
    agg_total = final_df.loc['Total', 'Tot_Sold_THB']
    if not np.isclose(original_total, agg_total, rtol=1e-5):
        logger.warning("Brand-channel aggregated sales (%.2f) != original total (%.2f)", agg_total, original_total)

    return final_df

def generate_sales_onhand_by_channel_brand(
    df_sale,
    df_onhand,
    channel_name,
    period_type='monthly',
    current_date=None,
    year_list=None
):

    assert period_type in ['weekly', 'monthly'], "period_type must be either 'weekly' or 'monthly'"

    now = pd.Timestamp.now() if current_date is None else pd.to_datetime(current_date)

    df_sale = df_sale.copy()
    df_sale['DocDate'] = pd.to_datetime(df_sale['DocDate'])

    # ===== FILTER BY CHANNEL (GroupName) =====
    df_sale['GroupName'] = df_sale['GroupName'].fillna('Unknown')

    df_sale_channel = df_sale[df_sale['GroupName'] == channel_name].copy()
    df_onhand_channel = df_onhand.copy()
    display_channel_name = channel_name

    if df_sale_channel.empty:
        logger.warning("No sales data found for channel: %s", display_channel_name)
        return pd.DataFrame()

    # ===== PERIODS =====
    if period_type == 'weekly':
        df_sale_channel['Period'] = df_sale_channel['DocDate'].dt.to_period('W-MON').dt.start_time
        current_period_start = now.to_period('W-MON').start_time
        def _is_fully_elapsed(p): return p < current_period_start
    else:
        df_sale_channel['Period'] = df_sale_channel['DocDate'].dt.to_period('M').dt.start_time
        current_month_start = pd.Timestamp(now.year, now.month, 1)
        def _is_fully_elapsed(p): return p < current_month_start

    # ===== YEAR FILTERING =====
    if year_list:
        df_sale_channel = df_sale_channel[df_sale_channel['Period'].dt.year.isin(year_list)]
        if df_sale_channel.empty:
            logger.warning("No sales data for channel %s in years %s", display_channel_name, year_list)
            return pd.DataFrame()

    # ===== AGGREGATE (ROWS = BRAND) =====
    df_sale_channel = df_sale_channel.drop_duplicates(
        subset=['DocEntry', 'ItemCode', 'Period', 'Brand']
    )

    df_agg = df_sale_channel.groupby(['Brand', 'Period']).agg(
        Quantity=('Quantity', 'sum'),
        LineTotal=('LineTotal', 'sum')
    ).reset_index()

    if df_agg.empty:
        return pd.DataFrame()

    qty_pivot = df_agg.pivot(index='Brand', columns='Period', values='Quantity').fillna(0)
    thb_pivot = df_agg.pivot(index='Brand', columns='Period', values='LineTotal').fillna(0)

    # ===== ONHAND SNAPSHOT =====
    df_onhand_filtered = df_onhand_channel.dropna(subset=['OnHand', 'Master Price'])
    if df_onhand_filtered.empty:
        onhand_units_snapshot = 0.0
        onhand_thb_snapshot = 0.0
    else:
        df_onhand_filtered['OnHand_THB'] = df_onhand_filtered['OnHand'] * df_onhand_filtered['Master Price']
        onhand_units_snapshot = float(df_onhand_filtered['OnHand'].sum())
        onhand_thb_snapshot = float(df_onhand_filtered['OnHand_THB'].sum())

    periods_sorted_asc = sorted(qty_pivot.columns)
    if not periods_sorted_asc:
        return pd.DataFrame()

    fully_elapsed_periods = [p for p in periods_sorted_asc if _is_fully_elapsed(p)]
    anchor_period = fully_elapsed_periods[-1] if fully_elapsed_periods else None

    onhand_units_df = pd.DataFrame(index=qty_pivot.index, columns=periods_sorted_asc, dtype=float)
    onhand_thb_df   = pd.DataFrame(index=qty_pivot.index, columns=periods_sorted_asc, dtype=float)
    onhand_units_df[:] = np.nan
    onhand_thb_df[:] = np.nan

    if anchor_period is not None:
        put_idx = periods_sorted_asc.index(anchor_period)
        for i in range(put_idx, len(periods_sorted_asc)):
            p = periods_sorted_asc[i]
            onhand_units_df[p] = onhand_units_snapshot
            onhand_thb_df[p] = onhand_thb_snapshot

    # ===== BUILD FINAL DF =====
    final_data = {}
    for p in periods_sorted_asc:
        key = p.strftime('%Y-%m-%d')
        final_data[f"{key}_Sold_QTY"]   = qty_pivot[p]
        final_data[f"{key}_Sold_THB"]   = thb_pivot[p]
        final_data[f"{key}_OnHand_QTY"] = onhand_units_df[p]
        final_data[f"{key}_OnHand_THB"] = onhand_thb_df[p]

    final_df = pd.DataFrame(final_data, index=qty_pivot.index)

    metric_order = {"Sold_QTY": 0, "Sold_THB": 1, "OnHand_QTY": 2, "OnHand_THB": 3}
    def _sort_key(c):
        date_part, metric_part = c.split("_", 1)
        return (date_part, metric_order.get(metric_part, 99), metric_part)

    final_df = final_df.reindex(columns=sorted(final_df.columns, key=_sort_key))

    # ---------- YEAR FILTERING FOR TOTALS AND AVERAGES ----------
    all_keys = [p.strftime('%Y-%m-%d') for p in periods_sorted_asc]
    fully_elapsed_keys = [p.strftime('%Y-%m-%d') for p in fully_elapsed_periods]

    # For Prev2_Avg: Use the 2 most recent fully elapsed periods
    prev2_periods = fully_elapsed_periods[-2:] if len(fully_elapsed_periods) >= 2 else fully_elapsed_periods
    prev2_keys = [p.strftime('%Y-%m-%d') for p in prev2_periods]

    def _sold_cols_for(keys):
        qty_cols = [f"{k}_Sold_QTY" for k in keys if f"{k}_Sold_QTY" in final_df.columns]
        thb_cols = [f"{k}_Sold_THB" for k in keys if f"{k}_Sold_THB" in final_df.columns]
        return qty_cols, thb_cols

    # Sales totals across ALL periods (which are now filtered to year_list only)
    all_qty_cols, all_thb_cols = _sold_cols_for(all_keys)
    final_df['Tot_Sold_QTY'] = final_df[all_qty_cols].sum(axis=1) if all_qty_cols else 0.0
    final_df['Tot_Sold_THB'] = final_df[all_thb_cols].sum(axis=1) if all_thb_cols else 0.0

    # Current OnHand per row = latest non-NA across onhand timeline (no summing)
    onhand_qty_cols = [f"{k}_OnHand_QTY" for k in all_keys]
    onhand_thb_cols = [f"{k}_OnHand_THB" for k in all_keys]
    final_df['Tot_OnHand_QTY'] = final_df[onhand_qty_cols].bfill(axis=1).iloc[:, -1] if onhand_qty_cols else np.nan
    final_df['Tot_OnHand_THB'] = final_df[onhand_thb_cols].bfill(axis=1).iloc[:, -1] if onhand_thb_cols else np.nan

    # Lifetime averages (ALL fully elapsed periods)
    lt_qty_cols, lt_thb_cols = _sold_cols_for(fully_elapsed_keys)
    final_df['LT_Avg_Sold_QTY'] = final_df[lt_qty_cols].mean(axis=1) if lt_qty_cols else np.nan
    final_df['LT_Avg_Sold_THB'] = final_df[lt_thb_cols].mean(axis=1) if lt_thb_cols else np.nan

    # Previous 2 fully elapsed periods average
    prev2_qty_cols, prev2_thb_cols = _sold_cols_for(prev2_keys)
    final_df['Prev2_Avg_Sold_QTY'] = final_df[prev2_qty_cols].mean(axis=1) if prev2_qty_cols else np.nan
    final_df['Prev2_Avg_Sold_THB'] = final_df[prev2_thb_cols].mean(axis=1) if prev2_thb_cols else np.nan

    # Put the new columns in front
    front_cols = [
        'Tot_Sold_QTY', 'Tot_Sold_THB', 'Tot_OnHand_QTY', 'Tot_OnHand_THB',
        'LT_Avg_Sold_QTY', 'LT_Avg_Sold_THB',
        'Prev2_Avg_Sold_QTY', 'Prev2_Avg_Sold_THB'
    ]
    remaining_cols = [c for c in final_df.columns if c not in front_cols]
    final_df = final_df[front_cols + remaining_cols]

    # ----- Custom Total row -----
    total_row = {}
    # Sales totals = sum across brands
    total_row['Tot_Sold_QTY'] = final_df['Tot_Sold_QTY'].sum()
    total_row['Tot_Sold_THB'] = final_df['Tot_Sold_THB'].sum()
    # OnHand total = sum of current onhand across brands (no summing across periods)
    total_row['Tot_OnHand_QTY'] = final_df['Tot_OnHand_QTY'].sum(min_count=1)
    total_row['Tot_OnHand_THB'] = final_df['Tot_OnHand_THB'].sum(min_count=1)

    # Period columns: sum sales; onhand = sum across brands
    for p in periods_sorted_asc:
        key = p.strftime('%Y-%m-%d')
        # Sales
        qcol, tcol = f"{key}_Sold_QTY", f"{key}_Sold_THB"
        total_row[qcol] = final_df[qcol].sum(min_count=1)
        total_row[tcol] = final_df[tcol].sum(min_count=1)
        # OnHand: NOT a sum across time; but summing across brands is okay
        ohq, oht = f"{key}_OnHand_QTY", f"{key}_OnHand_THB"
        total_row[ohq] = final_df[ohq].sum(min_count=1)
        total_row[oht] = final_df[oht].sum(min_count=1)
    
    # Averages for Total row: Calculate from total period sums
    # LT_Avg should be: sum of all fully elapsed periods / number of fully elapsed periods
    num_fully_elapsed = len(fully_elapsed_periods)
    if num_fully_elapsed > 0:
        # Sum across all fully elapsed period columns for total row
        lt_qty_sum = sum(total_row[f"{p.strftime('%Y-%m-%d')}_Sold_QTY"] 
                        for p in fully_elapsed_periods)
        lt_thb_sum = sum(total_row[f"{p.strftime('%Y-%m-%d')}_Sold_THB"] 
                        for p in fully_elapsed_periods)
        total_row['LT_Avg_Sold_QTY'] = lt_qty_sum / num_fully_elapsed
        total_row['LT_Avg_Sold_THB'] = lt_thb_sum / num_fully_elapsed
    else:
        total_row['LT_Avg_Sold_QTY'] = np.nan
        total_row['LT_Avg_Sold_THB'] = np.nan
    
    # Prev2_Avg: average of last 2 fully elapsed periods for total
    num_prev2 = len(prev2_periods)
    if num_prev2 > 0:
        prev2_qty_sum = sum(total_row[f"{p.strftime('%Y-%m-%d')}_Sold_QTY"] 
                           for p in prev2_periods)
        prev2_thb_sum = sum(total_row[f"{p.strftime('%Y-%m-%d')}_Sold_THB"] 
                           for p in prev2_periods)
        total_row['Prev2_Avg_Sold_QTY'] = prev2_qty_sum / num_prev2
        total_row['Prev2_Avg_Sold_THB'] = prev2_thb_sum / num_prev2
    else:
        total_row['Prev2_Avg_Sold_QTY'] = np.nan
        total_row['Prev2_Avg_Sold_THB'] = np.nan

    final_df.loc['Total'] = total_row

    # Debug - validate totals
    original_total = df_sale_channel['LineTotal'].sum()
    agg_total = final_df.loc['Total', 'Tot_Sold_THB']
    if not np.isclose(original_total, agg_total, rtol=1e-5):
        logger.warning("Channel-brand aggregated sales (%.2f) != original total (%.2f)", agg_total, original_total)

    return final_df

def get_brands(df_sale, df_item_master: Optional[pd.DataFrame] = None):
    """
    Unique product brands for dropdowns. When df_item_master is provided, missing line Brand
    is filled from master GroupName (same rule as prepare_sales_and_onhand_data).
    """
    if df_item_master is not None and not df_item_master.empty and 'ItemCode' in df_sale.columns:
        mb = df_item_master[['ItemCode', 'GroupName']].drop_duplicates(subset=['ItemCode'])
        mb = mb.rename(columns={'GroupName': '_MasterBrand'})
        m = df_sale.merge(mb, on='ItemCode', how='left')
        s = m['Brand'].fillna(m['_MasterBrand'])
    else:
        s = df_sale['Brand']
    brand_list = list(pd.Series(s).dropna().unique())
    brand_list = ['None' if str(brand) == 'nan' else brand for brand in brand_list]
    return brand_list

def get_channels(df_sale):
    channel_list = list(df_sale['GroupName'].unique())
    channel_list = ['None' if str(channel) == 'nan' else channel for channel in channel_list]

    return channel_list

def generate_brand_health_summary(
    df_raw_sale,
    df_raw_onhand,
    df_item_master,
    df_gpro_detail,
    # current_date=None,
    year_list=None
):
    """
    Generate brand-level health summary showing:
    - Sold quantities and THB (Master Price)
    - On-hand quantities and THB (Master Price)
    - Purchased quantities (calculated as Sold + OnHand), FOB costs, and Master Price value
    - Current stock FOB value and Master Price value
    
    NOTE: Purchased_Units is calculated as Sold_Units + OnHand_Units to ensure inventory balance.
    Purchased THB values are from actual purchase records.
    
    Returns DataFrame with brands as rows
    """

    # Prepare sales data
    df_sale = df_raw_sale.copy()
    df_sale['DocDate'] = pd.to_datetime(df_sale['DocDate'])
    
    # Filter by year_list if provided
    if year_list:
        df_sale = df_sale[df_sale['DocDate'].dt.year.isin(year_list)].copy()
    
    # Prepare on-hand data with Master Price
    df_onhand = df_raw_onhand.copy()
    
    # Remove conflicting columns if they exist
    cols_to_drop = ['Price', 'GroupName', 'Brand']
    for col in cols_to_drop:
        if col in df_onhand.columns:
            df_onhand = df_onhand.drop(columns=[col])
    
    # Merge master data for on-hand
    df_onhand = df_onhand.merge(
        df_item_master[['ItemCode', 'GroupName', 'Price']],
        on='ItemCode',
        how='left'
    )
    
    # Rename columns
    df_onhand = df_onhand.rename(columns={
        'GroupName': 'Brand',
        'Price': 'MasterPrice'
    })
    
    # Fill missing Brand values with 'Unknown'
    df_onhand['Brand'] = df_onhand['Brand'].fillna('Unknown')
    
    # Prepare purchase data with FOB costs
    df_purchase = df_gpro_detail.copy() if df_gpro_detail is not None else pd.DataFrame()
    
    if not df_purchase.empty:
        df_purchase['DocDate'] = pd.to_datetime(df_purchase['DocDate'])
        
        # Filter purchases by year_list
        if year_list:
            df_purchase = df_purchase[df_purchase['DocDate'].dt.year.isin(year_list)].copy()
        
        # Calculate FOB in THB (Price * Rate = FOB per unit in THB)
        # Note: 'Price' here is the FOB price in foreign currency
        df_purchase['FOB_THB_Unit'] = df_purchase['Price'] * df_purchase['Rate']
        df_purchase['FOB_THB_Total'] = df_purchase['FOB_THB_Unit'] * df_purchase['Quantity']
        
        # Merge brand info and Master Price from item_master
        # Use suffixes to handle the Price column conflict
        df_purchase = df_purchase.merge(
            df_item_master[['ItemCode', 'GroupName', 'Price']],
            on='ItemCode',
            how='left',
            suffixes=('_FOB', '_Master')
        )
        
        # Rename columns appropriately
        df_purchase = df_purchase.rename(columns={
            'GroupName': 'Brand',
            'Price_Master': 'MasterPrice'
        })
        
        # Calculate Master Price value for purchases
        df_purchase['Master_THB_Total'] = df_purchase['MasterPrice'].fillna(0) * df_purchase['Quantity']
    
    # ===== 1. SALES SUMMARY BY BRAND =====
    # Fill missing Brand values with 'Unknown' for sales
    df_sale['Brand'] = df_sale['Brand'].fillna('Unknown')
    
    df_sale_summary = df_sale.groupby('Brand').agg({
        'Quantity': 'sum',
        'LineTotal': 'sum'
    }).reset_index()
    df_sale_summary.columns = ['Brand', 'Sold_Units', 'Sold_THB_Master']
    
    # ===== 2. ON-HAND SUMMARY BY BRAND =====
    # Calculate OnHand THB value, handling NaN in MasterPrice
    df_onhand['OnHand_THB'] = df_onhand['OnHand'].fillna(0) * df_onhand['MasterPrice'].fillna(0)
    
    df_onhand_summary = df_onhand.groupby('Brand').agg({
        'OnHand': 'sum',
        'OnHand_THB': 'sum'
    }).reset_index()
    df_onhand_summary.columns = ['Brand', 'OnHand_Units', 'OnHand_THB_Master']
    
    # ===== 3. PURCHASE SUMMARY BY BRAND =====
    if not df_purchase.empty:
        # Fill missing Brand values
        df_purchase['Brand'] = df_purchase['Brand'].fillna('Unknown')
        
        # Calculate THB values from actual purchases (NOT units)
        df_purchase_summary = df_purchase.groupby('Brand').agg({
            'FOB_THB_Total': 'sum',
            'Master_THB_Total': 'sum'
        }).reset_index()
        df_purchase_summary.columns = ['Brand', 'Purchased_FOB_THB', 'Purchased_Master_THB']
    else:
        df_purchase_summary = pd.DataFrame(columns=['Brand', 'Purchased_FOB_THB', 'Purchased_Master_THB'])
    
    # ===== 4. CURRENT STOCK FOB VALUE =====
    # Calculate FOB value of current on-hand stock
    # We need LastPurPrc from item_master as the unit FOB cost
    if not df_purchase.empty:
        # Get average FOB cost per item from purchases
        df_fob_per_item = df_purchase.groupby('ItemCode').agg({
            'FOB_THB_Unit': 'mean'  # Average FOB cost per unit
        }).reset_index()
        df_fob_per_item.columns = ['ItemCode', 'Avg_FOB_Unit']
        
        # Merge with on-hand data
        df_onhand_fob = df_onhand.merge(
            df_fob_per_item,
            on='ItemCode',
            how='left'
        )
        
        # If no purchase history, use LastPurPrc from item_master
        df_onhand_fob = df_onhand_fob.merge(
            df_item_master[['ItemCode', 'LastPurPrc']],
            on='ItemCode',
            how='left'
        )
        
        # Use purchase FOB if available, otherwise LastPurPrc
        df_onhand_fob['FOB_Unit'] = df_onhand_fob['Avg_FOB_Unit'].fillna(
            df_onhand_fob['LastPurPrc']
        )
        
        # Calculate stock FOB value
        df_onhand_fob['Stock_FOB_THB'] = df_onhand_fob['OnHand'].fillna(0) * df_onhand_fob['FOB_Unit'].fillna(0)
        
        df_stock_fob_summary = df_onhand_fob.groupby('Brand').agg({
            'Stock_FOB_THB': 'sum'
        }).reset_index()
    else:
        # Use LastPurPrc from master
        df_onhand_fob = df_onhand.merge(
            df_item_master[['ItemCode', 'LastPurPrc']],
            on='ItemCode',
            how='left'
        )
        df_onhand_fob['Stock_FOB_THB'] = df_onhand_fob['OnHand'].fillna(0) * df_onhand_fob['LastPurPrc'].fillna(0)
        
        df_stock_fob_summary = df_onhand_fob.groupby('Brand').agg({
            'Stock_FOB_THB': 'sum'
        }).reset_index()
    
    # ===== 5. CURRENT STOCK MASTER PRICE VALUE =====
    # This is already calculated in df_onhand_summary as 'OnHand_THB_Master'
    # But let's create a separate column for clarity
    df_stock_master_summary = df_onhand_summary[['Brand', 'OnHand_THB_Master']].copy()
    df_stock_master_summary.columns = ['Brand', 'Stock_Master_THB']
    
    # ===== 6. COMBINE ALL SUMMARIES =====
    # Start with all unique brands
    all_brands = set()
    all_brands.update(df_sale_summary['Brand'].dropna())
    all_brands.update(df_onhand_summary['Brand'].dropna())
    all_brands.update(df_purchase_summary['Brand'].dropna())
    
    df_final = pd.DataFrame({'Brand': sorted(all_brands)})
    
    # Merge all summaries
    df_final = df_final.merge(df_sale_summary, on='Brand', how='left')
    df_final = df_final.merge(df_onhand_summary, on='Brand', how='left')
    df_final = df_final.merge(df_purchase_summary, on='Brand', how='left')
    df_final = df_final.merge(df_stock_fob_summary, on='Brand', how='left')
    df_final = df_final.merge(df_stock_master_summary, on='Brand', how='left')
    
    # Fill NaN with 0 for calculation
    numeric_cols = [
        'Sold_Units', 'Sold_THB_Master',
        'OnHand_Units', 'OnHand_THB_Master',
        'Purchased_FOB_THB', 'Purchased_Master_THB',
        'Stock_FOB_THB', 'Stock_Master_THB'
    ]
    df_final[numeric_cols] = df_final[numeric_cols].fillna(0)
    
    # ===== 7. CALCULATE PURCHASED_UNITS AS SOLD + ONHAND =====
    df_final['Purchased_Units'] = df_final['Sold_Units'] + df_final['OnHand_Units']
    
    # ===== 8. ADD TOTAL ROW =====
    total_row = {
        'Brand': 'TOTAL',
        'Sold_Units': df_final['Sold_Units'].sum(),
        'Sold_THB_Master': df_final['Sold_THB_Master'].sum(),
        'OnHand_Units': df_final['OnHand_Units'].sum(),
        'OnHand_THB_Master': df_final['OnHand_THB_Master'].sum(),
        'Purchased_Units': df_final['Purchased_Units'].sum(),
        'Purchased_FOB_THB': df_final['Purchased_FOB_THB'].sum(),
        'Purchased_Master_THB': df_final['Purchased_Master_THB'].sum(),
        'Stock_FOB_THB': df_final['Stock_FOB_THB'].sum(),
        'Stock_Master_THB': df_final['Stock_Master_THB'].sum()
    }
    
    df_final = pd.concat([df_final, pd.DataFrame([total_row])], ignore_index=True)
    
    # ===== 9. REORDER COLUMNS FOR LOGICAL FLOW =====
    column_order = [
        'Brand',
        'Purchased_Units', 'Purchased_FOB_THB', 'Purchased_Master_THB',
        'Sold_Units', 'Sold_THB_Master',
        'OnHand_Units', 'OnHand_THB_Master',
        'Stock_FOB_THB', 'Stock_Master_THB'
    ]
    df_final = df_final[column_order]
    
    # Round numeric columns for readability
    numeric_cols_final = [col for col in df_final.columns if col != 'Brand']
    for col in numeric_cols_final:
        df_final[col] = df_final[col].round(2)
    
    return df_final

def generate_brand_product_profit_loss(df_sale, df_onhand, df_grpo_detail, brand_name, year_list=None):
    """
    Generate a comprehensive product-level analysis for a specific brand showing:
    - Quantities: Brought (purchased), Sold, OnHand
    - Cost Information: FOB price, currency, exchange rate
    - Values: OnHand value in FOB THB, Sale value (Master Price), Sale value (Average Sold Price)
    - Profit/Loss calculations
    
    Parameters:
    -----------
    df_sale : DataFrame
        Sales transaction data
    df_onhand : DataFrame
        Current inventory on-hand
    df_grpo_detail : DataFrame
        Goods received/purchase order details with cost information
    brand_name : str
        Brand name to filter (use 'None' for items with no brand)
    
    Returns:
    --------
    DataFrame with columns:
        - ItemCode
        - Description
        - Brought_QTY: Total quantity purchased
        - Sold_QTY: Total quantity sold
        - OnHand_QTY: Current inventory
        - FOB_Price: Cost per unit in original currency
        - Currency: Original currency
        - Exchange_Rate: Rate used for conversion
        - FOB_Price_THB: Cost per unit in THB
        - OnHand_Value_FOB_THB: Current inventory value at cost
        - Master_Price: Retail price per unit
        - Sale_Value_Master_Price: OnHand value at retail price
        - Avg_Sold_Price: Average actual selling price
        - Sale_Value_Avg_Price: OnHand value at average sold price
        - Total_Cost_THB: Total cost of goods brought
        - Total_Revenue_THB: Total revenue from sales
        - Profit_Loss_THB: Total profit or loss
        - Profit_Margin_%: Profit margin percentage
    """
    
    # Handle brand filtering
    if brand_name == 'None':
        df_sale_brand = df_sale[df_sale['Brand'].isna()].copy()
        df_onhand_brand = df_onhand[df_onhand['Brand'].isna()].copy()
        display_brand_name = 'None (NaN values)'
    else:
        df_sale['Brand'] = df_sale['Brand'].fillna('Unknown')
        df_sale_brand = df_sale[df_sale['Brand'] == brand_name].copy()
        df_onhand_brand = df_onhand[df_onhand['Brand'] == brand_name].copy()
        display_brand_name = brand_name
    
    # Apply year filter to sales and GRPO data (on-hand is always current snapshot)
    if year_list:
        if "DocDate" in df_sale_brand.columns:
            df_sale_brand = df_sale_brand[df_sale_brand["DocDate"].dt.year.isin(year_list)].copy()
        if "DocDate" in df_grpo_detail.columns:
            df_grpo_detail = df_grpo_detail[df_grpo_detail["DocDate"].dt.year.isin(year_list)].copy()

    # Dedup sales: same (DocEntry, ItemCode) across multiple warehouse locations
    # is the SAME transaction — must not be double-counted.
    # This matches the dedup logic used in brand_list_metrics / channel matrix.
    if "Period" not in df_sale_brand.columns:
        df_sale_brand["DocDate"] = pd.to_datetime(df_sale_brand["DocDate"], errors="coerce")
        df_sale_brand["Period"] = df_sale_brand["DocDate"].dt.to_period("M").dt.start_time
    dedup_cols = ["DocEntry", "ItemCode"]
    if "Period" in df_sale_brand.columns:
        dedup_cols.append("Period")
    if "GroupName" in df_sale_brand.columns:
        dedup_cols.append("GroupName")
    df_sale_brand = df_sale_brand.drop_duplicates(subset=dedup_cols)

    # Get all unique items for this brand from all sources
    items_from_sale = set(df_sale_brand['ItemCode'].dropna().unique())
    items_from_onhand = set(df_onhand_brand['ItemCode'].dropna().unique())
    all_items = items_from_sale.union(items_from_onhand)
    
    if not all_items:
        logger.warning("No items found for brand: %s", display_brand_name)
        return pd.DataFrame()
    
    # Initialize result list
    results = []
    
    for item_code in all_items:
        item_data = {}
        item_data['ItemCode'] = item_code
        
        # Get description (prefer from onhand, fallback to sale)
        desc_onhand = df_onhand_brand[df_onhand_brand['ItemCode'] == item_code]['ItemName'].iloc[0] \
            if not df_onhand_brand[df_onhand_brand['ItemCode'] == item_code].empty else None
        desc_sale = df_sale_brand[df_sale_brand['ItemCode'] == item_code]['ItemName'].iloc[0] \
            if not df_sale_brand[df_sale_brand['ItemCode'] == item_code].empty else None
        item_data['Description'] = desc_onhand if desc_onhand else desc_sale
        
        # === BROUGHT (Purchased) Quantity ===
        # Filter gpro_detail for goods receipt (TargetType = 20 means Goods Receipt PO)
        # or use BaseType to identify the transaction type
        df_gpro_item = df_grpo_detail[
            (df_grpo_detail['ItemCode'] == item_code) &
            (df_grpo_detail['Quantity'] > 0)
        ].copy()
        
        # Sum all positive quantities (purchases/receipts)
        brought_qty = df_gpro_item['Quantity'].sum() if not df_gpro_item.empty else 0
        item_data['Brought_QTY'] = brought_qty
        
        # === SOLD Quantity ===
        df_sale_item = df_sale_brand[df_sale_brand['ItemCode'] == item_code]
        sold_qty = df_sale_item['Quantity'].sum() if not df_sale_item.empty else 0
        item_data['Sold_QTY'] = sold_qty
        
        # === ONHAND Quantity ===
        df_onhand_item = df_onhand_brand[df_onhand_brand['ItemCode'] == item_code]
        onhand_qty = df_onhand_item['OnHand'].sum() if not df_onhand_item.empty else 0
        item_data['OnHand_QTY'] = onhand_qty
        
        # === COST INFORMATION (FOB) ===
        if not df_gpro_item.empty:
            # Filter out rows with zero or null quantities
            df_gpro_item_valid = df_gpro_item[
                (df_gpro_item['Quantity'] > 0) & 
                (df_gpro_item['Quantity'].notna()) &
                (df_gpro_item['Price'].notna()) &
                (df_gpro_item['Rate'].notna())
            ].copy()
            
            if not df_gpro_item_valid.empty:
                # Calculate FOB Price in THB for each record first
                df_gpro_item_valid['FOB_Price_THB_Record'] = df_gpro_item_valid['Price'] * df_gpro_item_valid['Rate']
                
                # Weighted average FOB Price in THB
                total_qty = df_gpro_item_valid['Quantity'].sum()
                weighted_fob_thb = (
                    (df_gpro_item_valid['FOB_Price_THB_Record'] * df_gpro_item_valid['Quantity']).sum() / total_qty
                    if total_qty > 0 else 0.0
                )
                
                # Get most recent record for currency and rate display
                latest_record = df_gpro_item_valid.sort_values('DocDate', ascending=False).iloc[0]
                
                item_data['FOB_Price'] = round(latest_record['Price'], 5)
                item_data['Currency'] = latest_record['Currency']
                item_data['Exchange_Rate'] = round(latest_record['Rate'], 4)
                item_data['FOB_Price_THB'] = round(weighted_fob_thb, 2)
            else:
                item_data['FOB_Price'] = 0
                item_data['Currency'] = None
                item_data['Exchange_Rate'] = 0
                item_data['FOB_Price_THB'] = 0
        else:
            item_data['FOB_Price'] = 0
            item_data['Currency'] = None
            item_data['Exchange_Rate'] = 0
            item_data['FOB_Price_THB'] = 0
        
        # === ONHAND VALUE at FOB Cost ===
        item_data['OnHand_Value_FOB_THB'] = round(onhand_qty * item_data['FOB_Price_THB'], 2)
        
        # === MASTER PRICE (Retail Price) ===
        master_price = df_onhand_item['Master Price'].iloc[0] \
            if not df_onhand_item.empty and pd.notna(df_onhand_item['Master Price'].iloc[0]) else 0
        item_data['Master_Price'] = master_price
        
        # === SALE VALUE at Master Price ===
        item_data['Sale_Value_Master_Price'] = round(onhand_qty * master_price, 2)
        
        # === AVERAGE SOLD PRICE (Actual) ===
        if not df_sale_item.empty and sold_qty > 0:
            avg_sold_price = df_sale_item['Price'].mean()
            item_data['Avg_Sold_Price'] = round(avg_sold_price, 2)
        else:
            item_data['Avg_Sold_Price'] = 0
        
        # === SALE VALUE at Average Sold Price ===
        item_data['Sale_Value_Avg_Price'] = round(onhand_qty * item_data['Avg_Sold_Price'], 2)
        
        # === PROFIT/LOSS CALCULATIONS ===
        # Total cost of goods brought
        item_data['Total_Cost_THB'] = round(brought_qty * item_data['FOB_Price_THB'], 2)

        # Total revenue from sales (using Master Price)
        total_revenue_master = sold_qty * master_price
        item_data['Total_Revenue_THB'] = round(total_revenue_master, 2)

        # Actual revenue from sales (using LineTotal — what customers actually paid)
        actual_revenue = df_sale_item['LineTotal'].sum() if not df_sale_item.empty else 0
        item_data['Actual_Revenue_THB'] = round(float(actual_revenue), 2)

        # === GP COMMISSION (consignment sales) ===
        # Uses shared helper: compute_gp_commission()
        gp_per_row = compute_gp_commission(df_sale_item)
        gp_commission = float(gp_per_row.sum())
        if not df_sale_item.empty and 'Sale Type' in df_sale_item.columns:
            consignment_mask = df_sale_item['Sale Type'] == 'Consignment'
            consignment_revenue = float(df_sale_item.loc[consignment_mask, 'LineTotal'].sum())
            credit_revenue = float(df_sale_item.loc[~consignment_mask, 'LineTotal'].sum())
        else:
            consignment_revenue = 0.0
            credit_revenue = float(actual_revenue)

        item_data['GP_Commission_THB'] = round(float(gp_commission), 2)
        item_data['Consignment_Revenue_THB'] = round(float(consignment_revenue), 2)
        item_data['Credit_Revenue_THB'] = round(float(credit_revenue), 2)

        # Net Revenue = Actual Revenue − GP Commission
        net_revenue = float(actual_revenue) - float(gp_commission)
        item_data['Net_Revenue_THB'] = round(net_revenue, 2)

        # Profit/Loss = Net Revenue − Cost of goods sold (FOB)
        # For Credit sales: P/L = Revenue − COGS
        # For Consignment sales: P/L = Revenue − COGS − GP Commission
        # Combined: P/L = Actual Revenue − COGS − GP Commission = Net Revenue − COGS
        cost_of_goods_sold = sold_qty * item_data['FOB_Price_THB']
        item_data['Profit_Loss_THB'] = round(net_revenue - cost_of_goods_sold, 2)

        # Profit Margin % (based on actual revenue, after GP commission)
        if float(actual_revenue) > 0:
            item_data['Profit_Margin_%'] = round((item_data['Profit_Loss_THB'] / float(actual_revenue)) * 100, 2)
        else:
            item_data['Profit_Margin_%'] = 0
        
        results.append(item_data)
    
    # Create DataFrame
    result_df = pd.DataFrame(results)
    
    # Sort by ItemCode
    result_df = result_df.sort_values('ItemCode').reset_index(drop=True)
    
    # Add totals row
    total_actual_rev = result_df['Actual_Revenue_THB'].sum()
    total_pl = result_df['Profit_Loss_THB'].sum()
    total_row = {
        'ItemCode': 'TOTAL',
        'Description': f'Total for {display_brand_name}',
        'Brought_QTY': result_df['Brought_QTY'].sum(),
        'Sold_QTY': result_df['Sold_QTY'].sum(),
        'OnHand_QTY': result_df['OnHand_QTY'].sum(),
        'FOB_Price': np.nan,
        'Currency': '',
        'Exchange_Rate': np.nan,
        'FOB_Price_THB': np.nan,
        'OnHand_Value_FOB_THB': result_df['OnHand_Value_FOB_THB'].sum(),
        'Master_Price': np.nan,
        'Sale_Value_Master_Price': result_df['Sale_Value_Master_Price'].sum(),
        'Avg_Sold_Price': np.nan,
        'Sale_Value_Avg_Price': result_df['Sale_Value_Avg_Price'].sum(),
        'Total_Cost_THB': result_df['Total_Cost_THB'].sum(),
        'Total_Revenue_THB': result_df['Total_Revenue_THB'].sum(),
        'Actual_Revenue_THB': total_actual_rev,
        'GP_Commission_THB': result_df['GP_Commission_THB'].sum(),
        'Consignment_Revenue_THB': result_df['Consignment_Revenue_THB'].sum(),
        'Credit_Revenue_THB': result_df['Credit_Revenue_THB'].sum(),
        'Net_Revenue_THB': result_df['Net_Revenue_THB'].sum(),
        'Profit_Loss_THB': total_pl,
        'Profit_Margin_%': round((total_pl / total_actual_rev * 100)
                                 if total_actual_rev > 0 else 0, 2)
    }
    
    result_df = pd.concat([result_df, pd.DataFrame([total_row])], ignore_index=True)
    
    # Calculate inventory discrepancy
    total_brought = total_row['Brought_QTY']
    total_sold = total_row['Sold_QTY']
    total_onhand = total_row['OnHand_QTY']
    expected_onhand = total_brought - total_sold
    discrepancy = total_onhand - expected_onhand
    
    logger.debug(
        "Brand Product Analysis for %s: %d items, brought=%.0f, sold=%.0f, onhand=%.0f, expected=%.0f, discrepancy=%+.0f, P/L=฿%,.2f (%.2f%%)",
        display_brand_name, len(results), total_brought, total_sold, total_onhand,
        expected_onhand, discrepancy, total_row['Profit_Loss_THB'], total_row['Profit_Margin_%']
    )
    if abs(discrepancy) > 0.01:
        logger.debug("  Inventory discrepancy: possible returns, damages, transfers, or data sync issues")
    
    return result_df
   
def analyze_brand_item_locations(brand_name, df_item_master, df_raw_onhand, df_raw_sale, df_gpro_detail, df_whs_code):
    # --- Filter items belonging to the brand ---
    brand_items_df = df_item_master[df_item_master['GroupName'] == brand_name][['ItemCode','ItemName','Price','LastPurPrc']]
    brand_items_df = brand_items_df.rename(columns={'Price':'Master Price','LastPurPrc':'Last Purchase Price'})
    brand_items = brand_items_df['ItemCode'].unique()
    
    if len(brand_items) == 0:
        logger.warning("No items found for brand '%s'", brand_name)
        return [pd.DataFrame(), pd.DataFrame()]
    
    # --- Purchases ---
    df_purchase = df_gpro_detail[df_gpro_detail['ItemCode'].isin(brand_items)].copy()
    df_purchase['TotalTHB'] = df_purchase['Quantity'] * df_purchase['Price'] * df_purchase['Rate']
    
    purchase_by_item = df_purchase.groupby('ItemCode').agg(
        **{
            'Total Purchased Units':('Quantity','sum'),
            'TotalFOBTHB':('TotalTHB','sum'),
            'FOB Price in Currency':('Price','mean'),
            'Purchase Currency':('Currency', lambda x: x.iloc[0] if len(x)>0 else np.nan),
            'Purchase Exchange Rate':('Rate','mean')
        }
    ).reset_index()
    
    purchase_by_item['FOB Price THB'] = purchase_by_item['TotalFOBTHB'] / purchase_by_item['Total Purchased Units']
    purchase_by_item['Landed Cost THB'] = purchase_by_item['FOB Price THB'] * 1.2
    
    # --- Sales ---
    df_sale = df_raw_sale[df_raw_sale['ItemCode'].isin(brand_items)].copy()
    df_sale['Total Sold Master THB'] = df_sale['Quantity'] * df_sale['Master Price']
    sales_by_item = df_sale.groupby('ItemCode').agg(
        **{
            'Total Sold Units':('Quantity','sum'),
            'Total Sold Master THB':('Total Sold Master THB','sum')
        }
    ).reset_index()
    
    # --- OnHand ---
    df_onhand = df_raw_onhand[df_raw_onhand['ItemCode'].isin(brand_items)].copy()
    df_onhand['Total OnHand Master THB'] = df_onhand['OnHand'] * df_onhand['Price']
    
    onhand_by_item = df_onhand.groupby('ItemCode').agg(
        **{
            'Total OnHand Units':('OnHand','sum'),
            'Total OnHand Master THB':('Total OnHand Master THB','sum')
        }
    ).reset_index()
    
    # --- Merge master info ---
    df_brand_item_summary = brand_items_df \
        .merge(purchase_by_item, on='ItemCode', how='left') \
        .merge(sales_by_item, on='ItemCode', how='left') \
        .merge(onhand_by_item, on='ItemCode', how='left')
    
    # Fill NaN with 0 for numeric fields
    numeric_fill_cols = ['Master Price','FOB Price THB','Landed Cost THB','FOB Price in Currency','Purchase Exchange Rate',
                         'Total Purchased Units','Total Sold Units','Total OnHand Units','Total OnHand Master THB',
                         'Total Sold Master THB']
    for col in numeric_fill_cols:
        if col not in df_brand_item_summary.columns:
            df_brand_item_summary[col] = 0
    df_brand_item_summary[numeric_fill_cols] = df_brand_item_summary[numeric_fill_cols].fillna(0)
    
    # --- Calculate additional metrics ---
    df_brand_item_summary['Total OnHand Landed Cost'] = df_brand_item_summary['Landed Cost THB'] * df_brand_item_summary['Total OnHand Units']
    df_brand_item_summary['Ratio Units'] = df_brand_item_summary.apply(
        lambda row: row['Total Sold Units']/row['Total OnHand Units'] if row['Total OnHand Units']>0 else np.inf if row['Total Sold Units']>0 else 0, axis=1
    )
    df_brand_item_summary['Ratio THB'] = df_brand_item_summary.apply(
        lambda row: row['Total Sold Master THB']/row['Total OnHand Master THB'] if row['Total OnHand Master THB']>0 else np.inf if row['Total Sold Master THB']>0 else 0, axis=1
    )
    
    # --- Warehouse level quantities ---
    onhand_whs = df_onhand.merge(df_whs_code, on='WhsCode', how='left')
    onhand_pivot = onhand_whs.pivot_table(index='ItemCode', columns='WhsName', values='OnHand', fill_value=0)
    onhand_pivot.columns = [f'OnHand {col}' for col in onhand_pivot.columns]
    
    sales_whs = df_sale.merge(df_whs_code, on='WhsCode', how='left')
    sold_pivot = sales_whs.pivot_table(index='ItemCode', columns='WhsName', values='Quantity', fill_value=0)
    sold_pivot.columns = [f'Sold {col}' for col in sold_pivot.columns]
    
    df_brand_item_summary = df_brand_item_summary.merge(onhand_pivot, left_on='ItemCode', right_index=True, how='left') \
                                                 .merge(sold_pivot, left_on='ItemCode', right_index=True, how='left')
    
    # Reorder columns
    cols_order = ['ItemCode','ItemName','Master Price','FOB Price THB','Landed Cost THB','FOB Price in Currency',
                  'Purchase Currency','Purchase Exchange Rate','Total Purchased Units','Total Sold Units',
                  'Total OnHand Units','Total OnHand Landed Cost','Total Sold Master THB','Total OnHand Master THB',
                  'Ratio Units','Ratio THB']
    whs_cols = [c for c in df_brand_item_summary.columns if c not in cols_order]
    df_brand_item_summary = df_brand_item_summary[cols_order + sorted(whs_cols)]
    
    # Round numeric columns
    round_cols = [c for c in df_brand_item_summary.columns if c not in ['ItemCode','ItemName','Purchase Currency']]
    df_brand_item_summary[round_cols] = df_brand_item_summary[round_cols].round(2)
    
    # --- df_brand_locations_summary ---
    loc_summary = pd.merge(df_onhand, df_sale[['ItemCode','Quantity','Total Sold Master THB','WhsCode']], on=['ItemCode','WhsCode'], how='outer')
    loc_summary = loc_summary.merge(df_whs_code, on='WhsCode', how='left')
    loc_summary = loc_summary.fillna(0)
    
    df_brand_locations_summary = loc_summary.groupby('WhsName').agg(
        **{
            'Total Sold Units':('Quantity','sum'),
            'Total OnHand Units':('OnHand','sum'),
            'Total Sold Master THB':('Total Sold Master THB','sum'),
            'Total OnHand Master THB':('Total OnHand Master THB','sum')
        }
    ).reset_index()
    
    df_brand_locations_summary['Ratio Units'] = df_brand_locations_summary.apply(
        lambda row: row['Total Sold Units']/row['Total OnHand Units'] if row['Total OnHand Units']>0 else np.inf if row['Total Sold Units']>0 else 0, axis=1
    )
    df_brand_locations_summary['Ratio THB'] = df_brand_locations_summary.apply(
        lambda row: row['Total Sold Master THB']/row['Total OnHand Master THB'] if row['Total OnHand Master THB']>0 else np.inf if row['Total Sold Master THB']>0 else 0, axis=1
    )
    
    df_brand_locations_summary.rename(columns={'WhsName':'Location'}, inplace=True)
    
    # Round numeric columns
    loc_round_cols = [c for c in df_brand_locations_summary.columns if c not in ['Location']]
    df_brand_locations_summary[loc_round_cols] = df_brand_locations_summary[loc_round_cols].round(2)
    
    # Filter only active locations
    df_brand_locations_summary = df_brand_locations_summary[
        (df_brand_locations_summary['Total Sold Units']>0) | (df_brand_locations_summary['Total OnHand Units']>0)
    ].reset_index(drop=True)
    
    return [df_brand_item_summary, df_brand_locations_summary]

def analyse_brand_item_channels(brand_name,
                        df_item_master,
                        df_raw_onhand,
                        df_raw_sale,
                        df_gpro_detail,
                        df_whs_code):
    # 1. Filter items for the brand
    df_items = df_item_master[df_item_master['GroupName'] == brand_name].copy()
    df_items = df_items[['ItemCode', 'ItemName', 'Price']].rename(columns={'Price': 'Master Price'})

    # 2. Prepare OnHand data per customer
    df_onhand = df_raw_onhand.copy()
    # Merge to get warehouse names
    df_onhand = df_onhand.merge(df_whs_code, how='left', left_on='WhsCode', right_on='WhsCode')
    # Group by ItemCode and Customer (BP Code / GroupName)
    df_onhand_cust = df_onhand.groupby(['ItemCode', 'GroupName'])['OnHand'].sum().reset_index()
    df_onhand_cust = df_onhand_cust.rename(columns={'OnHand': 'OnHand Units'})

    # 3. Prepare Sales data per customer
    df_sale = df_raw_sale.copy()
    df_sale_cust = df_sale.groupby(['ItemCode', 'GroupName'])['Quantity'].sum().reset_index()
    df_sale_cust = df_sale_cust.rename(columns={'Quantity': 'Sold Units'})

    # 4. Prepare Purchase data
    df_purchase = df_gpro_detail.copy()
    df_purchase = df_purchase.groupby('ItemCode')['Quantity'].sum().reset_index()
    df_purchase = df_purchase.rename(columns={'Quantity': 'Purchased Units'})

    # 5. Merge to create item summary
    df_item_summary = df_items.merge(df_purchase, how='left', on='ItemCode')
    df_item_summary = df_item_summary.merge(df_sale_cust.groupby('ItemCode')['Sold Units'].sum().reset_index(), how='left', on='ItemCode')
    df_item_summary = df_item_summary.merge(df_onhand_cust.groupby('ItemCode')['OnHand Units'].sum().reset_index(), how='left', on='ItemCode')

    # Fill NaN with 0
    df_item_summary[['Purchased Units', 'Sold Units', 'OnHand Units']] = df_item_summary[['Purchased Units', 'Sold Units', 'OnHand Units']].fillna(0)

    # Calculate ratios and Master THB
    df_item_summary['Ratio Units'] = np.where(df_item_summary['Sold Units'] + df_item_summary['OnHand Units'] > 0,
                                              df_item_summary['Sold Units'] / (df_item_summary['Sold Units'] + df_item_summary['OnHand Units']),
                                              0)
    df_item_summary['Total Sold Master THB'] = df_item_summary['Sold Units'] * df_item_summary['Master Price']
    df_item_summary['Total OnHand Master THB'] = df_item_summary['OnHand Units'] * df_item_summary['Master Price']

    # Round decimals
    df_item_summary[['Master Price','Purchased Units','Sold Units','OnHand Units','Ratio Units','Total Sold Master THB','Total OnHand Master THB']] = \
        df_item_summary[['Master Price','Purchased Units','Sold Units','OnHand Units','Ratio Units','Total Sold Master THB','Total OnHand Master THB']].round(2)

    # 6. Add columns for each customer
    customer_list = df_onhand_cust['GroupName'].unique()
    for cust in customer_list:
        onhand_cust = df_onhand_cust[df_onhand_cust['GroupName'] == cust][['ItemCode','OnHand Units']]
        sold_cust = df_sale_cust[df_sale_cust['GroupName'] == cust][['ItemCode','Sold Units']]
        df_item_summary = df_item_summary.merge(onhand_cust.rename(columns={'OnHand Units': f'{cust} OnHand Units'}), on='ItemCode', how='left')
        df_item_summary = df_item_summary.merge(sold_cust.rename(columns={'Sold Units': f'{cust} Sold Units'}), on='ItemCode', how='left')
        # Fill NaN
        df_item_summary[[f'{cust} OnHand Units', f'{cust} Sold Units']] = df_item_summary[[f'{cust} OnHand Units', f'{cust} Sold Units']].fillna(0)

    # 7. Prepare location summary
    df_location_summary = pd.DataFrame(columns=['Customer Name','Total Sold Units','Total OnHand Units','Total Sold Master THB','Total OnHand Master THB','Ratio THB'])
    for cust in customer_list:
        sold = df_sale_cust[df_sale_cust['GroupName']==cust]['Sold Units'].sum()
        onhand = df_onhand_cust[df_onhand_cust['GroupName']==cust]['OnHand Units'].sum()
        # Get Master Price weighted THB
        sold_thb = df_item_summary[df_item_summary['ItemCode'].isin(df_sale_cust[df_sale_cust['GroupName']==cust]['ItemCode'])].apply(
            lambda x: x[f'{cust} Sold Units'] * x['Master Price'], axis=1).sum()
        onhand_thb = df_item_summary[df_item_summary['ItemCode'].isin(df_onhand_cust[df_onhand_cust['GroupName']==cust]['ItemCode'])].apply(
            lambda x: x[f'{cust} OnHand Units'] * x['Master Price'], axis=1).sum()
        ratio_thb = sold_thb / onhand_thb if onhand_thb > 0 else 0
        df_location_summary = pd.concat([df_location_summary, pd.DataFrame([{
            'Customer Name': cust,
            'Total Sold Units': sold,
            'Total OnHand Units': onhand,
            'Total Sold Master THB': round(sold_thb,2),
            'Total OnHand Master THB': round(onhand_thb,2),
            'Ratio THB': round(ratio_thb,2)
        }])], ignore_index=True)

    return [df_item_summary, df_location_summary]

def generate_store_health_summary(
    df_sale,
    df_onhand,
    df_item_master,
    df_whs_code,
    period_type='monthly',
    current_date=None,
    year_list=None
):
    """
    Summarizes sales and on-hand data per store (warehouse).
    
    df_sale: raw sales data (with DocDate, Quantity, LineTotal, ItemCode, WhsCode)
    df_onhand: raw on-hand data (with ItemCode, OnHand, WhsCode)
    df_whs_code: warehouse code -> warehouse name mapping (WhsCode, WhsName)
    df_item_master: master item data (ItemCode, Price)
    period_type: 'monthly' or 'weekly'
    current_date: reference date (str or datetime)
    year_list: list of years to include in the summary
    """

    if df_whs_code is None or df_whs_code.empty:
        raise ValueError("df_whs_code is required for store health summary")

    df_sale = df_sale.copy()
    df_onhand = df_onhand.copy()

    now = pd.Timestamp.now() if current_date is None else pd.to_datetime(current_date)

    df_sale['DocDate'] = pd.to_datetime(df_sale['DocDate'], errors='coerce')
    df_sale = df_sale[df_sale['DocDate'] <= now].copy()

    # Create period column
    if period_type == 'monthly':
        df_sale['Period'] = df_sale['DocDate'].dt.to_period('M').dt.start_time
        current_period_start = pd.Timestamp(now.year, now.month, 1)
        def _is_fully_elapsed(p): return p < current_period_start
    elif period_type == 'weekly':
        df_sale['Period'] = df_sale['DocDate'].dt.to_period('W-MON').dt.start_time
        current_period_start = now.to_period('W-MON').start_time
        def _is_fully_elapsed(p): return p < current_period_start
    else:
        raise ValueError("period_type must be 'monthly' or 'weekly'")

    # Filter by year_list
    if year_list:
        df_sale = df_sale[df_sale['Period'].dt.year.isin(year_list)].copy()
        if df_sale.empty:
            logger.warning("No sales data for years: %s", year_list)
            return pd.DataFrame()

    # Merge warehouse names
    df_sale = df_sale.merge(df_whs_code, on='WhsCode', how='left')

    # Apply location consolidation (e.g., CT-ลาดพร้าว GP25/GP33 -> CT-ลาดพร้าว)
    from app.utils.location_consolidation import add_consolidated_column
    _whs_lookup = dict(zip(
        df_whs_code["WhsCode"].astype(str).str.strip(),
        df_whs_code["WhsName"].astype(str),
    ))
    df_sale = add_consolidated_column(df_sale, _whs_lookup)
    df_sale["WhsName"] = df_sale["ConsolidatedLocation"]

    # Merge on-hand price
    if 'Price' in df_item_master.columns:
        df_item_master = df_item_master.rename(columns={'Price': 'Master Price'})
    else:
        raise KeyError("df_item_master must contain column 'Price'")

    df_onhand = df_onhand.merge(
        df_item_master[['ItemCode', 'Master Price']],
        on='ItemCode',
        how='left'
    )

    # Filter out rows missing OnHand or Master Price
    df_onhand_filtered = df_onhand.dropna(subset=['OnHand', 'Master Price']).copy()
    if df_onhand_filtered.empty:
        onhand_units_snapshot = 0.0
        onhand_thb_snapshot = 0.0
    else:
        df_onhand_filtered['OnHand_THB'] = df_onhand_filtered['OnHand'] * df_onhand_filtered['Master Price']
        # Apply consolidation to on-hand so we group by consolidated location
        df_onhand_filtered = add_consolidated_column(df_onhand_filtered, _whs_lookup)
        onhand_units_snapshot = df_onhand_filtered.groupby('ConsolidatedLocation')['OnHand'].sum()
        onhand_thb_snapshot = df_onhand_filtered.groupby('ConsolidatedLocation')['OnHand_THB'].sum()

    # Aggregate sales by store (now using consolidated location names)
    df_agg = df_sale.groupby(['WhsName','Period']).agg(
        Quantity=('Quantity','sum'),
        LineTotal=('LineTotal','sum')
    ).reset_index()

    # Pivot for period columns
    qty_pivot = df_agg.pivot(index='WhsName', columns='Period', values='Quantity').fillna(0)
    thb_pivot = df_agg.pivot(index='WhsName', columns='Period', values='LineTotal').fillna(0)

    periods_sorted_asc = sorted(qty_pivot.columns)
    fully_elapsed_periods = [p for p in periods_sorted_asc if _is_fully_elapsed(p)]

    # Build onhand matrices
    onhand_units_df = pd.DataFrame(0, index=qty_pivot.index, columns=periods_sorted_asc, dtype=float)
    onhand_thb_df = pd.DataFrame(0, index=qty_pivot.index, columns=periods_sorted_asc, dtype=float)

    # Assign snapshot to the last fully elapsed period
    # Use consolidated location name to look up on-hand (summed across sub-codes)
    if fully_elapsed_periods:
        anchor_period = fully_elapsed_periods[-1]
        for whs in qty_pivot.index:
            oh_units = onhand_units_snapshot.get(whs, 0) if not isinstance(onhand_units_snapshot, float) else 0
            oh_thb = onhand_thb_snapshot.get(whs, 0) if not isinstance(onhand_thb_snapshot, float) else 0
            put_idx = periods_sorted_asc.index(anchor_period)
            for i in range(put_idx, len(periods_sorted_asc)):
                onhand_units_df.iloc[onhand_units_df.index.get_loc(whs), i] = oh_units
                onhand_thb_df.iloc[onhand_thb_df.index.get_loc(whs), i] = oh_thb

    # Build final dataframe
    final_data = {}
    for p in periods_sorted_asc:
        key = p.strftime('%Y-%m-%d')
        final_data[f"{key}_Sold_QTY"] = qty_pivot[p]
        final_data[f"{key}_Sold_THB"] = thb_pivot[p]
        final_data[f"{key}_OnHand_QTY"] = onhand_units_df[p]
        final_data[f"{key}_OnHand_THB"] = onhand_thb_df[p]

    final_df = pd.DataFrame(final_data, index=qty_pivot.index)

    # Totals across periods
    final_df['Tot_Sold_QTY'] = final_df[[f"{p.strftime('%Y-%m-%d')}_Sold_QTY" for p in periods_sorted_asc]].sum(axis=1)
    final_df['Tot_Sold_THB'] = final_df[[f"{p.strftime('%Y-%m-%d')}_Sold_THB" for p in periods_sorted_asc]].sum(axis=1)
    final_df['Tot_OnHand_QTY'] = final_df[[f"{p.strftime('%Y-%m-%d')}_OnHand_QTY" for p in periods_sorted_asc]].iloc[:, -1]
    final_df['Tot_OnHand_THB'] = final_df[[f"{p.strftime('%Y-%m-%d')}_OnHand_THB" for p in periods_sorted_asc]].iloc[:, -1]

    # Add Total row
    total_row = final_df.sum(numeric_only=True)
    final_df.loc['Total'] = total_row

    return final_df

def extract_date_from_filename(filename: str):
    """
    Extract date from filename in format (YYYYMMDD)
    and return as Python datetime object.
    """
    pattern = r"\((\d{8})\)"
    match = re.search(pattern, filename)
    
    if not match:
        return None
    
    date_str = match.group(1)
    return datetime.strptime(date_str, "%Y%m%d")

def summarize_sales_onhand_by_location(sale_data_file_name, df_sale, df_onhand, df_whs_code, df_item_master):
    """
    Summarize lifetime and yearly sales value at Master Price
    by WhsName (full WhsCode join — no truncation).

    Output columns:
    - Lifetime Master Sale Value
    - Master Sale Value <Year> (one column per year)
    """
    if df_whs_code is None or df_whs_code.empty:
        raise ValueError("df_whs_code is required for location summary")
    if df_item_master is None or df_item_master.empty:
        raise ValueError("df_item_master is required for location summary")

    df_s = df_sale.copy()
    df_s["WhsCode"] = df_s["WhsCode"].astype(str).str.strip()

    df_s = df_s.merge(
        df_whs_code[['WhsCode', 'WhsName']],
        on='WhsCode',
        how='left'
    )

    df_oh = df_onhand.copy()
    df_oh["WhsCode"] = df_oh["WhsCode"].astype(str).str.strip()

    df_oh = df_oh.merge(
        df_item_master[["ItemCode", "Price"]].rename(columns={"Price": "Price Master"}),
        on="ItemCode",
        how="left"
    )

    df_oh = df_oh.merge(
        df_whs_code[['WhsCode', 'WhsName']],
        on='WhsCode',
        how='left'
    )

    snap = extract_date_from_filename(sale_data_file_name) if sale_data_file_name else None
    if snap is None:
        df_s["DocDate"] = pd.to_datetime(df_s["DocDate"], errors="coerce")
        mx = df_s["DocDate"].max()
        if pd.isna(mx):
            raise ValueError("Cannot infer snapshot date: filename has no (YYYYMMDD) and sale dates are empty")
        current_year, current_month = int(mx.year), int(mx.month)
    else:
        current_year, current_month = snap.year, snap.month
    
    df_oh["Master Stock Value"] = df_oh["Price Master"] * df_oh["OnHand"]
    
    # -----------------------------
    # Lifetime sales (all years)
    # -----------------------------
    onhand_master_value_by_whs = (
        df_oh.groupby("WhsName")["Master Stock Value"]
        .sum()
        .to_frame("Onhand Master Value")
    )
    
    # Ensure datetime & extract year
    df_s["DocDate"] = pd.to_datetime(df_s["DocDate"], errors="coerce")
    df_s["Year"] = df_s["DocDate"].dt.year
    
    # Ensure numeric columns
    numeric_cols = ["Quantity", "Price Master"]
    df_s[numeric_cols] = df_s[numeric_cols].apply(pd.to_numeric, errors="coerce")

    # Calculate Master Sale Value
    df_s["Master Sale Value"] = df_s["Quantity"] * df_s["Price Master"]

    # -----------------------------
    # Lifetime sales (all years)
    # -----------------------------
    lifetime_sales = (
        df_s.groupby("WhsName")["Master Sale Value"]
        .sum()
        .to_frame("Lifetime Master Sale Value")
    )
    
    
    # -----------------------------
    # Yearly sales (pivot)
    # -----------------------------
    yearly_sales = (
        df_s.pivot_table(
            index="WhsName",
            columns="Year",
            values="Master Sale Value",
            aggfunc="sum",
            fill_value=0
        )
    )
        
    # Rename yearly columns
    yearly_sales.columns = [
        f"Master Sale Value {int(year)}" for year in yearly_sales.columns
    ]    
    
    for year in df_s["Year"].unique():
        if year == current_year:
            monthly_avg_in_year = yearly_sales[f"Master Sale Value {int(year)}"] / current_month
        else:
            monthly_avg_in_year = yearly_sales[f"Master Sale Value {int(year)}"] / 12
        yearly_sales[f"Avg Sale Value {int(year)}"] = monthly_avg_in_year    
    
    # -----------------------------
    # Combine lifetime + yearly
    # -----------------------------
    summary_sale = lifetime_sales.join(yearly_sales, how="left")
        
    summary_sale = summary_sale[~summary_sale.index.str.lower().str.startswith("pro")] # get rid or "pro" locations

    merged_df = summary_sale.merge(
        onhand_master_value_by_whs,
        left_index=True,
        right_index=True,
        how="left"
    )

    for year in df_s["Year"].unique():
        stock_ratio = merged_df["Onhand Master Value"] / merged_df[f"Avg Sale Value {int(year)}"]
        merged_df[f"Stock Ratio {int(year)}"] = stock_ratio
            
    return merged_df
