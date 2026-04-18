"""
Master price recovery for items missing from the Item Master.

The Item Master currently contains ~1,062 items, but the OnHand sheet has
2,937 unique items and sales history touches 2,311+ items. That means
~64.8% of on-hand items (461,878 units) have no master price, and every
dashboard that values inventory or revenue at Master Price under-counts
them at THB 0.

This module provides a single helper — build_master_price_map() — that
returns a dict ItemCode -> unit master price, filling gaps in the Item
Master with fallbacks from the Sale sheet's "Price Master" column and
(as a last resort) GRPO FOB costs.

Design:
  Tier 1 (authoritative): Item Master.Price  — real list price
  Tier 2 (fallback):       Sale.Price Master / Quantity  (derived unit price)
  Tier 3 (last resort):    GRPO Price x Rate x 2.5  (approximate 2.5x markup
                            over import cost, used only when no sale history)

Tier 1 is always preferred. Tier 2 and Tier 3 kick in ONLY for items that
are absent from the Item Master — they do NOT override the master for
items that already have a price.

Example usage:
    price_map = build_master_price_map(df_item_master, df_sale)
    df_onhand["Master Price"] = df_onhand["ItemCode"].map(price_map).fillna(0)
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


# Per-process cache of the Sale-derived unit master price map.
# Keyed by (nrows, min_date, max_date) which is stable across DataFrame copies
# but changes whenever the Sale frame is reloaded.
_SALE_MP_CACHE: dict[tuple, pd.Series] = {}


def _cache_key_for(df_sale: pd.DataFrame) -> Optional[tuple]:
    """Build a stable cache key for a sale DataFrame — survives .copy()."""
    if df_sale is None or df_sale.empty:
        return None
    n = len(df_sale)
    try:
        if "DocDate" in df_sale.columns:
            d = pd.to_datetime(df_sale["DocDate"], errors="coerce")
            return (n, d.min(), d.max())
    except Exception:
        pass
    return (n,)


def _sale_unit_master_price_map(df_sale: pd.DataFrame) -> pd.Series:
    """Return ItemCode -> unit master price derived from Sale.Price Master.

    Cached by shape + date range of the input so we don't rescan 600K+ rows
    on every request, even though upstream code calls .copy() on the frame.
    """
    key = _cache_key_for(df_sale)
    if key is not None:
        cached = _SALE_MP_CACHE.get(key)
        if cached is not None:
            return cached
    if df_sale is None or df_sale.empty or "Price Master" not in df_sale.columns:
        result = pd.Series(dtype=float)
    else:
        s = df_sale[["ItemCode", "Price Master", "Quantity"]].copy()
        s["ItemCode"] = s["ItemCode"].astype(str).str.strip()
        s["Price Master"] = pd.to_numeric(s["Price Master"], errors="coerce")
        s["Quantity"] = pd.to_numeric(s["Quantity"], errors="coerce")
        s = s[(s["Price Master"] > 0) & (s["Quantity"] > 0)]
        if s.empty:
            result = pd.Series(dtype=float)
        else:
            s["unit_mp"] = s["Price Master"] / s["Quantity"]
            result = s.groupby("ItemCode")["unit_mp"].mean()
    if key is not None:
        _SALE_MP_CACHE[key] = result
        if len(_SALE_MP_CACHE) > 4:
            for k in list(_SALE_MP_CACHE.keys())[:-4]:
                _SALE_MP_CACHE.pop(k, None)
    return result


def build_master_price_map(
    df_item_master: pd.DataFrame,
    df_sale: Optional[pd.DataFrame] = None,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    grpo_markup: float = 2.5,
) -> pd.Series:
    """Return a Series ItemCode -> unit master price, using fallbacks for
    items missing from the Item Master.

    Parameters
    ----------
    df_item_master : DataFrame
        Must have columns ItemCode, Price. Authoritative source.
    df_sale : DataFrame, optional
        Must have columns ItemCode, Price Master, Quantity. Used to derive
        unit master price for items not in Item Master.
    df_grpo_detail : DataFrame, optional
        Must have columns ItemCode, Price, Rate. Used as last resort —
        import cost x markup.
    grpo_markup : float
        Multiplier applied to FOB cost to approximate master price. Default 2.5.

    Returns
    -------
    Series indexed by ItemCode (str) with float unit master prices.
    """
    # --- Tier 1: Item Master (authoritative) ---
    if df_item_master is None or df_item_master.empty or "Price" not in df_item_master.columns:
        master_map = pd.Series(dtype=float)
    else:
        mm = df_item_master[["ItemCode", "Price"]].dropna(subset=["ItemCode"]).copy()
        mm["ItemCode"] = mm["ItemCode"].astype(str).str.strip()
        mm["Price"] = pd.to_numeric(mm["Price"], errors="coerce")
        mm = mm[mm["Price"].notna() & (mm["Price"] > 0)]
        master_map = mm.drop_duplicates("ItemCode").set_index("ItemCode")["Price"]

    # --- Tier 2: Sale-derived unit master price (Price Master / Quantity) ---
    sale_map = pd.Series(dtype=float)
    if df_sale is not None and not df_sale.empty and "Price Master" in df_sale.columns:
        s = df_sale[["ItemCode", "Price Master", "Quantity"]].copy()
        s["ItemCode"] = s["ItemCode"].astype(str).str.strip()
        s["Price Master"] = pd.to_numeric(s["Price Master"], errors="coerce")
        s["Quantity"] = pd.to_numeric(s["Quantity"], errors="coerce")
        s = s[(s["Price Master"] > 0) & (s["Quantity"] > 0)]
        if not s.empty:
            s["unit_mp"] = s["Price Master"] / s["Quantity"]
            # Average unit price per item (most items sell at one price)
            sale_map = s.groupby("ItemCode")["unit_mp"].mean()

    # --- Tier 3: GRPO FOB x markup ---
    grpo_map = pd.Series(dtype=float)
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        g = df_grpo_detail[["ItemCode", "Price", "Rate"]].copy()
        g["ItemCode"] = g["ItemCode"].astype(str).str.strip()
        g["Price"] = pd.to_numeric(g["Price"], errors="coerce")
        g["Rate"] = pd.to_numeric(g["Rate"], errors="coerce")
        g["fob_thb"] = g["Price"] * g["Rate"]
        g = g[g["fob_thb"] > 0]
        if not g.empty:
            grpo_map = g.groupby("ItemCode")["fob_thb"].mean() * grpo_markup

    # --- Combine: Master wins; then Sale; then GRPO ---
    # Only items missing from Master get filled by Sale; then Sale also missing
    # falls to GRPO. Items in Master are never overwritten.
    combined = master_map.copy()

    missing_from_master = sale_map.index.difference(combined.index)
    if len(missing_from_master) > 0:
        combined = pd.concat([combined, sale_map.loc[missing_from_master]])

    still_missing = grpo_map.index.difference(combined.index)
    if len(still_missing) > 0:
        combined = pd.concat([combined, grpo_map.loc[still_missing]])

    combined.index = combined.index.astype(str)
    return combined


def build_master_price_map_with_provenance(
    df_item_master: pd.DataFrame,
    df_sale: Optional[pd.DataFrame] = None,
    df_grpo_detail: Optional[pd.DataFrame] = None,
    grpo_markup: float = 2.5,
) -> pd.DataFrame:
    """Like build_master_price_map but also returns the source tier per item.

    Returns DataFrame with columns [ItemCode, price, source] where source is
    one of 'master', 'sale_derived', or 'grpo_fob'. Useful for data-quality
    dashboards that need to show exactly how many items rely on each tier.
    """
    mm = df_item_master[["ItemCode", "Price"]].copy() if (
        df_item_master is not None and "Price" in df_item_master.columns
    ) else pd.DataFrame(columns=["ItemCode", "Price"])
    mm["ItemCode"] = mm["ItemCode"].astype(str).str.strip()
    mm["Price"] = pd.to_numeric(mm["Price"], errors="coerce")
    mm = mm[mm["Price"].notna() & (mm["Price"] > 0)].drop_duplicates("ItemCode")
    master_rows = mm.rename(columns={"Price": "price"}).assign(source="master")

    # Sale-derived
    sale_rows = pd.DataFrame(columns=["ItemCode", "price", "source"])
    if df_sale is not None and "Price Master" in df_sale.columns:
        s = df_sale[["ItemCode", "Price Master", "Quantity"]].copy()
        s["ItemCode"] = s["ItemCode"].astype(str).str.strip()
        s["Price Master"] = pd.to_numeric(s["Price Master"], errors="coerce")
        s["Quantity"] = pd.to_numeric(s["Quantity"], errors="coerce")
        s = s[(s["Price Master"] > 0) & (s["Quantity"] > 0)]
        if not s.empty:
            s["unit_mp"] = s["Price Master"] / s["Quantity"]
            avg = s.groupby("ItemCode", as_index=False)["unit_mp"].mean()
            avg = avg.rename(columns={"unit_mp": "price"}).assign(source="sale_derived")
            # Only keep items not already in master
            avg = avg[~avg["ItemCode"].isin(master_rows["ItemCode"])]
            sale_rows = avg

    # GRPO
    grpo_rows = pd.DataFrame(columns=["ItemCode", "price", "source"])
    if df_grpo_detail is not None and not df_grpo_detail.empty:
        g = df_grpo_detail[["ItemCode", "Price", "Rate"]].copy()
        g["ItemCode"] = g["ItemCode"].astype(str).str.strip()
        g["Price"] = pd.to_numeric(g["Price"], errors="coerce")
        g["Rate"] = pd.to_numeric(g["Rate"], errors="coerce")
        g["fob_thb"] = g["Price"] * g["Rate"]
        g = g[g["fob_thb"] > 0]
        if not g.empty:
            avg = g.groupby("ItemCode", as_index=False)["fob_thb"].mean()
            avg["price"] = avg["fob_thb"] * grpo_markup
            avg = avg[["ItemCode", "price"]].assign(source="grpo_fob")
            # Only keep items not already covered
            have = set(master_rows["ItemCode"]) | set(sale_rows["ItemCode"])
            avg = avg[~avg["ItemCode"].isin(have)]
            grpo_rows = avg

    out = pd.concat([master_rows, sale_rows, grpo_rows], ignore_index=True)
    return out
