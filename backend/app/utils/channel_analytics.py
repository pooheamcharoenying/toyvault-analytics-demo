"""Channel Analytics — channel detail, channel list, channel-location mapping.

Business context: A "channel" (Sale.GroupName) is a sales category like "Shop", "E-Commerce",
"Pinnacle", "Grandway". One channel maps to MANY physical locations (WhsCode). This module
makes that mapping explicit and provides per-channel and per-location-within-channel metrics.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from app.utils import nichi_stock as nstk


# ---------------------------------------------------------------------------
# Channel descriptions — human-readable explanation of each SAP GroupName
# ---------------------------------------------------------------------------

CHANNEL_DESCRIPTIONS: dict[str, str] = {
    "Flagship Store": "ToyVault standalone retail stores",
    "E-Commerce": "E-commerce sales via online marketplaces",
    "Grandway": "Grandway department store branches",
    "Pinnacle": "Pinnacle department store branches",
    "Plaza Group": "Plaza Group shopping centers",
    "DutyFree Plus": "DutyFree Plus duty-free stores",
    "Value Mart": "Value Mart outlet locations",
    "Pop-Up Events": "Promotional events, pop-ups, and seasonal sales",
    "KidZone": "KidZone retail locations",
    "Heritage Mall": "Heritage Mall department store",
    "ReadMore": "ReadMore retail locations",
    "Other": "Miscellaneous other sales channels",
}


def _dedup_sale(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate sales by (DocEntry, ItemCode, Period, GroupName)."""
    df = df.copy()
    df["DocDate"] = pd.to_datetime(df["DocDate"], errors="coerce")
    df = df.dropna(subset=["DocDate"])
    df["Period"] = df["DocDate"].dt.to_period("M").dt.start_time
    return df.drop_duplicates(subset=["DocEntry", "ItemCode", "Period", "GroupName"])


# ---------------------------------------------------------------------------
# Channel list — all channels with location counts and revenue
# ---------------------------------------------------------------------------

def compute_channel_list(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Return all channels with metrics: revenue, location count, top location.

    Parameters
    ----------
    year_list : optional list of int
        Filter sales to these years. None = all years (lifetime).
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _dedup_sale(df_sale)

    if d.empty:
        return {"channels": [], "year_list": year_list}

    # Year filter
    if year_list:
        d = d[d["DocDate"].dt.year.isin(year_list)]
        if d.empty:
            return {"channels": [], "year_list": year_list}

    # Build whs name lookup
    whs_lookup = {}
    if df_whs_code is not None and not df_whs_code.empty:
        whs_lookup = dict(zip(df_whs_code["WhsCode"].astype(str), df_whs_code["WhsName"].astype(str)))

    total_revenue = d["LineTotal"].sum()

    # Compute Revenue (Master) — prefer Sale sheet 'Price Master' (line-level,
    # covers ALL items including discontinued); fall back to Item Master lookup
    if "Price Master" in d.columns:
        d["Revenue_Master_THB"] = pd.to_numeric(
            d["Price Master"], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
    elif "Master_Price_Unit" not in d.columns:
        price_map = df_item_master.drop_duplicates("ItemCode").set_index("ItemCode")["Price"]
        d["Master_Price_Unit"] = d["ItemCode"].map(price_map).fillna(0)
        d["Revenue_Master_THB"] = d["Quantity"] * d["Master_Price_Unit"]
    else:
        d["Revenue_Master_THB"] = d["Quantity"] * d["Master_Price_Unit"]

    # Per-channel metrics
    ch_agg = d.groupby("GroupName", as_index=False).agg(
        revenue=("LineTotal", "sum"),
        revenue_master=("Revenue_Master_THB", "sum"),
        sold_qty=("Quantity", "sum"),
        location_count=("WhsCode", "nunique"),
        brand_count=("Brand", "nunique"),
        transaction_count=("DocEntry", "nunique"),
    ).sort_values("revenue", ascending=False)

    # Top location per channel
    ch_loc = d.groupby(["GroupName", "WhsCode"], as_index=False).agg(
        loc_revenue=("LineTotal", "sum"),
    )
    idx_max = ch_loc.groupby("GroupName")["loc_revenue"].idxmax()
    top_locs = ch_loc.loc[idx_max].set_index("GroupName")

    channels = []
    for _, row in ch_agg.iterrows():
        ch_name = str(row["GroupName"])
        top_loc_code = str(top_locs.loc[ch_name, "WhsCode"]) if ch_name in top_locs.index else ""
        top_loc_rev = float(top_locs.loc[ch_name, "loc_revenue"]) if ch_name in top_locs.index else 0
        top_loc_name = whs_lookup.get(top_loc_code, top_loc_code)

        channels.append({
            "channel": ch_name,
            "description": CHANNEL_DESCRIPTIONS.get(ch_name, f"Sales channel: {ch_name}"),
            "revenue": round(float(row["revenue"]), 2),
            "sold_master_thb": round(float(row["revenue_master"]), 2),
            "revenue_pct": round(float(row["revenue"]) / total_revenue * 100, 2) if total_revenue > 0 else 0,
            "sold_qty": int(row["sold_qty"]),
            "location_count": int(row["location_count"]),
            "brand_count": int(row["brand_count"]),
            "transaction_count": int(row["transaction_count"]),
            "top_location_code": top_loc_code,
            "top_location_name": top_loc_name,
            "top_location_revenue": round(top_loc_rev, 2),
        })

    total_revenue_master = float(d["Revenue_Master_THB"].sum())

    return {
        "channels": channels,
        "total_revenue": round(float(total_revenue), 2),
        "total_revenue_master": round(total_revenue_master, 2),
        "total_channels": len(channels),
        "year_list": year_list,
    }


# ---------------------------------------------------------------------------
# Channel detail — all locations within a specific channel
# ---------------------------------------------------------------------------

def compute_channel_detail(
    channel_name: str,
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    year_list: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Return detail for a specific channel: all locations with metrics.

    Parameters
    ----------
    channel_name : str
        The GroupName (channel) to analyze.
    year_list : optional list of int
        Filter sales to these years. None = all years.
    """
    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _dedup_sale(df_sale)

    empty_result = {
        "channel": channel_name,
        "description": CHANNEL_DESCRIPTIONS.get(channel_name, f"Sales channel: {channel_name}"),
        "locations": [],
        "brands": [],
        "monthly_trend": [],
        "total_revenue": 0,
        "total_revenue_master": 0,
        "total_sold_qty": 0,
        "location_count": 0,
        "year_list": year_list,
    }

    if d.empty:
        return empty_result

    # Filter to this channel
    d = d[d["GroupName"] == channel_name]
    if d.empty:
        return empty_result

    # Year filter
    if year_list:
        d = d[d["DocDate"].dt.year.isin(year_list)]
        if d.empty:
            return empty_result

    # Build whs name lookup
    whs_lookup = {}
    if df_whs_code is not None and not df_whs_code.empty:
        whs_lookup = dict(zip(df_whs_code["WhsCode"].astype(str), df_whs_code["WhsName"].astype(str)))

    # Compute Revenue (Master) — prefer Sale sheet 'Price Master' column
    if "Price Master" in d.columns:
        d["Revenue_Master_THB"] = pd.to_numeric(
            d["Price Master"], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
    elif "Master_Price_Unit" not in d.columns:
        price_map = df_item_master.drop_duplicates("ItemCode").set_index("ItemCode")["Price"]
        d["Master_Price_Unit"] = d["ItemCode"].map(price_map).fillna(0)
        d["Revenue_Master_THB"] = d["Quantity"] * d["Master_Price_Unit"]
    else:
        d["Revenue_Master_THB"] = d["Quantity"] * d["Master_Price_Unit"]

    total_revenue = d["LineTotal"].sum()
    total_revenue_master = d["Revenue_Master_THB"].sum()
    total_sold_qty = d["Quantity"].sum()

    # --- Per-location metrics ---
    loc_agg = d.groupby("WhsCode", as_index=False).agg(
        revenue=("LineTotal", "sum"),
        revenue_master=("Revenue_Master_THB", "sum"),
        sold_qty=("Quantity", "sum"),
        brand_count=("Brand", "nunique"),
        item_count=("ItemCode", "nunique"),
        transaction_count=("DocEntry", "nunique"),
    ).sort_values("revenue", ascending=False)

    # On-hand by location (from RAW snapshot — not year-filtered, not aggregated)
    # Use df_raw_onhand which has WhsCode per row (df_onhand from prepare_ aggregates by ItemCode)
    raw_oh = df_raw_onhand.copy()
    raw_oh["OnHand"] = pd.to_numeric(raw_oh["OnHand"], errors="coerce").fillna(0)
    oh_by_loc = raw_oh.groupby("WhsCode", as_index=False).agg(
        onhand_qty=("OnHand", "sum"),
    )
    # Merge master price for on-hand value
    if "Master Price" not in raw_oh.columns:
        price_map = df_item_master.drop_duplicates("ItemCode").set_index("ItemCode")["Price"]
        raw_oh["Master Price"] = raw_oh["ItemCode"].map(price_map).fillna(0)
    else:
        raw_oh["Master Price"] = pd.to_numeric(raw_oh["Master Price"], errors="coerce").fillna(0)
    raw_oh["onhand_thb"] = raw_oh["OnHand"] * raw_oh["Master Price"]
    oh_val_by_loc = raw_oh.groupby("WhsCode", as_index=False).agg(
        onhand_thb=("onhand_thb", "sum"),
    )

    locations = []
    for _, row in loc_agg.iterrows():
        whs = str(row["WhsCode"])
        oh_match = oh_by_loc[oh_by_loc["WhsCode"] == whs]
        oh_qty = int(oh_match["onhand_qty"].sum()) if not oh_match.empty else 0
        oh_val_match = oh_val_by_loc[oh_val_by_loc["WhsCode"] == whs]
        oh_thb = float(oh_val_match["onhand_thb"].sum()) if not oh_val_match.empty else 0
        rev = float(row["revenue"])

        rev_master = float(row["revenue_master"])
        locations.append({
            "whs_code": whs,
            "whs_name": whs_lookup.get(whs, whs),
            "revenue": round(rev, 2),
            "sold_master_thb": round(rev_master, 2),
            "revenue_pct": round(rev / total_revenue * 100, 2) if total_revenue > 0 else 0,
            "sold_qty": int(row["sold_qty"]),
            "onhand_qty": oh_qty,
            "onhand_thb": round(oh_thb, 2),
            "brand_count": int(row["brand_count"]),
            "item_count": int(row["item_count"]),
            "transaction_count": int(row["transaction_count"]),
            "revenue_per_inv": round(rev / oh_thb, 2) if oh_thb > 0 else None,
        })

    # --- Top brands in this channel ---
    brand_agg = d.groupby("Brand", as_index=False).agg(
        revenue=("LineTotal", "sum"),
        revenue_master=("Revenue_Master_THB", "sum"),
        sold_qty=("Quantity", "sum"),
        item_count=("ItemCode", "nunique"),
    ).sort_values("revenue", ascending=False).head(20)

    brands = [
        {
            "brand": str(row["Brand"]),
            "revenue": round(float(row["revenue"]), 2),
            "sold_master_thb": round(float(row["revenue_master"]), 2),
            "revenue_pct": round(float(row["revenue"]) / total_revenue * 100, 2) if total_revenue > 0 else 0,
            "sold_qty": int(row["sold_qty"]),
            "item_count": int(row["item_count"]),
        }
        for _, row in brand_agg.iterrows()
    ]

    # --- Monthly trend ---
    d_m = d.copy()
    d_m["_period"] = d_m["DocDate"].dt.to_period("M")
    monthly = d_m.groupby("_period", as_index=False).agg(
        revenue=("LineTotal", "sum"),
        revenue_master=("Revenue_Master_THB", "sum"),
        sold_qty=("Quantity", "sum"),
    ).sort_values("_period")
    monthly_trend = [
        {
            "period": str(row["_period"]),
            "revenue": round(float(row["revenue"]), 2),
            "sold_master_thb": round(float(row["revenue_master"]), 2),
            "sold_qty": int(row["sold_qty"]),
        }
        for _, row in monthly.iterrows()
    ]

    return {
        "channel": channel_name,
        "description": CHANNEL_DESCRIPTIONS.get(channel_name, f"Sales channel: {channel_name}"),
        "locations": locations,
        "brands": brands,
        "monthly_trend": monthly_trend,
        "total_revenue": round(float(total_revenue), 2),
        "total_revenue_master": round(float(total_revenue_master), 2),
        "total_sold_qty": int(total_sold_qty),
        "location_count": len(locations),
        "year_list": year_list,
    }


# ---------------------------------------------------------------------------
# Channel-to-location mapping helper — used for tooltips and enrichment
# ---------------------------------------------------------------------------

def compute_channel_location_mapping(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
) -> dict[str, Any]:
    """Return a mapping of channel -> list of locations with revenue.

    Used by other functions and API endpoints to enrich channel names
    with location information (e.g., tooltips, badges).
    """
    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    d = _dedup_sale(df_sale)

    if d.empty:
        return {"mapping": {}}

    whs_lookup = {}
    if df_whs_code is not None and not df_whs_code.empty:
        whs_lookup = dict(zip(df_whs_code["WhsCode"].astype(str), df_whs_code["WhsName"].astype(str)))

    # Group by channel and location
    cl = d.groupby(["GroupName", "WhsCode"], as_index=False).agg(
        revenue=("LineTotal", "sum"),
    ).sort_values(["GroupName", "revenue"], ascending=[True, False])

    mapping = {}
    for ch_name, group in cl.groupby("GroupName"):
        ch_str = str(ch_name)
        locs = []
        ch_total = group["revenue"].sum()
        for _, row in group.iterrows():
            whs = str(row["WhsCode"])
            rev = float(row["revenue"])
            locs.append({
                "whs_code": whs,
                "whs_name": whs_lookup.get(whs, whs),
                "revenue": round(rev, 2),
                "revenue_pct": round(rev / ch_total * 100, 2) if ch_total > 0 else 0,
            })
        mapping[ch_str] = {
            "description": CHANNEL_DESCRIPTIONS.get(ch_str, f"Sales channel: {ch_str}"),
            "location_count": len(locs),
            "locations": locs,
        }

    return {"mapping": mapping}
