"""Per-(item × location) on-hand state, enriched with master price and names.

Joins the prepared on-hand frame with Item Master (for ItemName, Brand,
validity flags) and Whs Code (for the warehouse display name).
"""
from __future__ import annotations

import math

import pandas as pd


def _norm_str(value, fallback: str) -> str:
    """Coerce a possibly-NaN / None / "nan" pandas value to a clean fallback.

    pandas' fillna only catches actual NaN floats; once a NaN has been
    stringified to "nan" it's invisible to fillna. This helper closes that
    gap at the boundary where DataFrames feed into the domain layer.
    """
    if value is None:
        return fallback
    if isinstance(value, float) and math.isnan(value):
        return fallback
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return fallback
    return s


def build_item_location_onhand(
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
) -> pd.DataFrame:
    """Build the bot's per-(item, location) stock state frame.

    Args:
        df_raw_onhand: The raw OnHand sheet (will be normalised).
        df_item_master: Item Master with ItemCode, GroupName (→ Brand),
            ItemName, Price (→ Master Price), validFor, frozenFor.
        df_whs_code: Whs Code with WhsCode → WhsName mapping.

    Returns:
        DataFrame, one row per (ItemCode, WhsCode), with columns:
          ItemCode, WhsCode, WhsName, OnHand, master_price_thb,
          on_hand_thb_master, Brand, ItemName, validFor, frozenFor
    """
    if df_raw_onhand.empty:
        return pd.DataFrame(columns=[
            "ItemCode", "WhsCode", "WhsName", "OnHand", "master_price_thb",
            "on_hand_thb_master", "Brand", "ItemName", "validFor", "frozenFor",
        ])

    oh = df_raw_onhand.copy()
    oh["ItemCode"] = oh["ItemCode"].astype(str).str.strip()
    oh["WhsCode"] = oh["WhsCode"].astype(str).str.strip()
    oh["OnHand"] = pd.to_numeric(oh["OnHand"], errors="coerce").fillna(0.0)

    # Item Master: take ItemCode, GroupName→Brand, ItemName, Price→master_price
    im = df_item_master.copy()
    im["ItemCode"] = im["ItemCode"].astype(str).str.strip()
    keep_cols = [c for c in ["ItemCode", "GroupName", "ItemName", "Price",
                              "validFor", "frozenFor"] if c in im.columns]
    im = im[keep_cols].rename(columns={
        "GroupName": "Brand",
        "Price": "master_price_thb",
    })
    im["master_price_thb"] = pd.to_numeric(
        im["master_price_thb"], errors="coerce"
    ).fillna(0.0)
    if "Brand" in im.columns:
        im["Brand"] = im["Brand"].fillna("Unknown")
    if "ItemName" not in im.columns:
        im["ItemName"] = im["ItemCode"]
    if "validFor" not in im.columns:
        im["validFor"] = "Y"
    if "frozenFor" not in im.columns:
        im["frozenFor"] = "N"

    # Whs Code: WhsCode → WhsName
    whs = df_whs_code.copy()
    whs["WhsCode"] = whs["WhsCode"].astype(str).str.strip()
    if "WhsName" not in whs.columns:
        whs["WhsName"] = whs["WhsCode"]
    whs = whs[["WhsCode", "WhsName"]].drop_duplicates(subset=["WhsCode"])

    merged = oh.merge(im, on="ItemCode", how="left")
    merged = merged.merge(whs, on="WhsCode", how="left")

    merged["WhsName"] = merged["WhsName"].fillna(merged["WhsCode"])
    merged["Brand"] = merged["Brand"].fillna("Unknown")
    merged["ItemName"] = merged["ItemName"].fillna(merged["ItemCode"])
    merged["master_price_thb"] = pd.to_numeric(
        merged["master_price_thb"], errors="coerce"
    ).fillna(0.0)
    merged["validFor"] = merged["validFor"].fillna("Y")
    merged["frozenFor"] = merged["frozenFor"].fillna("N")

    merged["on_hand_thb_master"] = merged["OnHand"] * merged["master_price_thb"]

    # Aggregate to one row per (ItemCode, WhsCode) — the raw sheet sometimes
    # has multiple rows for the same pair (different BP codes).
    agg = (
        merged.groupby(["ItemCode", "WhsCode"], as_index=False)
        .agg(
            OnHand=("OnHand", "sum"),
            on_hand_thb_master=("on_hand_thb_master", "sum"),
            master_price_thb=("master_price_thb", "max"),
            Brand=("Brand", "first"),
            ItemName=("ItemName", "first"),
            WhsName=("WhsName", "first"),
            validFor=("validFor", "first"),
            frozenFor=("frozenFor", "first"),
        )
    )

    # Boundary cleanup: pandas fillna leaves stringified "nan" / "None"
    # untouched, so do a final normalisation pass before the engine layer
    # sees these as user-facing labels.
    agg["WhsName"] = agg.apply(
        lambda r: _norm_str(r["WhsName"], r["WhsCode"]), axis=1
    )
    agg["ItemName"] = agg.apply(
        lambda r: _norm_str(r["ItemName"], r["ItemCode"]), axis=1
    )
    agg["Brand"] = agg.apply(
        lambda r: _norm_str(r["Brand"], "Unknown"), axis=1
    )
    return agg
