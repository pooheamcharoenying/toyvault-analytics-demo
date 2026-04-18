"""Period Comparison Reports — side-by-side comparison of two periods.

Business context: Executives need to compare this quarter vs last quarter,
this year vs last year, or any two custom periods. The comparison must show
KPIs side-by-side with absolute change and % change, plus breakdowns by
brand and channel so managers can see what's driving the differences.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import pandas as pd

from app.utils import nichi_stock as nstk


def _channel_dedup_sale(
    df_sale_prepared: pd.DataFrame,
) -> pd.DataFrame:
    """Deduplicate sales by (DocEntry, ItemCode, Period, GroupName)."""
    df = df_sale_prepared.copy()
    df["DocDate"] = pd.to_datetime(df["DocDate"], errors="coerce")
    df = df.dropna(subset=["DocDate"])
    df["Period"] = df["DocDate"].dt.to_period("M").dt.start_time
    return df.drop_duplicates(subset=["DocEntry", "ItemCode", "Period", "GroupName"])


def _period_range(year: int, quarter: Optional[int] = None, month: Optional[int] = None):
    """Return (start_date, end_date) for a year, quarter, or month."""
    if month is not None:
        start = pd.Timestamp(year=year, month=month, day=1)
        end = start + pd.offsets.MonthEnd(0)
    elif quarter is not None:
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        start = pd.Timestamp(year=year, month=start_month, day=1)
        end = pd.Timestamp(year=year, month=end_month, day=1) + pd.offsets.MonthEnd(0)
    else:
        start = pd.Timestamp(year=year, month=1, day=1)
        end = pd.Timestamp(year=year, month=12, day=31)
    return start, end


def _compute_period_kpis(
    d: pd.DataFrame,
    df_onhand: pd.DataFrame,
    df_grpo: Optional[pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    """Compute KPIs for a date range from deduped sales."""
    mask = (d["DocDate"] >= start) & (d["DocDate"] <= end)
    period_sales = d[mask]

    revenue_thb = float(period_sales["LineTotal"].sum()) if not period_sales.empty else 0.0
    sold_qty = float(period_sales["Quantity"].sum()) if not period_sales.empty else 0.0
    unique_items_sold = int(period_sales["ItemCode"].nunique()) if not period_sales.empty else 0
    transaction_count = int(period_sales["DocEntry"].nunique()) if not period_sales.empty else 0

    # GP Commission for consignment sales
    gp_commission_thb = float(nstk.compute_gp_commission(period_sales).sum()) if not period_sales.empty else 0.0

    # Brand breakdown
    brand_agg = (
        period_sales.groupby("Brand", as_index=False)
        .agg(revenue_thb=("LineTotal", "sum"), sold_qty=("Quantity", "sum"))
        .sort_values("revenue_thb", ascending=False)
    ) if not period_sales.empty else pd.DataFrame(columns=["Brand", "revenue_thb", "sold_qty"])

    brand_rows = []
    for _, br in brand_agg.head(20).iterrows():
        brand_rows.append({
            "brand": str(br["Brand"]),
            "revenue_thb": float(br["revenue_thb"]),
            "sold_qty": float(br["sold_qty"]),
        })

    # Channel breakdown
    channel_agg = (
        period_sales.groupby("GroupName", as_index=False)
        .agg(revenue_thb=("LineTotal", "sum"), sold_qty=("Quantity", "sum"))
        .sort_values("revenue_thb", ascending=False)
    ) if not period_sales.empty else pd.DataFrame(columns=["GroupName", "revenue_thb", "sold_qty"])

    channel_rows = []
    for _, ch in channel_agg.iterrows():
        channel_rows.append({
            "channel": str(ch["GroupName"]),
            "revenue_thb": float(ch["revenue_thb"]),
            "sold_qty": float(ch["sold_qty"]),
        })

    # Monthly breakdown within period
    monthly_agg = (
        period_sales.groupby("Period", as_index=False)
        .agg(revenue_thb=("LineTotal", "sum"), sold_qty=("Quantity", "sum"))
        .sort_values("Period")
    ) if not period_sales.empty else pd.DataFrame(columns=["Period", "revenue_thb", "sold_qty"])

    monthly_rows = []
    for _, m in monthly_agg.iterrows():
        monthly_rows.append({
            "period": m["Period"].strftime("%Y-%m"),
            "revenue_thb": float(m["revenue_thb"]),
            "sold_qty": float(m["sold_qty"]),
        })

    # GRPO (purchases) in period
    purchased_thb = 0.0
    purchased_qty = 0.0
    if df_grpo is not None and not df_grpo.empty:
        g = df_grpo.copy()
        g["DocDate"] = pd.to_datetime(g["DocDate"], errors="coerce")
        g = g.dropna(subset=["DocDate"])
        g_mask = (g["DocDate"] >= start) & (g["DocDate"] <= end)
        g_period = g[g_mask]
        if not g_period.empty:
            g_period = g_period.copy()
            g_period["Price"] = pd.to_numeric(g_period["Price"], errors="coerce").fillna(0)
            g_period["Rate"] = pd.to_numeric(g_period["Rate"], errors="coerce").fillna(0)
            g_period["Quantity"] = pd.to_numeric(g_period["Quantity"], errors="coerce").fillna(0)
            g_period["FOB_THB"] = g_period["Price"] * g_period["Rate"] * g_period["Quantity"]
            purchased_thb = float(g_period["FOB_THB"].sum())
            purchased_qty = float(g_period["Quantity"].sum())

    # Gross margin = Revenue − COGS (purchased) − GP Commission
    gross_margin = (revenue_thb - purchased_thb - gp_commission_thb) if purchased_thb > 0 else None
    gross_margin_pct = (
        (gross_margin / revenue_thb * 100) if revenue_thb > 0 and gross_margin is not None else 0.0
    ) if purchased_thb > 0 else None

    return {
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "revenue_thb": revenue_thb,
        "sold_qty": sold_qty,
        "unique_items_sold": unique_items_sold,
        "transaction_count": transaction_count,
        "purchased_thb": purchased_thb,
        "purchased_qty": purchased_qty,
        "gp_commission_thb": gp_commission_thb,
        "gross_margin_thb": gross_margin,
        "gross_margin_pct": gross_margin_pct,
        "brands": brand_rows,
        "channels": channel_rows,
        "monthly": monthly_rows,
    }


def _safe_change(current, previous) -> dict[str, Any]:
    """Compute absolute and percentage change between two values."""
    if current is None or previous is None:
        return {"absolute": None, "pct": None, "direction": "flat"}
    abs_change = float(current) - float(previous)
    pct_change = (abs_change / float(previous) * 100) if float(previous) != 0 else None
    direction = "up" if abs_change > 0 else ("down" if abs_change < 0 else "flat")
    return {
        "absolute": abs_change,
        "pct": round(pct_change, 1) if pct_change is not None else None,
        "direction": direction,
    }


def compute_period_comparison(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    period_a_year: Optional[int] = None,
    period_a_quarter: Optional[int] = None,
    period_a_month: Optional[int] = None,
    period_b_year: Optional[int] = None,
    period_b_quarter: Optional[int] = None,
    period_b_month: Optional[int] = None,
) -> dict[str, Any]:
    """Compare two periods side-by-side with KPIs, brand/channel breakdowns, and changes.

    Period specification:
    - year only: full year comparison (e.g., 2025 vs 2024)
    - year + quarter: quarterly comparison (e.g., 2025-Q1 vs 2024-Q1)
    - year + month: monthly comparison (e.g., 2025-03 vs 2024-03)

    Returns:
        dict with period_a, period_b KPIs and changes dict showing deltas
    """
    current_year = datetime.now().year
    if period_a_year is None:
        period_a_year = current_year
    if period_b_year is None:
        period_b_year = current_year - 1

    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale)

    start_a, end_a = _period_range(period_a_year, period_a_quarter, period_a_month)
    start_b, end_b = _period_range(period_b_year, period_b_quarter, period_b_month)

    kpi_a = _compute_period_kpis(d, df_onhand, df_grpo_detail, start_a, end_a)
    kpi_b = _compute_period_kpis(d, df_onhand, df_grpo_detail, start_b, end_b)

    # Compute changes for headline KPIs
    changes = {
        "revenue_thb": _safe_change(kpi_a["revenue_thb"], kpi_b["revenue_thb"]),
        "sold_qty": _safe_change(kpi_a["sold_qty"], kpi_b["sold_qty"]),
        "purchased_thb": _safe_change(kpi_a["purchased_thb"], kpi_b["purchased_thb"]),
        "gross_margin_thb": _safe_change(kpi_a["gross_margin_thb"], kpi_b["gross_margin_thb"]),
        "transaction_count": _safe_change(float(kpi_a["transaction_count"]), float(kpi_b["transaction_count"])),
        "unique_items_sold": _safe_change(float(kpi_a["unique_items_sold"]), float(kpi_b["unique_items_sold"])),
    }

    # Brand comparison: merge period_a and period_b brand rows
    brand_map_a = {b["brand"]: b for b in kpi_a["brands"]}
    brand_map_b = {b["brand"]: b for b in kpi_b["brands"]}
    all_brands = sorted(set(brand_map_a.keys()) | set(brand_map_b.keys()))

    brand_comparison = []
    for br in all_brands:
        a_rev = brand_map_a.get(br, {}).get("revenue_thb", 0)
        b_rev = brand_map_b.get(br, {}).get("revenue_thb", 0)
        a_qty = brand_map_a.get(br, {}).get("sold_qty", 0)
        b_qty = brand_map_b.get(br, {}).get("sold_qty", 0)
        brand_comparison.append({
            "brand": br,
            "period_a_revenue": a_rev,
            "period_b_revenue": b_rev,
            "revenue_change": _safe_change(a_rev, b_rev),
            "period_a_qty": a_qty,
            "period_b_qty": b_qty,
        })
    brand_comparison.sort(key=lambda x: abs(x["revenue_change"]["absolute"]), reverse=True)

    # Channel comparison
    ch_map_a = {c["channel"]: c for c in kpi_a["channels"]}
    ch_map_b = {c["channel"]: c for c in kpi_b["channels"]}
    all_channels = sorted(set(ch_map_a.keys()) | set(ch_map_b.keys()))

    channel_comparison = []
    for ch in all_channels:
        a_rev = ch_map_a.get(ch, {}).get("revenue_thb", 0)
        b_rev = ch_map_b.get(ch, {}).get("revenue_thb", 0)
        a_qty = ch_map_a.get(ch, {}).get("sold_qty", 0)
        b_qty = ch_map_b.get(ch, {}).get("sold_qty", 0)
        channel_comparison.append({
            "channel": ch,
            "period_a_revenue": a_rev,
            "period_b_revenue": b_rev,
            "revenue_change": _safe_change(a_rev, b_rev),
            "period_a_qty": a_qty,
            "period_b_qty": b_qty,
        })
    channel_comparison.sort(key=lambda x: abs(x["revenue_change"]["absolute"]), reverse=True)

    # Label for display
    def _label(year, quarter, month):
        if month is not None:
            return f"{year}-{month:02d}"
        if quarter is not None:
            return f"{year} Q{quarter}"
        return str(year)

    return {
        "period_a_label": _label(period_a_year, period_a_quarter, period_a_month),
        "period_b_label": _label(period_b_year, period_b_quarter, period_b_month),
        "period_a": kpi_a,
        "period_b": kpi_b,
        "changes": changes,
        "brand_comparison": brand_comparison[:20],
        "channel_comparison": channel_comparison,
    }


def _period_label(year: int, quarter: Optional[int], month: Optional[int]) -> str:
    """Create a human-readable label for a period."""
    if month is not None:
        return f"{year}-{month:02d}"
    if quarter is not None:
        return f"{year} Q{quarter}"
    return str(year)


def compute_multi_period_comparison(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    periods: list[dict] | None = None,
) -> dict[str, Any]:
    """Compare 2-4 periods side-by-side with KPIs, brand/channel breakdowns.

    Each period in *periods* is ``{"year": int, "quarter": int|None, "month": int|None}``.
    Returns a generalised structure with lists instead of fixed period_a / period_b keys.

    Response shape::

        {
            "period_count": int,
            "labels": ["2025", "2024", "2023"],
            "periods": [ {kpi_dict}, {kpi_dict}, ... ],
            "changes": {  # first→last change for headline KPIs
                "revenue_thb": {"absolute": ..., "pct": ..., "direction": ...}, ...
            },
            "brand_comparison": [
                {"brand": "X", "revenues": [v0, v1, ...], "qtys": [q0, q1, ...],
                 "change": {"absolute": ..., "pct": ..., "direction": ...}}, ...
            ],
            "channel_comparison": [ ... same structure ... ],
        }
    """
    if periods is None or len(periods) < 2:
        raise ValueError("At least 2 periods are required")
    if len(periods) > 4:
        raise ValueError("Maximum 4 periods are supported")

    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _channel_dedup_sale(df_sale)

    labels: list[str] = []
    kpis: list[dict] = []
    for p in periods:
        yr = int(p["year"])
        qtr = p.get("quarter")
        mon = p.get("month")
        qtr = int(qtr) if qtr is not None else None
        mon = int(mon) if mon is not None else None
        start, end = _period_range(yr, qtr, mon)
        kpi = _compute_period_kpis(d, df_onhand, df_grpo_detail, start, end)
        kpis.append(kpi)
        labels.append(_period_label(yr, qtr, mon))

    # Changes: first period vs last period (most recent vs oldest)
    first = kpis[0]
    last = kpis[-1]
    changes = {
        "revenue_thb": _safe_change(first["revenue_thb"], last["revenue_thb"]),
        "sold_qty": _safe_change(first["sold_qty"], last["sold_qty"]),
        "purchased_thb": _safe_change(first["purchased_thb"], last["purchased_thb"]),
        "gross_margin_thb": _safe_change(first["gross_margin_thb"], last["gross_margin_thb"]),
        "transaction_count": _safe_change(float(first["transaction_count"]), float(last["transaction_count"])),
        "unique_items_sold": _safe_change(float(first["unique_items_sold"]), float(last["unique_items_sold"])),
    }

    # Brand comparison across all periods
    brand_maps = []
    all_brand_names: set[str] = set()
    for kpi in kpis:
        bm = {b["brand"]: b for b in kpi["brands"]}
        brand_maps.append(bm)
        all_brand_names.update(bm.keys())

    brand_comparison = []
    for br in sorted(all_brand_names):
        revenues = [bm.get(br, {}).get("revenue_thb", 0) for bm in brand_maps]
        qtys = [bm.get(br, {}).get("sold_qty", 0) for bm in brand_maps]
        brand_comparison.append({
            "brand": br,
            "revenues": revenues,
            "qtys": qtys,
            "change": _safe_change(revenues[0], revenues[-1]),
        })
    brand_comparison.sort(
        key=lambda x: abs(x["change"]["absolute"]) if x["change"]["absolute"] is not None else 0,
        reverse=True,
    )

    # Channel comparison across all periods
    ch_maps = []
    all_ch_names: set[str] = set()
    for kpi in kpis:
        cm = {c["channel"]: c for c in kpi["channels"]}
        ch_maps.append(cm)
        all_ch_names.update(cm.keys())

    channel_comparison = []
    for ch in sorted(all_ch_names):
        revenues = [cm.get(ch, {}).get("revenue_thb", 0) for cm in ch_maps]
        qtys = [cm.get(ch, {}).get("sold_qty", 0) for cm in ch_maps]
        channel_comparison.append({
            "channel": ch,
            "revenues": revenues,
            "qtys": qtys,
            "change": _safe_change(revenues[0], revenues[-1]),
        })
    channel_comparison.sort(
        key=lambda x: abs(x["change"]["absolute"]) if x["change"]["absolute"] is not None else 0,
        reverse=True,
    )

    return {
        "period_count": len(periods),
        "labels": labels,
        "periods": kpis,
        "changes": changes,
        "brand_comparison": brand_comparison[:20],
        "channel_comparison": channel_comparison,
    }
