"""Per-location summary of Stock Bot recommendations.

For a given physical location, produces a per-item summary the
location-detail page can render as extra columns:
    - Shelf Cap            (from ItemLocationState — every item, not
                            just items with active proposals)
    - Recommended Transfer (from proposals — only items the bot
                            actually decided to move)
    - Stock at D1 Warehouse (from raw on-hand — diagnostic for "why
                             isn't there a transfer rec?")

The cap signal comes from the bot's pre-planner state objects (so it
covers ALL items the bot considered, not just items that made it into
a proposal). The transfer signal comes from the bot's plan output.
The D1 signal comes directly from raw on-hand data.

Pure functions. No globals.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from app.stock_bot.output.physical_location import derive_physical_location


# WhsCode prefixes / codes that count as the D1 main warehouse. Keep this
# broad so the column populates regardless of which exact SAP code the
# data uses (D1, 01, etc).
_D1_WHS_CODES = {"D1", "01"}
_D1_NAME_HINTS = ("main warehouse", "warehouse d1", "d1 main")


def compute_location_summary(
    plan: Dict[str, Any],
    location: str,
    *,
    policy: Optional[dict] = None,
) -> Dict[str, Any]:
    """Build a per-item summary of the Stock Bot recommendations at ``location``.

    Args:
        plan: The full response from ``generate_transfer_plan`` (the dict
            with keys ``status``, ``destination_groups``, ``summary``, etc.).
        location: The consolidated / physical location name as it appears
            on the location-detail page (e.g. ``"M-เอ็มโพเรียม"``).
        policy: Optional policy dict — passed to ``derive_physical_location``
            so any ``physical_location_overrides`` in policy.yaml are honoured
            when matching transfers' source whs codes to this location.

    Returns:
        Dict shaped:
            {
                "location": "M-เอ็มโพเรียม",
                "items": {
                    "<item_code>": {
                        "shelf_cap": int | None,
                        "net_transfer": int,
                        "transfers_in_qty": int,
                        "transfers_out_qty": int,
                        "transfers_in_count": int,
                        "transfers_out_count": int,
                    },
                    ...
                },
                "status": "ok" | "no_plan",
                "transfers_in_total_qty": int,
                "transfers_out_total_qty": int,
            }

        Items with no Stock Bot signal at this location (no transfer in
        either direction and no group entry) are simply absent from the
        dict — the frontend can render "—" for them.
    """
    policy = policy or {}
    overrides = (policy.get("physical_location_overrides") or {}) if policy else {}

    if not plan or plan.get("status") != "ok":
        return {
            "location": location,
            "items": {},
            "status": "no_plan",
            "transfers_in_total_qty": 0,
            "transfers_out_total_qty": 0,
        }

    items: Dict[str, dict] = {}
    in_total = 0
    out_total = 0

    groups = plan.get("destination_groups") or []

    # --- INBOUND: this location is the destination of the group ---
    for group in groups:
        if group.get("physical_location") != location:
            continue
        for t in group.get("transfers") or []:
            ic = str(t.get("item_code"))
            qty = int(t.get("qty") or 0)
            cap = t.get("shelf_capacity_estimate")
            entry = items.setdefault(ic, _new_entry())
            entry["transfers_in_qty"] += qty
            entry["transfers_in_count"] += 1
            # Cap is per (item, destination) — same value for every transfer
            # of this item INTO this location, so first-wins is fine.
            if entry["shelf_cap"] is None and cap is not None:
                entry["shelf_cap"] = int(cap)
            in_total += qty

    # --- OUTBOUND: this location is the source of a transfer in any group ---
    # We have to scan all groups for from_whs entries that normalise to this
    # location.
    for group in groups:
        for t in group.get("transfers") or []:
            from_name = t.get("from_whs_name") or ""
            from_code = t.get("from_whs_code") or ""
            src_location = derive_physical_location(from_name, from_code, overrides)
            if src_location != location:
                continue
            ic = str(t.get("item_code"))
            qty = int(t.get("qty") or 0)
            entry = items.setdefault(ic, _new_entry())
            entry["transfers_out_qty"] += qty
            entry["transfers_out_count"] += 1
            out_total += qty

    # --- Compute net + finalise ---
    for ic, entry in items.items():
        entry["net_transfer"] = entry["transfers_in_qty"] - entry["transfers_out_qty"]

    return {
        "location": location,
        "items": items,
        "status": "ok",
        "transfers_in_total_qty": in_total,
        "transfers_out_total_qty": out_total,
    }


def _new_entry() -> dict:
    return {
        "shelf_cap": None,
        "net_transfer": 0,
        "transfers_in_qty": 0,
        "transfers_out_qty": 0,
        "transfers_in_count": 0,
        "transfers_out_count": 0,
        "d1_stock": None,
        "monthly_velocity": None,   # units/mo at this location (recent 90d)
    }


# ---------------------------------------------------------------------------
# Cap-from-states enrichment (covers items with NO transfer proposal)
# ---------------------------------------------------------------------------

def enrich_with_caps_from_states(
    summary: Dict[str, Any],
    states: Iterable[Any],
    location: str,
    *,
    policy_overrides: Optional[dict] = None,
) -> Dict[str, Any]:
    """Fill in ``shelf_cap`` for items the bot considered but had no
    proposal for.

    ``states`` is the list of ``ItemLocationState`` objects produced by
    ``app.stock_bot.api.build_all_item_location_states``. Since the bot
    pipeline now consolidates WhsCodes to physical-location labels at
    its first step, each state's ``whs_code`` IS the physical location
    string (e.g. ``"M-Grandway Riverside"``) — no derivation needed.

    For safety against either path (fully consolidated OR legacy
    SAP-code data), we keep the derive_physical_location fallback. On
    consolidated data it's an identity; on raw data it normalises.

    Mutates and returns ``summary``.
    """
    if not summary or summary.get("status") != "ok":
        return summary

    overrides = (policy_overrides or {}) if policy_overrides else {}
    items = summary.setdefault("items", {})

    cap_by_item: Dict[str, int] = {}
    velo_by_item: Dict[str, float] = {}   # units / month at this location
    for s in states or []:
        whs_name = getattr(s, "whs_name", "") or ""
        whs_code = getattr(s, "whs_code", "") or ""
        # Fast path — after consolidation, whs_code is already the
        # physical label. Fall back to derive_physical_location for any
        # legacy/edge cases.
        if whs_code == location:
            physical = location
        else:
            physical = derive_physical_location(whs_name, whs_code, overrides)
            if physical != location:
                continue
        ic = str(getattr(s, "item_code", "") or "")
        if not ic:
            continue
        # Shelf cap — take max across any duplicate states for this item
        # (shouldn't happen under consolidation, but defensive).
        cap = getattr(s, "shelf_capacity", None)
        if cap is not None and (ic not in cap_by_item or cap > cap_by_item[ic]):
            cap_by_item[ic] = int(cap)
        # Monthly velocity — convert per-day → per-month. Sum across any
        # duplicate states so we end up with the true throughput at this
        # physical location.
        velo_per_day = getattr(s, "velocity_per_day", None)
        if velo_per_day is not None and velo_per_day > 0:
            velo_by_item[ic] = velo_by_item.get(ic, 0.0) + float(velo_per_day) * 30.0

    for ic, cap in cap_by_item.items():
        entry = items.setdefault(ic, _new_entry())
        if entry["shelf_cap"] is None or cap > entry["shelf_cap"]:
            entry["shelf_cap"] = cap

    for ic, velo in velo_by_item.items():
        entry = items.setdefault(ic, _new_entry())
        entry["monthly_velocity"] = round(velo, 1)

    return summary


# ---------------------------------------------------------------------------
# D1 stock enrichment
# ---------------------------------------------------------------------------

def enrich_with_d1_stock(
    summary: Dict[str, Any],
    df_raw_onhand: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    """Fill in ``d1_stock`` (units currently on-hand at the D1 main
    warehouse) for every item in ``summary["items"]``. Mutates and
    returns ``summary``.

    Items the data shows at D1 with zero stock will get ``d1_stock = 0``;
    items the data has no row for at D1 will also get 0 (D1 doesn't
    stock that SKU). The frontend renders 0 explicitly so a manager can
    immediately see "the bot didn't recommend a transfer because D1 is
    empty" vs. "the bot didn't consider this SKU at all" (shelf_cap is
    also None in the latter case).
    """
    if not summary or summary.get("status") != "ok":
        return summary
    items = summary.setdefault("items", {})

    d1_by_item: Dict[str, int] = {}
    if df_raw_onhand is not None and not df_raw_onhand.empty:
        oh = df_raw_onhand[["WhsCode", "ItemCode", "OnHand"]].copy()
        oh["WhsCode"] = oh["WhsCode"].astype(str).str.strip()
        oh["ItemCode"] = oh["ItemCode"].astype(str).str.strip()
        oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0.0)
        # Match either exact WhsCode in the D1 set, OR a name hint
        is_d1 = oh["WhsCode"].str.upper().isin({c.upper() for c in _D1_WHS_CODES})
        d1_rows = oh[is_d1]
        if not d1_rows.empty:
            grp = d1_rows.groupby("ItemCode")["OnHand"].sum()
            for ic, qty in grp.items():
                d1_by_item[str(ic)] = int(round(float(qty)))

    for ic in list(items.keys()):
        items[ic]["d1_stock"] = d1_by_item.get(ic, 0)
    # Also surface items that have D1 stock but no other signal — they
    # may appear elsewhere in the location's product tables and we want
    # the D1 column to populate.
    for ic, qty in d1_by_item.items():
        entry = items.setdefault(ic, _new_entry())
        entry["d1_stock"] = qty

    summary["d1_stock_total"] = int(sum(d1_by_item.values()))
    return summary
