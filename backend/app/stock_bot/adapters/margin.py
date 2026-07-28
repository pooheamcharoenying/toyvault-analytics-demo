"""Per-item margin estimation.

Margin per unit (THB) = master_price − FOB cost (latest GRPO) − GP commission.

GP commission is the cut the retailer takes on consignment sales. Defaults to
``config.TYPICAL_GP_COMMISSION_PCT`` (33%) when not available per item.

Items with no GRPO history get margin_per_unit_thb = 0 (the bot's safety
filters will drop them — we don't recommend moving stock we can't price).
"""
from __future__ import annotations

import pandas as pd

from app.stock_bot import config


def build_item_margin(
    df_grpo_detail: pd.DataFrame,
    df_item_master: pd.DataFrame,
    typical_gp_pct: float | None = None,
) -> pd.DataFrame:
    """Per-item margin estimate.

    Args:
        df_grpo_detail: GRPO Detail sheet. Uses ``Price``, ``Rate``, ``DocDate``,
            ``ItemCode`` to derive the FOB cost per unit in THB (the latest
            available GRPO row per item).
        df_item_master: Item Master with ItemCode + Price.
        typical_gp_pct: Default GP commission percent (0–100). Defaults to
            ``config.TYPICAL_GP_COMMISSION_PCT`` (33).

    Returns:
        DataFrame, one row per ItemCode, with columns:
          ItemCode, master_price_thb, fob_thb_unit, gp_commission_pct,
          margin_per_unit_thb.

    Notes:
        - If no GRPO row exists for an item, ``fob_thb_unit = 0`` and the
          implied margin is just the master price minus the GP commission.
          The safety filter (§4.7) drops items with margin ≤ 0, so a stub-FOB
          item still gets a positive margin from its master price and survives.
        - If master price is zero or missing, margin is set to 0 (the filter
          will drop the item).
    """
    if typical_gp_pct is None:
        typical_gp_pct = config.TYPICAL_GP_COMMISSION_PCT

    im = df_item_master.copy()
    im["ItemCode"] = im["ItemCode"].astype(str).str.strip()
    if "Price" in im.columns:
        im = im.rename(columns={"Price": "master_price_thb"})
    else:
        im["master_price_thb"] = 0.0
    im["master_price_thb"] = pd.to_numeric(
        im["master_price_thb"], errors="coerce"
    ).fillna(0.0)
    im = im[["ItemCode", "master_price_thb"]].drop_duplicates("ItemCode")

    if df_grpo_detail.empty:
        im["fob_thb_unit"] = 0.0
    else:
        g = df_grpo_detail.copy()
        g["ItemCode"] = g["ItemCode"].astype(str).str.strip()
        g["DocDate"] = pd.to_datetime(g.get("DocDate"), errors="coerce")
        g["Price"] = pd.to_numeric(g.get("Price", 0), errors="coerce").fillna(0.0)
        g["Rate"] = pd.to_numeric(g.get("Rate", 1), errors="coerce").fillna(1.0)
        # Rate of 0 means missing → treat as 1 (already in THB).
        g["Rate"] = g["Rate"].where(g["Rate"] > 0, 1.0)
        g["fob_thb_unit"] = g["Price"] * g["Rate"]
        # Latest GRPO row per item — sort by date desc and keep first.
        g = g.dropna(subset=["DocDate"]).sort_values("DocDate", ascending=False)
        latest = (
            g[["ItemCode", "fob_thb_unit"]]
            .drop_duplicates("ItemCode", keep="first")
        )
        im = im.merge(latest, on="ItemCode", how="left")
        im["fob_thb_unit"] = pd.to_numeric(
            im["fob_thb_unit"], errors="coerce"
        ).fillna(0.0)

    im["gp_commission_pct"] = float(typical_gp_pct)
    im["margin_per_unit_thb"] = (
        im["master_price_thb"]
        - im["fob_thb_unit"]
        - im["master_price_thb"] * (im["gp_commission_pct"] / 100.0)
    )
    return im[[
        "ItemCode", "master_price_thb", "fob_thb_unit",
        "gp_commission_pct", "margin_per_unit_thb",
    ]]
