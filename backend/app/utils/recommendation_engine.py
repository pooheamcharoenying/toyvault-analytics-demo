"""
Rule-Based Recommendation Engine (Layer 1) — OBJ-86.

Applies deterministic business rules to generate actionable recommendations.
Runs on every page load — no external API calls, instant results.

Each recommendation has:
  - rule_id  : R-01, R-02, etc.
  - severity : critical | warning | info
  - title    : short bold heading
  - text     : detailed actionable recommendation
  - metric   : key number driving the recommendation (for sorting)
  - source   : "rule" (Layer 1)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _fmt_thb(v: float) -> str:
    """Format THB value with commas."""
    if abs(v) >= 1e6:
        return f"฿{v / 1e6:,.1f}M"
    if abs(v) >= 1e3:
        return f"฿{v / 1e3:,.0f}K"
    return f"฿{v:,.0f}"


# ---------------------------------------------------------------------------
# Brand-level recommendations
# ---------------------------------------------------------------------------

def recommend_for_brand(
    brand_name: str,
    products: list[dict],
    brand_metrics: Optional[dict] = None,
) -> list[dict]:
    """Generate recommendations for a brand detail page.

    Parameters
    ----------
    brand_name : str
        The brand being viewed.
    products : list[dict]
        Product rows with keys: ItemCode, Description, Sold_QTY, OnHand_QTY,
        Actual_Revenue_THB, Total_Cost_THB, Profit_Loss_THB, Profit_Margin_%,
        abcde_class (optional).
    brand_metrics : dict, optional
        Brand-level metrics from brand_list_metrics (margin %, ABCDE counts, etc.).

    Returns
    -------
    list[dict]  — recommendation objects, max 7.
    """
    recs: list[dict] = []

    if not products:
        return recs

    # Compute ABCDE if not already on products
    total_rev = sum(p.get("Actual_Revenue_THB", 0) or 0 for p in products)
    if total_rev > 0:
        sorted_prods = sorted(products, key=lambda p: p.get("Actual_Revenue_THB", 0) or 0, reverse=True)
        cum = 0
        abcde_map = {}
        for i, p in enumerate(sorted_prods):
            cum += p.get("Actual_Revenue_THB", 0) or 0
            pct = cum / total_rev * 100
            if pct <= 50 or i == 0:
                abcde_map[p.get("ItemCode")] = "A"
            elif pct <= 80:
                abcde_map[p.get("ItemCode")] = "B"
            elif pct <= 95:
                abcde_map[p.get("ItemCode")] = "C"
            elif pct <= 99:
                abcde_map[p.get("ItemCode")] = "D"
            else:
                abcde_map[p.get("ItemCode")] = "E"
        for p in products:
            if "abcde_class" not in p:
                p["abcde_class"] = abcde_map.get(p.get("ItemCode"), "E")

    # R-01: Dead stock products (zero sales, positive on-hand)
    dead_items = [
        p for p in products
        if (p.get("Sold_QTY", 0) or 0) == 0 and (p.get("OnHand_QTY", 0) or 0) > 0
    ]
    if dead_items:
        dead_value = sum((p.get("OnHand_QTY", 0) or 0) * (p.get("Master_Price", 0) or 0) for p in dead_items)
        top_dead = sorted(dead_items, key=lambda p: (p.get("OnHand_QTY", 0) or 0) * (p.get("Master_Price", 0) or 0), reverse=True)[:3]
        dead_names = ", ".join(p.get("ItemCode", "?") for p in top_dead)
        recs.append({
            "rule_id": "R-01",
            "severity": "critical" if dead_value > 100_000 else "warning",
            "title": "Dead stock alert",
            "text": (
                f"{len(dead_items)} product(s) have zero sales with on-hand inventory "
                f"worth {_fmt_thb(dead_value)} (@ Master Price). "
                f"Top items: {dead_names}. "
                f"Consider markdown, return to vendor, or liquidation."
            ),
            "metric": dead_value,
            "source": "rule",
        })

    # R-07: Unhealthy portfolio (>60% D/E products)
    d_count = sum(1 for p in products if p.get("abcde_class") == "D")
    e_count = sum(1 for p in products if p.get("abcde_class") == "E")
    total_prods = len(products)
    if total_prods > 0:
        de_pct = (d_count + e_count) / total_prods * 100
        if de_pct > 60:
            recs.append({
                "rule_id": "R-07",
                "severity": "warning",
                "title": "Unhealthy portfolio",
                "text": (
                    f"{brand_name} has {de_pct:.0f}% of products in D/E class "
                    f"({d_count} D-class, {e_count} E-class out of {total_prods} total), "
                    f"contributing less than 5% of revenue. "
                    f"Consider pruning the bottom {e_count} E-class items to free up capital."
                ),
                "metric": de_pct,
                "source": "rule",
            })

    # R-06 (simplified): Negative margin products
    negative_margin = [
        p for p in products
        if (p.get("Profit_Loss_THB") or 0) < 0 and (p.get("Sold_QTY", 0) or 0) > 0
    ]
    if negative_margin:
        total_loss = sum(abs(p.get("Profit_Loss_THB", 0) or 0) for p in negative_margin)
        worst = sorted(negative_margin, key=lambda p: p.get("Profit_Loss_THB", 0) or 0)[:3]
        worst_names = ", ".join(f"{p.get('ItemCode')} ({_fmt_thb(p.get('Profit_Loss_THB', 0))})" for p in worst)
        recs.append({
            "rule_id": "R-06",
            "severity": "warning",
            "title": "Loss-making products",
            "text": (
                f"{len(negative_margin)} product(s) have negative P/L, losing {_fmt_thb(total_loss)} total. "
                f"Worst: {worst_names}. "
                f"Review pricing or discontinue these items."
            ),
            "metric": total_loss,
            "source": "rule",
        })

    # Positive insight: high-performing A-class products
    a_products = [p for p in products if p.get("abcde_class") == "A"]
    if a_products and len(a_products) <= 5:
        a_rev = sum(p.get("Actual_Revenue_THB", 0) or 0 for p in a_products)
        a_pct = a_rev / total_rev * 100 if total_rev > 0 else 0
        recs.append({
            "rule_id": "R-INFO-01",
            "severity": "info",
            "title": "Star products",
            "text": (
                f"{len(a_products)} A-class product(s) generate {a_pct:.0f}% of {brand_name}'s revenue "
                f"({_fmt_thb(a_rev)}). Protect availability of these items."
            ),
            "metric": a_rev,
            "source": "rule",
        })

    return sorted(recs, key=lambda r: {"critical": 3, "warning": 2, "info": 1}.get(r["severity"], 0), reverse=True)[:7]


# ---------------------------------------------------------------------------
# Location-level recommendations
# ---------------------------------------------------------------------------

def recommend_for_location(
    location_name: str,
    location_metrics: dict,
    company_avg: Optional[dict] = None,
) -> list[dict]:
    """Generate recommendations for a location detail page.

    Parameters
    ----------
    location_metrics : dict
        Location data with keys: sold_thb, onhand_thb, revenue_per_thb_inventory,
        sell_through_rate, dead_stock_pct, dead_stock_thb, days_cover, health_score,
        abcde_class.
    company_avg : dict, optional
        Company average metrics for comparison.
    """
    recs: list[dict] = []

    eff = location_metrics.get("revenue_per_thb_inventory", 0)
    dead_pct = location_metrics.get("dead_stock_pct", 0)
    dead_thb = location_metrics.get("dead_stock_thb", 0)
    onhand_thb = location_metrics.get("onhand_thb", 0)
    sold_thb = location_metrics.get("sold_thb", 0)
    health = location_metrics.get("health_score", 0)
    avg_eff = (company_avg or {}).get("revenue_per_thb_inventory", 0)

    # R-04: Underperforming location
    if avg_eff > 0 and eff < avg_eff and eff > 0:
        recs.append({
            "rule_id": "R-04",
            "severity": "warning",
            "title": "Below-average efficiency",
            "text": (
                f"{location_name} generates {_fmt_thb(eff)} revenue per ฿1 of inventory "
                f"(company average: {_fmt_thb(avg_eff)}). "
                f"Dead stock is {dead_pct:.0f}% of inventory ({_fmt_thb(dead_thb)}). "
                f"Review product mix and consider transferring slow-moving items."
            ),
            "metric": avg_eff - eff,
            "source": "rule",
        })

    # R-05: Star location
    if avg_eff > 0 and eff > avg_eff * 2:
        recs.append({
            "rule_id": "R-05",
            "severity": "info",
            "title": "Star location",
            "text": (
                f"{location_name} is highly efficient at {eff:.2f}x revenue per ฿1 inventory "
                f"(company average: {avg_eff:.2f}x). "
                f"Consider increasing stock allocation to capture more sales."
            ),
            "metric": eff,
            "source": "rule",
        })

    # High dead stock warning
    if dead_pct > 30 and dead_thb > 50_000:
        recs.append({
            "rule_id": "R-01-LOC",
            "severity": "critical" if dead_pct > 50 else "warning",
            "title": "High dead stock",
            "text": (
                f"{dead_pct:.0f}% of inventory at {location_name} is dead stock "
                f"({_fmt_thb(dead_thb)} with zero sales in 90 days). "
                f"Transfer or markdown these items to free up space and capital."
            ),
            "metric": dead_thb,
            "source": "rule",
        })

    return sorted(recs, key=lambda r: {"critical": 3, "warning": 2, "info": 1}.get(r["severity"], 0), reverse=True)[:5]


# ---------------------------------------------------------------------------
# Item-level recommendations
# ---------------------------------------------------------------------------

def recommend_for_item(
    item_info: dict,
    locations: list[dict],
) -> list[dict]:
    """Generate recommendations for an item detail page.

    Parameters
    ----------
    item_info : dict
        From compute_item_location_detail: item_code, item_name, brand,
        total_onhand_qty, total_sold_qty, total_sold_thb, abcde_class_in_brand,
        abcde_class_overall.
    locations : list[dict]
        Per-location data: whs_name, onhand_qty, lifetime_sold_qty, lifetime_sold_thb.
    """
    recs: list[dict] = []

    total_onhand = item_info.get("total_onhand_qty", 0)
    total_sold = item_info.get("total_sold_qty", 0)
    abcde = item_info.get("abcde_class_in_brand", "E")
    item_code = item_info.get("item_code", "?")

    # R-01: Dead stock item (no sales)
    if total_sold == 0 and total_onhand > 0:
        onhand_thb = item_info.get("total_onhand_thb", 0)
        recs.append({
            "rule_id": "R-01",
            "severity": "critical",
            "title": "Zero sales",
            "text": (
                f"{item_code} has {total_onhand} units on-hand ({_fmt_thb(onhand_thb)}) "
                f"but zero sales in the selected period. "
                f"Consider markdown, return to vendor, or liquidation."
            ),
            "metric": onhand_thb,
            "source": "rule",
        })

    # R-03: Stock imbalance across locations
    if locations and len(locations) >= 2:
        selling_locs = [l for l in locations if l.get("lifetime_sold_qty", 0) > 0]
        stocked_no_sales = [
            l for l in locations
            if l.get("onhand_qty", 0) > 0 and l.get("lifetime_sold_qty", 0) == 0
        ]
        if selling_locs and stocked_no_sales:
            best_seller = max(selling_locs, key=lambda l: l.get("lifetime_sold_qty", 0))
            worst_loc = max(stocked_no_sales, key=lambda l: l.get("onhand_qty", 0))
            recs.append({
                "rule_id": "R-03",
                "severity": "warning",
                "title": "Stock imbalance",
                "text": (
                    f"{item_code} sells well at {best_seller.get('whs_name', '?')} "
                    f"({best_seller.get('lifetime_sold_qty', 0):.0f} units) but "
                    f"{worst_loc.get('whs_name', '?')} holds {worst_loc.get('onhand_qty', 0):.0f} units "
                    f"with zero sales. Consider transferring stock."
                ),
                "metric": worst_loc.get("onhand_qty", 0),
                "source": "rule",
            })

    # Positive: A/B class product
    if abcde in ("A", "B") and total_sold > 0:
        recs.append({
            "rule_id": "R-INFO-02",
            "severity": "info",
            "title": f"Class {abcde} product",
            "text": (
                f"{item_code} is a Class {abcde} product within its brand — "
                f"{'a star performer contributing to the top 50%' if abcde == 'A' else 'a strong performer in the top 80%'} "
                f"of brand revenue. Protect availability."
            ),
            "metric": total_sold,
            "source": "rule",
        })

    return sorted(recs, key=lambda r: {"critical": 3, "warning": 2, "info": 1}.get(r["severity"], 0), reverse=True)[:5]
