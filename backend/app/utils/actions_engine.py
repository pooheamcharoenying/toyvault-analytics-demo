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
            onhand_units = float(row.get("onhand_qty", 0))
            actions.append({
                "type": "markdown",
                "severity": sev,
                "title": f"{'Dead' if cat == 'dead' else 'Slow'} stock: {brand or '?'} — {row.get('item_code', '?')}",
                "reason": (
                    f"{row.get('description', '')} — "
                    f"{onhand_units:,.0f} units on hand (฿{thb:,.0f}), "
                    f"sold {row.get('sold_qty_window', 0):.0f} units in 180 days. "
                    f"{row.get('recommended_action', '')}.{extra}"
                ),
                "impact_thb": round(thb, 0),
                "onhand_qty": round(onhand_units),
                "item_code": row.get("item_code"),
                "brand": brand,
                "link": f"/dashboards/item-detail/{row.get('item_code', '')}" if row.get("item_code") else f"/dashboards/inventory-alerts?tab=deadstock&brand={brand}",
            })
    except Exception:
        logger.warning("Actions engine: dead stock computation failed", exc_info=True)

    # ── 3. Brand-grouped reorder warnings (long-cycle planning) ─────────
    # Purchase orders flow brand → supplier → quotation → production → shipping
    # → distribution, which can run 3-4 months. So we warn on top-selling
    # items per brand whose current days-cover is under 120 days and propose
    # an order quantity targeting 5 months (150 days) of forward cover.
    try:
        brand_warn = ialerts.compute_brand_reorder_warnings(
            df_raw_sale=df_raw_sale,
            df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            df_grpo_detail=df_grpo_detail,
            as_of=as_of,
            window_days=90,
            top_items_per_brand=15,
            warning_days_cover=120,
            target_cover_days=150,
        )
        # Avoid duplicating items that already produced a stockout-risk action
        existing_items = {a.get("item_code") for a in actions if a.get("type") == "reorder"}
        for brand_rec in brand_warn.get("brands", []):
            brand_name = brand_rec.get("brand", "?")
            avg_dc = brand_rec.get("avg_days_cover")
            warnings_count = brand_rec.get("warnings_count", 0)
            if warnings_count <= 0:
                continue
            avg_dc_text = f"{avg_dc:.0f}d avg cover" if avg_dc is not None else "no recent sales"
            for it in brand_rec.get("items", []):
                if not it.get("is_warning"):
                    continue
                ic = it.get("item_code")
                if ic in existing_items:
                    continue
                dc = it.get("days_cover")
                if dc is None:
                    continue
                # Severity: <14d critical, <30d warning, otherwise info ("watch")
                if dc < 14:
                    sev = "critical"
                elif dc < 30:
                    sev = "warning"
                else:
                    sev = "info"
                order_thb = float(it.get("suggested_order_thb", 0) or 0)
                actions.append({
                    "type": "reorder",
                    "severity": sev,
                    "title": f"Reorder {brand_name} — {ic} ({it.get('item_name','')[:40]})",
                    "reason": (
                        f"{dc:.0f}d cover at current pace "
                        f"({it.get('avg_daily_qty', 0):.1f} units/day). "
                        f"Order {it.get('suggested_order_qty', 0):,} units "
                        f"(est. ฿{order_thb:,.0f}) to reach 150-day target. "
                        f"Brand {brand_name}: {avg_dc_text}, "
                        f"{warnings_count} of {brand_rec.get('top_items_count', 0)} top sellers under 120d. "
                        f"Last purchased: {it.get('last_purchase_date', 'N/A')}."
                    ),
                    "impact_thb": round(order_thb, 0),
                    "item_code": ic,
                    "brand": brand_name,
                    "days_cover": dc,
                    "suggested_order_qty": it.get("suggested_order_qty"),
                    "link": f"/dashboards/item-detail/{ic}" if ic else f"/dashboards/inventory-alerts?tab=reorder&brand={brand_name}",
                })
    except Exception:
        logger.warning("Actions engine: brand reorder warnings computation failed", exc_info=True)

    # ── 4. Smart transfer recommendations (dead stock at poor → good) ───
    # Move dead stock OUT of poorly-performing locations and INTO high
    # performers that have capacity, never overstocking the destination.
    try:
        transfers = sal.compute_smart_transfer_recommendations(
            df_raw_sale=df_raw_sale,
            df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            df_whs_code=df_whs_code,
            window_days=90,
            target_days_at_destination=90,
            min_transfer_thb=5_000,
            top_n=15,
        )
        for rec in transfers.get("recommendations", []):
            thb = float(rec.get("transfer_thb", 0))
            item_code = rec.get("item_code", "")
            brand = rec.get("brand", "?")
            # Severity scales with capital being mobilised
            sev = "warning" if thb >= 50_000 else "info"
            actions.append({
                "type": "transfer",
                "severity": sev,
                "title": (
                    f"Transfer {brand} — {item_code} "
                    f"from {rec.get('from_location', '?')} → {rec.get('to_location', '?')}"
                ),
                "reason": rec.get("rationale", ""),
                "impact_thb": round(thb, 0),
                "transfer_qty": rec.get("transfer_qty"),
                "item_code": item_code,
                "brand": brand,
                "link": f"/dashboards/item-detail/{item_code}" if item_code else "/dashboards/stock-allocation",
            })
    except Exception:
        logger.warning("Actions engine: smart transfer recommendations failed", exc_info=True)

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
            loc_name = loc.get("location", "")
            # Warehouses are back-of-house holding locations — efficiency and
            # dead-stock metrics there reflect distribution patterns, not store
            # performance. Exclude them from "Investigate" recommendations.
            if loc_name and loc_name.strip().lower().startswith("warehouse "):
                continue
            thb = float(loc.get("dead_stock_thb", 0))
            onhand = float(loc.get("onhand_thb", 0))
            if onhand < 50_000:
                continue
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

    # Reserve a minimum quota per action type so transfer recommendations and
    # reorder recommendations (good-selling, low-stock items) always show up
    # as their own sections — otherwise high-THB dead-stock items can crowd
    # out the entire list.
    min_quota = {"reorder": 5, "transfer": 5, "markdown": 5, "investigate": 3}
    quota_picks: List[Dict[str, Any]] = []
    quota_seen_ids = set()
    remaining_by_type = dict(min_quota)
    for a in actions:
        t = a.get("type")
        if remaining_by_type.get(t, 0) > 0:
            quota_picks.append(a)
            quota_seen_ids.add(id(a))
            remaining_by_type[t] -= 1
    # Fill remaining slots by global score order, skipping already-picked items
    leftovers = [a for a in actions if id(a) not in quota_seen_ids]
    final = quota_picks + leftovers
    final = final[:max_actions]
    # Re-sort the final selection by score so the dashboard still ranks correctly
    final.sort(key=lambda x: x["score"], reverse=True)
    actions = final

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
