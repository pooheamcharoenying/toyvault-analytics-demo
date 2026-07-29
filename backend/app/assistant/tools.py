"""The read-only tools the assistant may call, and how to run them.

Each tool wraps an existing route handler in ``app.api.routes.data_analysis`` and
calls it **in-process** — the same code that serves the dashboard pages — then
decodes its JSON response. So a tool's numbers are identical to the page's by
construction, and "never invent a number" holds automatically.

Adding a tool is one ``Tool(...)`` entry in ``TOOLS``. Every handler parameter
must be listed in ``params`` (the handler's ``Query`` defaults do NOT apply when
we call it directly, so we always pass explicit values).
"""
from __future__ import annotations

import json
import logging

from app.api.routes import data_analysis as da

logger = logging.getLogger(__name__)

_REQUIRED = object()  # marks a parameter with no default (must be supplied)

# Reusable parameter schemas
_YEAR_LIST = {
    "type": "array", "items": {"type": "integer"},
    "description": "Calendar years to include, e.g. [2024, 2025]. Omit for all years / lifetime.",
    "default": None,
}
_GRANULARITY = {
    "type": "string", "enum": ["monthly", "weekly"],
    "description": "Time bucket for the series.", "default": "monthly",
}
_BRAND_OPT = {"type": "string", "description": "Filter to one brand (case-insensitive). Omit for all brands.", "default": None}


class Tool:
    """One callable tool: an OpenAI function spec bound to a route handler.

    ``transform`` optionally post-processes the handler's dict before it goes back
    to the model — used to surface the right ranking and to trim huge payloads
    (a 500-row matrix re-sent every step is slow and expensive)."""

    def __init__(self, name: str, description: str, params: dict, handler, transform=None):
        self.name = name
        self.description = description
        self.params = params        # {param_name: {type, description, default, [enum], [items]}}
        self.handler = handler
        self.transform = transform

    def openai_spec(self) -> dict:
        properties, required = {}, []
        for pname, p in self.params.items():
            schema = {"type": p["type"]}
            if "description" in p:
                schema["description"] = p["description"]
            if "enum" in p:
                schema["enum"] = p["enum"]
            if "items" in p:
                schema["items"] = p["items"]
            properties[pname] = schema
            if p.get("default", _REQUIRED) is _REQUIRED:
                required.append(pname)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        }

    def build_kwargs(self, args: dict) -> dict:
        kwargs = {}
        for pname, p in self.params.items():
            if pname in args and args[pname] is not None:
                kwargs[pname] = args[pname]
            elif p.get("default", _REQUIRED) is _REQUIRED:
                raise KeyError(pname)
            else:
                kwargs[pname] = p["default"]
        return kwargs


def _to_dict(result):
    """Normalise a handler's return (JSONResponse / Response / dict / list) to a
    plain JSON-serialisable object."""
    if isinstance(result, (dict, list)):
        return result
    body = getattr(result, "body", None)
    if body is not None:
        try:
            return json.loads(body)
        except Exception:
            return {"raw": body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)}
    return {"result": str(result)}


def _lpm_transform(d: dict) -> dict:
    """location_product_mix returns a 594-row `all_stocks` list (every item's on-hand
    here) — too big to hand the model raw, and its `top_items` are revenue-ranked, so
    the model can't answer 'most on-hand' from them. Replace the raw list with the
    on-hand leaders (by qty and by value) and trim the rest."""
    if not isinstance(d, dict):
        return d
    d = dict(d)
    stocks = d.pop("all_stocks", None) or []
    d["item_count_with_onhand"] = len(stocks)
    d["top_items_by_onhand_qty"] = sorted(
        stocks, key=lambda x: -(x.get("onhand_qty") or 0))[:15]
    d["top_items_by_onhand_value"] = sorted(
        stocks, key=lambda x: -(x.get("onhand_thb") or 0))[:15]
    for k in ("top_items", "non_movers", "top_brands"):
        if isinstance(d.get(k), list):
            d[k] = d[k][:15]
    d.pop("brand_heatmap", None)  # bulky and rarely needed in a chat answer
    return d


def _trend_yearly(d: dict) -> dict:
    """Add a per-year revenue breakdown to sales_trend, computed server-side from
    its monthly series — so the model can contextualise a lifetime total by year
    without doing the arithmetic itself. Flags the latest year as partial when the
    data ends mid-year."""
    if not isinstance(d, dict):
        return d
    from collections import OrderedDict
    series = d.get("series") or []
    yr = OrderedDict()
    last_period = ""
    for p in series:
        period = str(p.get("period") or "")
        if period > last_period:
            last_period = period
        y = period[:4]
        if not y.isdigit():
            continue
        e = yr.setdefault(y, {"revenue_actual_thb": 0.0, "revenue_master_thb": 0.0, "qty": 0.0})
        e["revenue_actual_thb"] += p.get("revenue_thb") or 0
        e["revenue_master_thb"] += p.get("revenue_master_thb") or 0
        e["qty"] += p.get("qty") or 0
    latest_year = max(yr) if yr else None
    yearly = []
    for y, e in yr.items():
        row = {"year": int(y), "revenue_actual_thb": round(e["revenue_actual_thb"]),
               "revenue_master_thb": round(e["revenue_master_thb"]), "qty": int(e["qty"])}
        if y == latest_year and last_period[5:7] != "12":
            row["partial_year"] = True  # data ends mid-year — this year is incomplete
        yearly.append(row)
    d = dict(d)
    d["yearly_totals"] = yearly
    return d


def _loc_names_transform(d: dict) -> dict:
    """Reduce location_performance to just names (+ revenue for context) — a cheap
    way to resolve a user's location to its exact stored name."""
    if not isinstance(d, dict):
        return d
    locs = d.get("locations") or []
    out = [{"name": l.get("location"), "revenue_thb": round(l.get("sold_thb") or 0)} for l in locs]
    out.sort(key=lambda x: -(x["revenue_thb"] or 0))
    return {"count": len(out), "locations": out}


# ---------------------------------------------------------------------------
# Tool registry — one entry per capability. Extend freely.
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        "get_executive_summary",
        "Company-wide headline KPIs: total revenue (actual + master), on-hand stock value (master "
        "price), GP commission, net revenue, and the latest month-over-month change. Use for "
        "'how's the business overall', total revenue/stock value, or MoM. Not per-brand or "
        "per-location.",
        {},
        da.get_executive_summary,
    ),
    Tool(
        "get_sales_trend",
        "Organisation-wide revenue over time. Returns a monthly/weekly `series` (with "
        "year-over-year % and trailing-12-month rolling revenue) AND `yearly_totals` — revenue "
        "per year (actual + master), with the latest year flagged partial. Use for 'are we "
        "growing', revenue trend, YoY, and to break a lifetime total down BY YEAR.",
        {"granularity": _GRANULARITY, "year_list": _YEAR_LIST},
        da.get_sales_trend_executive,
        transform=_trend_yearly,
    ),
    Tool(
        "get_concentration_risk",
        "Top-N revenue concentration by brand or channel — how dependent the business is on a few "
        "names (Pareto / share). Use for 'are we too reliant on one brand/channel'.",
        {
            "dimension": {"type": "string", "enum": ["brand", "channel"],
                          "description": "Group by brand or by sales channel.", "default": "brand"},
            "year": {"type": "integer", "description": "Single calendar year. Omit for current year.", "default": None},
            "top_n": {"type": "integer", "description": "How many top names to rank (1–100).", "default": 10},
        },
        da.get_concentration_summary,
    ),
    Tool(
        "list_brands",
        "Every brand ranked with revenue (actual + master), COGS (FOB), GP commission, gross margin "
        "%, on-hand value (master), sell-through rate, and ABCDE product-tier counts. The primary "
        "brand tool — use for 'all brands ranked', brand health, or which brands make money.",
        {"year_list": _YEAR_LIST},
        da.get_brand_list_metrics,
    ),
    Tool(
        "get_margin_by_brand",
        "Brand profitability ranking: revenue vs FOB COGS vs GP commission = gross margin and margin "
        "% per brand, with company totals. Use for a focused 'which brands are most/least "
        "profitable' answer.",
        {"year_list": _YEAR_LIST},
        da.get_margin_by_brand,
    ),
    Tool(
        "list_locations",
        "Location scorecard with efficiency metrics: revenue (actual + master), on-hand value "
        "(master), revenue-per-THB-inventory, stock turnover, sell-through, days of cover, "
        "dead-stock %, health score, ABCDE, and a green/yellow/red traffic light. Use for 'which "
        "locations are efficient / underperforming'. Default ranking is by efficiency, not raw "
        "revenue.",
        {
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "year_list": _YEAR_LIST,
            "window_days": {"type": "integer", "description": "Sales-velocity window in days (7–365).", "default": 90},
            "target_cover_days": {"type": "integer", "description": "Target days of stock cover for the gap calc (7–365).", "default": 60},
        },
        da.get_location_performance,
    ),
    Tool(
        "get_location_product_mix",
        "For ONE location, everything about its product mix. Returns: `top_items` (top SELLERS, "
        "revenue-ranked), `top_items_by_onhand_qty` and `top_items_by_onhand_value` (the items with "
        "the most STOCK here — use these for 'most/least on-hand' questions), `non_movers` (stocked "
        "but not selling), `top_brands`, and totals. Each item row has `onhand_qty`, `onhand_thb` "
        "(master), `sold_qty`, `sold_thb`. First resolve the exact location name with list_locations "
        "(locations are stored under a consolidated name, often in Thai).",
        {
            "location": {"type": "string", "description": "Exact consolidated location name (resolve via list_locations first)."},
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "year_list": _YEAR_LIST,
            "top_n": {"type": "integer", "description": "How many top sellers/brands to return (1–100).", "default": 20},
            "window_days": {"type": "integer", "description": "Recent window (days) used to judge non-movers (7–365).", "default": 90},
            "brand": _BRAND_OPT,
        },
        da.get_location_product_mix,
        transform=_lpm_transform,
    ),
    Tool(
        "get_item_detail",
        "Full detail for ONE product by ItemCode: its on-hand and lifetime sales broken down across "
        "ALL locations, its P&L (revenue actual + master, FOB cost, GP commission, margin), ABCDE "
        "class, and purchase history. Use for 'where is item X stocked, where does it sell, is it "
        "profitable'.",
        {
            "item_code": {"type": "string", "description": "The exact ItemCode."},
            "year_list": _YEAR_LIST,
        },
        da.get_item_location_detail,
    ),
    Tool(
        "get_location_trend",
        "Monthly or weekly revenue trend for ONE location, or the top-N locations as multiple lines. "
        "Use for 'is this store improving' or comparing store trajectories over time.",
        {
            "location": {"type": "string", "description": "One location (resolve via list_locations). Omit for top-N locations.", "default": None},
            "top_n": {"type": "integer", "description": "Number of top locations when no single location is given (1–50).", "default": 10},
            "year_list": _YEAR_LIST,
            "granularity": _GRANULARITY,
        },
        da.get_location_trends,
    ),
    Tool(
        "list_channels",
        "Every sales channel (Central, Robinson, The Mall, Online, …) with revenue (actual + "
        "master), mix %, number of physical locations, margins, and its top location. Use for "
        "'channels ranked', channel sizes, or channel mix. A channel maps to many locations.",
        {"year_list": _YEAR_LIST},
        da.get_channel_list,
    ),
    Tool(
        "get_stockout_risk",
        "Items about to run out — projected stockout date, severity, and a suggested reorder "
        "quantity, from on-hand vs recent sales velocity. Use for 'what's about to run out'.",
        {
            "window_days": {"type": "integer", "description": "Velocity window in days (7–365).", "default": 90},
            "threshold_days": {"type": "integer", "description": "Flag items with fewer than this many days of cover (1–180).", "default": 30},
            "top_n": {"type": "integer", "description": "Max items to return (1–500).", "default": 50},
            "brand": _BRAND_OPT,
        },
        da.get_stockout_risk,
    ),
    Tool(
        "get_dead_stock",
        "Dead / slow-moving stock: items with zero or near-zero sales but positive on-hand, the "
        "capital at risk (master value), whether they're still being purchased, and a recommended "
        "action. Use for 'what's not selling / write-off candidates'.",
        {
            "window_days": {"type": "integer", "description": "No-sales lookback in days (30–730).", "default": 180},
            "top_n": {"type": "integer", "description": "Max items to return (1–500).", "default": 100},
            "brand": _BRAND_OPT,
        },
        da.get_dead_stock,
    ),
    Tool(
        "get_reorder_analysis",
        "Reorder-point analysis with suggested order quantities and last purchase cost (FOB), from "
        "sales velocity + lead time + target cover. Use for 'what should we reorder and how much'.",
        {
            "window_days": {"type": "integer", "description": "Velocity window in days (7–365).", "default": 90},
            "lead_time_days": {"type": "integer", "description": "Vendor lead time in days (1–180).", "default": 28},
            "target_cover_days": {"type": "integer", "description": "Target days of cover to reorder up to (7–365).", "default": 56},
            "top_n": {"type": "integer", "description": "Max items to return (1–500).", "default": 100},
            "brand": _BRAND_OPT,
        },
        da.get_reorder_analysis,
    ),
    Tool(
        "get_priority_actions",
        "The unified 'Monday-morning' action feed: top prioritised reorder / dead-stock / stockout / "
        "transfer / location alerts across the business, each with a THB impact and severity. Use "
        "for 'what needs my attention now' or 'top actions'.",
        {"max_actions": {"type": "integer", "description": "Max actions to return (1–100).", "default": 30}},
        da.get_priority_actions,
    ),

    # --- Channels ---
    Tool(
        "get_channel_growth",
        "Per-channel latest-vs-prior-period revenue, mix %, and month-over-month growth. Use for "
        "'which channels are growing or shrinking'.",
        {"year_list": _YEAR_LIST, "period_type": _GRANULARITY},
        da.get_channel_performance_executive,
    ),
    Tool(
        "get_channel_detail",
        "One channel drilled down: the physical locations inside it, its brand breakdown, and its "
        "monthly revenue trend. Use for 'which stores and brands make up Robinson/Central, over "
        "time'. Resolve the channel name with list_channels first.",
        {
            "channel": {"type": "string", "description": "Exact channel name (resolve via list_channels)."},
            "year_list": _YEAR_LIST,
        },
        da.get_channel_detail,
    ),

    # --- Brand drill-downs ---
    Tool(
        "get_brand_trend",
        "Monthly/weekly revenue, cost and margin trend for ONE brand, or the top-N brands as "
        "multiple lines. Use for a brand's trajectory over time or comparing brands' trends.",
        {
            "brand_name": {"type": "string", "description": "One brand (omit for top-N brands).", "default": None},
            "top_n": {"type": "integer", "description": "Number of brands when no single brand given (1–20).", "default": 5},
            "year_list": _YEAR_LIST,
            "granularity": _GRANULARITY,
        },
        da.get_brand_monthly_trend,
    ),
    # (product_market_fit + brand_stock_vs_sales tools omitted — those dashboards aren't in ToyVault yet)

    # --- Products / classification ---
    Tool(
        "get_abc_classification",
        "ABC classification of items (or brands) by cumulative revenue — A-items are the top ~80% "
        "of revenue. Use for 'which are our A-items / where should we focus'.",
        {
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "dimension": {"type": "string", "enum": ["item", "brand"], "description": "Classify items or brands.", "default": "item"},
            "a_threshold": {"type": "number", "description": "Cumulative revenue %% cutoff for class A.", "default": 80.0},
            "b_threshold": {"type": "number", "description": "Cumulative revenue %% cutoff for class B.", "default": 95.0},
        },
        da.get_abc_classification,
    ),
    Tool(
        "get_product_channel_fit",
        "Product/brand x channel matrix — what sells where, with the star products per channel. "
        "Use for 'what sells well in which channel' and allocation/placement decisions.",
        {
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "year_list": _YEAR_LIST,
            "dimension": {"type": "string", "enum": ["brand", "item"], "description": "Rows are brands or items.", "default": "brand"},
            "top_n": {"type": "integer", "description": "Top products/brands in the matrix (1–100).", "default": 15},
        },
        da.get_product_channel_fit,
    ),

    # --- Margin / profitability ---
    Tool(
        "get_margin_mix",
        "Blended gross-margin trend plus a per-brand margin-contribution waterfall — which brands "
        "lift or drag overall margin. Use for 'what's dragging our margin'.",
        {
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "top_n": {"type": "integer", "description": "Top contributing brands (1–50).", "default": 15},
            "year_list": _YEAR_LIST,
        },
        da.get_margin_mix_analysis,
    ),

    # --- Purchasing ---
    Tool(
        "get_purchase_cost_trends",
        "FOB landed-cost trend over time (overall and per brand) and currency/FX impact. Use for "
        "'are we paying more for goods', landed-cost trend, or FX impact.",
        {
            "brand": _BRAND_OPT,
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "year_list": _YEAR_LIST,
        },
        da.get_purchase_cost_trends,
    ),
    Tool(
        "get_purchase_vs_sold",
        "Purchased vs sold by brand — over/under-buying and inventory build-up. Use for 'are we "
        "buying more than we sell' or procurement discipline by brand.",
        {
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "top_n": {"type": "integer", "description": "Top brands by activity (1–100).", "default": 30},
            "year_list": _YEAR_LIST,
        },
        da.get_purchase_vs_sold,
    ),

    # --- Inventory / working capital / allocation ---
    Tool(
        "get_working_capital_trends",
        "Inventory value (master) and inventory-efficiency (turnover, stock-to-sales) over time. "
        "Use for 'how much cash is tied up in stock over time' or turnover trend.",
        {"window_months": {"type": "integer", "description": "Months of history (3–36).", "default": 12}},
        da.get_working_capital_trends,
    ),
    Tool(
        "get_stock_allocation",
        "Item-level overstocked/understocked locations plus transfer recommendations (compares "
        "on-hand to each location's own velocity). Use for 'where should we move stock'.",
        {
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "brand": _BRAND_OPT,
            "window_days": {"type": "integer", "description": "Velocity window (7–365).", "default": 90},
            "top_n": {"type": "integer", "description": "Max recommendations (1–200).", "default": 20},
        },
        da.get_stock_allocation,
    ),
    Tool(
        "get_rebalancing_summary",
        "Executive-level surplus/deficit by location and by brand — how much stock is "
        "rebalanceable. Use for a high-level 'how much stock is in the wrong place'.",
        {
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "window_days": {"type": "integer", "description": "Velocity window (7–365).", "default": 90},
        },
        da.get_rebalancing_summary,
    ),
    Tool(
        "get_transfer_history",
        "Past inter-location transfer flows: net senders vs receivers, most-transferred items, "
        "monthly trend. Use for 'how does stock move between locations'.",
        {
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "top_n": {"type": "integer", "description": "Top items/locations (1–100).", "default": 20},
        },
        da.get_transfer_history,
    ),

    # --- Seasonality / trends / detail ---
    Tool(
        "get_seasonality",
        "Monthly seasonal patterns across years, seasonal index, and current-vs-pattern. Use for "
        "'when do sales peak' and planning. Optionally scope to one brand or channel.",
        {
            "dimension": {"type": "string", "enum": ["overall", "brand", "channel"], "description": "Overall, or scoped to a brand/channel.", "default": "overall"},
            "filter_value": {"type": "string", "description": "The brand or channel name when dimension is brand/channel.", "default": None},
        },
        da.get_seasonality_analysis,
    ),
    Tool(
        "get_item_trend",
        "Monthly sales trend for ONE item (by ItemCode), with reconstructed end-of-month on-hand. "
        "Use for a single product's trajectory over time.",
        {
            "item_code": {"type": "string", "description": "The exact ItemCode."},
            "year_list": _YEAR_LIST,
        },
        da.get_item_monthly_trend,
    ),
    Tool(
        "get_brand_at_location_trend",
        "Monthly/weekly revenue for ONE brand at ONE location over time. Resolve both names first "
        "(list_brand_names, list_location_names).",
        {
            "location": {"type": "string", "description": "Exact location name."},
            "brand": {"type": "string", "description": "Exact brand name."},
            "year_list": _YEAR_LIST,
            "granularity": _GRANULARITY,
        },
        da.get_brand_at_location_trend,
    ),

    # --- Recommendations & data trust ---
    Tool(
        "get_recommendations",
        "Deterministic rule-based recommendations for a brand / location / item context (dead "
        "stock, loss-makers, star products, efficiency, stock imbalance). Use for 'what should we "
        "do about brand/location/item X'.",
        {
            "context": {"type": "string", "enum": ["brand", "location", "item"], "description": "What kind of thing `name` is."},
            "name": {"type": "string", "description": "The brand name, location name, or ItemCode."},
            "year_list": _YEAR_LIST,
        },
        da.get_recommendations,
    ),
    Tool(
        "get_data_quality",
        "Item-Master coverage and price/brand recovery tiers — how complete and trustworthy the "
        "data is. Use for 'can I trust these numbers' or data-completeness questions.",
        {},
        da.get_data_quality,
    ),

    # --- Entity-resolution list tools (cheap; use to resolve names) ---
    Tool(
        "list_brand_names",
        "Every product-brand name. Use this to resolve a user's brand to the exact stored name "
        "before calling a brand-scoped tool.",
        {},
        da.get_brand_list,
    ),
    Tool(
        "list_location_names",
        "Every location's exact name (with revenue for context) — a cheap way to resolve a user's "
        "location (e.g. 'Siam Paragon') to its stored name (often Thai, e.g. 'M-สยาพารากอน') "
        "before calling a location-scoped tool. Prefer this over list_locations when you only need "
        "the name.",
        {
            "year": {"type": "integer", "description": "Single year. Omit for all years.", "default": None},
            "year_list": _YEAR_LIST,
            "window_days": {"type": "integer", "description": "Velocity window (7–365).", "default": 90},
            "target_cover_days": {"type": "integer", "description": "Target days of cover (7–365).", "default": 60},
        },
        da.get_location_performance,
        transform=_loc_names_transform,
    ),
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}

# present_table is a DISPLAY directive, not a data tool — it is handled by the
# agent (it renders the rows from the most recent data tool as the single table
# the user sees). The model decides the columns and row count from the question.
PRESENT_TABLE_SPEC = {
    "type": "function",
    "function": {
        "name": "present_table",
        "description": (
            "Display the rows from your MOST RECENT data tool as ONE table to the user. Use this "
            "for any answer that is a list of records (items, brands, locations, at-risk items…) "
            "INSTEAD of writing a Markdown table yourself. You choose: the columns that matter for "
            "the question (3–6 of the row's fields, not every field), and how many rows — a few for "
            "a 'top N' ask, or ALL of them (set max_rows to a large number like 1000) whenever the "
            "user asks for everything / the full list. After calling it, write only a short "
            "narrative (the total, the key insight) — do NOT also write the table in text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "columns": {"type": "array", "items": {"type": "string"},
                            "description": "Row field keys to show, in order. Pick the few that answer the question. Omit to show all fields."},
                "max_rows": {"type": "integer",
                             "description": "How many rows to show — small for a preview/top-N, large (e.g. 1000) to show every row when the user asked for all."},
                "sort_by": {"type": "string", "description": "Row field key to sort by (optional)."},
                "sort_desc": {"type": "boolean", "description": "Sort descending (default true)."},
                "title": {"type": "string", "description": "Short caption for the table (optional)."},
            },
            "required": [],
        },
    },
}

# export_table is also a DIRECTIVE (handled by the agent, not a data tool): it
# turns the table you just showed into a downloadable .xlsx/.csv and returns a
# link. LINE can't attach files, so this is how a user gets the data as a file.
EXPORT_TABLE_SPEC = {
    "type": "function",
    "function": {
        "name": "export_table",
        "description": (
            "Deliver the table you JUST showed as a downloadable FILE (Excel or CSV) — returns a "
            "download link that is delivered to the user automatically. Use this whenever the user "
            "asks for the data as a file / excel / xlsx / csv / download / 'ขอเป็น excel' / "
            "'ขอไฟล์'. You MUST call present_table first (the export uses that exact table); then "
            "call export_table. Never claim you can't create a file — use this. After calling it, "
            "just tell the user their file/link is ready (the link itself is attached for them)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["xlsx", "csv"],
                           "description": "File format — xlsx (Excel) or csv. Default xlsx."},
            },
            "required": [],
        },
    },
}

TOOL_SPECS = [t.openai_spec() for t in TOOLS] + [PRESENT_TABLE_SPEC, EXPORT_TABLE_SPEC]


def run_tool(name: str, args: dict) -> dict:
    """Execute one tool call in-process. Always returns a JSON-serialisable dict:
    ``{"ok": True, "data": ...}`` or ``{"ok": False, "error": ..., "message": ...}``
    (never raises)."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return {"ok": False, "error": "unknown_tool", "message": f"No such tool: {name}"}
    try:
        kwargs = tool.build_kwargs(args)
    except KeyError as exc:
        return {"ok": False, "error": "missing_argument", "message": f"Missing required argument: {exc}"}
    try:
        data = _to_dict(tool.handler(**kwargs))
        if tool.transform:
            data = tool.transform(data)
        return {"ok": True, "data": data}
    except Exception as exc:  # a handler blew up — surface cleanly, log details
        logger.exception("tool %s failed", name)
        return {"ok": False, "error": "tool_error", "message": str(exc)}


def tool_result_to_message(result: dict) -> str:
    return json.dumps(result, default=str, ensure_ascii=False)
