"""Planogram (PAR) settings — minimum units per SKU on shelf, per location.

This is the first APP-OWNED writable data in MongoDB. Everything else the app
serves mirrors the SAP export (parsed from the Excel workbook); this collection
is authored by users and must never be overwritten by a data refresh.

    SAP-mirrored (sale, onhand, tr_in, …)  →  rebuilt from Excel
    planogram (this module)                →  authored by humans, never synced

Storage: one document per consolidated location, in the `toyvaultdemo` database.

    {
      "_id":       "Heritage Mall",         # consolidated location name
      "location":  "Heritage Mall",
      "items":     { "SV20675": {"min_qty": 6, "updated_at": ..., "updated_by": ...} },
      "updated_at": ...,
      "updated_by": "user@toyvault"
    }

Keyed by ItemCode inside one document rather than a document per (location,
item) because a planogram is read and written as a whole page — one round trip
instead of 100, and a location's settings are naturally atomic.

WHY min_qty ALONE IS ENOUGH FOR NOW
-----------------------------------
The simplest coherent model — "keep at least N units on the shelf; when it
drops below, top back up to N" — makes the refill target equal the minimum. The
storage shape is a per-item dict, so a `par_qty` key can be added later with no
migration.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

COLLECTION = "planogram"

# Sanity bounds for a shelf minimum. Rejecting absurd values here stops a typo
# ("600" instead of "6") from driving a 100x transfer request downstream.
MAX_MIN_QTY = 10_000


def _collection():
    """Return the planogram collection, or None when Mongo is unconfigured."""
    from app.utils import mongo_store as ms

    db = ms.get_db()
    if db is None:
        return None
    return db[COLLECTION]


def is_available() -> bool:
    return _collection() is not None


# ---------------------------------------------------------------------------
# Validation (pure — unit-tested without Mongo)
# ---------------------------------------------------------------------------

def validate_items(items: Any) -> Dict[str, int]:
    """Validate an ``{item_code: min_qty}`` payload.

    Returns the cleaned mapping. Raises ValueError with a specific message so
    the API can surface it as a 422. A ``min_qty`` of 0 is legitimate — it
    means "stock nothing here" — and is stored rather than dropped, because
    that is a deliberate decision worth persisting.
    """
    if not isinstance(items, dict):
        raise ValueError("items must be an object mapping item_code -> min_qty")

    cleaned: Dict[str, int] = {}
    for code, qty in items.items():
        if not isinstance(code, str) or not code.strip():
            raise ValueError(f"invalid item code: {code!r}")
        if isinstance(qty, bool) or not isinstance(qty, (int, float)):
            raise ValueError(f"min_qty for {code} must be a number, got {qty!r}")
        if qty != int(qty):
            raise ValueError(f"min_qty for {code} must be a whole number, got {qty}")
        qty = int(qty)
        if qty < 0:
            raise ValueError(f"min_qty for {code} must be >= 0, got {qty}")
        if qty > MAX_MIN_QTY:
            raise ValueError(
                f"min_qty for {code} is {qty:,}, above the {MAX_MIN_QTY:,} limit — "
                "this looks like a typo"
            )
        cleaned[code.strip()] = qty
    return cleaned


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def _norm_id(s: str) -> str:
    """Whitespace-insensitive, lowercased location key. SAP WhsNames vary in
    spacing across a store's sub-codes ("CT-ZEN" vs "CT- ZEN"), so consolidated
    names occasionally differ by whitespace between the planogram doc and the
    locations page. Normalizing lets lookups still line up."""
    return re.sub(r"\s+", "", str(s or "")).lower()


def resolve_id(location: str) -> Optional[str]:
    """The actual stored planogram _id for a location: exact match, else a
    whitespace-normalized match. Returns the requested name if none exists."""
    coll = _collection()
    if coll is None:
        return None
    if coll.find_one({"_id": location}, {"_id": 1}):
        return location
    target = _norm_id(location)
    for d in coll.find({}, {"_id": 1}):
        if _norm_id(d["_id"]) == target:
            return d["_id"]
    return location


def all_location_ids() -> list:
    """Every location that has a planogram — the definitive set (Master Con)."""
    coll = _collection()
    if coll is None:
        return []
    return [d["_id"] for d in coll.find({}, {"_id": 1})]


def load(location: str) -> Dict[str, int]:
    """Return ``{item_code: min_qty}`` for a location. Empty when unset."""
    coll = _collection()
    if coll is None:
        return {}
    doc = coll.find_one({"_id": resolve_id(location)})
    if not doc:
        return {}
    return {code: int(v.get("min_qty", 0)) for code, v in (doc.get("items") or {}).items()}


def load_full(location: str) -> Optional[dict]:
    """Return the whole stored document (items + WhsCode mapping), or None."""
    coll = _collection()
    if coll is None:
        return None
    return coll.find_one({"_id": resolve_id(location)})


def load_all() -> list:
    """Every planogram document — for the all-locations grid."""
    coll = _collection()
    if coll is None:
        return []
    return list(coll.find({}))


def save(
    location: str,
    items: Dict[str, int],
    updated_by: Optional[str] = None,
    *,
    whs_codes: Optional[list] = None,
    primary_whs_code: Optional[str] = None,
    primary_source: Optional[str] = None,
) -> Dict[str, int]:
    """Merge ``items`` into a location's planogram and return the full result.

    A MERGE, not a replace: the UI shows the top 100 SKUs, so a save carries
    only those. Replacing would silently delete settings for any SKU that has
    since dropped out of the top 100 — losing a deliberate human decision
    because sales moved. Send an explicit 0 to zero something out.

    ``whs_codes`` / ``primary_whs_code`` persist the WhsCode mapping. A shop
    consolidates several GP-tier sub-codes; WhsCode is the stable join key to
    on-hand / transfers (the location NAME is a mutable display string), and
    ``primary_whs_code`` is the sub-code a refill transfer ships into.
    ``primary_source`` is "manual" when a human picked it, "auto" when defaulted
    — the route uses it so an auto-refresh never clobbers a manual choice.
    """
    cleaned = validate_items(items)
    coll = _collection()
    if coll is None:
        raise RuntimeError("MongoDB is not configured; cannot save planogram")

    now = datetime.now(timezone.utc)
    updates = {
        f"items.{code}": {"min_qty": qty, "updated_at": now, "updated_by": updated_by}
        for code, qty in cleaned.items()
    }
    updates["location"] = location
    updates["updated_at"] = now
    updates["updated_by"] = updated_by
    if whs_codes is not None:
        updates["whs_codes"] = list(whs_codes)
    if primary_whs_code is not None:
        updates["primary_whs_code"] = primary_whs_code
    if primary_source is not None:
        updates["primary_source"] = primary_source

    # Write to the existing doc even if its stored _id differs only in spacing,
    # so an edit never spawns a duplicate location.
    coll.update_one({"_id": resolve_id(location)}, {"$set": updates}, upsert=True)
    logger.info(
        "planogram %s: saved %d item(s), primary_whs=%s",
        location, len(cleaned), primary_whs_code,
    )
    return load(location)


def replace_location(
    location: str,
    items: Dict[str, int],
    *,
    whs_codes: Optional[list] = None,
    primary_whs_code: Optional[str] = None,
    primary_source: Optional[str] = None,
    source: Optional[str] = None,
    meta: Optional[dict] = None,
) -> int:
    """REPLACE a location's entire item map (not a merge) — used by the
    Master Con default-values import, where the imported sheet is the baseline
    and should overwrite whatever items were stored for that location.

    Unlike ``save`` (which $sets dotted item keys and preserves the rest), this
    writes the whole ``items`` object. Returns the number of items written.
    """
    cleaned = validate_items(items)
    coll = _collection()
    if coll is None:
        raise RuntimeError("MongoDB is not configured; cannot import planogram")

    now = datetime.now(timezone.utc)
    doc = {
        "location": location,
        "items": {code: {"min_qty": qty, "updated_at": now, "source": source or "import"}
                  for code, qty in cleaned.items()},
        "updated_at": now,
        "source": source or "import",
    }
    if whs_codes is not None:
        doc["whs_codes"] = list(whs_codes)
    if primary_whs_code is not None:
        doc["primary_whs_code"] = primary_whs_code
    if primary_source is not None:
        doc["primary_source"] = primary_source
    if meta:
        # Display metadata from the source sheet (grade, channel, column order)
        # so an all-locations grid can mirror the sheet's column layout.
        doc.update({k: meta[k] for k in ("grade", "channel", "order") if k in meta})

    coll.replace_one({"_id": location}, {"_id": location, **doc}, upsert=True)
    return len(cleaned)


def clear_item(location: str, item_code: str) -> None:
    """Remove one item's setting entirely (distinct from setting it to 0)."""
    coll = _collection()
    if coll is None:
        return
    coll.update_one({"_id": location}, {"$unset": {f"items.{item_code}": ""}})


def summary() -> Dict[str, Any]:
    """Counts across all locations — for an overview badge."""
    coll = _collection()
    if coll is None:
        return {"locations": 0, "items": 0}
    locations = 0
    items = 0
    for doc in coll.find({}, {"items": 1}):
        locations += 1
        items += len(doc.get("items") or {})
    return {"locations": locations, "items": items}
