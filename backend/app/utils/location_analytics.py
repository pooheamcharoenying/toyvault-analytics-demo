"""Enhanced Location Analytics — efficiency metrics, trends, and product mix per location.

Business context: A toy distributor has stock spread across multiple warehouses and stores.
Raw revenue is misleading for comparing locations — a flagship holding 10M THB of inventory
*should* outsell a small shop holding 500K.  The real question is *efficiency*: who generates
the most revenue relative to the stock they hold?

Key metrics:
- Revenue per THB of inventory (sales / on-hand value) — the #1 efficiency metric
- Stock turnover (revenue / inventory value per period)
- Sell-through rate (sold qty / on-hand qty)
- Days of cover (on-hand qty / avg daily sales)
- Dead stock % (on-hand value with zero sales / total on-hand value)
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from app.utils import nichi_stock as nstk


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _add_master_revenue(sale: pd.DataFrame, df_item_master: pd.DataFrame) -> pd.DataFrame:
    """Add Revenue_Master_THB column = Quantity × Master Price.

    Prefer the Sale sheet's 'Price Master' column (= Quantity × Master Price per
    line, available for ALL rows including discontinued items).  Fall back to Item
    Master lookup only when the column is missing.
    """
    if "Price Master" in sale.columns:
        # 'Price Master' is already line-level (Qty × unit master price)
        sale["Revenue_Master_THB"] = pd.to_numeric(
            sale["Price Master"], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
    else:
        # Fallback: lookup from Item Master (may miss discontinued items)
        if "Price" in df_item_master.columns:
            price_map = (
                df_item_master[["ItemCode", "Price"]]
                .drop_duplicates(subset=["ItemCode"])
                .set_index("ItemCode")["Price"]
            )
        else:
            price_map = pd.Series(dtype=float)
        sale["Master_Price_Unit"] = sale["ItemCode"].map(price_map).fillna(0.0)
        sale["Master_Price_Unit"] = pd.to_numeric(sale["Master_Price_Unit"], errors="coerce").fillna(0.0)
        sale["Revenue_Master_THB"] = sale["Quantity"].abs() * sale["Master_Price_Unit"]
    return sale


def _channel_dedup_sale(df_sale_prepared: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate sales by (DocEntry, ItemCode, Period, GroupName)."""
    df = df_sale_prepared.copy()
    df["DocDate"] = pd.to_datetime(df["DocDate"], errors="coerce")
    df = df.dropna(subset=["DocDate"])
    df["Period"] = df["DocDate"].dt.to_period("M").dt.start_time
    return df.drop_duplicates(subset=["DocEntry", "ItemCode", "Period", "GroupName"])


def _prepare_onhand_with_price(
    df_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare on-hand data with master price and warehouse names."""
    oh = df_onhand.copy()
    oh["WhsCode"] = oh["WhsCode"].astype(str).str.strip()
    oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0.0)

    # Merge master price
    im = df_item_master[["ItemCode", "Price"]].copy()
    im = im.rename(columns={"Price": "Master Price"})
    oh = oh.merge(im, on="ItemCode", how="left")
    oh["Master Price"] = pd.to_numeric(oh["Master Price"], errors="coerce").fillna(0.0)
    oh["OnHand_THB"] = oh["OnHand"] * oh["Master Price"]

    # Merge brand from master (item master GroupName = product brand)
    # Note: raw on-hand also has a GroupName column (= BP bucket, NOT brand)
    # so we must rename before merging to avoid duplicate column names.
    if "GroupName" in df_item_master.columns:
        brand_map = (
            df_item_master[["ItemCode", "GroupName"]]
            .drop_duplicates("ItemCode")
            .rename(columns={"GroupName": "Brand"})
        )
        # Drop any pre-existing GroupName from on-hand (it's BP bucket, not brand)
        if "GroupName" in oh.columns:
            oh = oh.drop(columns=["GroupName"])
        oh = oh.merge(brand_map, on="ItemCode", how="left")
        oh["Brand"] = oh["Brand"].fillna("Unknown")
    else:
        oh["Brand"] = "Unknown"

    # Merge warehouse names
    oh = oh.merge(df_whs_code[["WhsCode", "WhsName"]], on="WhsCode", how="left")
    oh = oh.dropna(subset=["WhsName"])
    return oh


# ---------------------------------------------------------------------------
# F-038: Enhanced Location Performance Analytics
# ---------------------------------------------------------------------------

def compute_location_performance(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    *,
    year: Optional[int] = None,
    year_list: Optional[list[int]] = None,
    window_days: int = 90,
    target_cover_days: int = 90,
) -> dict[str, Any]:
    """Compute location performance rankings with efficiency metrics.

    Returns a dict with:
    - locations: list of dicts (one per location) with absolute + efficiency metrics
      including optimal inventory estimation (target vs actual on-hand)
    - summary: org-wide totals
    - company_avg: company average efficiency metrics for comparison
    """
    if df_whs_code is None or df_whs_code.empty:
        return {"locations": [], "summary": {}, "company_avg": {}}

    # Prepare sales
    df_sale, df_onhand_prep, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    sale = _channel_dedup_sale(df_sale)
    if sale.empty:
        return {"locations": [], "summary": {}, "company_avg": {}}

    # Add Revenue (Master) = Qty × Master Price
    sale = _add_master_revenue(sale, df_item_master)

    # Merge warehouse names into sales
    whs_map = df_whs_code[["WhsCode", "WhsName"]].copy()
    whs_map["WhsCode"] = whs_map["WhsCode"].astype(str).str.strip()
    sale["WhsCode"] = sale["WhsCode"].astype(str).str.strip()
    sale = sale.merge(whs_map, on="WhsCode", how="left")
    sale = sale.dropna(subset=["WhsName"])

    # Apply location consolidation (e.g., CT-ลาดพร้าว GP25/GP33 -> CT-ลาดพร้าว)
    from app.utils.location_consolidation import add_consolidated_column
    _whs_lookup = dict(zip(whs_map["WhsCode"], whs_map["WhsName"]))
    sale = add_consolidated_column(sale, _whs_lookup)
    sale["WhsName"] = sale["ConsolidatedLocation"]

    # Filter by year if specified (year_list takes precedence over year)
    _years = year_list if year_list else ([year] if year is not None else None)
    if _years is not None:
        sale = sale[sale["DocDate"].dt.year.isin(_years)].copy()
        if sale.empty:
            return {"locations": [], "summary": {}, "company_avg": {}}

    # Prepare on-hand with prices and warehouse names
    oh = _prepare_onhand_with_price(df_raw_onhand, df_item_master, df_whs_code)
    # Apply consolidation to on-hand as well
    oh = add_consolidated_column(oh, _whs_lookup)
    oh["WhsName"] = oh["ConsolidatedLocation"]

    # Filter out "pro" locations
    sale = sale[~sale["WhsName"].str.lower().str.startswith("pro", na=False)]
    oh = oh[~oh["WhsName"].str.lower().str.startswith("pro", na=False)]

    # --- Aggregate sales by location ---
    sale_by_loc = sale.groupby("WhsName", as_index=False).agg(
        sold_qty=("Quantity", "sum"),
        sold_thb=("LineTotal", "sum"),
        sold_master_thb=("Revenue_Master_THB", "sum"),
    )

    # --- Aggregate on-hand by location ---
    oh_by_loc = oh.groupby("WhsName", as_index=False).agg(
        onhand_qty=("OnHand", "sum"),
        onhand_thb=("OnHand_THB", "sum"),
    )

    # --- Dead stock % per location ---
    # Items with zero sales at each location
    as_of = sale["DocDate"].max()
    start = as_of - pd.Timedelta(days=window_days - 1)
    recent_sale = sale[(sale["DocDate"] >= start) & (sale["DocDate"] <= as_of)]

    items_sold_by_loc = (
        recent_sale.groupby(["WhsCode", "ItemCode"])["Quantity"]
        .sum()
        .reset_index()
        .rename(columns={"Quantity": "recent_sold"})
    )
    items_sold_by_loc["WhsCode"] = items_sold_by_loc["WhsCode"].astype(str).str.strip()

    oh_items = oh[["WhsCode", "WhsName", "ItemCode", "OnHand", "OnHand_THB"]].copy()
    oh_items["WhsCode"] = oh_items["WhsCode"].astype(str).str.strip()
    oh_with_sales = oh_items.merge(items_sold_by_loc, on=["WhsCode", "ItemCode"], how="left")
    oh_with_sales["recent_sold"] = oh_with_sales["recent_sold"].fillna(0.0)

    dead_mask = (oh_with_sales["recent_sold"] == 0) & (oh_with_sales["OnHand"] > 0)
    dead_by_loc = (
        oh_with_sales[dead_mask]
        .groupby("WhsName", as_index=False)
        .agg(dead_stock_thb=("OnHand_THB", "sum"))
    )

    # --- Days of sale in the dataset (for avg daily calc) ---
    # +1 for inclusive range (Jan 1 to Jan 31 = 31 days, not 30)
    date_range_days = max(1, (sale["DocDate"].max() - sale["DocDate"].min()).days + 1)
    if _years is not None:
        # Use actual data range within the selected years
        year_start = max(pd.Timestamp(min(_years), 1, 1), sale["DocDate"].min())
        year_end = min(sale["DocDate"].max(), pd.Timestamp(max(_years), 12, 31))
        date_range_days = max(1, (year_end - year_start).days + 1)

    # --- Combine everything ---
    result = sale_by_loc.merge(oh_by_loc, on="WhsName", how="outer")
    result = result.merge(dead_by_loc, on="WhsName", how="left")

    result["sold_qty"] = result["sold_qty"].fillna(0.0)
    result["sold_thb"] = result["sold_thb"].fillna(0.0)
    result["sold_master_thb"] = result["sold_master_thb"].fillna(0.0)
    result["onhand_qty"] = result["onhand_qty"].fillna(0.0)
    result["onhand_thb"] = result["onhand_thb"].fillna(0.0)
    result["dead_stock_thb"] = result["dead_stock_thb"].fillna(0.0)

    # --- Efficiency metrics ---
    result["revenue_per_thb_inventory"] = result.apply(
        lambda r: round(float(r["sold_thb"]) / float(r["onhand_thb"]), 2)
        if float(r["onhand_thb"]) > 0 else 0.0,
        axis=1,
    )

    result["sell_through_rate"] = result.apply(
        lambda r: round(float(r["sold_qty"]) / float(r["onhand_qty"]) * 100, 1)
        if float(r["onhand_qty"]) > 0 else 0.0,
        axis=1,
    )

    result["avg_daily_sales"] = result["sold_qty"] / float(date_range_days)

    result["days_cover"] = result.apply(
        lambda r: round(float(r["onhand_qty"]) / float(r["avg_daily_sales"]), 0)
        if float(r["avg_daily_sales"]) > 0 else float("inf"),
        axis=1,
    )

    result["dead_stock_pct"] = result.apply(
        lambda r: round(float(r["dead_stock_thb"]) / float(r["onhand_thb"]) * 100, 1)
        if float(r["onhand_thb"]) > 0 else 0.0,
        axis=1,
    )

    result["stock_turnover"] = result["revenue_per_thb_inventory"]  # same metric, different name

    # --- Optimal inventory estimation ---
    # Target on-hand = avg daily sales qty × target_cover_days
    # Then compare actual on-hand to target to find over/under-stocked locations
    result["target_onhand_qty"] = result["avg_daily_sales"] * float(target_cover_days)
    # Target on-hand THB: use average unit price at each location (onhand_thb / onhand_qty)
    result["avg_unit_price"] = result.apply(
        lambda r: float(r["onhand_thb"]) / float(r["onhand_qty"])
        if float(r["onhand_qty"]) > 0 else 0.0,
        axis=1,
    )
    result["target_onhand_thb"] = result["target_onhand_qty"] * result["avg_unit_price"]
    result["inventory_gap_qty"] = result["onhand_qty"] - result["target_onhand_qty"]
    result["inventory_gap_thb"] = result["onhand_thb"] - result["target_onhand_thb"]
    result["inventory_status"] = result.apply(
        lambda r: "understocked" if float(r["inventory_gap_qty"]) < -float(r["target_onhand_qty"]) * 0.2
        else ("overstocked" if float(r["inventory_gap_qty"]) > float(r["target_onhand_qty"]) * 0.2
              else "optimal"),
        axis=1,
    )

    # --- Traffic light: compare to company average ---
    total_sold = float(result["sold_thb"].sum())
    total_oh = float(result["onhand_thb"].sum())
    company_avg_efficiency = round(total_sold / total_oh, 2) if total_oh > 0 else 0.0

    def _traffic_light(eff):
        if eff >= company_avg_efficiency * 1.2:
            return "green"
        elif eff >= company_avg_efficiency * 0.8:
            return "yellow"
        else:
            return "red"

    result["status"] = result["revenue_per_thb_inventory"].apply(_traffic_light)

    # --- Composite Health Score ---
    # Combines efficiency (40%), sell-through (25%), dead stock (20%, inverted),
    # and days-cover leanness (15%) into 0-100 score.
    # Each component is normalized via percentile rank within the dataset.
    def _pct_rank(series: pd.Series) -> pd.Series:
        """Percentile rank: 0 = worst, 1 = best.  Handles ties and NaN."""
        return series.rank(method="average", pct=True, na_option="bottom")

    # Days-cover leanness: lower is better (but not zero — that means no sales).
    # Cap inf at a large number so it ranks last.
    dc_capped = result["days_cover"].replace([np.inf, float("inf")], 99999)
    dc_rank = 1 - _pct_rank(dc_capped)  # invert: low days cover = high rank
    dead_rank = 1 - _pct_rank(result["dead_stock_pct"])  # invert: low dead % = high rank
    eff_rank = _pct_rank(result["revenue_per_thb_inventory"])
    st_rank = _pct_rank(result["sell_through_rate"])

    result["health_score"] = (
        eff_rank * 40 + st_rank * 25 + dead_rank * 20 + dc_rank * 15
    ).round(1)

    # --- Location ABCDE classification (OBJ-83 Part 2) ---
    # Rank locations by revenue contribution using cumulative % thresholds:
    # A ≤ 50%, B ≤ 80%, C ≤ 95%, D ≤ 99%, E = rest
    result = result.sort_values("sold_thb", ascending=False).reset_index(drop=True)
    total_revenue = float(result["sold_thb"].sum())
    if total_revenue > 0:
        cum_rev = result["sold_thb"].cumsum()
        cum_pct = cum_rev / total_revenue * 100.0
        def _classify_loc(pct_val, idx):
            if pct_val <= 50.0 or idx == 0:
                return "A"
            elif pct_val <= 80.0:
                return "B"
            elif pct_val <= 95.0:
                return "C"
            elif pct_val <= 99.0:
                return "D"
            else:
                return "E"
        result["abcde_class"] = [_classify_loc(p, i) for i, p in enumerate(cum_pct)]
    else:
        result["abcde_class"] = "E"

    # Sort by composite health score (desc)
    result = result.sort_values("health_score", ascending=False).reset_index(drop=True)

    # Build response
    locations = []
    for _, row in result.iterrows():
        dc = float(row["days_cover"]) if not np.isinf(row["days_cover"]) else None
        locations.append({
            "location": str(row["WhsName"]),
            "sold_qty": round(float(row["sold_qty"])),
            "sold_thb": round(float(row["sold_thb"]), 2),
            "sold_master_thb": round(float(row["sold_master_thb"]), 2),
            "onhand_qty": round(float(row["onhand_qty"])),
            "onhand_thb": round(float(row["onhand_thb"]), 2),
            "revenue_per_thb_inventory": float(row["revenue_per_thb_inventory"]),
            "sell_through_rate": float(row["sell_through_rate"]),
            "days_cover": dc,
            "dead_stock_pct": float(row["dead_stock_pct"]),
            "dead_stock_thb": round(float(row["dead_stock_thb"]), 2),
            "stock_turnover": float(row["stock_turnover"]),
            "status": row["status"],
            "health_score": float(row["health_score"]),
            "abcde_class": str(row["abcde_class"]),
            "target_onhand_qty": round(float(row["target_onhand_qty"])),
            "target_onhand_thb": round(float(row["target_onhand_thb"]), 2),
            "inventory_gap_qty": round(float(row["inventory_gap_qty"])),
            "inventory_gap_thb": round(float(row["inventory_gap_thb"]), 2),
            "inventory_status": str(row["inventory_status"]),
        })

    total_sold_qty = round(float(result["sold_qty"].sum()))
    total_onhand_qty = round(float(result["onhand_qty"].sum()))
    total_dead = round(float(result["dead_stock_thb"].sum()), 2)

    avg_health = round(float(result["health_score"].mean()), 1) if not result.empty else 0.0
    max_health = round(float(result["health_score"].max()), 1) if not result.empty else 0.0
    min_health = round(float(result["health_score"].min()), 1) if not result.empty else 0.0

    overstocked_count = sum(1 for loc in locations if loc["inventory_status"] == "overstocked")
    understocked_count = sum(1 for loc in locations if loc["inventory_status"] == "understocked")
    optimal_count = sum(1 for loc in locations if loc["inventory_status"] == "optimal")
    total_excess_thb = round(sum(
        loc["inventory_gap_thb"] for loc in locations if loc["inventory_gap_thb"] > 0
    ), 2)
    total_shortfall_thb = round(abs(sum(
        loc["inventory_gap_thb"] for loc in locations if loc["inventory_gap_thb"] < 0
    )), 2)

    summary = {
        "total_locations": len(locations),
        "total_sold_thb": round(total_sold, 2),
        "total_onhand_thb": round(total_oh, 2),
        "total_sold_qty": total_sold_qty,
        "total_onhand_qty": total_onhand_qty,
        "total_dead_stock_thb": total_dead,
        "green_count": sum(1 for loc in locations if loc["status"] == "green"),
        "yellow_count": sum(1 for loc in locations if loc["status"] == "yellow"),
        "red_count": sum(1 for loc in locations if loc["status"] == "red"),
        "avg_health_score": avg_health,
        "max_health_score": max_health,
        "min_health_score": min_health,
        "target_cover_days": target_cover_days,
        "overstocked_count": overstocked_count,
        "understocked_count": understocked_count,
        "optimal_count": optimal_count,
        "total_excess_thb": total_excess_thb,
        "total_shortfall_thb": total_shortfall_thb,
        "abcde_a_count": sum(1 for loc in locations if loc.get("abcde_class") == "A"),
        "abcde_b_count": sum(1 for loc in locations if loc.get("abcde_class") == "B"),
        "abcde_c_count": sum(1 for loc in locations if loc.get("abcde_class") == "C"),
        "abcde_d_count": sum(1 for loc in locations if loc.get("abcde_class") == "D"),
        "abcde_e_count": sum(1 for loc in locations if loc.get("abcde_class") == "E"),
    }

    # Weighted company-wide sell-through: total sold qty / total on-hand qty
    company_sell_through = round(
        total_sold_qty / total_onhand_qty * 100, 1
    ) if total_onhand_qty > 0 else 0.0
    # Weighted dead stock %: total dead stock THB / total on-hand THB
    company_dead_stock_pct = round(
        total_dead / total_oh * 100, 1
    ) if total_oh > 0 else 0.0

    company_avg = {
        "revenue_per_thb_inventory": company_avg_efficiency,
        "avg_sell_through": company_sell_through,
        "avg_dead_stock_pct": company_dead_stock_pct,
    }

    return {
        "locations": locations,
        "summary": summary,
        "company_avg": company_avg,
    }


def compute_location_trends(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    *,
    location: Optional[str] = None,
    top_n: int = 10,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Compute monthly revenue trends per location.

    Returns a dict with:
    - trends: list of {location, months: [{period, sold_thb, sold_qty}]}
    - periods: sorted list of period strings (YYYY-MM)
    """
    if df_whs_code is None or df_whs_code.empty:
        return {"trends": [], "periods": []}

    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    sale = _channel_dedup_sale(df_sale)
    if sale.empty:
        return {"trends": [], "periods": []}

    sale = _add_master_revenue(sale, df_item_master)

    whs_map = df_whs_code[["WhsCode", "WhsName"]].copy()
    whs_map["WhsCode"] = whs_map["WhsCode"].astype(str).str.strip()
    sale["WhsCode"] = sale["WhsCode"].astype(str).str.strip()
    sale = sale.merge(whs_map, on="WhsCode", how="left")
    sale = sale.dropna(subset=["WhsName"])

    # Apply location consolidation
    from app.utils.location_consolidation import add_consolidated_column
    _whs_lookup = dict(zip(whs_map["WhsCode"], whs_map["WhsName"]))
    sale = add_consolidated_column(sale, _whs_lookup)
    sale["WhsName"] = sale["ConsolidatedLocation"]

    sale = sale[~sale["WhsName"].str.lower().str.startswith("pro", na=False)]

    # Filter by year_list if specified
    if year_list:
        sale = sale[sale["DocDate"].dt.year.isin(year_list)].copy()
        if sale.empty:
            return {"trends": [], "periods": []}

    # Monthly aggregation
    sale["Month"] = sale["DocDate"].dt.to_period("M").dt.start_time

    if location:
        sale = sale[sale["WhsName"] == location]
        if sale.empty:
            return {"trends": [], "periods": []}

    monthly = sale.groupby(["WhsName", "Month"], as_index=False).agg(
        sold_thb=("LineTotal", "sum"),
        sold_master_thb=("Revenue_Master_THB", "sum"),
        sold_qty=("Quantity", "sum"),
    )

    periods_sorted = sorted(monthly["Month"].unique())
    period_strs = [p.strftime("%Y-%m") for p in periods_sorted]

    # Pick top N locations by total revenue (unless filtering by one)
    if not location:
        loc_totals = monthly.groupby("WhsName")["sold_thb"].sum().sort_values(ascending=False)
        top_locs = list(loc_totals.head(top_n).index)
        monthly = monthly[monthly["WhsName"].isin(top_locs)]

    trends = []
    for loc_name, grp in monthly.groupby("WhsName"):
        months = []
        for p in periods_sorted:
            row = grp[grp["Month"] == p]
            if not row.empty:
                months.append({
                    "period": p.strftime("%Y-%m"),
                    "sold_thb": round(float(row.iloc[0]["sold_thb"]), 2),
                    "sold_master_thb": round(float(row.iloc[0]["sold_master_thb"]), 2),
                    "sold_qty": round(float(row.iloc[0]["sold_qty"])),
                })
            else:
                months.append({"period": p.strftime("%Y-%m"), "sold_thb": 0.0, "sold_master_thb": 0.0, "sold_qty": 0})
        trends.append({"location": str(loc_name), "months": months})

    # Sort trends by total revenue descending
    trends.sort(key=lambda t: sum(m["sold_thb"] for m in t["months"]), reverse=True)

    # Annotate the last (possibly partial) month on each location series.
    try:
        from app.utils.running_rate import annotate_monthly_series, get_data_as_of_date
        as_of = get_data_as_of_date(df_raw_sale)
        for t in trends:
            annotate_monthly_series(
                t["months"],
                as_of,
                numeric_fields=["sold_thb", "sold_master_thb", "sold_qty"],
            )
    except Exception:
        pass

    return {"trends": trends, "periods": period_strs}


def compute_location_product_mix(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    *,
    location: str,
    year: Optional[int] = None,
    year_list: Optional[list[int]] = None,
    top_n: int = 20,
    window_days: int = 90,
    brand: Optional[str] = None,
    df_tr_in: Optional[pd.DataFrame] = None,
    df_grpo_detail: Optional[pd.DataFrame] = None,
) -> dict[str, Any]:
    """Compute product/brand mix for a specific location.

    Returns:
    - top_brands: top brands by revenue at this location
    - top_items: top items by revenue at this location
    - non_movers: items with on-hand > 0 but zero sales in the window AND
        with evidence they have been at this location at least `window_days`
        (fresh inbound stock is excluded — it hasn't had time to sell).
    - brand_heatmap: brand performance at this location vs. company
    """
    if df_whs_code is None or df_whs_code.empty:
        return {"top_brands": [], "top_items": [], "non_movers": [], "brand_heatmap": []}

    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    sale = _channel_dedup_sale(df_sale)
    sale = _add_master_revenue(sale, df_item_master)

    whs_map = df_whs_code[["WhsCode", "WhsName"]].copy()
    whs_map["WhsCode"] = whs_map["WhsCode"].astype(str).str.strip()
    sale["WhsCode"] = sale["WhsCode"].astype(str).str.strip()
    sale = sale.merge(whs_map, on="WhsCode", how="left")

    # Apply location consolidation
    from app.utils.location_consolidation import add_consolidated_column
    _whs_lookup = dict(zip(whs_map["WhsCode"], whs_map["WhsName"]))
    sale = add_consolidated_column(sale, _whs_lookup)
    sale["WhsName"] = sale["ConsolidatedLocation"]

    oh = _prepare_onhand_with_price(df_raw_onhand, df_item_master, df_whs_code)
    oh = add_consolidated_column(oh, _whs_lookup)
    oh["WhsName"] = oh["ConsolidatedLocation"]

    # Filter to the specified location
    loc_sale = sale[sale["WhsName"] == location].copy()
    loc_oh = oh[oh["WhsName"] == location].copy()

    _years = year_list if year_list else ([year] if year is not None else None)
    if _years is not None:
        loc_sale = loc_sale[loc_sale["DocDate"].dt.year.isin(_years)]

    # Filter by brand if specified (for brand-at-location drill-down)
    if brand is not None:
        loc_sale = loc_sale[loc_sale["Brand"] == brand].copy()
        loc_oh = loc_oh[loc_oh["Brand"] == brand].copy()

    # --- Top brands ---
    brand_agg = loc_sale.groupby("Brand", as_index=False).agg(
        sold_thb=("LineTotal", "sum"),
        sold_master_thb=("Revenue_Master_THB", "sum"),
        sold_qty=("Quantity", "sum"),
    ).sort_values("sold_thb", ascending=False)

    top_brands = []
    for _, row in brand_agg.head(top_n).iterrows():
        top_brands.append({
            "brand": str(row["Brand"]),
            "sold_thb": round(float(row["sold_thb"]), 2),
            "sold_master_thb": round(float(row["sold_master_thb"]), 2),
            "sold_qty": round(float(row["sold_qty"])),
        })

    # --- Top items ---
    item_agg = loc_sale.groupby(["ItemCode", "Brand"], as_index=False).agg(
        sold_thb=("LineTotal", "sum"),
        sold_master_thb=("Revenue_Master_THB", "sum"),
        sold_qty=("Quantity", "sum"),
    ).sort_values("sold_thb", ascending=False)

    # Merge item descriptions
    desc_map = df_item_master[["ItemCode", "ItemName"]].drop_duplicates("ItemCode")
    item_agg = item_agg.merge(desc_map, on="ItemCode", how="left")

    top_items = []
    for _, row in item_agg.head(top_n).iterrows():
        top_items.append({
            "item_code": str(row["ItemCode"]),
            "item_name": str(row.get("ItemName", "")),
            "brand": str(row["Brand"]),
            "sold_thb": round(float(row["sold_thb"]), 2),
            "sold_master_thb": round(float(row["sold_master_thb"]), 2),
            "sold_qty": round(float(row["sold_qty"])),
        })

    # --- Non-movers: items in stock but zero recent sales ---
    # Important: we exclude items that arrived at this location less than
    # `window_days` ago — they have NOT had a full window to sell, so flagging
    # them as dead stock is wrong. "Arrival" is the earliest TR IN or GRPO
    # date for the item at any WhsCode that rolls up to this consolidated
    # location. If we have no such date, we treat the item as long-tenured
    # (conservative — still flag it).
    as_of = loc_sale["DocDate"].max() if not loc_sale.empty else pd.Timestamp.now()
    start = as_of - pd.Timedelta(days=window_days - 1)

    recent_sold_items = set()
    if not loc_sale.empty:
        recent = loc_sale[(loc_sale["DocDate"] >= start) & (loc_sale["DocDate"] <= as_of)]
        recent_sold_items = set(recent["ItemCode"].unique())

    # Build the set of WhsCodes that roll up to this consolidated location
    loc_whs_codes = set(loc_oh["WhsCode"].astype(str).str.strip().unique())

    # --- Earliest stock-in date per (ItemCode) at this consolidated location ---
    # Combine TR IN + GRPO for WhsCodes belonging to this location.
    first_in_by_item: dict[str, pd.Timestamp] = {}

    def _collect_earliest(df_mov: Optional[pd.DataFrame]):
        if df_mov is None or df_mov.empty:
            return
        if "WhsCode" not in df_mov.columns or "DocDate" not in df_mov.columns:
            return
        m = df_mov[["ItemCode", "WhsCode", "DocDate"]].copy()
        m["WhsCode"] = m["WhsCode"].astype(str).str.strip()
        m = m[m["WhsCode"].isin(loc_whs_codes)]
        if m.empty:
            return
        m["ItemCode"] = m["ItemCode"].astype(str).str.strip()
        m["DocDate"] = pd.to_datetime(m["DocDate"], errors="coerce")
        m = m.dropna(subset=["DocDate"])
        if m.empty:
            return
        by_item = m.groupby("ItemCode")["DocDate"].min()
        for ic, dt in by_item.items():
            cur = first_in_by_item.get(ic)
            if cur is None or dt < cur:
                first_in_by_item[ic] = dt

    _collect_earliest(df_tr_in)
    _collect_earliest(df_grpo_detail)

    # Also treat any earlier sale at this location as evidence the item was here
    if not loc_sale.empty:
        earliest_sale = loc_sale.groupby("ItemCode")["DocDate"].min()
        for ic, dt in earliest_sale.items():
            cur = first_in_by_item.get(str(ic))
            if cur is None or dt < cur:
                first_in_by_item[str(ic)] = dt

    # "Fresh inbound" cutoff: arrived at this location within the window
    fresh_cutoff = as_of - pd.Timedelta(days=window_days - 1)

    non_movers = []
    fresh_excluded = 0
    for _, row in loc_oh.iterrows():
        ic = str(row["ItemCode"])
        if ic in recent_sold_items or float(row["OnHand"]) <= 0:
            continue
        arrival = first_in_by_item.get(ic)
        if arrival is not None and arrival >= fresh_cutoff:
            # Too recent — not enough tenure to call it dead stock
            fresh_excluded += 1
            continue
        non_movers.append({
            "item_code": ic,
            "brand": str(row.get("Brand", "Unknown")),
            "onhand_qty": round(float(row["OnHand"])),
            "onhand_thb": round(float(row["OnHand_THB"]), 2),
            "first_seen_at_location": arrival.strftime("%Y-%m-%d") if arrival is not None else None,
        })

    # Sort non-movers by value descending and limit
    non_movers.sort(key=lambda x: x["onhand_thb"], reverse=True)
    non_movers = non_movers[:top_n]

    # --- Brand heatmap: this location vs. company-wide ---
    # Apply same year filter to company-wide sale for consistent comparison
    filtered_sale = sale.copy()
    if _years is not None:
        filtered_sale = filtered_sale[filtered_sale["DocDate"].dt.year.isin(_years)]
    company_brand = filtered_sale.groupby("Brand", as_index=False).agg(
        company_sold_thb=("LineTotal", "sum"),
    )
    loc_brand = loc_sale.groupby("Brand", as_index=False).agg(
        loc_sold_thb=("LineTotal", "sum"),
        loc_sold_master_thb=("Revenue_Master_THB", "sum"),
    )

    # On-hand by brand at this location
    loc_oh_brand = loc_oh.groupby("Brand", as_index=False).agg(
        loc_onhand_thb=("OnHand_THB", "sum"),
        loc_onhand_qty=("OnHand", "sum"),
    )

    heatmap_df = company_brand.merge(loc_brand, on="Brand", how="left")
    heatmap_df = heatmap_df.merge(loc_oh_brand, on="Brand", how="left")
    heatmap_df["loc_sold_thb"] = heatmap_df["loc_sold_thb"].fillna(0.0)
    heatmap_df["loc_sold_master_thb"] = heatmap_df["loc_sold_master_thb"].fillna(0.0)
    heatmap_df["loc_onhand_thb"] = heatmap_df["loc_onhand_thb"].fillna(0.0)
    heatmap_df["loc_onhand_qty"] = heatmap_df["loc_onhand_qty"].fillna(0.0)

    heatmap_df["loc_share_pct"] = heatmap_df.apply(
        lambda r: round(float(r["loc_sold_thb"]) / float(r["company_sold_thb"]) * 100, 1)
        if float(r["company_sold_thb"]) > 0 else 0.0,
        axis=1,
    )

    heatmap_df["sell_through"] = heatmap_df.apply(
        lambda r: round(float(r["loc_sold_thb"]) / float(r["loc_onhand_thb"]), 2)
        if float(r["loc_onhand_thb"]) > 0 else 0.0,
        axis=1,
    )

    heatmap_df = heatmap_df.sort_values("loc_sold_thb", ascending=False)

    brand_heatmap = []
    for _, row in heatmap_df.head(top_n).iterrows():
        brand_heatmap.append({
            "brand": str(row["Brand"]),
            "company_sold_thb": round(float(row["company_sold_thb"]), 2),
            "loc_sold_thb": round(float(row["loc_sold_thb"]), 2),
            "loc_sold_master_thb": round(float(row["loc_sold_master_thb"]), 2),
            "loc_share_pct": float(row["loc_share_pct"]),
            "loc_onhand_thb": round(float(row["loc_onhand_thb"]), 2),
            "sell_through": float(row["sell_through"]),
        })

    non_mover_total_thb = round(sum(n["onhand_thb"] for n in non_movers), 2)

    # --- Average monthly sales (Actual and Master) ---
    # Count distinct calendar months with sales activity at this location
    # (within the year filter), then divide total by that count. This is the
    # honest "per active month" average — a location that had sales in only
    # 8 months of the selected period averages total / 8.
    avg_monthly_sold_thb = 0.0
    avg_monthly_sold_master_thb = 0.0
    active_months = 0
    total_sold_thb_loc = 0.0
    total_sold_master_thb_loc = 0.0
    if not loc_sale.empty:
        _s = loc_sale.copy()
        _s["_YM"] = _s["DocDate"].dt.to_period("M")
        active_months = int(_s["_YM"].nunique())
        total_sold_thb_loc = float(_s["LineTotal"].sum())
        total_sold_master_thb_loc = float(_s["Revenue_Master_THB"].sum())
        if active_months > 0:
            avg_monthly_sold_thb = total_sold_thb_loc / active_months
            avg_monthly_sold_master_thb = total_sold_master_thb_loc / active_months

    # --- All stock items at this location (on-hand > 0) ---
    # Aggregate sales (within the year filter) per item for context.
    sales_by_item = {}
    if not loc_sale.empty:
        _si = loc_sale.groupby("ItemCode", as_index=False).agg(
            sold_thb=("LineTotal", "sum"),
            sold_master_thb=("Revenue_Master_THB", "sum"),
            sold_qty=("Quantity", "sum"),
        )
        for _, r in _si.iterrows():
            sales_by_item[str(r["ItemCode"])] = {
                "sold_thb": round(float(r["sold_thb"]), 2),
                "sold_master_thb": round(float(r["sold_master_thb"]), 2),
                "sold_qty": round(float(r["sold_qty"])),
            }

    name_map = df_item_master.drop_duplicates("ItemCode").set_index("ItemCode")["ItemName"].to_dict() \
        if "ItemName" in df_item_master.columns else {}

    all_stocks = []
    for _, row in loc_oh.iterrows():
        if float(row["OnHand"]) <= 0:
            continue
        ic = str(row["ItemCode"])
        sales = sales_by_item.get(ic, {"sold_thb": 0.0, "sold_master_thb": 0.0, "sold_qty": 0})
        all_stocks.append({
            "item_code": ic,
            "item_name": str(name_map.get(ic, row.get("ItemName", "")) or ""),
            "brand": str(row.get("Brand", "Unknown")),
            "onhand_qty": round(float(row["OnHand"])),
            "onhand_thb": round(float(row["OnHand_THB"]), 2),
            "sold_qty": sales["sold_qty"],
            "sold_thb": sales["sold_thb"],
            "sold_master_thb": sales["sold_master_thb"],
        })
    all_stocks.sort(key=lambda x: x["onhand_thb"], reverse=True)

    return {
        "location": location,
        "top_brands": top_brands,
        "top_items": top_items,
        "non_movers": non_movers,
        "non_mover_total_thb": non_mover_total_thb,
        "non_mover_fresh_excluded": fresh_excluded,
        "non_mover_window_days": window_days,
        "brand_heatmap": brand_heatmap,
        "avg_monthly_sold_thb": round(avg_monthly_sold_thb, 2),
        "avg_monthly_sold_master_thb": round(avg_monthly_sold_master_thb, 2),
        "active_months": active_months,
        "total_sold_thb": round(total_sold_thb_loc, 2),
        "total_sold_master_thb": round(total_sold_master_thb_loc, 2),
        "all_stocks": all_stocks,
    }


def compute_brand_at_location_trend(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    *,
    location: str,
    brand: str,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Monthly revenue trend for a specific brand at a specific location.

    Returns
    -------
    dict with:
      - months: [{period, sold_thb, sold_master_thb, sold_qty}]
    """
    if df_whs_code is None or df_whs_code.empty:
        return {"months": []}

    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    sale = _channel_dedup_sale(df_sale)
    if sale.empty:
        return {"months": []}

    sale = _add_master_revenue(sale, df_item_master)

    whs_map = df_whs_code[["WhsCode", "WhsName"]].copy()
    whs_map["WhsCode"] = whs_map["WhsCode"].astype(str).str.strip()
    sale["WhsCode"] = sale["WhsCode"].astype(str).str.strip()
    sale = sale.merge(whs_map, on="WhsCode", how="left")
    sale = sale.dropna(subset=["WhsName"])

    # Apply location consolidation
    from app.utils.location_consolidation import add_consolidated_column
    _whs_lookup = dict(zip(whs_map["WhsCode"], whs_map["WhsName"]))
    sale = add_consolidated_column(sale, _whs_lookup)
    sale["WhsName"] = sale["ConsolidatedLocation"]

    sale = sale[sale["WhsName"] == location]
    if sale.empty:
        return {"months": []}

    sale["Brand"] = sale["Brand"].fillna("Unknown")
    sale = sale[sale["Brand"] == brand]
    if sale.empty:
        return {"months": []}

    if year_list:
        sale = sale[sale["DocDate"].dt.year.isin(year_list)]
        if sale.empty:
            return {"months": []}

    sale["Month"] = sale["DocDate"].dt.to_period("M").dt.start_time
    monthly = sale.groupby("Month", as_index=False).agg(
        sold_thb=("LineTotal", "sum"),
        sold_master_thb=("Revenue_Master_THB", "sum"),
        sold_qty=("Quantity", "sum"),
    )
    monthly = monthly.sort_values("Month")

    months = []
    for _, r in monthly.iterrows():
        months.append({
            "period": r["Month"].strftime("%Y-%m"),
            "sold_thb": round(float(r["sold_thb"]), 2),
            "sold_master_thb": round(float(r["sold_master_thb"]), 2),
            "sold_qty": round(float(r["sold_qty"])),
        })

    # Annotate the last (possibly partial) month with a running rate.
    try:
        from app.utils.running_rate import annotate_monthly_series, get_data_as_of_date
        annotate_monthly_series(
            months,
            get_data_as_of_date(df_raw_sale),
            numeric_fields=["sold_thb", "sold_master_thb", "sold_qty"],
        )
    except Exception:
        pass

    return {"months": months}
