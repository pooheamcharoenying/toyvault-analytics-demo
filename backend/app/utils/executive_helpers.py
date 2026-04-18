"""Executive dashboard aggregates — same prep and channel-level sales dedup as channel matrix."""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from app.utils import nichi_stock as nstk


def _channel_dedup_sale(
    df_sale_prepared: pd.DataFrame, period_type: str = "monthly"
) -> pd.DataFrame:
    df_sale = df_sale_prepared.copy()
    df_sale["DocDate"] = pd.to_datetime(df_sale["DocDate"], errors="coerce")
    df_sale = df_sale.dropna(subset=["DocDate"])
    if period_type == "weekly":
        df_sale["Period"] = df_sale["DocDate"].dt.to_period("W-MON").dt.start_time
    elif period_type == "monthly":
        df_sale["Period"] = df_sale["DocDate"].dt.to_period("M").dt.start_time
    else:
        raise ValueError("period_type must be 'monthly' or 'weekly'")
    return df_sale.drop_duplicates(
        subset=["DocEntry", "ItemCode", "Period", "GroupName"]
    )


def compute_executive_summary(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    as_of: Optional[str] = None,
) -> dict[str, Any]:
    """
    EX-01: organisation totals using prepare_sales_and_onhand_data + channel dedup for sales;
    on-hand THB matches channel matrix org total (prepared on-hand, dropna OnHand + Master Price).
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale, "monthly")
    sold_qty = float(d["Quantity"].sum())
    sold_thb = float(d["LineTotal"].sum())

    # Revenue (Master) — prefer Sale sheet 'Price Master' (line-level, all items)
    if "Price Master" in d.columns:
        d["Revenue_Master_THB"] = pd.to_numeric(
            d["Price Master"], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
    elif "Master_Price_Unit" not in d.columns:
        price_map = df_item_master.drop_duplicates("ItemCode").set_index("ItemCode")["Price"]
        d["Master_Price_Unit"] = d["ItemCode"].map(price_map).fillna(0)
        d["Revenue_Master_THB"] = d["Quantity"] * d["Master_Price_Unit"]
    else:
        d["Revenue_Master_THB"] = d["Quantity"] * d["Master_Price_Unit"]
    sold_master_thb = float(d["Revenue_Master_THB"].sum())

    oh_f = df_onhand.dropna(subset=["OnHand", "Master Price"]).copy()
    oh_f["OnHand_THB"] = oh_f["OnHand"] * oh_f["Master Price"]
    onhand_qty = float(oh_f["OnHand"].sum())
    onhand_thb = float(oh_f["OnHand_THB"].sum())

    by_period = (
        d.groupby("Period", as_index=False)
        .agg(Quantity=("Quantity", "sum"), LineTotal=("LineTotal", "sum"))
        .sort_values("Period")
    )
    comparison: Optional[dict[str, Any]] = None
    if len(by_period) >= 2:
        last = by_period.iloc[-1]
        prev = by_period.iloc[-2]
        prev_rev = float(prev["LineTotal"])
        last_rev = float(last["LineTotal"])
        comparison = {
            "last_period": last["Period"].strftime("%Y-%m-%d"),
            "prior_period": prev["Period"].strftime("%Y-%m-%d"),
            "last_revenue_thb": last_rev,
            "prior_revenue_thb": prev_rev,
            "revenue_mom_pct": float((last_rev - prev_rev) / prev_rev * 100.0)
            if prev_rev
            else None,
        }

    return {
        "as_of": as_of,
        "totals": {
            "sold_qty": sold_qty,
            "sold_thb": sold_thb,
            "sold_master_thb": sold_master_thb,
            "onhand_qty": onhand_qty,
            "onhand_thb_master": onhand_thb,
        },
        "comparison": comparison,
    }


def compute_sales_trend_executive(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    granularity: str = "monthly",
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """EX-02: period revenue/qty, YoY % on revenue, trailing-twelve-month revenue."""
    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale, granularity)
    # Revenue (Master) — prefer Sale sheet 'Price Master' (line-level, all items
    # including discontinued). 'Master Price' is per-unit but ~72% NaN on the
    # Sale sheet; 'Price Master' is line-level (Qty × unit price), 100% populated.
    if "Price Master" in d.columns:
        d["Revenue_Master_THB"] = pd.to_numeric(
            d["Price Master"], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
    elif "Master_Price_Unit" not in d.columns:
        price_map = df_item_master.drop_duplicates("ItemCode").set_index("ItemCode")["Price"]
        d["Master_Price_Unit"] = d["ItemCode"].map(price_map).fillna(0)
        d["Revenue_Master_THB"] = d["Quantity"] * d["Master_Price_Unit"]
    else:
        d["Revenue_Master_THB"] = d["Quantity"] * d["Master_Price_Unit"]
    if year_list:
        d = d[d["DocDate"].dt.year.isin(year_list)].copy()
    agg = (
        d.groupby("Period", as_index=False)
        .agg(qty=("Quantity", "sum"), revenue_thb=("LineTotal", "sum"), revenue_master_thb=("Revenue_Master_THB", "sum"))
        .sort_values("Period")
    )
    if agg.empty:
        return {"granularity": granularity, "series": []}

    periods = agg["Period"].tolist()
    rev = agg["revenue_thb"].astype(float).tolist()
    rev_master = agg["revenue_master_thb"].astype(float).tolist()
    qty = agg["qty"].astype(float).tolist()

    # YoY: match same calendar month (monthly) or same week start (weekly) via shifted period label
    yoy_pct: list[Optional[float]] = []
    ttm: list[float] = []
    period_keys: list[str] = []
    for i, p in enumerate(periods):
        period_keys.append(p.strftime("%Y-%m-%d"))
        if granularity == "monthly":
            prior = p - pd.DateOffset(years=1)
            mask = agg["Period"] == prior
            if mask.any():
                prev_rev = float(agg.loc[mask, "revenue_thb"].iloc[0])
                cur = rev[i]
                yoy_pct.append(
                    float((cur - prev_rev) / prev_rev * 100.0) if prev_rev else None
                )
            else:
                yoy_pct.append(None)
        else:
            prior = p - pd.DateOffset(weeks=52)
            mask = agg["Period"] == prior
            if mask.any():
                prev_rev = float(agg.loc[mask, "revenue_thb"].iloc[0])
                cur = rev[i]
                yoy_pct.append(
                    float((cur - prev_rev) / prev_rev * 100.0) if prev_rev else None
                )
            else:
                yoy_pct.append(None)

        start = max(0, i - 11)
        ttm.append(float(sum(rev[start : i + 1])))

    series = [
        {
            "period": period_keys[i],
            "revenue_thb": rev[i],
            "revenue_master_thb": rev_master[i],
            "qty": qty[i],
            "yoy_revenue_pct": yoy_pct[i],
            "ttm_revenue_thb": ttm[i],
        }
        for i in range(len(periods))
    ]

    # Annotate the last (possibly partial) month with a running rate.
    try:
        from app.utils.running_rate import annotate_monthly_series, get_data_as_of_date
        annotate_monthly_series(
            series,
            get_data_as_of_date(df_raw_sale),
            numeric_fields=["revenue_thb", "revenue_master_thb", "qty"],
        )
    except Exception:
        pass

    return {"granularity": granularity, "series": series}


def compute_concentration_summary(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    dimension: str,
    year: int,
    top_n: int = 10,
) -> dict[str, Any]:
    """EX-05: top-N share of revenue by brand (product) or channel (GroupName)."""
    if dimension not in ("brand", "channel"):
        raise ValueError("dimension must be 'brand' or 'channel'")
    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale, "monthly")
    d = d[d["DocDate"].dt.year == year].copy()
    key = "Brand" if dimension == "brand" else "GroupName"
    d[key] = d[key].fillna("Unknown")
    g = d.groupby(key, as_index=True)["LineTotal"].sum().sort_values(ascending=False)
    total = float(g.sum())
    if total <= 0 or g.empty:
        return {
            "dimension": dimension,
            "year": year,
            "total_revenue_thb": total,
            "top_n": top_n,
            "rows": [],
            "top_k_share_pct": 0.0,
        }

    top = g.head(top_n)
    rows = [
        {
            "name": str(name),
            "revenue_thb": float(val),
            "share_pct": round(float(val) / total * 100.0, 2),
        }
        for name, val in top.items()
    ]
    top_k_share_pct = round(float(top.sum()) / total * 100.0, 2)
    return {
        "dimension": dimension,
        "year": year,
        "total_revenue_thb": total,
        "top_n": top_n,
        "rows": rows,
        "top_k_share_pct": top_k_share_pct,
    }


def global_df_line_counts(global_df: dict) -> dict[str, Any]:
    """Cheap row counts for EX-11 trust strip."""

    def _n(key: str) -> Optional[int]:
        df = global_df.get(key)
        if df is None:
            return None
        try:
            return int(len(df))
        except TypeError:
            return None

    return {
        "sale": _n("sale"),
        "onhand": _n("onhand"),
        "master": _n("master"),
        "grpo_detail": _n("grpo_detail"),
        "whs_code": _n("whs_code"),
    }


def channel_matrix_lifetime_revenue_thb(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
) -> float:
    """Cross-check: sum of all monthly Sold_THB columns on channel matrix Total row."""
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    mat = nstk.generate_sales_onhand_by_channel(df_sale, df_onhand, period_type="monthly")
    if mat.empty:
        return 0.0
    total_row = mat.iloc[-1]
    thb_cols = [c for c in mat.columns if c.endswith("_Sold_THB")]
    s = total_row[thb_cols].sum(min_count=1)
    return float(s) if pd.notna(s) else 0.0


def compute_margin_by_brand(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """
    EX-03: Brand-level profitability.
    Revenue uses sale LineTotal from canonical sales prep + channel-style dedup.
    COGS uses item-level average FOB from GRPO; falls back to LastPurPrc from Item Master.
    """
    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale, "monthly")
    if year_list:
        d = d[d["DocDate"].dt.year.isin(year_list)].copy()
    if d.empty:
        return {"rows": [], "totals": {"revenue_thb": 0.0, "cogs_thb": 0.0, "gross_margin_thb": 0.0, "gross_margin_pct": None}}

    # Build unit FOB lookup
    fob_by_item: pd.Series
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        g = df_grpo_detail.copy()
        g["FOB_THB_Unit"] = pd.to_numeric(g["Price"], errors="coerce") * pd.to_numeric(
            g["Rate"], errors="coerce"
        )
        fob_by_item = g.groupby("ItemCode")["FOB_THB_Unit"].mean()
    else:
        fob_by_item = pd.Series(dtype=float)

    if "LastPurPrc" in df_item_master.columns:
        master_last = (
            df_item_master[["ItemCode", "LastPurPrc"]]
            .drop_duplicates(subset=["ItemCode"])
            .set_index("ItemCode")["LastPurPrc"]
        )
    else:
        master_last = pd.Series(dtype=float)

    d["Brand"] = d["Brand"].fillna("Unknown")
    d["Quantity"] = pd.to_numeric(d["Quantity"], errors="coerce").fillna(0.0)
    d["LineTotal"] = pd.to_numeric(d["LineTotal"], errors="coerce").fillna(0.0)
    d["FOB_Unit"] = d["ItemCode"].map(fob_by_item)
    d["FOB_Unit"] = d["FOB_Unit"].fillna(d["ItemCode"].map(master_last)).fillna(0.0)
    d["COGS_THB"] = d["Quantity"] * d["FOB_Unit"]

    # GP Commission for consignment sales
    d["GP_Commission_THB"] = nstk.compute_gp_commission(d)

    agg = (
        d.groupby("Brand", as_index=False)
        .agg(
            sold_qty=("Quantity", "sum"),
            revenue_thb=("LineTotal", "sum"),
            cogs_thb=("COGS_THB", "sum"),
            gp_commission_thb=("GP_Commission_THB", "sum"),
        )
        .sort_values("revenue_thb", ascending=False)
    )
    # Gross margin = Revenue − COGS − GP Commission
    agg["gross_margin_thb"] = agg["revenue_thb"] - agg["cogs_thb"] - agg["gp_commission_thb"]
    agg["gross_margin_pct"] = agg.apply(
        lambda r: (float(r["gross_margin_thb"]) / float(r["revenue_thb"]) * 100.0)
        if float(r["revenue_thb"]) != 0.0
        else None,
        axis=1,
    )

    rows = []
    for _, r in agg.iterrows():
        rows.append(
            {
                "brand": str(r["Brand"]),
                "sold_qty": float(r["sold_qty"]),
                "revenue_thb": float(r["revenue_thb"]),
                "cogs_thb": float(r["cogs_thb"]),
                "gp_commission_thb": float(r["gp_commission_thb"]),
                "gross_margin_thb": float(r["gross_margin_thb"]),
                "gross_margin_pct": float(r["gross_margin_pct"]) if pd.notna(r["gross_margin_pct"]) else None,
            }
        )

    total_revenue = float(agg["revenue_thb"].sum())
    total_cogs = float(agg["cogs_thb"].sum())
    total_gp = float(agg["gp_commission_thb"].sum())
    total_margin = total_revenue - total_cogs - total_gp
    total_margin_pct = (total_margin / total_revenue * 100.0) if total_revenue else None

    return {
        "rows": rows,
        "totals": {
            "revenue_thb": total_revenue,
            "cogs_thb": total_cogs,
            "gp_commission_thb": total_gp,
            "gross_margin_thb": total_margin,
            "gross_margin_pct": total_margin_pct,
        },
    }


def compute_inventory_risk_summary(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    as_of: Optional[pd.Timestamp] = None,
    window_days: int = 90,
    top_n: int = 20,
) -> dict[str, Any]:
    """
    EX-04: Inventory risk / days-cover using on-hand snapshot and recent sales velocity.
    days_cover = onhand_qty / (sold_qty_last_window / window_days), with inf when no recent sales.
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale, "monthly")
    if d.empty:
        return {"as_of": None, "window_days": window_days, "rows": [], "summary": {}}

    d["DocDate"] = pd.to_datetime(d["DocDate"], errors="coerce")
    d = d.dropna(subset=["DocDate"])
    if d.empty:
        return {"as_of": None, "window_days": window_days, "rows": [], "summary": {}}

    if as_of is None:
        as_of_ts = d["DocDate"].max()
    else:
        as_of_ts = pd.to_datetime(as_of)
    start = as_of_ts - pd.Timedelta(days=window_days - 1)

    recent = d[(d["DocDate"] >= start) & (d["DocDate"] <= as_of_ts)].copy()
    sold_agg = (
        recent.groupby("ItemCode", as_index=False)
        .agg(sold_qty_90d=("Quantity", "sum"), sold_thb_90d=("LineTotal", "sum"))
    )

    oh = df_onhand.copy()
    oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0.0)
    oh["Master Price"] = pd.to_numeric(oh["Master Price"], errors="coerce").fillna(0.0)
    oh["Brand"] = oh["Brand"].fillna("Unknown")
    oh["onhand_thb"] = oh["OnHand"] * oh["Master Price"]

    item = oh.merge(sold_agg, on="ItemCode", how="left")
    item["sold_qty_90d"] = pd.to_numeric(item["sold_qty_90d"], errors="coerce").fillna(0.0)
    item["sold_thb_90d"] = pd.to_numeric(item["sold_thb_90d"], errors="coerce").fillna(0.0)
    item["avg_daily_qty"] = item["sold_qty_90d"] / float(window_days)
    item["days_cover"] = item.apply(
        lambda r: (float(r["OnHand"]) / float(r["avg_daily_qty"]))
        if float(r["avg_daily_qty"]) > 0
        else float("inf"),
        axis=1,
    )

    # Risk score: high on-hand value with very long/undefined days cover
    # No-sales items (inf days_cover) get the maximum multiplier so they rank highest.
    # Items with finite days_cover get a proportional multiplier capped at the same max.
    _MAX_RISK_MULT = 13.0  # slightly above 365/30 ≈ 12.17 so inf always ranks above finite
    item["risk_score"] = item.apply(
        lambda r: float(r["onhand_thb"]) * _MAX_RISK_MULT
        if pd.isna(r["days_cover"]) or r["days_cover"] == float("inf")
        else float(r["onhand_thb"]) * min(float(r["days_cover"]), 365.0) / 30.0,
        axis=1,
    )
    item_sorted = item.sort_values("risk_score", ascending=False).head(top_n)

    rows = []
    for _, r in item_sorted.iterrows():
        dc = r["days_cover"]
        rows.append(
            {
                "item_code": str(r["ItemCode"]),
                "brand": str(r["Brand"]),
                "onhand_qty": float(r["OnHand"]),
                "onhand_thb": float(r["onhand_thb"]),
                "sold_qty_90d": float(r["sold_qty_90d"]),
                "avg_daily_qty": float(r["avg_daily_qty"]),
                "days_cover": None if dc == float("inf") else float(dc),
                "days_cover_label": "No recent sales" if dc == float("inf") else f"{float(dc):.1f}",
                "risk_score": float(r["risk_score"]),
            }
        )

    brand_summary = (
        item.groupby("Brand", as_index=False)
        .agg(
            onhand_qty=("OnHand", "sum"),
            onhand_thb=("onhand_thb", "sum"),
            sold_qty_90d=("sold_qty_90d", "sum"),
        )
        .sort_values("onhand_thb", ascending=False)
    )
    brand_summary["avg_daily_qty"] = brand_summary["sold_qty_90d"] / float(window_days)
    brand_summary["days_cover"] = brand_summary.apply(
        lambda r: (float(r["onhand_qty"]) / float(r["avg_daily_qty"]))
        if float(r["avg_daily_qty"]) > 0
        else float("inf"),
        axis=1,
    )

    summary_rows = []
    for _, r in brand_summary.head(10).iterrows():
        dc = r["days_cover"]
        summary_rows.append(
            {
                "brand": str(r["Brand"]),
                "onhand_thb": float(r["onhand_thb"]),
                "sold_qty_90d": float(r["sold_qty_90d"]),
                "days_cover": None if dc == float("inf") else float(dc),
            }
        )

    return {
        "as_of": pd.Timestamp(as_of_ts).strftime("%Y-%m-%d"),
        "window_days": window_days,
        "rows": rows,
        "summary": {
            "total_onhand_thb": float(item["onhand_thb"].sum()),
            "total_sold_qty_90d": float(item["sold_qty_90d"].sum()),
            "brands": summary_rows,
        },
    }


def compute_channel_performance_executive(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    year_list: Optional[list[int]] = None,
    period_type: str = "monthly",
) -> dict[str, Any]:
    """
    EX-07: channel performance summary with latest period mix and growth vs prior period.
    Uses canonical sales prep + channel-style dedup; no on-hand allocation by channel.
    """
    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale, period_type)
    if year_list:
        d = d[d["DocDate"].dt.year.isin(year_list)].copy()
    if d.empty:
        return {"rows": [], "latest_period": None, "prior_period": None}

    g = (
        d.groupby(["GroupName", "Period"], as_index=False)
        .agg(revenue_thb=("LineTotal", "sum"), sold_qty=("Quantity", "sum"))
        .sort_values("Period")
    )
    periods = sorted(g["Period"].dropna().unique())
    if len(periods) == 0:
        return {"rows": [], "latest_period": None, "prior_period": None}
    latest = periods[-1]
    prior = periods[-2] if len(periods) > 1 else None

    cur = g[g["Period"] == latest][["GroupName", "revenue_thb", "sold_qty"]].copy()
    cur = cur.rename(
        columns={
            "GroupName": "channel",
            "revenue_thb": "latest_revenue_thb",
            "sold_qty": "latest_sold_qty",
        }
    )
    if prior is not None:
        prv = g[g["Period"] == prior][["GroupName", "revenue_thb", "sold_qty"]].copy()
        prv = prv.rename(
            columns={
                "GroupName": "channel",
                "revenue_thb": "prior_revenue_thb",
                "sold_qty": "prior_sold_qty",
            }
        )
        out = cur.merge(prv, on="channel", how="left")
        out["prior_revenue_thb"] = out["prior_revenue_thb"].fillna(0.0)
        out["prior_sold_qty"] = out["prior_sold_qty"].fillna(0.0)
    else:
        out = cur.copy()
        out["prior_revenue_thb"] = 0.0
        out["prior_sold_qty"] = 0.0

    total_latest = float(out["latest_revenue_thb"].sum())
    out["mix_pct"] = out["latest_revenue_thb"].apply(
        lambda v: (float(v) / total_latest * 100.0) if total_latest else 0.0
    )
    out["mom_revenue_pct"] = out.apply(
        lambda r: (
            (float(r["latest_revenue_thb"]) - float(r["prior_revenue_thb"]))
            / float(r["prior_revenue_thb"])
            * 100.0
        )
        if float(r["prior_revenue_thb"]) != 0.0
        else None,
        axis=1,
    )
    out = out.sort_values("latest_revenue_thb", ascending=False)

    rows = []
    for _, r in out.iterrows():
        rows.append(
            {
                "channel": str(r["channel"]),
                "latest_revenue_thb": float(r["latest_revenue_thb"]),
                "prior_revenue_thb": float(r["prior_revenue_thb"]),
                "latest_sold_qty": float(r["latest_sold_qty"]),
                "mix_pct": float(r["mix_pct"]),
                "mom_revenue_pct": float(r["mom_revenue_pct"]) if pd.notna(r["mom_revenue_pct"]) else None,
            }
        )

    return {
        "rows": rows,
        "latest_period": pd.Timestamp(latest).strftime("%Y-%m-%d"),
        "prior_period": pd.Timestamp(prior).strftime("%Y-%m-%d") if prior is not None else None,
    }


def compute_brand_list_metrics(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """
    Brand drill-down list: one row per brand with revenue, COGS, margin,
    on-hand (units + THB @ Master Price), sold qty, and sell-through rate.
    """
    # --- Revenue / COGS from deduped sales (same logic as compute_margin_by_brand) ---
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale, "monthly")
    if year_list:
        d = d[d["DocDate"].dt.year.isin(year_list)].copy()

    # Build FOB lookup
    fob_by_item: pd.Series
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        g = df_grpo_detail.copy()
        g["FOB_THB_Unit"] = pd.to_numeric(g["Price"], errors="coerce") * pd.to_numeric(
            g["Rate"], errors="coerce"
        )
        fob_by_item = g.groupby("ItemCode")["FOB_THB_Unit"].mean()
    else:
        fob_by_item = pd.Series(dtype=float)

    if "LastPurPrc" in df_item_master.columns:
        master_last = (
            df_item_master[["ItemCode", "LastPurPrc"]]
            .drop_duplicates(subset=["ItemCode"])
            .set_index("ItemCode")["LastPurPrc"]
        )
    else:
        master_last = pd.Series(dtype=float)

    d["Brand"] = d["Brand"].fillna("Unknown")
    d["Quantity"] = pd.to_numeric(d["Quantity"], errors="coerce").fillna(0.0)
    d["LineTotal"] = pd.to_numeric(d["LineTotal"], errors="coerce").fillna(0.0)
    d["FOB_Unit"] = d["ItemCode"].map(fob_by_item)
    d["FOB_Unit"] = d["FOB_Unit"].fillna(d["ItemCode"].map(master_last)).fillna(0.0)
    d["COGS_THB"] = d["Quantity"] * d["FOB_Unit"]

    # Revenue (Master) — prefer Sale sheet 'Price Master' column
    if "Price Master" in d.columns:
        d["Revenue_Master_THB"] = pd.to_numeric(
            d["Price Master"], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
    else:
        if "Price" in df_item_master.columns:
            master_price_map = (
                df_item_master[["ItemCode", "Price"]]
                .drop_duplicates(subset=["ItemCode"])
                .set_index("ItemCode")["Price"]
            )
        else:
            master_price_map = pd.Series(dtype=float)
        d["Master_Price_Unit"] = d["ItemCode"].map(master_price_map).fillna(0.0)
        d["Revenue_Master_THB"] = d["Quantity"] * pd.to_numeric(d["Master_Price_Unit"], errors="coerce").fillna(0.0)

    # GP Commission for consignment sales
    d["GP_Commission_THB"] = nstk.compute_gp_commission(d)

    sales_agg = (
        d.groupby("Brand", as_index=False)
        .agg(
            sold_qty=("Quantity", "sum"),
            revenue_thb=("LineTotal", "sum"),
            revenue_master_thb=("Revenue_Master_THB", "sum"),
            cogs_thb=("COGS_THB", "sum"),
            gp_commission_thb=("GP_Commission_THB", "sum"),
        )
    )
    # Gross margin = Revenue − COGS − GP Commission
    sales_agg["gross_margin_thb"] = sales_agg["revenue_thb"] - sales_agg["cogs_thb"] - sales_agg["gp_commission_thb"]
    sales_agg["gross_margin_pct"] = sales_agg.apply(
        lambda r: (float(r["gross_margin_thb"]) / float(r["revenue_thb"]) * 100.0)
        if float(r["revenue_thb"]) != 0.0
        else None,
        axis=1,
    )

    # --- On-hand from prepared data (@ Master Price) ---
    oh = df_onhand.copy()
    oh["Brand"] = oh["Brand"].fillna("Unknown")
    oh["OnHand"] = pd.to_numeric(oh["OnHand"] if "OnHand" in oh.columns else 0, errors="coerce").fillna(0.0)
    # After prepare_sales_and_onhand_data, the column is "Master Price" (with space)
    master_price_col = next(
        (c for c in ["Master Price", "MasterPrice", "Price"] if c in oh.columns), None
    )
    if master_price_col:
        oh["OnHand_THB"] = oh["OnHand"] * pd.to_numeric(oh[master_price_col], errors="coerce").fillna(0.0)
    else:
        oh["OnHand_THB"] = 0.0
    oh_agg = (
        oh.groupby("Brand", as_index=False)
        .agg(onhand_qty=("OnHand", "sum"), onhand_thb=("OnHand_THB", "sum"))
    )

    # --- Merge ---
    merged = pd.merge(sales_agg, oh_agg, on="Brand", how="outer").fillna(0.0)
    merged["sell_through_rate"] = merged.apply(
        lambda r: (float(r["sold_qty"]) / (float(r["sold_qty"]) + float(r["onhand_qty"])) * 100.0)
        if (float(r["sold_qty"]) + float(r["onhand_qty"])) > 0
        else None,
        axis=1,
    )
    merged = merged.sort_values("revenue_thb", ascending=False)

    # --- ABCDE classification per brand (OBJ-83) ---
    # Group items within each brand by revenue, classify A/B/C/D/E using 50/80/95/99 thresholds
    item_rev = d.groupby(["Brand", "ItemCode"], as_index=False)["LineTotal"].sum()
    item_rev.rename(columns={"LineTotal": "item_revenue"}, inplace=True)
    abc_counts = {}  # brand -> {a: N, b: N, c: N, d: N, e: N}
    for brand_name, grp in item_rev.groupby("Brand"):
        grp_sorted = grp.sort_values("item_revenue", ascending=False)
        total = grp_sorted["item_revenue"].sum()
        if total <= 0:
            abc_counts[brand_name] = {"a": 0, "b": 0, "c": 0, "d": 0, "e": len(grp_sorted)}
            continue
        cumsum = grp_sorted["item_revenue"].cumsum()
        cum_pct = cumsum / total * 100.0
        a_count = int((cum_pct <= 50.0).sum())
        if a_count == 0 and len(grp_sorted) > 0:
            a_count = 1
        b_count = int(((cum_pct > 50.0) & (cum_pct <= 80.0)).sum())
        c_count = int(((cum_pct > 80.0) & (cum_pct <= 95.0)).sum())
        d_count = int(((cum_pct > 95.0) & (cum_pct <= 99.0)).sum())
        e_count = len(grp_sorted) - a_count - b_count - c_count - d_count
        abc_counts[brand_name] = {"a": a_count, "b": b_count, "c": c_count, "d": d_count, "e": e_count}

    rows = []
    for _, r in merged.iterrows():
        brand_name = str(r["Brand"])
        abc = abc_counts.get(brand_name, {"a": 0, "b": 0, "c": 0, "d": 0, "e": 0})
        rows.append({
            "brand": brand_name,
            "sold_qty": float(r["sold_qty"]),
            "revenue_thb": float(r["revenue_thb"]),
            "revenue_master_thb": float(r.get("revenue_master_thb", 0)),
            "cogs_thb": float(r["cogs_thb"]),
            "gp_commission_thb": float(r.get("gp_commission_thb", 0)),
            "gross_margin_thb": float(r["gross_margin_thb"]),
            "gross_margin_pct": float(r["gross_margin_pct"]) if pd.notna(r["gross_margin_pct"]) else None,
            "onhand_qty": float(r["onhand_qty"]),
            "onhand_thb": float(r["onhand_thb"]),
            "sell_through_rate": float(r["sell_through_rate"]) if pd.notna(r["sell_through_rate"]) else None,
            "abcde_a_count": abc["a"],
            "abcde_b_count": abc["b"],
            "abcde_c_count": abc["c"],
            "abcde_d_count": abc["d"],
            "abcde_e_count": abc["e"],
        })

    return {"rows": rows}


def compute_brand_monthly_trend(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    *,
    brand_name: Optional[str] = None,
    top_n: int = 5,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Monthly revenue/cost/margin trend by brand.

    If brand_name is given, returns a single brand with monthly P/L breakdown.
    If brand_name is None, returns top_n brands as separate series for an
    overlay line chart on the brands list page.

    Returns
    -------
    dict with:
      - trends: list of {brand, months: [{period, sold_thb, sold_master_thb,
                         sold_qty, cogs_thb, gp_commission_thb, profit_loss}]}
      - periods: sorted list of YYYY-MM strings
    """
    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale, "monthly")
    if year_list:
        d = d[d["DocDate"].dt.year.isin(year_list)].copy()
    if d.empty:
        return {"trends": [], "periods": []}

    d["Brand"] = d["Brand"].fillna("Unknown")
    d["Quantity"] = pd.to_numeric(d["Quantity"], errors="coerce").fillna(0.0)
    d["LineTotal"] = pd.to_numeric(d["LineTotal"], errors="coerce").fillna(0.0)

    # Revenue (Master) — prefer Sale sheet 'Price Master' column
    if "Price Master" in d.columns:
        d["Revenue_Master_THB"] = pd.to_numeric(
            d["Price Master"], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
    else:
        if "Price" in df_item_master.columns:
            mp_map = (
                df_item_master[["ItemCode", "Price"]]
                .drop_duplicates(subset=["ItemCode"])
                .set_index("ItemCode")["Price"]
            )
        else:
            mp_map = pd.Series(dtype=float)
        d["Master_Price_Unit"] = d["ItemCode"].map(mp_map).fillna(0.0)
        d["Revenue_Master_THB"] = d["Quantity"] * pd.to_numeric(
            d["Master_Price_Unit"], errors="coerce"
        ).fillna(0.0)

    # FOB lookup
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        g = df_grpo_detail.copy()
        g["FOB_THB_Unit"] = pd.to_numeric(g["Price"], errors="coerce") * pd.to_numeric(
            g["Rate"], errors="coerce"
        )
        fob_by_item = g.groupby("ItemCode")["FOB_THB_Unit"].mean()
    else:
        fob_by_item = pd.Series(dtype=float)

    if "LastPurPrc" in df_item_master.columns:
        master_last = (
            df_item_master[["ItemCode", "LastPurPrc"]]
            .drop_duplicates(subset=["ItemCode"])
            .set_index("ItemCode")["LastPurPrc"]
        )
    else:
        master_last = pd.Series(dtype=float)

    d["FOB_Unit"] = d["ItemCode"].map(fob_by_item)
    d["FOB_Unit"] = d["FOB_Unit"].fillna(d["ItemCode"].map(master_last)).fillna(0.0)
    d["COGS_THB"] = d["Quantity"] * d["FOB_Unit"]

    # GP Commission
    d["GP_Commission_THB"] = nstk.compute_gp_commission(d)

    d["Month"] = d["DocDate"].dt.to_period("M").dt.start_time

    if brand_name:
        d = d[d["Brand"] == brand_name]
        if d.empty:
            return {"trends": [], "periods": []}

    monthly = d.groupby(["Brand", "Month"], as_index=False).agg(
        sold_thb=("LineTotal", "sum"),
        sold_master_thb=("Revenue_Master_THB", "sum"),
        sold_qty=("Quantity", "sum"),
        cogs_thb=("COGS_THB", "sum"),
        gp_commission_thb=("GP_Commission_THB", "sum"),
    )
    monthly["profit_loss"] = monthly["sold_thb"] - monthly["cogs_thb"] - monthly["gp_commission_thb"]

    periods_sorted = sorted(monthly["Month"].unique())
    period_strs = [p.strftime("%Y-%m") for p in periods_sorted]

    if not brand_name:
        brand_totals = monthly.groupby("Brand")["sold_thb"].sum().sort_values(ascending=False)
        top_brands = list(brand_totals.head(top_n).index)
        monthly = monthly[monthly["Brand"].isin(top_brands)]

    trends = []
    for bname, grp in monthly.groupby("Brand"):
        months = []
        for p in periods_sorted:
            row = grp[grp["Month"] == p]
            if not row.empty:
                r = row.iloc[0]
                months.append({
                    "period": p.strftime("%Y-%m"),
                    "sold_thb": round(float(r["sold_thb"]), 2),
                    "sold_master_thb": round(float(r["sold_master_thb"]), 2),
                    "sold_qty": round(float(r["sold_qty"])),
                    "cogs_thb": round(float(r["cogs_thb"]), 2),
                    "gp_commission_thb": round(float(r["gp_commission_thb"]), 2),
                    "profit_loss": round(float(r["profit_loss"]), 2),
                })
            else:
                months.append({
                    "period": p.strftime("%Y-%m"),
                    "sold_thb": 0.0, "sold_master_thb": 0.0,
                    "sold_qty": 0, "cogs_thb": 0.0,
                    "gp_commission_thb": 0.0, "profit_loss": 0.0,
                })
        trends.append({"brand": str(bname), "months": months})

    trends.sort(key=lambda t: sum(m["sold_thb"] for m in t["months"]), reverse=True)

    # Annotate the last (possibly partial) month on each brand series.
    try:
        from app.utils.running_rate import annotate_monthly_series, get_data_as_of_date
        as_of = get_data_as_of_date(df_raw_sale)
        for t in trends:
            annotate_monthly_series(
                t["months"],
                as_of,
                numeric_fields=[
                    "sold_thb", "sold_master_thb", "sold_qty",
                    "cogs_thb", "gp_commission_thb", "profit_loss",
                ],
            )
    except Exception:
        pass

    return {"trends": trends, "periods": period_strs}
