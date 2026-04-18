"""
Actions Engine — Computes top priority business actions.

Calls existing computation functions (stockout risk, dead stock, reorder,
stock allocation, location performance) and synthesises a ranked list of
the most urgent actions a manager should take *right now*.

Each action carries:
  - type       : reorder | transfer | markdown | investigate
  - severity   : critical | warning | info
  - title      : one-line human-readable summary
  - reason     : why this matters
  - impact_thb : estimated THB at stake
  - link       : deep-link to the relevant dashboard
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from app.utils import inventory_alerts as ialerts
from app.utils import stock_allocation as sal
from app.utils import location_analytics as la

logger = logging.getLogger(__name__)


def compute_priority_actions(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    as_of: Optional[pd.Timestamp] = None,
    max_actions: int = 30,
) -> Dict[str, Any]:
    """Return the top *max_actions* ranked business actions."""

    actions: List[Dict[str, Any]] = []

    # ── 1. Stockout-risk items → reorder actions ────────────────────────
    try:
        stockout = ialerts.compute_stockout_risk(
            df_raw_sale=df_raw_sale,
            df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            as_of=as_of,
            window_days=90,
            stockout_threshold_days=30,
            top_n=20,
        )
        for row in stockout.get("rows", []):
            sev = row.get("severity", "watch")
            if sev not in ("critical", "warning"):
                continue
            impact = float(row.get("onhand_thb", 0))
            weekly = row.get("weekly_rate", 0)
            # Estimate lost-revenue impact: weekly rate * master price * weeks-to-stockout gap
            if weekly and weekly > 0:
                impact = max(impact, weekly * 4 * float(row.get("onhand_thb", 0)) / max(float(row.get("onhand_qty", 1)), 1))
            brand = row.get("brand", "")
            actions.append({
                "type": "reorder",
                "severity": sev,
                "title": f"Reorder {brand or '?'} — {row.get('item_code', '?')}",
                "reason": (
                    f"Only {row.get('days_cover', '?')} days of cover left, "
                    f"selling {row.get('weekly_rate', 0):.0f} units/week. "
                    f"Projected stockout: {row.get('projected_stockout', 'N/A')}."
                ),
                "impact_thb": round(impact, 0),
                "item_code": row.get("item_code"),
                "brand": brand,
                "link": f"/dashboards/item-detail/{row.get('item_code', '')}" if row.get("item_code") else f"/dashboards/inventory-alerts?tab=stockout&brand={brand}",
            })
    except Exception:
        logger.warning("Actions engine: stockout risk computation failed", exc_info=True)

    # ── 2. Dead stock → markdown / liquidate actions ────────────────────
    try:
        dead = ialerts.compute_dead_stock(
            df_raw_sale=df_raw_sale,
            df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            df_grpo_detail=df_grpo_detail,
            as_of=as_of,
            window_days=180,
            top_n=20,
        )
        for row in dead.get("rows", []):
            cat = row.get("category", "slow_moving")
            thb = float(row.get("onhand_thb", 0))
            if thb < 10_000:
                continue  # skip trivial amounts
            sev = "critical" if cat == "dead" and thb >= 100_000 else "warning"
            still_purchasing = row.get("still_purchasing", False)
            extra = " STILL BEING PURCHASED!" if still_purchasing else ""
            brand = row.get("brand", "")
            actions.append({
                "type": "markdown",
                "severity": sev,
                "title": f"{'Dead' if cat == 'dead' else 'Slow'} stock: {brand or '?'} — {row.get('item_code', '?')}",
                "reason": (
                    f"{row.get('description', '')} — "
                    f"on-hand value ฿{thb:,.0f}, "
                    f"sold {row.get('sold_qty_window', 0):.0f} units in 180 days. "
                    f"{row.get('recommended_action', '')}.{extra}"
                ),
                "impact_thb": round(thb, 0),
                "item_code": row.get("item_code"),
                "brand": brand,
                "link": f"/dashboards/item-detail/{row.get('item_code', '')}" if row.get("item_code") else f"/dashboards/inventory-alerts?tab=deadstock&brand={brand}",
            })
    except Exception:
        logger.warning("Actions engine: dead stock computation failed", exc_info=True)

    # ── 3. Reorder analysis → urgent reorder actions ────────────────────
    try:
        reorder = ialerts.compute_reorder_analysis(
            df_raw_sale=df_raw_sale,
            df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            df_grpo_detail=df_grpo_detail,
            as_of=as_of,
            window_days=90,
            lead_time_days=28,
            target_cover_days=56,
            top_n=20,
        )
        # Avoid duplicating items already captured by stockout risk
        existing_items = {a["item_code"] for a in actions if a.get("type") == "reorder"}
        for row in reorder.get("rows", []):
            ic = row.get("item_code")
            if ic in existing_items:
                continue
            urgency = row.get("urgency", "reorder")
            if urgency not in ("critical", "urgent"):
                continue
            thb = float(row.get("suggested_order_thb", 0))
            sev = "critical" if urgency == "critical" else "warning"
            brand = row.get("brand", "")
            actions.append({
                "type": "reorder",
                "severity": sev,
                "title": f"Reorder {brand or '?'} — {ic}",
                "reason": (
                    f"{row.get('days_cover', '?')} days cover, need to order "
                    f"{row.get('suggested_order_qty', 0):.0f} units "
                    f"(est. ฿{thb:,.0f}). Last purchased: {row.get('last_purchase_date', 'N/A')}."
                ),
                "impact_thb": round(thb, 0),
                "item_code": ic,
                "brand": brand,
                "link": f"/dashboards/item-detail/{ic}" if ic else f"/dashboards/inventory-alerts?tab=reorder&brand={brand}",
            })
    except Exception:
        logger.warning("Actions engine: reorder analysis computation failed", exc_info=True)

    # ── 4. Stock transfer recommendations ───────────────────────────────
    try:
        alloc = sal.compute_stock_allocation(
            df_raw_sale=df_raw_sale,
            df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            df_whs_code=df_whs_code,
            window_days=90,
            top_n=15,
        )
        for rec in alloc.get("recommendations", [])[:10]:
            thb = float(rec.get("transfer_thb", 0))
            if thb < 5_000:
                continue
            item_code = rec.get("ItemCode", "")
            actions.append({
                "type": "transfer",
                "severity": "warning",
                "title": (
                    f"Transfer {rec.get('Brand', '?')} — {item_code or '?'} "
                    f"from {rec.get('from_name', '?')} to {rec.get('to_name', '?')}"
                ),
                "reason": (
                    f"Move {rec.get('transfer_qty', 0):.0f} units (฿{thb:,.0f}). "
                    f"Source has {rec.get('from_days_cover', 0):.0f} days cover, "
                    f"destination has {rec.get('to_days_cover', 0):.0f} days cover."
                ),
                "impact_thb": round(thb, 0),
                "item_code": item_code,
                "brand": rec.get("Brand"),
                "link": f"/dashboards/item-detail/{item_code}" if item_code else "/dashboards/stock-allocation",
            })
    except Exception:
        logger.warning("Actions engine: stock allocation computation failed", exc_info=True)

    # ── 5. Location red-flags → investigate actions ─────────────────────
    try:
        loc_perf = la.compute_location_performance(
            df_raw_sale=df_raw_sale,
            df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            df_whs_code=df_whs_code,
            window_days=90,
        )
        for loc in loc_perf.get("locations", []):
            if loc.get("status") != "red":
                continue
            thb = float(loc.get("dead_stock_thb", 0))
            onhand = float(loc.get("onhand_thb", 0))
            if onhand < 50_000:
                continue
            loc_name = loc.get("location", "")
            actions.append({
                "type": "investigate",
                "severity": "warning",
                "title": f"Investigate location: {loc_name or '?'}",
                "reason": (
                    f"Health score {loc.get('health_score', 0):.0f}/100, "
                    f"dead stock ฿{thb:,.0f} ({loc.get('dead_stock_pct', 0):.0f}%), "
                    f"revenue per ฿ inventory: {loc.get('revenue_per_thb_inventory', 0):.2f}x."
                ),
                "impact_thb": round(thb, 0),
                "item_code": None,
                "brand": None,
                "link": f"/dashboards/locations/{loc_name}" if loc_name else "/dashboards/locations",
            })
    except Exception:
        logger.warning("Actions engine: location performance computation failed", exc_info=True)

    # ── Score & rank ────────────────────────────────────────────────────
    severity_weight = {"critical": 3, "warning": 2, "info": 1}
    for a in actions:
        a["score"] = severity_weight.get(a["severity"], 1) * max(a.get("impact_thb", 0), 1)

    actions.sort(key=lambda x: x["score"], reverse=True)
    actions = actions[:max_actions]

    # ── Summary counts ──────────────────────────────────────────────────
    by_type: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    total_impact = 0.0
    for a in actions:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
        by_severity[a["severity"]] = by_severity.get(a["severity"], 0) + 1
        total_impact += a.get("impact_thb", 0)

    return {
        "as_of": str(as_of.date()) if as_of is not None else None,
        "total_actions": len(actions),
        "by_type": by_type,
        "by_severity": by_severity,
        "total_impact_thb": round(total_impact, 0),
        "actions": actions,
    }
