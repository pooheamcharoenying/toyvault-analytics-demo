"""Planogram (PAR) endpoints — minimum units per SKU on shelf, per location.

- ``GET  /api/location_planogram?location=X`` — the SKUs at a location, each
  with its current planogram minimum, plus location-wide SKU counts.
- ``PUT  /api/location_planogram?location=X`` — save minimums (a merge).
- ``GET  /api/planogram_locations`` — locations that have a planogram.
- ``GET/PUT /api/all_planograms`` — the all-locations minimum-quantity matrix.

Auth is enforced at include_router() in app/main.py, as for the other routers.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import APIRouter, Body, HTTPException, Query

from app.utils import helper_functions as hf
from app.utils import location_analytics as la
from app.utils import planogram_par as pp
from app.utils.location_consolidation import add_consolidated_column

logger = logging.getLogger(__name__)
router = APIRouter()


def _velocity_and_recent_months(
    location: str, window_days: int = 90, months_range: str = "3m"
) -> Dict[str, Any]:
    """Per-item monthly velocity and revenue over a selectable month range.

    ``months_range`` chooses which calendar months become columns, all anchored
    on the latest month present in the data (the workbook is a snapshot):
      - ``"3m"``   the last 3 complete months (default)
      - ``"year"`` January of the latest year through the latest month
      - ``"2y"``   January of last year through the latest month

    Reuses the SAME preparation helpers as `location_analytics` — channel dedup
    and location consolidation — so these figures reconcile with the tables on
    the location pages rather than quietly diverging.

    'Monthly velocity' matches the definition already used elsewhere in the
    app: average units sold per month over the recent `window_days` window, and
    is independent of ``months_range``.

    Returns {"months": [labels…], "by_item": {code: {"velocity": v,
             "month_revenue": [r1, r2, …]}}}
    """
    from app.utils import nichi_stock as nstk
    from app.utils.location_consolidation import add_consolidated_column

    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs = hf.GLOBAL_DF.get("whs_code")
    empty = {"months": [], "by_item": {}}
    if any(x is None for x in (df_raw_sale, df_raw_onhand, df_item_master, df_whs)):
        return empty

    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    sale = la._channel_dedup_sale(df_sale)

    whs = df_whs[["WhsCode", "WhsName"]].copy()
    whs["WhsCode"] = whs["WhsCode"].astype(str).str.strip()
    lookup = dict(zip(whs["WhsCode"], whs["WhsName"]))
    sale["WhsCode"] = sale["WhsCode"].astype(str).str.strip()
    sale = add_consolidated_column(sale, lookup)
    sale = sale[sale["ConsolidatedLocation"] == location].copy()
    if sale.empty:
        return empty

    sale["DocDate"] = pd.to_datetime(sale["DocDate"], errors="coerce")
    sale = sale.dropna(subset=["DocDate"])
    if sale.empty:
        return empty

    # Anchor on the newest sale in the data, not today's date — the workbook is
    # a snapshot and may be days old; using "now" would shift the windows and
    # silently show emptier months than the data actually contains.
    latest = sale["DocDate"].max()

    # --- velocity over the recent window ---
    cutoff = latest - pd.Timedelta(days=window_days)
    recent = sale[sale["DocDate"] >= cutoff]
    months_in_window = max(window_days / 30.0, 1e-9)
    vel = (
        recent.groupby("ItemCode")["Quantity"].sum() / months_in_window
        if not recent.empty else pd.Series(dtype=float)
    )

    # --- revenue over the selected month range ---
    # Build a CONTINUOUS calendar range (not just months that happen to have
    # sales) so a quiet month still shows as a 0 column rather than vanishing.
    sale["Period"] = sale["DocDate"].dt.to_period("M")
    latest_p = max(sale["Period"])
    if months_range == "year":
        start = pd.Period(year=latest_p.year, month=1, freq="M")
        periods = list(pd.period_range(start=start, end=latest_p, freq="M"))
    elif months_range == "2y":
        start = pd.Period(year=latest_p.year - 1, month=1, freq="M")
        periods = list(pd.period_range(start=start, end=latest_p, freq="M"))
    else:  # "3m" — the 3 months ending at the latest data month
        periods = list(pd.period_range(end=latest_p, periods=3, freq="M"))
    month_labels = [str(p) for p in periods]

    # Both revenue and units per month, so the UI can toggle between them with
    # no round trip.
    in_range = sale[sale["Period"].isin(periods)]
    rev = in_range.groupby(["ItemCode", "Period"])["LineTotal"].sum().unstack(fill_value=0.0)
    qty = in_range.groupby(["ItemCode", "Period"])["Quantity"].sum().unstack(fill_value=0.0)

    by_item: Dict[str, Any] = {}
    for code in set(vel.index) | set(rev.index) | set(qty.index):
        rrow = rev.loc[code] if code in rev.index else None
        qrow = qty.loc[code] if code in qty.index else None
        by_item[str(code)] = {
            "velocity": round(float(vel.get(code, 0.0)), 1),
            "month_revenue": [
                round(float(rrow[p]), 2) if rrow is not None and p in rrow else 0.0
                for p in periods
            ],
            "month_qty": [
                int(qrow[p]) if qrow is not None and p in qrow else 0
                for p in periods
            ],
        }
    return {"months": month_labels, "by_item": by_item}


def _onhand_sku_counts(location: str) -> Dict[str, Any]:
    """SKU counts for a location, computed the same way the rest of the app
    resolves locations (consolidated names), so the badge agrees with the
    tables beside it."""
    df_onhand = hf.GLOBAL_DF.get("onhand")
    df_whs = hf.GLOBAL_DF.get("whs_code")
    if df_onhand is None or df_whs is None or df_onhand.empty:
        return {"skus_with_onhand": 0, "total_onhand_units": 0}

    from app.utils.location_consolidation import add_consolidated_column

    whs = df_whs[["WhsCode", "WhsName"]].copy()
    whs["WhsCode"] = whs["WhsCode"].astype(str).str.strip()
    lookup = dict(zip(whs["WhsCode"], whs["WhsName"]))

    oh = df_onhand.copy()
    oh["WhsCode"] = oh["WhsCode"].astype(str).str.strip()
    oh = add_consolidated_column(oh, lookup)
    oh = oh[oh["ConsolidatedLocation"] == location]
    if oh.empty:
        return {"skus_with_onhand": 0, "total_onhand_units": 0}

    oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0)
    # Aggregate first: one SKU can sit in several sub-codes of the same
    # consolidated location, and must count once.
    per_item = oh.groupby("ItemCode")["OnHand"].sum()
    positive = per_item[per_item > 0]
    return {
        "skus_with_onhand": int(len(positive)),
        "total_onhand_units": int(positive.sum()),
    }


def _longest_common_prefix(codes: list) -> str:
    """Longest common prefix of a set of WhsCodes.

    The primary WhsCode is the base the GP-tier sub-codes extend: CSMTR for
    {CSMTR, CSMTRN30, CSMTRP20}; CCTR9 for {CCTR9N33, CCTR9P25} (owner-defined
    rule — the base "minus the extra N33/P25"). Note the base need not itself
    be a standalone WhsCode (CCTR9 isn't). LCP of a set == LCP of its lexical
    min and max.
    """
    if not codes:
        return ""
    lo, hi = min(codes), max(codes)
    i = 0
    while i < len(lo) and i < len(hi) and lo[i] == hi[i]:
        i += 1
    return lo[:i]


# Below this, a "common prefix" is too short to be a real store base — it means
# the group is heterogeneous (unrelated branches merged under one chain name,
# e.g. BookPlay / PagePoint / QuickMart). Such a primary is unsafe to auto-pick.
_MIN_BASE_LEN = 4


def _resolve_location_whs(location: str) -> Dict[str, Any]:
    """Map a consolidated shop to its WhsCodes and derive the primary base code.

    A shop consolidates several GP-tier sub-codes (Grandway has 11). WhsCode is
    the stable join key to on-hand/transfers; the location NAME is a mutable
    display string. The primary = the longest common prefix of the codes (the
    store base). When that prefix is too short the group is heterogeneous
    (different branches wrongly merged under one chain name); we flag it rather
    than guess.
    """
    df_whs = hf.GLOBAL_DF.get("whs_code")
    df_onhand = hf.GLOBAL_DF.get("onhand")
    empty = {"whs_codes": [], "sub_codes": [], "default_primary": None, "heterogeneous": False}
    if df_whs is None or df_whs.empty:
        return empty

    from app.utils.location_consolidation import get_consolidated_name

    whs = df_whs[["WhsCode", "WhsName"]].copy()
    whs["WhsCode"] = whs["WhsCode"].astype(str).str.strip()
    lookup = dict(zip(whs["WhsCode"], whs["WhsName"]))
    whs["cons"] = whs["WhsCode"].map(lambda c: get_consolidated_name(c, lookup))
    codes = whs[whs["cons"] == location]["WhsCode"].tolist()
    if not codes:
        return empty

    onhand_by_code: Dict[str, int] = {c: 0 for c in codes}
    if df_onhand is not None and not df_onhand.empty:
        oh = df_onhand[["WhsCode", "OnHand"]].copy()
        oh["WhsCode"] = oh["WhsCode"].astype(str).str.strip()
        oh = oh[oh["WhsCode"].isin(codes)]
        oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0)
        for code, units in oh.groupby("WhsCode")["OnHand"].sum().items():
            onhand_by_code[code] = int(units)

    # Primary = the common base the sub-codes extend (owner rule). A single-code
    # location's base is that code itself.
    base = _longest_common_prefix(codes)
    heterogeneous = len(base) < _MIN_BASE_LEN
    if heterogeneous:
        # Unrelated branches merged under one chain name (BookPlay / PagePoint /
        # QuickMart). No trustworthy base — leave it for a human / the pending
        # consolidation split rather than store a bogus "C".
        default_primary = None
    else:
        default_primary = base

    sub_codes = [
        {"whs_code": c, "whs_name": str(lookup.get(c, "")), "onhand_units": onhand_by_code.get(c, 0)}
        for c in sorted(codes, key=lambda c: (len(c), c))  # base-like first
    ]
    return {
        "whs_codes": codes,
        "sub_codes": sub_codes,
        "default_primary": default_primary,
        "base_prefix": base,
        "heterogeneous": heterogeneous,
    }


def _active_master_items(df_item_master) -> Dict[str, Dict[str, str]]:
    """{ItemCode: {name, brand}} for every active, valid Item Master SKU — the
    universe the planogram mirrors so any current product is settable."""
    out: Dict[str, Dict[str, str]] = {}
    dm = df_item_master
    if dm is None or getattr(dm, "empty", True):
        return out
    sub = dm
    if "validFor" in dm.columns:
        sub = sub[sub["validFor"].astype(str).str.upper() == "Y"]
    if "frozenFor" in dm.columns:
        sub = sub[sub["frozenFor"].astype(str).str.upper() != "Y"]
    for _, r in sub.iterrows():
        code = str(r.get("ItemCode", "") or "").strip()
        if not code:
            continue
        out[code] = {
            "name": str(r.get("ItemName", "") or ""),
            "brand": str(r.get("GroupName", "") or ""),
        }
    return out


@router.get("/location_planogram", summary="Planogram minimums + catalog SKUs for a location")
def get_location_planogram(
    location: str = Query(..., min_length=1),
    year: Optional[int] = Query(default=None),
    top_n: int = Query(default=100, ge=1, le=500),
    window_days: int = Query(default=90, ge=7, le=365),
    all_items: bool = Query(default=True),
    months_range: str = Query(default="3m", pattern="^(3m|year|2y)$"),
) -> Dict[str, Any]:
    """The SKUs at this location, each carrying its saved planogram minimum
    (0 when unset). With ``all_items`` (default) every active Item Master SKU
    appears — the planogram mirrors the live catalog, so any current product is
    settable even if it never sold here — sorted performers first. With
    ``all_items=false`` only the location's top-N sellers are returned."""
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if any(x is None for x in (df_raw_sale, df_raw_onhand, df_item_master, df_whs_code)):
        raise HTTPException(status_code=503, detail="Data not ready yet")

    # Mirror mode: a large cap so mix returns every item with activity here; the
    # full universe is then taken from the Item Master below.
    mix_top_n = 100_000 if all_items else top_n
    mix = la.compute_location_product_mix(
        df_raw_sale, df_raw_onhand, df_item_master, df_whs_code,
        location=location, year=year, top_n=mix_top_n, window_days=window_days,
        df_tr_in=hf.GLOBAL_DF.get("tr_in"),
        df_grpo_detail=hf.GLOBAL_DF.get("grpo_detail"),
    )
    mix_by_code = {it["item_code"]: it for it in mix.get("top_items", [])}

    saved = pp.load(location)
    whs = _resolve_location_whs(location)
    # Primary is rule-derived (the common base prefix), so it is always recomputed
    # rather than read from storage — no manual override.
    primary = whs["default_primary"]

    extra = _velocity_and_recent_months(location, window_days=window_days, months_range=months_range)
    by_item = extra["by_item"]
    months = extra["months"]

    active_master = _active_master_items(df_item_master)
    # Union in mix + saved codes so nothing already relevant is ever hidden.
    if all_items:
        universe = set(active_master) | set(mix_by_code) | set(saved)
    else:
        universe = set(mix_by_code) | set(saved)

    items = []
    for code in universe:
        m = mix_by_code.get(code, {})
        ex = by_item.get(code, {})
        meta = active_master.get(code, {})
        items.append({
            "item_code": code,
            "item_name": m.get("item_name") or meta.get("name", ""),
            "brand": m.get("brand") or meta.get("brand", ""),
            "sold_thb": m.get("sold_thb", 0),
            "sold_master_thb": m.get("sold_master_thb", 0),
            "sold_qty": m.get("sold_qty", 0),
            "onhand_qty": m.get("onhand_qty", 0),
            "onhand_thb": m.get("onhand_thb", 0),
            "monthly_velocity": ex.get("velocity", 0.0),
            "month_revenue": ex.get("month_revenue", [0.0] * len(months)),
            "month_qty": ex.get("month_qty", [0] * len(months)),
            "min_qty": int(saved.get(code, 0)),
            "is_set": code in saved,
            "in_master": code in active_master,
        })
    # Performers first, then items with a set minimum, then the rest by code.
    items.sort(key=lambda i: (-(i["sold_master_thb"] or 0), not i["is_set"], i["item_code"]))
    for rank, it in enumerate(items, start=1):
        it["rank"] = rank

    counts = _onhand_sku_counts(location)
    return {
        "location": location,
        "year": year,
        "ranked_by": "Revenue (THB, Actual) at this location",
        "all_items": all_items,
        "catalog_size": len(active_master),
        "top_n": top_n,
        "months_range": months_range,
        "months": months,
        "velocity_window_days": window_days,
        "items": items,
        "whs_mapping": {
            "primary_whs_code": primary,           # the common base prefix; None if heterogeneous
            "base_prefix": whs.get("base_prefix"),
            "heterogeneous": whs.get("heterogeneous", False),
            "sub_codes": whs["sub_codes"],         # each: whs_code, whs_name, onhand_units
        },
        "summary": {
            **counts,
            "skus_shown": len(items),
            "skus_with_planogram": sum(1 for i in items if i["is_set"]),
            "planogram_total_units": sum(i["min_qty"] for i in items),
        },
        "storage_available": pp.is_available(),
    }


@router.get("/planogram_locations", summary="Locations that have a planogram (Master Con set)")
def get_planogram_locations() -> Dict[str, Any]:
    """The definitive set of locations that have a planogram — the Master Con
    locations. The locations list UI uses this to show the Planogram button
    only for these (whitespace-normalized so spacing variants still match)."""
    ids = pp.all_location_ids()
    return {
        "locations": ids,
        "normalized": [pp._norm_id(x) for x in ids],
        "count": len(ids),
    }


@router.get("/all_planograms", summary="All-locations planogram matrix (Master Con view)")
def get_all_planograms(
    brand: Optional[str] = Query(default=None),
    all_brands: bool = Query(default=False),
) -> Dict[str, Any]:
    """The full SKU x location minimum-quantity matrix from the planogram
    collection — mirroring the Master Con sheet. Locations are the columns
    (ordered as in the sheet); each SKU row carries its per-location minimums.

    ``brand`` filters the SKU rows (the grid is large, so the UI picks a brand).
    ``locations`` and ``brands`` are always returned so the filters can render.
    """
    docs = pp.load_all()

    # Columns: one per planogram location, ordered by the sheet's column order.
    locations = sorted(
        [
            {
                "location": d["_id"],
                "primary_whs_code": d.get("primary_whs_code"),
                "grade": d.get("grade"),
                "channel": d.get("channel"),
                "order": d.get("order", 9999),
            }
            for d in docs
        ],
        key=lambda x: x["order"],
    )

    # Invert to per-item: item -> {location: min_qty}
    per_item: Dict[str, Dict[str, int]] = {}
    for d in docs:
        loc = d["_id"]
        for code, v in (d.get("items") or {}).items():
            per_item.setdefault(code, {})[loc] = int(v.get("min_qty", 0))

    # Item master for brand / name / price
    master = hf.GLOBAL_DF.get("master")
    meta: Dict[str, Dict[str, Any]] = {}
    if master is not None and not master.empty:
        m = master.copy()
        m["ItemCode"] = m["ItemCode"].astype(str).str.strip()
        for _, r in m.iterrows():
            meta[r["ItemCode"]] = {
                "brand": str(r.get("GroupName", "")),
                "item_name": str(r.get("ItemName", "")),
                "price": float(r["Price"]) if pd.notna(r.get("Price")) else None,
            }

    # Brand list (only brands that actually have planogram SKUs)
    brand_counts: Dict[str, int] = {}
    for code in per_item:
        b = meta.get(code, {}).get("brand", "") or "(no brand)"
        brand_counts[b] = brand_counts.get(b, 0) + 1
    brands = sorted(
        [{"brand": b, "sku_count": n} for b, n in brand_counts.items()],
        key=lambda x: -x["sku_count"],
    )

    # On-hand for the refill view: D1 warehouse supply (WhsCode "D1" — the main
    # warehouse, NOT D1-SL online / D1-DEM demo), company-wide total, and per
    # planogram-location on-hand. Only computed when rows are actually returned.
    onhand_d1: Dict[str, int] = {}
    onhand_total: Dict[str, int] = {}
    onhand_loc: Dict[str, Dict[str, int]] = {}
    if (brand or all_brands):
        oh = hf.GLOBAL_DF.get("onhand")
        whs = hf.GLOBAL_DF.get("whs_code")
        if oh is not None and not oh.empty and whs is not None:
            o = oh[["ItemCode", "WhsCode", "OnHand"]].copy()
            o["ItemCode"] = o["ItemCode"].astype(str).str.strip()
            o["WhsCode"] = o["WhsCode"].astype(str).str.strip()
            o["OnHand"] = pd.to_numeric(o["OnHand"], errors="coerce").fillna(0)
            onhand_total = o.groupby("ItemCode")["OnHand"].sum().astype(int).to_dict()
            onhand_d1 = (
                o[o["WhsCode"] == "D1"].groupby("ItemCode")["OnHand"].sum().astype(int).to_dict()
            )
            lookup = dict(zip(
                whs["WhsCode"].astype(str).str.strip(),
                whs["WhsName"].fillna("").astype(str),
            ))
            o = add_consolidated_column(o, lookup)
            plocs = {d["_id"] for d in docs}
            o = o[o["ConsolidatedLocation"].isin(plocs)]
            for (code, loc), v in o.groupby(["ItemCode", "ConsolidatedLocation"])["OnHand"].sum().items():
                onhand_loc.setdefault(str(code), {})[loc] = int(v)

    # SKU rows (filtered by brand when given)
    items = []
    for code, mins in per_item.items():
        info = meta.get(code, {})
        b = info.get("brand", "") or "(no brand)"
        if brand and b != brand:
            continue
        items.append({
            "item_code": code,
            "brand": b,
            "item_name": info.get("item_name", ""),
            "price": info.get("price"),
            "mins": mins,
            "total_min": sum(mins.values()),
            "onhand_d1": int(onhand_d1.get(code, 0)),
            "onhand_total": int(onhand_total.get(code, 0)),
            "onhand_by_loc": onhand_loc.get(code, {}),
        })
    items.sort(key=lambda x: -x["total_min"])

    return {
        "locations": locations,
        "brands": brands,
        "brand": brand,
        # Require a brand pick by default — the full set is huge — but honour an
        # explicit all_brands=true (the "All brands" option) to return everything.
        "items": items if (brand or all_brands) else [],
        "total_skus": len(per_item),
    }


@router.put("/all_planograms", summary="Batch-save grid edits across locations")
def put_all_planograms(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Merge grid edits: ``{"changes": {location: {item_code: min_qty}}}``.

    Each location is a merge (only the edited cells), so untouched minimums are
    preserved. Resolves and re-stamps the WhsCode mapping per location.
    """
    if not pp.is_available():
        raise HTTPException(status_code=503, detail="MongoDB is not configured.")

    changes = body.get("changes", {})
    if not isinstance(changes, dict) or not changes:
        raise HTTPException(status_code=422, detail="Body must be {'changes': {location: {item: qty}}}.")

    saved_locations = 0
    saved_cells = 0
    for location, items in changes.items():
        if not isinstance(items, dict) or not items:
            continue
        whs = _resolve_location_whs(location)
        try:
            pp.save(
                location, items, updated_by=body.get("updated_by"),
                whs_codes=whs["whs_codes"] or None,
                primary_whs_code=whs["default_primary"],
                primary_source="heterogeneous" if whs.get("heterogeneous") else "base_prefix",
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"{location}: {e}")
        saved_locations += 1
        saved_cells += len(items)

    return {"status": "ok", "locations_saved": saved_locations, "cells_saved": saved_cells}


@router.put("/location_planogram", summary="Save planogram minimums for a location")
def put_location_planogram(
    location: str = Query(..., min_length=1),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """Merge ``{"items": {item_code: min_qty}}`` into this location's planogram.

    A merge, not a replace — the UI only ever sends the SKUs it is showing.
    The WhsCode mapping (all sub-codes + the rule-derived primary base) is
    resolved fresh and persisted as the join key.
    """
    if not pp.is_available():
        raise HTTPException(
            status_code=503,
            detail="MongoDB is not configured, so planogram settings cannot be saved.",
        )

    whs = _resolve_location_whs(location)
    primary = whs["default_primary"]  # common base prefix; None when heterogeneous

    try:
        saved = pp.save(
            location, body.get("items", {}), updated_by=body.get("updated_by"),
            whs_codes=whs["whs_codes"] or None,
            primary_whs_code=primary,
            primary_source="heterogeneous" if whs.get("heterogeneous") else "base_prefix",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {
        "status": "ok", "location": location, "items_saved": len(saved),
        "items": saved, "primary_whs_code": primary,
        "heterogeneous": whs.get("heterogeneous", False),
        "whs_codes": whs["whs_codes"],
    }
