"""
Brand recovery for items missing from the Item Master.

The Item Master has GroupName (= product brand) for its 1,062 items. But
1,902 items in OnHand and 2,311+ items with sales history are missing from
the master and therefore have no brand attribution — they show as "Unknown".

This module provides build_brand_map() — a dict ItemCode -> brand — using
this tiered fallback strategy:

  Tier 1 (authoritative): Item Master.GroupName
  Tier 2 (high-confidence): Sale.Brand per item (taking the mode across rows)
  Tier 3 (inference):      Item code prefix mapping (prefix -> brand)

Tier 1 is never overridden. Tier 2 kicks in for items absent from the master
but with Brand populated on their sales lines. Tier 3 is inference-based and
used only when the first two produce nothing.

The prefix map is derived empirically from Item Master items that DO have
both ItemCode and GroupName — prefixes with >=80% brand purity.
"""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd


# Item-code prefix -> brand, for Tier-3 inference of items that are missing from
# the Item Master. In this anonymized demo the Item Master coverage is complete
# (every item carries a brand via Tier-1/Tier-2), so Tier-3 never fires; the
# prefix map is intentionally empty here.
PREFIX_TO_BRAND: dict[str, str] = {}


_PREFIX_RE = re.compile(r"^([A-Z]+)")


# Per-process cache of the Sale-derived brand map (mode per ItemCode).
# Keyed by (nrows, min_date, max_date) which is stable across DataFrame copies.
_SALE_BRAND_CACHE: dict[tuple, pd.Series] = {}


def _brand_cache_key(df_sale: pd.DataFrame) -> Optional[tuple]:
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


def _sale_brand_map(df_sale: pd.DataFrame) -> pd.Series:
    """Return ItemCode -> brand (most common brand per item on Sale rows).

    Cached by shape + date range of the sale DataFrame so repeated calls
    within a single request don't rescan 600K+ rows.
    """
    key = _brand_cache_key(df_sale)
    if key is not None:
        cached = _SALE_BRAND_CACHE.get(key)
        if cached is not None:
            return cached
    if df_sale is None or df_sale.empty or "Brand" not in df_sale.columns:
        result = pd.Series(dtype=object)
    else:
        s = df_sale[["ItemCode", "Brand"]].copy()
        s["ItemCode"] = s["ItemCode"].astype(str).str.strip()
        s["Brand"] = s["Brand"].astype(str).str.strip()
        s = s[s["Brand"].notna() & (s["Brand"] != "") & (s["Brand"].str.lower() != "nan")]
        if s.empty:
            result = pd.Series(dtype=object)
        else:
            counts = s.groupby(["ItemCode", "Brand"]).size().reset_index(name="n")
            counts = counts.sort_values(["ItemCode", "n"], ascending=[True, False])
            result = counts.drop_duplicates("ItemCode").set_index("ItemCode")["Brand"]
    if key is not None:
        _SALE_BRAND_CACHE[key] = result
        if len(_SALE_BRAND_CACHE) > 4:
            for k in list(_SALE_BRAND_CACHE.keys())[:-4]:
                _SALE_BRAND_CACHE.pop(k, None)
    return result


def _extract_prefix(code: str) -> str:
    """Extract the leading letter prefix from an ItemCode (e.g. 'SV88651' -> 'SV')."""
    if not code:
        return ""
    m = _PREFIX_RE.match(str(code).upper())
    return m.group(1) if m else ""


def _longest_prefix_match(code: str) -> Optional[str]:
    """Return the brand for the longest matching prefix in PREFIX_TO_BRAND."""
    if not code:
        return None
    up = str(code).upper()
    for length in range(min(len(up), 8), 0, -1):
        p = up[:length]
        if p in PREFIX_TO_BRAND:
            return PREFIX_TO_BRAND[p]
    return None


def build_brand_map(
    df_item_master: pd.DataFrame,
    df_sale: Optional[pd.DataFrame] = None,
    all_item_codes: Optional[pd.Series] = None,
) -> pd.Series:
    """Return Series ItemCode -> brand, with fallbacks.

    Parameters
    ----------
    df_item_master : DataFrame with columns ItemCode, GroupName (brand).
    df_sale : DataFrame with columns ItemCode, Brand. Optional fallback.
    all_item_codes : Optional Series of all ItemCodes to include. If given,
        prefix inference is applied to codes not covered by the other tiers.

    Returns
    -------
    Series indexed by ItemCode (str), value = brand name (or NaN if unknown).
    """
    # --- Tier 1: Item Master ---
    if df_item_master is None or df_item_master.empty or "GroupName" not in df_item_master.columns:
        master_map = pd.Series(dtype=object)
    else:
        mm = df_item_master[["ItemCode", "GroupName"]].copy()
        mm["ItemCode"] = mm["ItemCode"].astype(str).str.strip()
        mm["GroupName"] = mm["GroupName"].astype(str).str.strip()
        mm = mm[mm["GroupName"].notna() & (mm["GroupName"] != "") & (mm["GroupName"].str.lower() != "nan")]
        master_map = mm.drop_duplicates("ItemCode").set_index("ItemCode")["GroupName"]

    combined = master_map.copy()

    # --- Tier 2: Sale.Brand for items not in master ---
    # Uses the module-level _sale_brand_map cache so we don't rescan the
    # full 600K+ sale dataset on every request.
    if df_sale is not None and "Brand" in df_sale.columns:
        sale_brand = _sale_brand_map(df_sale)
        if not sale_brand.empty:
            missing = sale_brand.index.difference(combined.index)
            if len(missing) > 0:
                combined = pd.concat([combined, sale_brand.loc[missing]])

    # --- Tier 3: Prefix inference for any remaining items ---
    # Vectorized: collect all new (code, brand) pairs, concat once. Previously
    # we did `combined.loc[code] = inferred` in a Python loop which reallocates
    # the Series index each iteration (quadratic).
    if all_item_codes is not None:
        codes = pd.Series(all_item_codes).astype(str).str.strip().unique()
        covered = set(combined.index.astype(str))
        new_items: dict[str, str] = {}
        for code in codes:
            if code and code not in covered and code not in new_items:
                inferred = _longest_prefix_match(code)
                if inferred:
                    new_items[code] = inferred
        if new_items:
            combined = pd.concat([
                combined,
                pd.Series(new_items, dtype=object),
            ])

    combined.index = combined.index.astype(str)
    return combined


def build_brand_map_with_provenance(
    df_item_master: pd.DataFrame,
    df_sale: Optional[pd.DataFrame] = None,
    all_item_codes: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Like build_brand_map but also returns the source tier per item.

    Returns DataFrame [ItemCode, brand, source] where source is one of
    'master', 'sale', 'prefix', or 'unknown'.
    """
    rows = []
    covered = set()

    if df_item_master is not None and "GroupName" in df_item_master.columns:
        mm = df_item_master[["ItemCode", "GroupName"]].copy()
        mm["ItemCode"] = mm["ItemCode"].astype(str).str.strip()
        mm["GroupName"] = mm["GroupName"].astype(str).str.strip()
        mm = mm[mm["GroupName"].notna() & (mm["GroupName"] != "") & (mm["GroupName"].str.lower() != "nan")]
        mm = mm.drop_duplicates("ItemCode")
        for _, r in mm.iterrows():
            rows.append({"ItemCode": r["ItemCode"], "brand": r["GroupName"], "source": "master"})
            covered.add(r["ItemCode"])

    if df_sale is not None and "Brand" in df_sale.columns:
        s = df_sale[["ItemCode", "Brand"]].copy()
        s["ItemCode"] = s["ItemCode"].astype(str).str.strip()
        s["Brand"] = s["Brand"].astype(str).str.strip()
        s = s[s["Brand"].notna() & (s["Brand"] != "") & (s["Brand"].str.lower() != "nan")]
        if not s.empty:
            # Vectorized mode per item (pick brand with largest count)
            counts = s.groupby(["ItemCode", "Brand"]).size().reset_index(name="n")
            counts = counts.sort_values(["ItemCode", "n"], ascending=[True, False])
            sale_brand = counts.drop_duplicates("ItemCode").set_index("ItemCode")["Brand"]
            for code, brand in sale_brand.items():
                if code not in covered:
                    rows.append({"ItemCode": code, "brand": brand, "source": "sale"})
                    covered.add(code)

    if all_item_codes is not None:
        for code in pd.Series(all_item_codes).astype(str).str.strip().unique():
            if code and code not in covered:
                inferred = _longest_prefix_match(code)
                if inferred:
                    rows.append({"ItemCode": code, "brand": inferred, "source": "prefix"})
                    covered.add(code)
                else:
                    rows.append({"ItemCode": code, "brand": "Unknown", "source": "unknown"})

    return pd.DataFrame(rows)
