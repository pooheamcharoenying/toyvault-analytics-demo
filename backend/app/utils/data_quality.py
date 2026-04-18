"""
Data Quality dashboard — surfaces the Item Master gap that silently
distorts every metric in the app.

Answers: how many items have authoritative master data vs. inferred vs.
missing entirely? How much revenue / on-hand value falls into each tier?
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from app.utils.brand_recovery import build_brand_map_with_provenance
from app.utils.price_recovery import build_master_price_map_with_provenance


def compute_data_quality_summary(
    df_sale: pd.DataFrame,
    df_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_grpo_detail: Optional[pd.DataFrame] = None,
) -> dict[str, Any]:
    """Item Master coverage + recovery breakdown across price and brand tiers."""
    # Universe of item codes: master + sale + on-hand
    master_codes = set(df_item_master["ItemCode"].astype(str).str.strip().unique())
    sale_codes = set(df_sale["ItemCode"].astype(str).str.strip().unique()) if df_sale is not None else set()
    oh_codes = set(df_onhand["ItemCode"].astype(str).str.strip().unique()) if df_onhand is not None else set()
    all_codes = master_codes | sale_codes | oh_codes

    # --- Price coverage ---
    price_prov = build_master_price_map_with_provenance(
        df_item_master, df_sale=df_sale, df_grpo_detail=df_grpo_detail,
    )
    # Coverage across ALL items (including those with no source at all)
    recovered_codes = set(price_prov["ItemCode"])
    unpriceable = all_codes - recovered_codes
    price_tiers = price_prov["source"].value_counts().to_dict() if not price_prov.empty else {}

    # --- Brand coverage ---
    brand_prov = build_brand_map_with_provenance(
        df_item_master, df_sale=df_sale, all_item_codes=pd.Series(sorted(all_codes)),
    )
    brand_tiers = brand_prov["source"].value_counts().to_dict() if not brand_prov.empty else {}

    # --- Revenue coverage ---
    rev_total = 0.0
    rev_master_only = 0.0
    rev_unmapped = 0.0
    if df_sale is not None and not df_sale.empty:
        s = df_sale.copy()
        s["ItemCode"] = s["ItemCode"].astype(str).str.strip()
        s["LineTotal"] = pd.to_numeric(s.get("LineTotal", 0), errors="coerce").fillna(0.0)
        rev_total = float(s["LineTotal"].sum())
        rev_master_only = float(s[s["ItemCode"].isin(master_codes)]["LineTotal"].sum())
        rev_unmapped = rev_total - rev_master_only

    # --- OnHand coverage ---
    oh_master = 0
    oh_unmapped = 0
    oh_value_master = 0.0
    oh_value_recovered = 0.0
    if df_onhand is not None and not df_onhand.empty:
        o = df_onhand.copy()
        o["ItemCode"] = o["ItemCode"].astype(str).str.strip()
        o["OnHand"] = pd.to_numeric(o.get("OnHand", 0), errors="coerce").fillna(0.0)
        in_master_mask = o["ItemCode"].isin(master_codes)
        oh_master = int(o[in_master_mask]["OnHand"].sum())
        oh_unmapped = int(o[~in_master_mask]["OnHand"].sum())

        # Value via master-only vs recovered map
        mm = df_item_master.copy()
        mm["ItemCode"] = mm["ItemCode"].astype(str).str.strip()
        mm["Price"] = pd.to_numeric(mm["Price"], errors="coerce").fillna(0.0)
        master_price_map = mm.drop_duplicates("ItemCode").set_index("ItemCode")["Price"]
        o["mp_master"] = o["ItemCode"].map(master_price_map).fillna(0.0)
        oh_value_master = float((o["OnHand"] * o["mp_master"]).sum())

        recovered_price_map = price_prov.drop_duplicates("ItemCode").set_index("ItemCode")["price"]
        o["mp_recovered"] = o["ItemCode"].map(recovered_price_map).fillna(0.0)
        oh_value_recovered = float((o["OnHand"] * o["mp_recovered"]).sum())

    return {
        "overview": {
            "total_unique_items": len(all_codes),
            "items_in_master": len(master_codes),
            "items_in_sale_history": len(sale_codes),
            "items_in_onhand": len(oh_codes),
            "items_missing_from_master": len(all_codes - master_codes),
            "pct_items_covered_by_master": (
                round(len(master_codes) / max(len(all_codes), 1) * 100, 1)
            ),
        },
        "price_coverage": {
            "master": int(price_tiers.get("master", 0)),
            "sale_derived": int(price_tiers.get("sale_derived", 0)),
            "grpo_fob": int(price_tiers.get("grpo_fob", 0)),
            "unpriceable": len(unpriceable),
        },
        "brand_coverage": {
            "master": int(brand_tiers.get("master", 0)),
            "sale": int(brand_tiers.get("sale", 0)),
            "prefix": int(brand_tiers.get("prefix", 0)),
            "unknown": int(brand_tiers.get("unknown", 0)),
        },
        "revenue_coverage": {
            "total_revenue_thb": round(rev_total, 2),
            "from_master_items_thb": round(rev_master_only, 2),
            "from_unmapped_items_thb": round(rev_unmapped, 2),
            "pct_revenue_from_master": (
                round(rev_master_only / rev_total * 100, 1) if rev_total > 0 else 0.0
            ),
        },
        "onhand_coverage": {
            "units_mapped_to_master": oh_master,
            "units_unmapped": oh_unmapped,
            "pct_units_unmapped": (
                round(oh_unmapped / max(oh_master + oh_unmapped, 1) * 100, 1)
            ),
            "value_master_only_thb": round(oh_value_master, 2),
            "value_with_recovery_thb": round(oh_value_recovered, 2),
            "value_recovery_gain_thb": round(oh_value_recovered - oh_value_master, 2),
        },
    }
