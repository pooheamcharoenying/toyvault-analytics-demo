"""Inventory Action Alerts — stockout risk, dead stock, and reorder point analysis.

Business context: A toy distributor's biggest risks are (1) running out of fast sellers
(lost revenue + damaged channel relationships) and (2) sitting on dead stock (locked
capital + warehouse costs).  These functions turn raw inventory + sales data into
actionable alerts that tell managers *what to do*, not just what the data says.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from app.utils import nichi_stock as nstk


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _channel_dedup_sale(
    df_sale_prepared: pd.DataFrame,
) -> pd.DataFrame:
    """Deduplicate sales by (DocEntry, ItemCode, Period, GroupName) using monthly periods."""
    df = df_sale_prepared.copy()
    df["DocDate"] = pd.to_datetime(df["DocDate"], errors="coerce")
    df = df.dropna(subset=["DocDate"])
    df["Period"] = df["DocDate"].dt.to_period("M").dt.start_time
    return df.drop_duplicates(subset=["DocEntry", "ItemCode", "Period", "GroupName"])


def _build_item_velocity(
    df_sale_prepared: pd.DataFrame,
    df_onhand: pd.DataFrame,
    window_days: int = 90,
    as_of: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Build per-item DataFrame with on-hand, sales velocity, and days of cover.

    Returns DataFrame with columns:
        ItemCode, Brand, ItemName, OnHand, Master Price, onhand_thb,
        sold_qty, sold_thb, avg_daily_qty, days_cover
    """
    d = _channel_dedup_sale(df_sale_prepared)
    if d.empty:
        # Return empty frame with correct columns
        return pd.DataFrame(columns=[
            "ItemCode", "Brand", "ItemName", "OnHand", "Master Price",
            "onhand_thb", "sold_qty", "sold_thb", "avg_daily_qty", "days_cover",
        ])

    if as_of is None:
        as_of_ts = d["DocDate"].max()
    else:
        as_of_ts = pd.to_datetime(as_of)
    start = as_of_ts - pd.Timedelta(days=window_days - 1)

    recent = d[(d["DocDate"] >= start) & (d["DocDate"] <= as_of_ts)]
    sold_agg = (
        recent.groupby("ItemCode", as_index=False)
        .agg(sold_qty=("Quantity", "sum"), sold_thb=("LineTotal", "sum"))
    )

    oh = df_onhand.copy()
    oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0.0)
    oh["Master Price"] = pd.to_numeric(oh["Master Price"], errors="coerce").fillna(0.0)
    oh["Brand"] = oh["Brand"].fillna("Unknown")
    oh["onhand_thb"] = oh["OnHand"] * oh["Master Price"]

    item = oh.merge(sold_agg, on="ItemCode", how="left")
    item["sold_qty"] = pd.to_numeric(item["sold_qty"], errors="coerce").fillna(0.0)
    item["sold_thb"] = pd.to_numeric(item["sold_thb"], errors="coerce").fillna(0.0)
    item["avg_daily_qty"] = item["sold_qty"] / float(window_days)
    item["days_cover"] = item.apply(
        lambda r: (float(r["OnHand"]) / float(r["avg_daily_qty"]))
        if float(r["avg_daily_qty"]) > 0
        else float("inf"),
        axis=1,
    )
    return item


# ---------------------------------------------------------------------------
# F-030a: Stockout Risk Alerts
# ---------------------------------------------------------------------------

def compute_stockout_risk(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    as_of: Optional[pd.Timestamp] = None,
    window_days: int = 90,
    stockout_threshold_days: int = 30,
    top_n: int = 50,
    brand: Optional[str] = None,
) -> dict[str, Any]:
    """Identify items at risk of stocking out based on sales velocity.

    An item is at risk if:
      - It has positive on-hand AND positive recent sales velocity
      - Its days_cover < stockout_threshold_days

    Returns items sorted by urgency (lowest days_cover first), with projected
    stockout dates and suggested reorder info.
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    item = _build_item_velocity(df_sale, df_onhand, window_days, as_of)
    if item.empty:
        return {"as_of": None, "window_days": window_days, "threshold_days": stockout_threshold_days, "rows": [], "summary": {}}

    if brand:
        item = item[item["Brand"].str.contains(brand, case=False, na=False)]
        if item.empty:
            return {"as_of": None, "window_days": window_days, "threshold_days": stockout_threshold_days, "rows": [], "summary": {}}

    # Determine as_of date for projected stockout
    d = _channel_dedup_sale(df_sale)
    as_of_ts = pd.to_datetime(as_of) if as_of is not None else d["DocDate"].max()

    # Filter: positive on-hand, positive velocity, days_cover below threshold
    at_risk = item[
        (item["OnHand"] > 0)
        & (item["avg_daily_qty"] > 0)
        & (item["days_cover"] < stockout_threshold_days)
    ].copy()

    at_risk = at_risk.sort_values("days_cover", ascending=True).head(top_n)

    # Severity: Critical (<7d), Warning (<14d), Watch (<threshold)
    def _severity(dc: float) -> str:
        if dc < 7:
            return "critical"
        if dc < 14:
            return "warning"
        return "watch"

    rows = []
    for _, r in at_risk.iterrows():
        dc = float(r["days_cover"])
        projected_stockout = as_of_ts + pd.Timedelta(days=dc)
        weekly_rate = float(r["avg_daily_qty"]) * 7
        rows.append({
            "item_code": str(r["ItemCode"]),
            "brand": str(r["Brand"]),
            "description": str(r.get("ItemName", "")),
            "onhand_qty": float(r["OnHand"]),
            "onhand_thb": float(r["onhand_thb"]),
            "sold_qty_window": float(r["sold_qty"]),
            "avg_daily_qty": round(float(r["avg_daily_qty"]), 2),
            "weekly_rate": round(weekly_rate, 1),
            "days_cover": round(dc, 1),
            "projected_stockout": projected_stockout.strftime("%Y-%m-%d"),
            "severity": _severity(dc),
            "suggested_reorder_qty": round(weekly_rate * 8, 0),  # 8 weeks cover
        })

    # Summary stats
    total_at_risk_thb = float(at_risk["onhand_thb"].sum()) if not at_risk.empty else 0.0
    critical_count = sum(1 for row in rows if row["severity"] == "critical")
    warning_count = sum(1 for row in rows if row["severity"] == "warning")

    return {
        "as_of": pd.Timestamp(as_of_ts).strftime("%Y-%m-%d"),
        "window_days": window_days,
        "threshold_days": stockout_threshold_days,
        "rows": rows,
        "summary": {
            "total_at_risk_items": len(rows),
            "critical_count": critical_count,
            "warning_count": warning_count,
            "total_at_risk_thb": total_at_risk_thb,
            "brands_affected": list({r["brand"] for r in rows}),
        },
    }


# ---------------------------------------------------------------------------
# F-030b: Dead Stock Identification
# ---------------------------------------------------------------------------

def compute_dead_stock(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    as_of: Optional[pd.Timestamp] = None,
    window_days: int = 180,
    top_n: int = 100,
    brand: Optional[str] = None,
) -> dict[str, Any]:
    """Identify dead stock — items with on-hand > 0 but zero or near-zero sales.

    Dead stock = on-hand > 0 AND sold_qty in the last `window_days` == 0.
    Slow-moving = on-hand > 0 AND days_cover > 180 (has some sales but very slow).

    Returns items sorted by on-hand THB value (highest capital at risk first).
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    item = _build_item_velocity(df_sale, df_onhand, window_days, as_of)
    if item.empty:
        return {"as_of": None, "window_days": window_days, "rows": [], "summary": {}}

    if brand:
        item = item[item["Brand"].str.contains(brand, case=False, na=False)]
        if item.empty:
            return {"as_of": None, "window_days": window_days, "rows": [], "summary": {}}

    d = _channel_dedup_sale(df_sale)
    as_of_ts = pd.to_datetime(as_of) if as_of is not None else d["DocDate"].max()

    # Items with on-hand but zero sales in window
    has_stock = item[item["OnHand"] > 0].copy()

    # Classify: dead (zero sales) vs slow-moving (has sales but >180 days cover)
    dead = has_stock[has_stock["sold_qty"] == 0].copy()
    dead["category"] = "dead"
    slow = has_stock[(has_stock["sold_qty"] > 0) & (has_stock["days_cover"] > 180)].copy()
    slow["category"] = "slow_moving"

    combined = pd.concat([dead, slow], ignore_index=True)
    combined = combined.sort_values("onhand_thb", ascending=False)

    # Compute brand summary from ALL dead/slow items BEFORE top_n truncation
    brand_agg_all = (
        combined.groupby("Brand", as_index=False)
        .agg(
            item_count=("ItemCode", "count"),
            total_onhand_thb=("onhand_thb", "sum"),
            total_onhand_qty=("OnHand", "sum"),
        )
        .sort_values("total_onhand_thb", ascending=False)
    )

    # Now truncate for display
    combined = combined.head(top_n)

    # Optionally check if still being purchased (GRPO activity)
    still_buying = set()
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        g = df_grpo_detail.copy()
        g["DocDate"] = pd.to_datetime(g["DocDate"], errors="coerce")
        g = g.dropna(subset=["DocDate"])
        recent_grpo_start = as_of_ts - pd.Timedelta(days=window_days)
        recent_purchases = g[g["DocDate"] >= recent_grpo_start]
        still_buying = set(recent_purchases["ItemCode"].unique())

    def _action(row: pd.Series) -> str:
        if row["category"] == "dead":
            if str(row["ItemCode"]) in still_buying:
                return "Stop purchasing — no sales but still being bought"
            return "Liquidate or return to vendor"
        # slow-moving
        if float(row["days_cover"]) > 365:
            return "Markdown or bundle promotion"
        return "Promote or transfer to higher-selling location"

    rows = []
    for _, r in combined.iterrows():
        dc = r["days_cover"]
        rows.append({
            "item_code": str(r["ItemCode"]),
            "brand": str(r["Brand"]),
            "description": str(r.get("ItemName", "")),
            "onhand_qty": float(r["OnHand"]),
            "onhand_thb": float(r["onhand_thb"]),
            "sold_qty_window": float(r["sold_qty"]),
            "days_cover": None if dc == float("inf") else round(float(dc), 1),
            "category": str(r["category"]),
            "still_purchasing": str(r["ItemCode"]) in still_buying,
            "recommended_action": _action(r),
        })

    # Brand summary (uses brand_agg_all computed from ALL items before top_n truncation)
    brand_rows = []
    for _, br in brand_agg_all.head(15).iterrows():
        brand_rows.append({
            "brand": str(br["Brand"]),
            "item_count": int(br["item_count"]),
            "total_onhand_thb": float(br["total_onhand_thb"]),
            "total_onhand_qty": float(br["total_onhand_qty"]),
        })

    dead_count = sum(1 for r in rows if r["category"] == "dead")
    slow_count = sum(1 for r in rows if r["category"] == "slow_moving")
    total_dead_thb = sum(r["onhand_thb"] for r in rows if r["category"] == "dead")
    total_slow_thb = sum(r["onhand_thb"] for r in rows if r["category"] == "slow_moving")

    return {
        "as_of": pd.Timestamp(as_of_ts).strftime("%Y-%m-%d"),
        "window_days": window_days,
        "rows": rows,
        "summary": {
            "dead_stock_items": dead_count,
            "dead_stock_thb": total_dead_thb,
            "slow_moving_items": slow_count,
            "slow_moving_thb": total_slow_thb,
            "total_capital_at_risk": total_dead_thb + total_slow_thb,
            "still_purchasing_count": sum(1 for r in rows if r["still_purchasing"]),
            "brands": brand_rows,
        },
    }


# ---------------------------------------------------------------------------
# F-031: Reorder Point Analysis
# ---------------------------------------------------------------------------

def compute_reorder_analysis(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    as_of: Optional[pd.Timestamp] = None,
    window_days: int = 90,
    lead_time_days: int = 28,
    target_cover_days: int = 56,
    top_n: int = 100,
    brand: Optional[str] = None,
) -> dict[str, Any]:
    """Reorder point analysis — which items need ordering and how much.

    Reorder point = avg_daily_qty * lead_time_days (+ safety buffer)
    Suggested order qty = (avg_daily_qty * target_cover_days) - current_onhand

    Only includes items with positive sales velocity where on-hand is below
    the reorder point.
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    item = _build_item_velocity(df_sale, df_onhand, window_days, as_of)
    if item.empty:
        return {"as_of": None, "window_days": window_days, "rows": [], "summary": {}}

    if brand:
        item = item[item["Brand"].str.contains(brand, case=False, na=False)]
        if item.empty:
            return {"as_of": None, "window_days": window_days, "rows": [], "summary": {}}

    d = _channel_dedup_sale(df_sale)
    as_of_ts = pd.to_datetime(as_of) if as_of is not None else d["DocDate"].max()

    # Only items with positive velocity
    active = item[item["avg_daily_qty"] > 0].copy()

    # Safety stock = 1 week of sales (7 days)
    safety_days = 7
    active["reorder_point"] = active["avg_daily_qty"] * (lead_time_days + safety_days)
    active["target_stock"] = active["avg_daily_qty"] * target_cover_days
    active["suggested_order_qty"] = (active["target_stock"] - active["OnHand"]).clip(lower=0)
    active["suggested_order_thb"] = active["suggested_order_qty"] * active["Master Price"]

    # Filter: only items where on-hand is below reorder point
    needs_reorder = active[active["OnHand"] < active["reorder_point"]].copy()
    needs_reorder["urgency"] = needs_reorder.apply(
        lambda r: "critical" if float(r["days_cover"]) < 7
        else ("urgent" if float(r["days_cover"]) < 14 else "reorder"),
        axis=1,
    )
    needs_reorder = needs_reorder.sort_values("days_cover", ascending=True).head(top_n)

    # Last purchase info from GRPO
    last_purchase = {}
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        g = df_grpo_detail.copy()
        g["DocDate"] = pd.to_datetime(g["DocDate"], errors="coerce")
        g = g.dropna(subset=["DocDate"])
        g["FOB_THB_Unit"] = pd.to_numeric(g["Price"], errors="coerce") * pd.to_numeric(
            g["Rate"], errors="coerce"
        )
        last = g.sort_values("DocDate").groupby("ItemCode").last()
        for idx, row in last.iterrows():
            last_purchase[str(idx)] = {
                "date": row["DocDate"].strftime("%Y-%m-%d") if pd.notna(row["DocDate"]) else None,
                "fob_thb_unit": float(row["FOB_THB_Unit"]) if pd.notna(row.get("FOB_THB_Unit")) else None,
            }

    rows = []
    for _, r in needs_reorder.iterrows():
        ic = str(r["ItemCode"])
        lp = last_purchase.get(ic, {})
        rows.append({
            "item_code": ic,
            "brand": str(r["Brand"]),
            "description": str(r.get("ItemName", "")),
            "onhand_qty": float(r["OnHand"]),
            "onhand_thb": float(r["onhand_thb"]),
            "avg_daily_qty": round(float(r["avg_daily_qty"]), 2),
            "days_cover": round(float(r["days_cover"]), 1),
            "reorder_point": round(float(r["reorder_point"]), 0),
            "target_stock": round(float(r["target_stock"]), 0),
            "suggested_order_qty": round(float(r["suggested_order_qty"]), 0),
            "suggested_order_thb": round(float(r["suggested_order_thb"]), 0),
            "urgency": str(r["urgency"]),
            "last_purchase_date": lp.get("date"),
            "last_fob_thb_unit": lp.get("fob_thb_unit"),
        })

    total_order_thb = sum(r["suggested_order_thb"] for r in rows)
    critical_count = sum(1 for r in rows if r["urgency"] == "critical")
    urgent_count = sum(1 for r in rows if r["urgency"] == "urgent")

    return {
        "as_of": pd.Timestamp(as_of_ts).strftime("%Y-%m-%d"),
        "window_days": window_days,
        "lead_time_days": lead_time_days,
        "target_cover_days": target_cover_days,
        "rows": rows,
        "summary": {
            "total_items_need_reorder": len(rows),
            "critical_count": critical_count,
            "urgent_count": urgent_count,
            "total_suggested_order_thb": total_order_thb,
            "brands_needing_reorder": list({r["brand"] for r in rows}),
        },
    }


# ---------------------------------------------------------------------------
# Brand-grouped reorder warnings (long-cycle planning)
# ---------------------------------------------------------------------------

def compute_brand_reorder_warnings(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    as_of: Optional[pd.Timestamp] = None,
    window_days: int = 90,
    top_items_per_brand: int = 15,
    warning_days_cover: int = 120,
    target_cover_days: int = 150,
    brand: Optional[str] = None,
) -> dict[str, Any]:
    """Brand-grouped reorder warnings for purchase-planning lead times.

    Purchase orders flow brand → supplier → quotation → production → shipping →
    distribution. The full cycle can take 3-4 months, so days-cover under
    ``warning_days_cover`` (default 120) means we need to start ordering NOW
    to avoid a stockout by the time goods arrive.

    For each brand, the function:
      1. Picks the top ``top_items_per_brand`` items by revenue in the window
         (because we don't worry about long-tail SKUs at planning time).
      2. Computes per-item days_cover at the company level (sum on-hand /
         daily sales velocity from the recent window).
      3. Computes the brand's average days_cover across the top items
         (weighted by current on-hand quantity — items we hold more of
         carry more weight in the brand decision).
      4. Flags any top-seller with days_cover < ``warning_days_cover``.
      5. Suggests an order quantity per flagged item that brings on-hand
         up to ``target_cover_days`` of sales (default 150 = 5 months).

    Returns a dict with one record per brand, sorted by warning urgency
    (most warnings + lowest avg days_cover first).
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    item = _build_item_velocity(df_sale, df_onhand, window_days, as_of)
    if item.empty:
        return {
            "as_of": None,
            "window_days": window_days,
            "warning_days_cover": warning_days_cover,
            "target_cover_days": target_cover_days,
            "top_items_per_brand": top_items_per_brand,
            "brands": [],
            "summary": {
                "total_brands": 0,
                "total_warnings": 0,
                "total_suggested_order_thb": 0.0,
            },
        }

    if brand:
        item = item[item["Brand"].str.contains(brand, case=False, na=False)]
        if item.empty:
            return {
                "as_of": None,
                "window_days": window_days,
                "warning_days_cover": warning_days_cover,
                "target_cover_days": target_cover_days,
                "top_items_per_brand": top_items_per_brand,
                "brands": [],
                "summary": {"total_brands": 0, "total_warnings": 0, "total_suggested_order_thb": 0.0},
            }

    d = _channel_dedup_sale(df_sale)
    as_of_ts = pd.to_datetime(as_of) if as_of is not None else d["DocDate"].max()

    # Last purchase info (for context in warnings)
    last_purchase = {}
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        g = df_grpo_detail.copy()
        g["DocDate"] = pd.to_datetime(g["DocDate"], errors="coerce")
        g = g.dropna(subset=["DocDate"])
        last = g.sort_values("DocDate").groupby("ItemCode").last()
        for idx, row in last.iterrows():
            last_purchase[str(idx)] = row["DocDate"].strftime("%Y-%m-%d")

    # Aggregate item velocity at the item level (across all locations) — the
    # brand makes one order decision regardless of where the stock will land.
    item_agg = (
        item.groupby(["ItemCode", "Brand"], as_index=False)
        .agg(
            ItemName=("ItemName", "first") if "ItemName" in item.columns else ("ItemCode", "first"),
            OnHand=("OnHand", "sum"),
            onhand_thb=("onhand_thb", "sum"),
            sold_qty=("sold_qty", "sum"),
            sold_thb=("sold_thb", "sum"),
            avg_master_price=("Master Price", "mean"),
        )
    )
    item_agg["avg_daily_qty"] = item_agg["sold_qty"] / float(window_days)
    item_agg["days_cover"] = item_agg.apply(
        lambda r: (float(r["OnHand"]) / float(r["avg_daily_qty"]))
        if float(r["avg_daily_qty"]) > 0
        else float("inf"),
        axis=1,
    )

    brands_out: list[dict[str, Any]] = []
    grand_total_warnings = 0
    grand_total_order_thb = 0.0

    for brand_name, brand_df in item_agg.groupby("Brand"):
        if not brand_name or str(brand_name).strip().lower() in ("unknown", "nan", ""):
            continue
        # Top items by revenue in the window
        top = (
            brand_df[brand_df["sold_thb"] > 0]
            .sort_values("sold_thb", ascending=False)
            .head(top_items_per_brand)
        )
        if top.empty:
            continue

        items_out: list[dict[str, Any]] = []
        warnings_count = 0
        brand_order_thb = 0.0
        for _, r in top.iterrows():
            dc = float(r["days_cover"])
            avg_daily = float(r["avg_daily_qty"])
            onhand = float(r["OnHand"])
            target_stock = avg_daily * float(target_cover_days)
            suggested_qty = max(0.0, target_stock - onhand)
            price = float(r.get("avg_master_price", 0) or 0)
            suggested_thb = suggested_qty * price
            is_warning = (not (avg_daily <= 0)) and dc < warning_days_cover
            if is_warning:
                warnings_count += 1
                brand_order_thb += suggested_thb
            # Severity bucket purely on days_cover
            if dc < 14:
                severity = "critical"
            elif dc < 30:
                severity = "warning"
            elif dc < warning_days_cover:
                severity = "watch"
            else:
                severity = "ok"
            ic = str(r["ItemCode"])
            items_out.append({
                "item_code": ic,
                "item_name": str(r.get("ItemName", "")),
                "onhand_qty": round(onhand),
                "onhand_thb": round(float(r["onhand_thb"]), 0),
                "sold_qty_window": round(float(r["sold_qty"])),
                "sold_thb_window": round(float(r["sold_thb"]), 0),
                "avg_daily_qty": round(avg_daily, 2),
                "days_cover": None if dc == float("inf") else round(dc, 1),
                "suggested_order_qty": round(suggested_qty),
                "suggested_order_thb": round(suggested_thb, 0),
                "severity": severity,
                "is_warning": is_warning,
                "last_purchase_date": last_purchase.get(ic),
            })

        # Brand average days_cover, weighted by current on-hand (items the
        # business holds more of dominate the planning decision). Items with
        # zero velocity are excluded — infinite cover would skew the mean.
        finite = top[top["avg_daily_qty"] > 0]
        if not finite.empty:
            weights = finite["OnHand"].clip(lower=1)
            avg_dc = float(
                (finite["days_cover"] * weights).sum() / weights.sum()
            )
        else:
            avg_dc = float("inf")

        brands_out.append({
            "brand": str(brand_name),
            "top_items_count": len(items_out),
            "warnings_count": warnings_count,
            "avg_days_cover": None if avg_dc == float("inf") else round(avg_dc, 1),
            "total_onhand_thb": round(float(top["onhand_thb"].sum()), 0),
            "total_sold_thb_window": round(float(top["sold_thb"].sum()), 0),
            "total_suggested_order_thb": round(brand_order_thb, 0),
            "items": items_out,
        })
        grand_total_warnings += warnings_count
        grand_total_order_thb += brand_order_thb

    # Sort brands: brands with the most warnings first; tiebreak on lowest
    # average days cover (most urgent overall).
    def _brand_sort_key(b):
        dc = b["avg_days_cover"] if b["avg_days_cover"] is not None else 1e9
        return (-b["warnings_count"], dc)
    brands_out.sort(key=_brand_sort_key)

    return {
        "as_of": pd.Timestamp(as_of_ts).strftime("%Y-%m-%d"),
        "window_days": window_days,
        "warning_days_cover": warning_days_cover,
        "target_cover_days": target_cover_days,
        "top_items_per_brand": top_items_per_brand,
        "brands": brands_out,
        "summary": {
            "total_brands": len(brands_out),
            "total_warnings": grand_total_warnings,
            "total_suggested_order_thb": round(grand_total_order_thb, 0),
        },
    }
