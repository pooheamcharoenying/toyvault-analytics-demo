"""Stock Allocation Optimization & Transfer Analysis.

Business context: A toy distributor has stock spread across multiple warehouses and stores.
A product sitting in Warehouse A with zero sales should be transferred to Store B where
it's selling fast.  Getting this right reduces dead stock AND prevents stockouts.

Three functions:
1. compute_stock_allocation() — per-item overstocked/understocked locations + transfer recs
2. compute_transfer_history() — TR IN/TR OUT analysis: net flow, top items, patterns
3. compute_rebalancing_summary() — high-level opportunity: total THB moveable, surplus/deficit
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


def _prepare_onhand_with_price(
    df_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare on-hand data with master price and warehouse names."""
    oh = df_onhand.copy()
    oh["WhsCode"] = oh["WhsCode"].astype(str).str.strip()
    oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0.0)

    im_cols = ["ItemCode", "Price", "GroupName"]
    if "ItemName" in df_item_master.columns:
        im_cols.append("ItemName")
    im = df_item_master[im_cols].copy()
    im = im.rename(columns={"Price": "Master Price", "GroupName": "Brand"})
    oh = oh.merge(im, on="ItemCode", how="left")
    oh["Master Price"] = pd.to_numeric(oh["Master Price"], errors="coerce").fillna(0.0)
    oh["OnHand_THB"] = oh["OnHand"] * oh["Master Price"]
    oh["Brand"] = oh["Brand"].fillna("Unknown")
    if "ItemName" in oh.columns:
        oh["ItemName"] = oh["ItemName"].fillna("")

    whs = df_whs_code[["WhsCode", "WhsName"]].copy()
    whs["WhsCode"] = whs["WhsCode"].astype(str).str.strip()
    oh = oh.merge(whs, on="WhsCode", how="left")
    oh["WhsName"] = oh["WhsName"].fillna(oh["WhsCode"])

    # Apply location consolidation (e.g., CT-ลาดพร้าว GP25/GP33 -> CT-ลาดพร้าว)
    from app.utils.location_consolidation import add_consolidated_column
    _whs_lookup = dict(zip(whs["WhsCode"], whs["WhsName"]))
    oh = add_consolidated_column(oh, _whs_lookup)
    oh["WhsName"] = oh["ConsolidatedLocation"]

    return oh


# ---------------------------------------------------------------------------
# 1. Stock Allocation — overstocked/understocked + transfer recommendations
# ---------------------------------------------------------------------------

def compute_stock_allocation(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    *,
    year: Optional[int] = None,
    brand: Optional[str] = None,
    window_days: int = 90,
    top_n: int = 50,
) -> dict[str, Any]:
    """Identify overstocked/understocked locations and generate transfer recommendations.

    For each item at each location, compare on-hand quantity against sales velocity.
    Locations with high days-of-cover (surplus) should transfer to locations with low
    days-of-cover (deficit).

    Returns:
        {
            "summary": {total_items, total_locations, transfer_recommendations, potential_thb_savings},
            "recommendations": [{item, from_location, to_location, qty, thb_value, ...}],
            "overstocked": [{item, location, onhand, days_cover, excess_qty, excess_thb}],
            "understocked": [{item, location, onhand, days_cover, deficit_qty, deficit_thb}],
        }
    """
    # Prepare data — returns (df_sale, df_onhand, df_item_month) tuple
    df_sale_prep, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    df_sale_prep = _channel_dedup_sale(df_sale_prep) if not df_sale_prep.empty else df_sale_prep

    oh = _prepare_onhand_with_price(df_raw_onhand, df_item_master, df_whs_code)

    # Filter by brand if specified
    if brand and not oh.empty:
        oh = oh[oh["Brand"] == brand]
    if brand and not df_sale_prep.empty:
        if "Brand" in df_sale_prep.columns:
            df_sale_prep = df_sale_prep[df_sale_prep["Brand"] == brand]

    if oh.empty:
        return {
            "summary": {"total_items": 0, "total_locations": 0,
                        "transfer_recommendations": 0, "potential_thb_savings": 0},
            "recommendations": [],
            "overstocked": [],
            "understocked": [],
        }

    # Compute sales velocity per item per location (last N days)
    velocity = pd.DataFrame()
    if not df_sale_prep.empty:
        cutoff = df_sale_prep["DocDate"].max() - pd.Timedelta(days=window_days)
        recent = df_sale_prep[df_sale_prep["DocDate"] >= cutoff].copy()
        if year:
            recent = recent[recent["DocDate"].dt.year == year]
        recent["WhsCode"] = recent["WhsCode"].astype(str).str.strip()
        velocity = (
            recent.groupby(["ItemCode", "WhsCode"])
            .agg(
                sold_qty=("Quantity", "sum"),
                sold_thb=("LineTotal", "sum"),
            )
            .reset_index()
        )
        velocity["daily_sales"] = velocity["sold_qty"] / max(window_days, 1)

    # Merge on-hand with velocity
    group_cols = ["ItemCode", "WhsCode", "WhsName", "Brand", "Master Price"]
    if "ItemName" in oh.columns:
        group_cols.insert(1, "ItemName")
    oh_agg = (
        oh.groupby(group_cols)
        .agg(onhand_qty=("OnHand", "sum"), onhand_thb=("OnHand_THB", "sum"))
        .reset_index()
    )
    oh_agg = oh_agg[oh_agg["onhand_qty"] > 0]

    if not velocity.empty:
        merged = oh_agg.merge(velocity, on=["ItemCode", "WhsCode"], how="left")
    else:
        merged = oh_agg.copy()
        merged["sold_qty"] = 0.0
        merged["sold_thb"] = 0.0
        merged["daily_sales"] = 0.0

    merged["sold_qty"] = merged["sold_qty"].fillna(0.0)
    merged["sold_thb"] = merged["sold_thb"].fillna(0.0)
    merged["daily_sales"] = merged["daily_sales"].fillna(0.0)

    # Days of cover per item-location
    merged["days_cover"] = np.where(
        merged["daily_sales"] > 0,
        merged["onhand_qty"] / merged["daily_sales"],
        np.inf,
    )

    # Compute item-level target: median days of cover across locations with sales
    # Items with no sales anywhere get infinity
    item_targets = (
        merged[merged["daily_sales"] > 0]
        .groupby("ItemCode")
        .agg(
            median_days_cover=("days_cover", "median"),
            total_daily_sales=("daily_sales", "sum"),
        )
        .reset_index()
    )

    merged = merged.merge(item_targets, on="ItemCode", how="left")
    merged["median_days_cover"] = merged["median_days_cover"].fillna(np.inf)
    merged["total_daily_sales"] = merged["total_daily_sales"].fillna(0.0)

    # Target days cover: use 90 days or median, whichever is higher (to avoid excessive transfers)
    TARGET_DAYS = 90
    merged["target_days"] = merged["median_days_cover"].clip(lower=TARGET_DAYS, upper=180)

    # Excess/deficit qty vs target
    merged["target_qty"] = np.where(
        merged["daily_sales"] > 0,
        merged["daily_sales"] * merged["target_days"],
        0,  # No sales = target is 0 stock here
    )
    merged["excess_qty"] = (merged["onhand_qty"] - merged["target_qty"]).clip(lower=0)
    merged["deficit_qty"] = (merged["target_qty"] - merged["onhand_qty"]).clip(lower=0)
    merged["excess_thb"] = merged["excess_qty"] * merged["Master Price"]
    merged["deficit_thb"] = merged["deficit_qty"] * merged["Master Price"]

    # Overstocked: high on-hand, no/low sales, or days_cover >> target
    overstocked_mask = (merged["excess_qty"] > 0) | (
        (merged["onhand_qty"] > 0) & (merged["daily_sales"] == 0)
    )
    overstocked = merged[overstocked_mask].copy()
    # For zero-sales locations, excess = entire on-hand
    zero_sales_mask = overstocked["daily_sales"] == 0
    overstocked.loc[zero_sales_mask, "excess_qty"] = overstocked.loc[zero_sales_mask, "onhand_qty"]
    overstocked.loc[zero_sales_mask, "excess_thb"] = overstocked.loc[zero_sales_mask, "onhand_thb"]
    overstocked = overstocked.sort_values("excess_thb", ascending=False).head(top_n)

    # Understocked: low on-hand relative to sales velocity
    understocked = merged[merged["deficit_qty"] > 0].copy()
    understocked = understocked.sort_values("deficit_thb", ascending=False).head(top_n)

    # Generate transfer recommendations
    recommendations = _generate_transfer_recs(merged, top_n)

    summary = {
        "total_items": int(merged["ItemCode"].nunique()),
        "total_locations": int(merged["WhsCode"].nunique()),
        "transfer_recommendations": len(recommendations),
        "potential_thb_savings": round(
            sum(r["transfer_thb"] for r in recommendations), 2
        ),
    }

    return {
        "summary": summary,
        "recommendations": recommendations,
        "overstocked": _df_to_records(overstocked, [
            "ItemCode", "ItemName", "WhsCode", "WhsName", "Brand", "onhand_qty", "onhand_thb",
            "sold_qty", "daily_sales", "days_cover", "excess_qty", "excess_thb",
        ]),
        "understocked": _df_to_records(understocked, [
            "ItemCode", "ItemName", "WhsCode", "WhsName", "Brand", "onhand_qty", "onhand_thb",
            "sold_qty", "daily_sales", "days_cover", "deficit_qty", "deficit_thb",
        ]),
    }


def _generate_transfer_recs(merged: pd.DataFrame, top_n: int) -> list[dict]:
    """Match surplus locations with deficit locations for the same item."""
    recs = []
    items_with_both = set(
        merged[merged["excess_qty"] > 0]["ItemCode"]
    ) & set(
        merged[merged["deficit_qty"] > 0]["ItemCode"]
    )

    for item in items_with_both:
        item_data = merged[merged["ItemCode"] == item]
        surplus = item_data[item_data["excess_qty"] > 0].sort_values("excess_qty", ascending=False)
        deficit = item_data[item_data["deficit_qty"] > 0].sort_values("deficit_qty", ascending=False)

        s_idx = 0
        d_idx = 0
        s_remaining = surplus.iloc[0]["excess_qty"] if len(surplus) > 0 else 0
        d_remaining = deficit.iloc[0]["deficit_qty"] if len(deficit) > 0 else 0

        while s_idx < len(surplus) and d_idx < len(deficit) and len(recs) < top_n * 2:
            s_row = surplus.iloc[s_idx]
            d_row = deficit.iloc[d_idx]

            transfer_qty = min(s_remaining, d_remaining)
            if transfer_qty <= 0:
                break

            price = float(s_row.get("Master Price", 0))
            recs.append({
                "ItemCode": str(item),
                "ItemName": str(s_row.get("ItemName", "")),
                "Brand": str(s_row.get("Brand", "")),
                "from_location": str(s_row["WhsCode"]),
                "from_name": str(s_row.get("WhsName", s_row["WhsCode"])),
                "from_days_cover": _safe_float(s_row["days_cover"]),
                "to_location": str(d_row["WhsCode"]),
                "to_name": str(d_row.get("WhsName", d_row["WhsCode"])),
                "to_days_cover": _safe_float(d_row["days_cover"]),
                "transfer_qty": round(float(transfer_qty)),
                "transfer_thb": round(float(transfer_qty) * price, 2),
            })

            s_remaining -= transfer_qty
            d_remaining -= transfer_qty

            if s_remaining <= 0:
                s_idx += 1
                if s_idx < len(surplus):
                    s_remaining = surplus.iloc[s_idx]["excess_qty"]
            if d_remaining <= 0:
                d_idx += 1
                if d_idx < len(deficit):
                    d_remaining = deficit.iloc[d_idx]["deficit_qty"]

    recs.sort(key=lambda r: r["transfer_thb"], reverse=True)
    return recs[:top_n]


def _safe_float(v) -> float:
    """Convert value to float, replacing inf/nan with sentinel."""
    f = float(v)
    if np.isinf(f):
        return 99999.0
    if np.isnan(f):
        return 0.0
    return round(f, 1)


def _df_to_records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    """Convert DataFrame to list of dicts with safe float conversion."""
    if df.empty:
        return []
    available = [c for c in cols if c in df.columns]
    out = df[available].copy()
    for c in out.select_dtypes(include=[np.floating]).columns:
        out[c] = out[c].apply(_safe_float)
    return out.to_dict(orient="records")


# ---------------------------------------------------------------------------
# 2. Transfer History Analysis
# ---------------------------------------------------------------------------

def compute_transfer_history(
    df_tr_in: pd.DataFrame,
    df_tr_out: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    df_item_master: pd.DataFrame,
    *,
    year: Optional[int] = None,
    top_n: int = 20,
) -> dict[str, Any]:
    """Analyze TR IN/TR OUT data for transfer patterns.

    Returns:
        {
            "summary": {total_transfers_in, total_transfers_out, total_items_transferred,
                        total_qty_in, total_qty_out, net_qty},
            "location_flows": [{WhsCode, WhsName, qty_in, qty_out, net_flow, transfer_count}],
            "top_items": [{ItemCode, Brand, total_in, total_out, net, location_count}],
            "monthly_trend": [{period, qty_in, qty_out, net, count}],
        }
    """
    whs = df_whs_code[["WhsCode", "WhsName"]].copy()
    whs["WhsCode"] = whs["WhsCode"].astype(str).str.strip()

    # Build consolidated name lookup for display
    from app.utils.location_consolidation import get_consolidated_name
    _whs_lookup = dict(zip(whs["WhsCode"], whs["WhsName"]))

    im = df_item_master[["ItemCode", "GroupName"]].copy()
    im = im.rename(columns={"GroupName": "Brand"})

    # Process TR IN
    tr_in = df_tr_in.copy() if df_tr_in is not None and not df_tr_in.empty else pd.DataFrame()
    tr_out = df_tr_out.copy() if df_tr_out is not None and not df_tr_out.empty else pd.DataFrame()

    if tr_in.empty and tr_out.empty:
        return {
            "summary": {"total_transfers_in": 0, "total_transfers_out": 0,
                        "total_items_transferred": 0, "total_qty_in": 0,
                        "total_qty_out": 0, "net_qty": 0},
            "location_flows": [],
            "top_items": [],
            "monthly_trend": [],
        }

    # Standardize
    for df in [tr_in, tr_out]:
        if not df.empty:
            df["DocDate"] = pd.to_datetime(df["DocDate"], errors="coerce")
            df["WhsCode"] = df["WhsCode"].astype(str).str.strip()
            df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)

    # Year filter
    if year:
        if not tr_in.empty:
            tr_in = tr_in[tr_in["DocDate"].dt.year == year]
        if not tr_out.empty:
            tr_out = tr_out[tr_out["DocDate"].dt.year == year]

    total_qty_in = int(tr_in["Quantity"].sum()) if not tr_in.empty else 0
    total_qty_out = int(abs(tr_out["Quantity"].sum())) if not tr_out.empty else 0

    # Location flows
    in_by_loc = pd.DataFrame()
    if not tr_in.empty:
        in_by_loc = (
            tr_in.groupby("WhsCode")
            .agg(qty_in=("Quantity", "sum"), count_in=("DocEntry", "nunique"))
            .reset_index()
        )

    out_by_loc = pd.DataFrame()
    if not tr_out.empty:
        out_by_loc = (
            tr_out.groupby("WhsCode")
            .agg(qty_out=("Quantity", lambda x: abs(x.sum())), count_out=("DocEntry", "nunique"))
            .reset_index()
        )

    # Combine
    all_whs = set()
    if not in_by_loc.empty:
        all_whs.update(in_by_loc["WhsCode"].tolist())
    if not out_by_loc.empty:
        all_whs.update(out_by_loc["WhsCode"].tolist())

    loc_flows = []
    for w in sorted(all_whs):
        qi = float(in_by_loc[in_by_loc["WhsCode"] == w]["qty_in"].sum()) if not in_by_loc.empty else 0
        qo = float(out_by_loc[out_by_loc["WhsCode"] == w]["qty_out"].sum()) if not out_by_loc.empty else 0
        ci = int(in_by_loc[in_by_loc["WhsCode"] == w]["count_in"].sum()) if not in_by_loc.empty else 0
        co = int(out_by_loc[out_by_loc["WhsCode"] == w]["count_out"].sum()) if not out_by_loc.empty else 0
        loc_flows.append({
            "WhsCode": w,
            "WhsName": get_consolidated_name(w, _whs_lookup),
            "qty_in": round(qi),
            "qty_out": round(qo),
            "net_flow": round(qi - qo),
            "transfer_count": ci + co,
        })
    loc_flows.sort(key=lambda r: abs(r["net_flow"]), reverse=True)

    # Top transferred items
    all_transfers = []
    if not tr_in.empty:
        ti = tr_in[["ItemCode", "Quantity", "WhsCode"]].copy()
        ti["direction"] = "in"
        all_transfers.append(ti)
    if not tr_out.empty:
        to = tr_out[["ItemCode", "Quantity", "WhsCode"]].copy()
        to["Quantity"] = to["Quantity"].abs()
        to["direction"] = "out"
        all_transfers.append(to)

    top_items = []
    if all_transfers:
        combined = pd.concat(all_transfers, ignore_index=True)
        combined = combined.merge(im, on="ItemCode", how="left")
        combined["Brand"] = combined["Brand"].fillna("Unknown")

        item_summary = (
            combined.groupby(["ItemCode", "Brand"])
            .agg(
                total_qty=("Quantity", "sum"),
                location_count=("WhsCode", "nunique"),
            )
            .reset_index()
        )

        # Split in/out
        if not tr_in.empty:
            in_items = tr_in.groupby("ItemCode")["Quantity"].sum().rename("total_in")
        else:
            in_items = pd.Series(dtype=float, name="total_in")

        if not tr_out.empty:
            out_items = tr_out.groupby("ItemCode")["Quantity"].apply(lambda x: abs(x.sum())).rename("total_out")
        else:
            out_items = pd.Series(dtype=float, name="total_out")

        item_summary = item_summary.merge(in_items, on="ItemCode", how="left")
        item_summary = item_summary.merge(out_items, on="ItemCode", how="left")
        item_summary["total_in"] = item_summary["total_in"].fillna(0).astype(int)
        item_summary["total_out"] = item_summary["total_out"].fillna(0).astype(int)
        item_summary["net"] = item_summary["total_in"] - item_summary["total_out"]

        item_summary = item_summary.sort_values("total_qty", ascending=False).head(top_n)
        top_items = item_summary[["ItemCode", "Brand", "total_in", "total_out", "net", "location_count"]].to_dict(orient="records")

    # Monthly trend
    monthly = []
    all_dated = []
    if not tr_in.empty:
        tin = tr_in[["DocDate", "Quantity", "DocEntry"]].copy()
        tin["direction"] = "in"
        all_dated.append(tin)
    if not tr_out.empty:
        tout = tr_out[["DocDate", "Quantity", "DocEntry"]].copy()
        tout["Quantity"] = tout["Quantity"].abs()
        tout["direction"] = "out"
        all_dated.append(tout)

    if all_dated:
        dated = pd.concat(all_dated, ignore_index=True)
        dated = dated.dropna(subset=["DocDate"])
        dated["Period"] = dated["DocDate"].dt.to_period("M").dt.start_time

        for period, grp in dated.groupby("Period"):
            gi = grp[grp["direction"] == "in"]
            go = grp[grp["direction"] == "out"]
            monthly.append({
                "period": str(period.date()) if hasattr(period, "date") else str(period),
                "qty_in": int(gi["Quantity"].sum()) if not gi.empty else 0,
                "qty_out": int(go["Quantity"].sum()) if not go.empty else 0,
                "net": int(gi["Quantity"].sum() - go["Quantity"].sum()) if not gi.empty or not go.empty else 0,
                "count": int(grp["DocEntry"].nunique()),
            })
        monthly.sort(key=lambda r: r["period"])

    items_transferred = set()
    if not tr_in.empty:
        items_transferred.update(tr_in["ItemCode"].unique())
    if not tr_out.empty:
        items_transferred.update(tr_out["ItemCode"].unique())

    summary = {
        "total_transfers_in": int(tr_in["DocEntry"].nunique()) if not tr_in.empty else 0,
        "total_transfers_out": int(tr_out["DocEntry"].nunique()) if not tr_out.empty else 0,
        "total_items_transferred": len(items_transferred),
        "total_qty_in": total_qty_in,
        "total_qty_out": total_qty_out,
        "net_qty": total_qty_in - total_qty_out,
    }

    return {
        "summary": summary,
        "location_flows": loc_flows,
        "top_items": top_items,
        "monthly_trend": monthly,
    }


# ---------------------------------------------------------------------------
# 3. Rebalancing Summary
# ---------------------------------------------------------------------------

def compute_rebalancing_summary(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    *,
    year: Optional[int] = None,
    window_days: int = 90,
) -> dict[str, Any]:
    """High-level rebalancing opportunity summary.

    Returns:
        {
            "summary": {total_surplus_thb, total_deficit_thb, rebalanceable_thb,
                        surplus_locations, deficit_locations, items_to_move},
            "location_balance": [{WhsCode, WhsName, surplus_thb, deficit_thb, net_thb, status, priority}],
            "brand_opportunities": [{Brand, surplus_thb, deficit_thb, rebalanceable_thb, item_count}],
        }
    """
    # Use stock_allocation to get per-item data
    alloc = compute_stock_allocation(
        df_raw_sale, df_raw_onhand, df_item_master, df_whs_code,
        year=year, window_days=window_days, top_n=9999,
    )

    if not alloc["overstocked"] and not alloc["understocked"]:
        return {
            "summary": {"total_surplus_thb": 0, "total_deficit_thb": 0,
                        "rebalanceable_thb": 0, "surplus_locations": 0,
                        "deficit_locations": 0, "items_to_move": 0},
            "location_balance": [],
            "brand_opportunities": [],
        }

    # Location-level aggregates
    over_df = pd.DataFrame(alloc["overstocked"]) if alloc["overstocked"] else pd.DataFrame()
    under_df = pd.DataFrame(alloc["understocked"]) if alloc["understocked"] else pd.DataFrame()

    loc_surplus = {}
    loc_deficit = {}

    if not over_df.empty:
        for _, row in over_df.iterrows():
            key = (str(row.get("WhsCode", "")), str(row.get("WhsName", "")))
            loc_surplus[key] = loc_surplus.get(key, 0) + float(row.get("excess_thb", 0))

    if not under_df.empty:
        for _, row in under_df.iterrows():
            key = (str(row.get("WhsCode", "")), str(row.get("WhsName", "")))
            loc_deficit[key] = loc_deficit.get(key, 0) + float(row.get("deficit_thb", 0))

    all_locs = set(list(loc_surplus.keys()) + list(loc_deficit.keys()))
    location_balance = []
    for whs_code, whs_name in sorted(all_locs):
        s = loc_surplus.get((whs_code, whs_name), 0)
        d = loc_deficit.get((whs_code, whs_name), 0)
        net = s - d
        status = "surplus" if net > 0 else ("deficit" if net < 0 else "balanced")
        priority = "high" if abs(net) > 50000 else ("medium" if abs(net) > 10000 else "low")
        location_balance.append({
            "WhsCode": whs_code,
            "WhsName": whs_name,
            "surplus_thb": round(s, 2),
            "deficit_thb": round(d, 2),
            "net_thb": round(net, 2),
            "status": status,
            "priority": priority,
        })
    location_balance.sort(key=lambda r: abs(r["net_thb"]), reverse=True)

    # Brand-level opportunities
    brand_data = {}
    if not over_df.empty:
        for _, row in over_df.iterrows():
            b = str(row.get("Brand", "Unknown"))
            if b not in brand_data:
                brand_data[b] = {"surplus_thb": 0, "deficit_thb": 0, "items": set()}
            brand_data[b]["surplus_thb"] += float(row.get("excess_thb", 0))
            brand_data[b]["items"].add(str(row.get("ItemCode", "")))

    if not under_df.empty:
        for _, row in under_df.iterrows():
            b = str(row.get("Brand", "Unknown"))
            if b not in brand_data:
                brand_data[b] = {"surplus_thb": 0, "deficit_thb": 0, "items": set()}
            brand_data[b]["deficit_thb"] += float(row.get("deficit_thb", 0))
            brand_data[b]["items"].add(str(row.get("ItemCode", "")))

    brand_opps = []
    for b, data in brand_data.items():
        rebal = min(data["surplus_thb"], data["deficit_thb"])
        brand_opps.append({
            "Brand": b,
            "surplus_thb": round(data["surplus_thb"], 2),
            "deficit_thb": round(data["deficit_thb"], 2),
            "rebalanceable_thb": round(rebal, 2),
            "item_count": len(data["items"]),
        })
    brand_opps.sort(key=lambda r: r["rebalanceable_thb"], reverse=True)

    total_surplus = sum(r["surplus_thb"] for r in location_balance)
    total_deficit = sum(r["deficit_thb"] for r in location_balance)
    rebalanceable = min(total_surplus, total_deficit)

    items_set = set()
    if not over_df.empty:
        items_set.update(over_df.get("ItemCode", pd.Series()).tolist())
    if not under_df.empty:
        items_set.update(under_df.get("ItemCode", pd.Series()).tolist())

    summary = {
        "total_surplus_thb": round(total_surplus, 2),
        "total_deficit_thb": round(total_deficit, 2),
        "rebalanceable_thb": round(rebalanceable, 2),
        "surplus_locations": sum(1 for r in location_balance if r["status"] == "surplus"),
        "deficit_locations": sum(1 for r in location_balance if r["status"] == "deficit"),
        "items_to_move": len(items_set),
    }

    return {
        "summary": summary,
        "location_balance": location_balance,
        "brand_opportunities": brand_opps,
    }
