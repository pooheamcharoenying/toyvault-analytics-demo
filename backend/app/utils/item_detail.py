"""Item Location Detail — per-item stock distribution and lifetime sales.

Business context: When a manager sees a transfer recommendation or inventory alert
for a specific item, they need the full picture:
- Where is ALL the stock for this item right now?
- Where has it historically sold?
- Which locations have stock but no sales (transfer candidates)?
- Which locations sell well but are running low (restock candidates)?

This module answers those questions for a single ItemCode.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd


def compute_item_location_detail(
    item_code: str,
    df_sale: pd.DataFrame,
    df_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    df_grpo_detail: pd.DataFrame = None,
    *,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Return stock distribution and sales for a single item across all locations.

    Parameters
    ----------
    item_code : str
        The ItemCode to look up.
    df_sale : pd.DataFrame
        Raw sales data (Sale sheet from GLOBAL_DF).
    df_onhand : pd.DataFrame
        Current on-hand snapshot (OnHand sheet).
    df_item_master : pd.DataFrame
        Item master data (for ItemName, Brand/GroupName, Price).
    df_whs_code : pd.DataFrame
        Warehouse lookup (WhsCode -> WhsName).
    year_list : list[int], optional
        Filter sales to these years. If None, show all years (lifetime).

    Returns
    -------
    dict with keys:
        - item_info: {item_code, item_name, brand, master_price, total_onhand_qty,
                      total_onhand_thb, total_sold_qty, total_sold_thb}
        - locations: [{whs_code, whs_name, onhand_qty, onhand_thb,
                       lifetime_sold_qty, lifetime_sold_thb}]
          sorted by onhand_qty descending
        - found: bool (False if item_code doesn't exist)
    """
    result_empty = {"found": False, "item_info": {}, "locations": []}

    if df_sale is None or df_onhand is None or df_item_master is None:
        return result_empty

    # --- Item info from master ---
    master_match = df_item_master[
        df_item_master["ItemCode"].astype(str).str.strip() == str(item_code).strip()
    ]
    if master_match.empty:
        return result_empty

    master_row = master_match.iloc[0]
    item_name = str(master_row.get("ItemName", ""))
    brand = str(master_row.get("GroupName", ""))
    master_price = float(master_row.get("Price", 0) or 0)

    # --- Warehouse name lookup ---
    whs_map = {}
    if df_whs_code is not None and not df_whs_code.empty:
        for _, r in df_whs_code.iterrows():
            whs_map[str(r.get("WhsCode", "")).strip()] = str(r.get("WhsName", "")).strip()

    # --- On-hand per location ---
    if df_onhand.empty or "ItemCode" not in df_onhand.columns:
        oh = pd.DataFrame()
    else:
        oh = df_onhand[df_onhand["ItemCode"].astype(str).str.strip() == str(item_code).strip()].copy()
    onhand_by_loc = {}
    if not oh.empty:
        if "OnHand" not in oh.columns and "on_hand" in oh.columns:
            oh = oh.rename(columns={"on_hand": "OnHand"})
        oh["OnHand"] = pd.to_numeric(oh.get("OnHand", 0), errors="coerce").fillna(0)
        oh["WhsCode"] = oh["WhsCode"].astype(str).str.strip()
        grouped_oh = oh.groupby("WhsCode")["OnHand"].sum()
        for whs_code, qty in grouped_oh.items():
            if qty > 0:
                onhand_by_loc[whs_code] = float(qty)

    # --- Lifetime sales per location ---
    if df_sale.empty or "ItemCode" not in df_sale.columns:
        sl = pd.DataFrame()
    else:
        sl = df_sale[df_sale["ItemCode"].astype(str).str.strip() == str(item_code).strip()].copy()

    # Deduplicate sales
    if not sl.empty and "DocDate" in sl.columns:
        sl["DocDate"] = pd.to_datetime(sl.get("DocDate"), errors="coerce")
        sl = sl.dropna(subset=["DocDate"])
        if "Period" not in sl.columns:
            sl["Period"] = sl["DocDate"].dt.to_period("M").dt.start_time
        sl["WhsCode"] = sl["WhsCode"].astype(str).str.strip()

        dedup_cols = ["DocEntry", "ItemCode", "Period", "WhsCode"]
        available_dedup = [c for c in dedup_cols if c in sl.columns]
        if available_dedup:
            sl = sl.drop_duplicates(subset=available_dedup)

        sl["Quantity"] = pd.to_numeric(sl.get("Quantity", 0), errors="coerce").fillna(0).abs()
        sl["LineTotal"] = pd.to_numeric(sl.get("LineTotal", 0), errors="coerce").fillna(0).abs()

        # Filter by year_list if specified
        if year_list:
            sl = sl[sl["DocDate"].dt.year.isin(year_list)]
    else:
        sl = pd.DataFrame()

    # --- Compute COGS (FOB) and GP Commission for this item ---
    total_cogs_thb = 0.0
    total_gp_commission = 0.0
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        grpo_item = df_grpo_detail[
            df_grpo_detail["ItemCode"].astype(str).str.strip() == str(item_code).strip()
        ].copy()
        if year_list and "DocDate" in grpo_item.columns:
            grpo_item["DocDate"] = pd.to_datetime(grpo_item["DocDate"], errors="coerce")
            grpo_item = grpo_item[grpo_item["DocDate"].dt.year.isin(year_list)]
        if not grpo_item.empty:
            grpo_item["Price"] = pd.to_numeric(grpo_item.get("Price", 0), errors="coerce").fillna(0)
            grpo_item["Rate"] = pd.to_numeric(grpo_item.get("Rate", 0), errors="coerce").fillna(0)
            grpo_item["Qty"] = pd.to_numeric(grpo_item.get("Quantity", 0), errors="coerce").fillna(0)
            total_cogs_thb = float((grpo_item["Price"] * grpo_item["Rate"] * grpo_item["Qty"]).sum())

    if not sl.empty:
        from app.utils.nichi_stock import compute_gp_commission
        gp_series = compute_gp_commission(sl)
        total_gp_commission = float(gp_series.sum())

    sold_by_loc = {}
    sold_thb_by_loc = {}
    if not sl.empty:
        grouped_sl = sl.groupby("WhsCode").agg(
            sold_qty=("Quantity", "sum"),
            sold_thb=("LineTotal", "sum"),
        )
        for whs_code, row in grouped_sl.iterrows():
            sold_by_loc[whs_code] = float(row["sold_qty"])
            sold_thb_by_loc[whs_code] = float(row["sold_thb"])

    # --- Merge into location rows (with consolidation) ---
    all_whs_codes = set(list(onhand_by_loc.keys()) + list(sold_by_loc.keys()))
    if not all_whs_codes:
        return result_empty

    # Apply location consolidation — group WhsCodes that map to the same location
    from app.utils.location_consolidation import get_consolidated_name
    from collections import defaultdict
    consolidated = defaultdict(lambda: {"oh_qty": 0, "s_qty": 0, "s_thb": 0, "whs_codes": []})
    for whs_code in sorted(all_whs_codes):
        display_name = get_consolidated_name(whs_code, whs_map)
        entry = consolidated[display_name]
        entry["oh_qty"] += onhand_by_loc.get(whs_code, 0)
        entry["s_qty"] += sold_by_loc.get(whs_code, 0)
        entry["s_thb"] += sold_thb_by_loc.get(whs_code, 0)
        entry["whs_codes"].append(whs_code)

    locations = []
    for display_name, vals in consolidated.items():
        oh_qty = vals["oh_qty"]
        oh_thb = oh_qty * master_price
        s_qty = vals["s_qty"]
        s_thb = vals["s_thb"]
        s_master_thb = s_qty * master_price
        # Use the first WhsCode as representative (for drill-down links)
        rep_code = vals["whs_codes"][0] if vals["whs_codes"] else ""
        locations.append({
            "whs_code": rep_code,
            "whs_name": display_name,
            "onhand_qty": oh_qty,
            "onhand_thb": round(oh_thb, 2),
            "lifetime_sold_qty": s_qty,
            "lifetime_sold_thb": round(s_thb, 2),
            "lifetime_sold_master_thb": round(s_master_thb, 2),
            "sub_codes": vals["whs_codes"] if len(vals["whs_codes"]) > 1 else None,
        })

    # Sort by on-hand qty descending (largest stock first)
    locations.sort(key=lambda x: x["onhand_qty"], reverse=True)

    total_oh_qty = sum(loc["onhand_qty"] for loc in locations)
    total_oh_thb = sum(loc["onhand_thb"] for loc in locations)
    total_sold_qty = sum(loc["lifetime_sold_qty"] for loc in locations)
    total_sold_thb = sum(loc["lifetime_sold_thb"] for loc in locations)
    total_sold_master_thb = sum(loc["lifetime_sold_master_thb"] for loc in locations)

    # --- ABCDE classification (OBJ-83) ---
    # Classify this item within its brand AND overall company by revenue contribution
    abcde_in_brand = "E"
    abcde_overall = "E"

    def _classify_item_in_group(item_code_target, df_sale_all, brand_filter=None, year_filter=None):
        """Classify an item's ABCDE tier within a revenue group."""
        sl2 = df_sale_all.copy()
        sl2["ItemCode"] = sl2["ItemCode"].astype(str).str.strip()
        sl2["DocDate"] = pd.to_datetime(sl2["DocDate"], errors="coerce")
        sl2 = sl2.dropna(subset=["DocDate"])
        if year_filter:
            sl2 = sl2[sl2["DocDate"].dt.year.isin(year_filter)]
        if brand_filter and "Brand" in sl2.columns:
            sl2 = sl2[sl2["Brand"].astype(str).str.strip() == brand_filter]
        if sl2.empty:
            return "E"
        rev_by_item = sl2.groupby("ItemCode")["LineTotal"].sum().sort_values(ascending=False)
        total = rev_by_item.sum()
        if total <= 0:
            return "E"
        cum_pct = rev_by_item.cumsum() / total * 100.0
        target = str(item_code_target).strip()
        if target not in cum_pct.index:
            return "E"
        pct = float(cum_pct[target])
        idx = list(cum_pct.index).index(target)
        if pct <= 50.0 or idx == 0:
            return "A"
        elif pct <= 80.0:
            return "B"
        elif pct <= 95.0:
            return "C"
        elif pct <= 99.0:
            return "D"
        return "E"

    # Need brand-enriched sales for classification
    if not df_sale.empty and "ItemCode" in df_sale.columns:
        sale_enriched = df_sale.copy()
        if "Brand" not in sale_enriched.columns and "GroupName" in df_item_master.columns:
            brand_lk = (
                df_item_master[["ItemCode", "GroupName"]]
                .drop_duplicates("ItemCode")
                .rename(columns={"GroupName": "Brand"})
            )
            sale_enriched["ItemCode"] = sale_enriched["ItemCode"].astype(str).str.strip()
            brand_lk["ItemCode"] = brand_lk["ItemCode"].astype(str).str.strip()
            sale_enriched = sale_enriched.merge(brand_lk, on="ItemCode", how="left")

        abcde_in_brand = _classify_item_in_group(
            item_code, sale_enriched, brand_filter=brand, year_filter=year_list,
        )
        abcde_overall = _classify_item_in_group(
            item_code, sale_enriched, brand_filter=None, year_filter=year_list,
        )

    gross_profit = total_sold_thb - total_cogs_thb - total_gp_commission
    margin_pct = (gross_profit / total_sold_thb * 100.0) if total_sold_thb > 0 else 0.0

    return {
        "found": True,
        "item_info": {
            "item_code": str(item_code).strip(),
            "item_name": item_name,
            "brand": brand,
            "master_price": master_price,
            "total_onhand_qty": total_oh_qty,
            "total_onhand_thb": round(total_oh_thb, 2),
            "total_sold_qty": total_sold_qty,
            "total_sold_thb": round(total_sold_thb, 2),
            "total_sold_master_thb": round(total_sold_master_thb, 2),
            "total_cogs_thb": round(total_cogs_thb, 2),
            "total_gp_commission": round(total_gp_commission, 2),
            "gross_profit_thb": round(gross_profit, 2),
            "margin_pct": round(margin_pct, 1),
            "abcde_class_in_brand": abcde_in_brand,
            "abcde_class_overall": abcde_overall,
        },
        "locations": locations,
    }


def compute_item_monthly_trend(
    item_code: str,
    df_sale: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_onhand: pd.DataFrame = None,
    df_grpo_detail: pd.DataFrame = None,
    df_tr_in: pd.DataFrame = None,
    df_tr_out: pd.DataFrame = None,
    *,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Monthly sales trend for a single item across all locations.

    Includes historical on-hand reconstruction: starting from the current
    on-hand snapshot, work backwards month by month:
      - Each month's sales (+) increases the prior month's on-hand
      - Each month's purchases (-) decreases the prior month's on-hand
      - Transfer IN (-) and Transfer OUT (+) adjust accordingly

    Returns
    -------
    dict with:
      - found: bool
      - months: [{period, sold_qty, sold_thb, sold_master_thb, onhand_qty}]
    """
    if df_sale is None or df_sale.empty or df_item_master is None:
        return {"found": False, "months": []}

    item_str = str(item_code).strip()

    # Master price lookup
    master_match = df_item_master[
        df_item_master["ItemCode"].astype(str).str.strip() == item_str
    ]
    master_price = float(master_match.iloc[0].get("Price", 0) or 0) if not master_match.empty else 0.0

    sl = df_sale[df_sale["ItemCode"].astype(str).str.strip() == item_str].copy()
    if sl.empty:
        if master_match.empty:
            return {"found": False, "months": []}
        return {"found": True, "months": []}

    sl["DocDate"] = pd.to_datetime(sl.get("DocDate"), errors="coerce")
    sl = sl.dropna(subset=["DocDate"])
    if sl.empty:
        return {"found": True, "months": []}

    sl["Month"] = sl["DocDate"].dt.to_period("M").dt.start_time

    # Dedup
    sl["WhsCode"] = sl["WhsCode"].astype(str).str.strip() if "WhsCode" in sl.columns else ""
    dedup_cols = ["DocEntry", "ItemCode", "Month", "WhsCode"]
    available = [c for c in dedup_cols if c in sl.columns]
    if available:
        sl = sl.drop_duplicates(subset=available)

    sl["Quantity"] = pd.to_numeric(sl.get("Quantity", 0), errors="coerce").fillna(0).abs()
    sl["LineTotal"] = pd.to_numeric(sl.get("LineTotal", 0), errors="coerce").fillna(0).abs()

    # Use 'Price Master' from Sale sheet (line-level = Qty × unit master price)
    has_price_master = "Price Master" in sl.columns
    if has_price_master:
        sl["_PriceMaster"] = pd.to_numeric(sl["Price Master"], errors="coerce").fillna(0.0).clip(lower=0.0)
    elif master_price == 0.0:
        # No Item Master match and no Price Master column — can't compute
        if master_match.empty:
            return {"found": False, "months": []}

    # --- Build monthly aggregates for ALL months (before year filter) for on-hand reconstruction ---
    agg_dict = {"sold_qty": ("Quantity", "sum"), "sold_thb": ("LineTotal", "sum")}
    if has_price_master:
        agg_dict["sold_master_thb_sum"] = ("_PriceMaster", "sum")
    monthly_all = sl.groupby("Month", as_index=False).agg(**agg_dict).sort_values("Month")

    # --- Purchases (GRPO) per month ---
    purchased_by_month = {}
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        grpo_item = df_grpo_detail[
            df_grpo_detail["ItemCode"].astype(str).str.strip() == item_str
        ].copy()
        if not grpo_item.empty and "DocDate" in grpo_item.columns:
            grpo_item["DocDate"] = pd.to_datetime(grpo_item["DocDate"], errors="coerce")
            grpo_item = grpo_item.dropna(subset=["DocDate"])
            grpo_item["Month"] = grpo_item["DocDate"].dt.to_period("M").dt.start_time
            grpo_item["Qty"] = pd.to_numeric(grpo_item.get("Quantity", 0), errors="coerce").fillna(0).abs()
            grpo_agg = grpo_item.groupby("Month")["Qty"].sum()
            purchased_by_month = grpo_agg.to_dict()

    # --- Transfer IN per month ---
    tr_in_by_month = {}
    if df_tr_in is not None and not df_tr_in.empty:
        tri = df_tr_in[df_tr_in["ItemCode"].astype(str).str.strip() == item_str].copy()
        if not tri.empty and "DocDate" in tri.columns:
            tri["DocDate"] = pd.to_datetime(tri["DocDate"], errors="coerce")
            tri = tri.dropna(subset=["DocDate"])
            tri["Month"] = tri["DocDate"].dt.to_period("M").dt.start_time
            tri["Qty"] = pd.to_numeric(tri.get("Quantity", 0), errors="coerce").fillna(0).abs()
            tr_in_by_month = tri.groupby("Month")["Qty"].sum().to_dict()

    # --- Transfer OUT per month (quantities are negative in raw data) ---
    tr_out_by_month = {}
    if df_tr_out is not None and not df_tr_out.empty:
        tro = df_tr_out[df_tr_out["ItemCode"].astype(str).str.strip() == item_str].copy()
        if not tro.empty and "DocDate" in tro.columns:
            tro["DocDate"] = pd.to_datetime(tro["DocDate"], errors="coerce")
            tro = tro.dropna(subset=["DocDate"])
            tro["Month"] = tro["DocDate"].dt.to_period("M").dt.start_time
            tro["Qty"] = pd.to_numeric(tro.get("Quantity", 0), errors="coerce").fillna(0).abs()
            tr_out_by_month = tro.groupby("Month")["Qty"].sum().to_dict()

    # --- Historical on-hand reconstruction (work backwards from current) ---
    current_onhand = 0
    if df_onhand is not None and not df_onhand.empty:
        oh_item = df_onhand[df_onhand["ItemCode"].astype(str).str.strip() == item_str]
        if not oh_item.empty:
            current_onhand = float(pd.to_numeric(oh_item["OnHand"], errors="coerce").fillna(0).sum())

    # Collect all months from all sources
    all_months = set(monthly_all["Month"].tolist())
    all_months.update(purchased_by_month.keys())
    all_months.update(tr_in_by_month.keys())
    all_months.update(tr_out_by_month.keys())

    if not all_months:
        return {"found": True, "months": []}

    all_months_sorted = sorted(all_months)
    sold_by_month = dict(zip(monthly_all["Month"], monthly_all["sold_qty"]))

    # Build on-hand time series: end-of-month on-hand working backwards
    # current_onhand is the latest snapshot (end of current month)
    # For month M (going backwards): onhand_at_end_of_M = onhand_at_end_of_(M+1) + sold_in_(M+1) - purchased_in_(M+1)
    # But we also need transfers: + tr_out_in_(M+1) - tr_in_in_(M+1)
    onhand_eom = {}
    onhand_eom[all_months_sorted[-1]] = current_onhand

    for i in range(len(all_months_sorted) - 2, -1, -1):
        next_month = all_months_sorted[i + 1]
        this_month = all_months_sorted[i]
        sold_next = sold_by_month.get(next_month, 0)
        purchased_next = purchased_by_month.get(next_month, 0)
        tr_in_next = tr_in_by_month.get(next_month, 0)
        tr_out_next = tr_out_by_month.get(next_month, 0)
        # Working backwards: prior on-hand = current + sold - purchased - tr_in + tr_out
        raw_oh = onhand_eom[next_month] + sold_next - purchased_next - tr_in_next + tr_out_next
        # Clamp at zero: negative on-hand means incomplete data before window
        onhand_eom[this_month] = max(0, raw_oh)

    # --- Now filter to requested years and build response ---
    sold_thb_by_month = dict(zip(monthly_all["Month"], monthly_all["sold_thb"]))
    # Use pre-aggregated Price Master from Sale sheet when available
    if has_price_master:
        sold_master_by_month = dict(zip(monthly_all["Month"], monthly_all["sold_master_thb_sum"]))
    else:
        sold_master_by_month = None

    months = []
    for m in all_months_sorted:
        if year_list and m.year not in year_list:
            continue
        qty = float(sold_by_month.get(m, 0))
        if sold_master_by_month is not None:
            master_val = float(sold_master_by_month.get(m, 0))
        else:
            master_val = qty * master_price
        months.append({
            "period": m.strftime("%Y-%m"),
            "sold_qty": round(qty),
            "sold_thb": round(float(sold_thb_by_month.get(m, 0)), 2),
            "sold_master_thb": round(master_val, 2),
            "onhand_qty": round(float(onhand_eom.get(m, 0))),
        })

    # Annotate the last (possibly partial) month with a running rate so charts
    # can show a projected full-month value instead of an apparent collapse.
    try:
        from app.utils.running_rate import annotate_monthly_series, get_data_as_of_date
        annotate_monthly_series(
            months,
            get_data_as_of_date(df_sale),
            numeric_fields=["sold_qty", "sold_thb", "sold_master_thb"],
        )
    except Exception:
        pass

    return {"found": True, "months": months}


# ---------------------------------------------------------------------------
# Item-at-Location trend — monthly time series for one item at one location
# ---------------------------------------------------------------------------

def compute_item_at_location_trend(
    item_code: str,
    whs_code: str,
    df_sale: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_onhand: pd.DataFrame = None,
    df_grpo_detail: pd.DataFrame = None,
    df_tr_in: pd.DataFrame = None,
    df_tr_out: pd.DataFrame = None,
    df_whs_code: pd.DataFrame = None,
    *,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Monthly sales trend for a single item at a single location.

    Includes historical on-hand reconstruction at this location,
    COGS, GP commission, and profit metrics.

    Returns
    -------
    dict with:
      - found: bool
      - item_info: dict (item_code, item_name, brand, master_price, whs_code, whs_name)
      - summary: dict (total sold qty/thb, on-hand, cogs, gp_commission, gross_profit, margin)
      - months: [{period, sold_qty, sold_thb, sold_master_thb, onhand_qty}]
    """
    if df_sale is None or df_sale.empty or df_item_master is None:
        return {"found": False, "months": [], "item_info": {}, "summary": {}}

    item_str = str(item_code).strip()
    whs_str = str(whs_code).strip()

    # Master price + item info
    master_match = df_item_master[
        df_item_master["ItemCode"].astype(str).str.strip() == item_str
    ]
    if master_match.empty:
        return {"found": False, "months": [], "item_info": {}, "summary": {}}
    row0 = master_match.iloc[0]
    master_price = float(row0.get("Price", 0) or 0)
    item_name = str(row0.get("ItemName", row0.get("Dscription", "")))
    brand = str(row0.get("GroupName", ""))

    # Warehouse name lookup
    whs_name = whs_str
    if df_whs_code is not None and not df_whs_code.empty:
        wn = df_whs_code[df_whs_code["WhsCode"].astype(str).str.strip() == whs_str]
        if not wn.empty:
            whs_name = str(wn.iloc[0].get("WhsName", whs_str))

    item_info = {
        "item_code": item_str,
        "item_name": item_name,
        "brand": brand,
        "master_price": master_price,
        "whs_code": whs_str,
        "whs_name": whs_name,
    }

    # --- Filter sales to this item + location ---
    sl = df_sale[
        (df_sale["ItemCode"].astype(str).str.strip() == item_str)
        & (df_sale["WhsCode"].astype(str).str.strip() == whs_str)
    ].copy()

    sl["DocDate"] = pd.to_datetime(sl.get("DocDate"), errors="coerce") if not sl.empty else sl
    if not sl.empty:
        sl = sl.dropna(subset=["DocDate"])
    if not sl.empty:
        sl["Month"] = sl["DocDate"].dt.to_period("M").dt.start_time
        dedup_cols = [c for c in ["DocEntry", "ItemCode", "Month", "WhsCode"] if c in sl.columns]
        if dedup_cols:
            sl = sl.drop_duplicates(subset=dedup_cols)
        sl["Quantity"] = pd.to_numeric(sl.get("Quantity", 0), errors="coerce").fillna(0).abs()
        sl["LineTotal"] = pd.to_numeric(sl.get("LineTotal", 0), errors="coerce").fillna(0).abs()

    # --- Monthly aggregates (all months, before year filter) ---
    if not sl.empty:
        monthly_all = sl.groupby("Month", as_index=False).agg(
            sold_qty=("Quantity", "sum"),
            sold_thb=("LineTotal", "sum"),
        ).sort_values("Month")
    else:
        monthly_all = pd.DataFrame(columns=["Month", "sold_qty", "sold_thb"])

    # --- Purchases (GRPO) at this location per month ---
    purchased_by_month = {}
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        grpo_item = df_grpo_detail[
            (df_grpo_detail["ItemCode"].astype(str).str.strip() == item_str)
            & (df_grpo_detail["WhsCode"].astype(str).str.strip() == whs_str)
        ].copy()
        if not grpo_item.empty and "DocDate" in grpo_item.columns:
            grpo_item["DocDate"] = pd.to_datetime(grpo_item["DocDate"], errors="coerce")
            grpo_item = grpo_item.dropna(subset=["DocDate"])
            grpo_item["Month"] = grpo_item["DocDate"].dt.to_period("M").dt.start_time
            grpo_item["Qty"] = pd.to_numeric(grpo_item.get("Quantity", 0), errors="coerce").fillna(0).abs()
            purchased_by_month = grpo_item.groupby("Month")["Qty"].sum().to_dict()

    # --- Transfer IN at this location per month ---
    tr_in_by_month = {}
    if df_tr_in is not None and not df_tr_in.empty:
        tri = df_tr_in[
            (df_tr_in["ItemCode"].astype(str).str.strip() == item_str)
            & (df_tr_in["WhsCode"].astype(str).str.strip() == whs_str)
        ].copy()
        if not tri.empty and "DocDate" in tri.columns:
            tri["DocDate"] = pd.to_datetime(tri["DocDate"], errors="coerce")
            tri = tri.dropna(subset=["DocDate"])
            tri["Month"] = tri["DocDate"].dt.to_period("M").dt.start_time
            tri["Qty"] = pd.to_numeric(tri.get("Quantity", 0), errors="coerce").fillna(0).abs()
            tr_in_by_month = tri.groupby("Month")["Qty"].sum().to_dict()

    # --- Transfer OUT from this location per month ---
    tr_out_by_month = {}
    if df_tr_out is not None and not df_tr_out.empty:
        tro = df_tr_out[
            (df_tr_out["ItemCode"].astype(str).str.strip() == item_str)
            & (df_tr_out["WhsCode"].astype(str).str.strip() == whs_str)
        ].copy()
        if not tro.empty and "DocDate" in tro.columns:
            tro["DocDate"] = pd.to_datetime(tro["DocDate"], errors="coerce")
            tro = tro.dropna(subset=["DocDate"])
            tro["Month"] = tro["DocDate"].dt.to_period("M").dt.start_time
            tro["Qty"] = pd.to_numeric(tro.get("Quantity", 0), errors="coerce").fillna(0).abs()
            tr_out_by_month = tro.groupby("Month")["Qty"].sum().to_dict()

    # --- Historical on-hand reconstruction at this location ---
    current_onhand = 0
    if df_onhand is not None and not df_onhand.empty:
        oh_item = df_onhand[
            (df_onhand["ItemCode"].astype(str).str.strip() == item_str)
            & (df_onhand["WhsCode"].astype(str).str.strip() == whs_str)
        ]
        if not oh_item.empty:
            current_onhand = float(pd.to_numeric(oh_item["OnHand"], errors="coerce").fillna(0).sum())

    # Collect all months
    all_months = set(monthly_all["Month"].tolist()) if not monthly_all.empty else set()
    all_months.update(purchased_by_month.keys())
    all_months.update(tr_in_by_month.keys())
    all_months.update(tr_out_by_month.keys())

    sold_by_month = dict(zip(monthly_all["Month"], monthly_all["sold_qty"])) if not monthly_all.empty else {}
    sold_thb_by_month = dict(zip(monthly_all["Month"], monthly_all["sold_thb"])) if not monthly_all.empty else {}

    onhand_eom = {}
    if all_months:
        all_months_sorted = sorted(all_months)
        onhand_eom[all_months_sorted[-1]] = current_onhand
        for i in range(len(all_months_sorted) - 2, -1, -1):
            next_month = all_months_sorted[i + 1]
            this_month = all_months_sorted[i]
            raw_oh = (
                onhand_eom[next_month]
                + sold_by_month.get(next_month, 0)
                - purchased_by_month.get(next_month, 0)
                - tr_in_by_month.get(next_month, 0)
                + tr_out_by_month.get(next_month, 0)
            )
            # Clamp at zero: negative on-hand means incomplete data before window
            onhand_eom[this_month] = max(0, raw_oh)
    else:
        all_months_sorted = []

    # --- COGS and GP Commission (year-filtered) ---
    total_cogs_thb = 0.0
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        grpo_loc = df_grpo_detail[
            (df_grpo_detail["ItemCode"].astype(str).str.strip() == item_str)
            & (df_grpo_detail["WhsCode"].astype(str).str.strip() == whs_str)
        ].copy()
        if year_list and not grpo_loc.empty and "DocDate" in grpo_loc.columns:
            grpo_loc["DocDate"] = pd.to_datetime(grpo_loc["DocDate"], errors="coerce")
            grpo_loc = grpo_loc[grpo_loc["DocDate"].dt.year.isin(year_list)]
        if not grpo_loc.empty:
            grpo_loc["Price"] = pd.to_numeric(grpo_loc.get("Price", 0), errors="coerce").fillna(0)
            grpo_loc["Rate"] = pd.to_numeric(grpo_loc.get("Rate", 0), errors="coerce").fillna(0)
            grpo_loc["Qty"] = pd.to_numeric(grpo_loc.get("Quantity", 0), errors="coerce").fillna(0)
            total_cogs_thb = float((grpo_loc["Price"] * grpo_loc["Rate"] * grpo_loc["Qty"]).sum())

    total_gp_commission = 0.0
    sl_for_gp = sl.copy() if not sl.empty else pd.DataFrame()
    if year_list and not sl_for_gp.empty:
        sl_for_gp = sl_for_gp[sl_for_gp["DocDate"].dt.year.isin(year_list)]
    if not sl_for_gp.empty:
        from app.utils.nichi_stock import compute_gp_commission
        gp_series = compute_gp_commission(sl_for_gp)
        total_gp_commission = float(gp_series.sum())

    # --- Build filtered months ---
    months = []
    total_sold_qty = 0
    total_sold_thb = 0.0
    total_sold_master = 0.0
    for m in all_months_sorted:
        if year_list and m.year not in year_list:
            continue
        qty = float(sold_by_month.get(m, 0))
        thb = float(sold_thb_by_month.get(m, 0))
        master = qty * master_price
        total_sold_qty += qty
        total_sold_thb += thb
        total_sold_master += master
        months.append({
            "period": m.strftime("%Y-%m"),
            "sold_qty": round(qty),
            "sold_thb": round(thb, 2),
            "sold_master_thb": round(master, 2),
            "onhand_qty": round(float(onhand_eom.get(m, 0))),
        })

    gross_profit = total_sold_thb - total_cogs_thb - total_gp_commission
    margin_pct = (gross_profit / total_sold_thb * 100) if total_sold_thb > 0 else None

    summary = {
        "total_sold_qty": round(total_sold_qty),
        "total_sold_thb": round(total_sold_thb, 2),
        "total_sold_master_thb": round(total_sold_master, 2),
        "current_onhand_qty": round(current_onhand),
        "current_onhand_thb": round(current_onhand * master_price, 2),
        "total_cogs_thb": round(total_cogs_thb, 2),
        "total_gp_commission": round(total_gp_commission, 2),
        "gross_profit_thb": round(gross_profit, 2),
        "margin_pct": round(margin_pct, 1) if margin_pct is not None else None,
    }

    # Annotate the last (possibly partial) month with a running rate.
    try:
        from app.utils.running_rate import annotate_monthly_series, get_data_as_of_date
        annotate_monthly_series(
            months,
            get_data_as_of_date(df_sale),
            numeric_fields=["sold_qty", "sold_thb", "sold_master_thb"],
        )
    except Exception:
        pass

    return {
        "found": True,
        "item_info": item_info,
        "summary": summary,
        "months": months,
    }
