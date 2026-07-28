"""Build ItemLocationState objects by joining all the adapter outputs.

This is the bridge from pandas-land to pure-Python-land. After this step,
the rest of the engine operates only on ItemLocationState dataclasses.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from app.stock_bot import config


def _safe_str(value, fallback: str) -> str:
    """NaN-safe string coercion. ``fallback`` is used for None, NaN, "" and "nan"."""
    if value is None:
        return fallback
    if isinstance(value, float) and math.isnan(value):
        return fallback
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return fallback
    return s
from app.stock_bot.adapters import item_size as itemsize_mod
from app.stock_bot.adapters import location_class as locclass_mod
from app.stock_bot.domain import capacity as cap_mod
from app.stock_bot.domain.models import ItemLocationState


def compute_item_location_states(
    stock_df: pd.DataFrame,
    velocity_df: pd.DataFrame,
    margin_df: pd.DataFrame,
    location_quality_df: pd.DataFrame,
    lifetime_df: Optional[pd.DataFrame] = None,
    policy: Optional[dict] = None,
) -> list[ItemLocationState]:
    """Build the full set of ItemLocationStates.

    Joins stock_df (one row per (item, location)) with velocity_df (same
    granularity), margin_df (per item), and location_quality_df (per
    location), then runs every (item, location) through the size/location
    classifiers and the shelf-capacity model. Computes target / surplus /
    deficit per state.

    Args:
        stock_df: From ``stock_state.build_item_location_onhand``.
        velocity_df: From ``velocity.build_item_location_velocity``.
        margin_df: From ``margin.build_item_margin``.
        location_quality_df: From ``location_quality.build_location_quality``.
        policy: Optional dict of policy.yaml contents. Expected keys:
            - ``item_size_class`` → {item_code: class}
            - ``location_class`` → {whs_code: class}
            - ``location_shelf_caps`` → {whs_code: {item_code: cap_int}}
            - ``expected_velocity_overrides`` → {item_code: {whs_code: per_day}}

    Returns:
        List of ItemLocationState. Length = number of (ItemCode, WhsCode)
        pairs across stock_df ∪ velocity_df.
    """
    policy = policy or {}
    size_overrides = policy.get("item_size_class") or {}
    loc_overrides = policy.get("location_class") or {}
    cap_overrides = policy.get("location_shelf_caps") or {}
    velo_overrides = policy.get("expected_velocity_overrides") or {}

    # Outer-join stock + velocity on (ItemCode, WhsCode). Either side missing
    # is OK — items in stock but never sold, or sold from a temporary location
    # that no longer holds stock.
    base = stock_df.merge(
        velocity_df, on=["ItemCode", "WhsCode"], how="outer"
    )
    if lifetime_df is not None and not lifetime_df.empty:
        base = base.merge(lifetime_df, on=["ItemCode", "WhsCode"], how="left")
    if "sold_qty_lifetime" not in base.columns:
        base["sold_qty_lifetime"] = 0.0
    if "sold_thb_lifetime" not in base.columns:
        base["sold_thb_lifetime"] = 0.0
    base["sold_qty_lifetime"] = pd.to_numeric(
        base["sold_qty_lifetime"], errors="coerce"
    ).fillna(0.0)
    base["sold_thb_lifetime"] = pd.to_numeric(
        base["sold_thb_lifetime"], errors="coerce"
    ).fillna(0.0)
    base["OnHand"] = pd.to_numeric(base.get("OnHand", 0), errors="coerce").fillna(0.0)
    base["avg_daily_qty"] = pd.to_numeric(
        base.get("avg_daily_qty", 0), errors="coerce"
    ).fillna(0.0)
    base["monthly_velocity"] = pd.to_numeric(
        base.get("monthly_velocity", 0), errors="coerce"
    ).fillna(0.0)
    base["velocity_basis"] = base.get("velocity_basis").fillna("no_history")
    base["sold_qty"] = pd.to_numeric(base.get("sold_qty", 0), errors="coerce").fillna(0.0)

    # Pre-classify locations once. Indexed by WhsCode.
    loc_meta: dict[str, tuple[str, str, str]] = {}
    loc_rev: dict[str, float] = {}
    loc_whsname: dict[str, str] = {}
    loc_on_hand: dict[str, float] = {}
    for _, row in location_quality_df.iterrows():
        wcode = str(row["WhsCode"]).strip()
        revenue = float(row.get("annual_revenue_thb", 0) or 0)
        on_hand = float(row.get("on_hand_thb_master", 0) or 0)
        pct = float(row.get("percentile_rank", 0.5) or 0.5)
        loc_rev[wcode] = revenue
        loc_on_hand[wcode] = on_hand
        loc_whsname[wcode] = str(row.get("WhsName", wcode))
        cls, basis, evidence = locclass_mod.classify_location_class(
            annual_revenue_thb=revenue,
            on_hand_thb=on_hand,
            percentile_rank=pct,
            policy_override=loc_overrides.get(wcode),
        )
        loc_meta[wcode] = (cls, basis, evidence)

    # Pre-classify items once. Indexed by ItemCode.
    item_meta: dict[str, tuple[str, str, str]] = {}
    margin_map: dict[str, dict] = {}
    for _, row in margin_df.iterrows():
        icode = str(row["ItemCode"]).strip()
        master_price = float(row.get("master_price_thb", 0) or 0)
        margin_map[icode] = {
            "master_price_thb": master_price,
            "fob_thb_unit": float(row.get("fob_thb_unit", 0) or 0),
            "gp_commission_pct": float(row.get("gp_commission_pct", 0) or 0),
            "margin_per_unit_thb": float(row.get("margin_per_unit_thb", 0) or 0),
        }
        cls, basis, evidence = itemsize_mod.classify_item_size(
            master_price=master_price,
            policy_override=size_overrides.get(icode),
        )
        item_meta[icode] = (cls, basis, evidence)

    states: list[ItemLocationState] = []
    for _, row in base.iterrows():
        item_code = str(row["ItemCode"]).strip()
        whs_code = str(row["WhsCode"]).strip()

        # Defaults if joins missed
        loc_class, loc_basis, loc_evidence = loc_meta.get(
            whs_code,
            ("boutique", locclass_mod.BASIS_REVENUE_PERCENTILE,
             "unknown location → default boutique"),
        )
        size_class, size_basis, size_evidence = item_meta.get(
            item_code,
            ("normal", itemsize_mod.BASIS_MISSING_PRICE,
             "unknown item → default normal"),
        )
        margin_info = margin_map.get(item_code, {
            "master_price_thb": float(row.get("master_price_thb", 0) or 0),
            "fob_thb_unit": 0.0,
            "gp_commission_pct": float(config.TYPICAL_GP_COMMISSION_PCT),
            "margin_per_unit_thb": 0.0,
        })

        # Velocity — observed; v1 doesn't do peer borrowing yet but we honour
        # policy.yaml overrides if present.
        velo_basis = str(row.get("velocity_basis") or "no_history")
        velo_per_day = float(row.get("avg_daily_qty", 0) or 0)
        velo_monthly = float(row.get("monthly_velocity", 0) or 0)
        v_override = (velo_overrides.get(item_code) or {}).get(whs_code)
        if v_override is not None:
            velo_per_day = float(v_override)
            velo_monthly = velo_per_day * 30.0
            velo_basis = "policy_override"

        velo_potential_per_day = velo_per_day  # v1: same as observed

        # Shelf capacity (with optional override)
        cap_ov = (cap_overrides.get(whs_code) or {}).get(item_code)
        shelf_cap, shelf_basis, shelf_modifiers = cap_mod.compute_shelf_capacity(
            monthly_velocity=velo_monthly,
            item_size_class=size_class,
            location_class=loc_class,
            policy_override=float(cap_ov) if cap_ov is not None else None,
        )

        # Target / surplus / deficit
        #
        # Target = the SHELF CAP directly (gated on whether we have any
        # sales signal at this location). The cap is already
        # velocity-aware via the tier table (5-10/mo→cap 20, etc.) plus
        # size and location-class multipliers. Clamping the target a
        # second time on `velocity × 56 days` (the previous behaviour)
        # produced tiny targets for low-velocity items — a 1/mo seller
        # got target=1 even when its shelf cap was 4 — and those tiny
        # deficits then died inside MIN_QTY_PER_TRANSFER, leaving the
        # SKU stocked out forever.
        #
        # New mental model: "shelf cap is the target we maintain at the
        # store." Fill the shelf, transfer as many units as possible from
        # warehouse-first then shop-to-shop, capped by available supply.
        #
        # SAFETY GATE: target = 0 for SKUs that have never sold at this
        # location. We don't want the bot pushing untested products in
        # (that's the failure mode that killed the Revenue Optimiser).
        on_hand = float(row.get("OnHand", 0) or 0)
        lifetime_sold = float(row.get("sold_qty_lifetime", 0) or 0)
        has_sales_signal = velo_per_day > 0 or lifetime_sold > 0
        target = shelf_cap if has_sales_signal else 0
        surplus = max(0, int(on_hand) - target)
        deficit = max(0, target - int(on_hand))

        master_price = float(margin_info["master_price_thb"])
        if master_price == 0.0:
            # Fallback to whatever stock_df has (might be 0 too, that's fine).
            master_price = float(row.get("master_price_thb", 0) or 0)

        # NaN-safe string coercion at the boundary.
        item_name = _safe_str(row.get("ItemName"), item_code)
        brand_name = _safe_str(row.get("Brand"), "Unknown")
        whs_name = _safe_str(
            row.get("WhsName"),
            _safe_str(loc_whsname.get(whs_code), whs_code),
        )

        states.append(ItemLocationState(
            item_code=item_code,
            item_name=item_name,
            brand=brand_name,
            whs_code=whs_code,
            whs_name=whs_name,
            on_hand=on_hand,
            master_price_thb=master_price,
            on_hand_thb_master=on_hand * master_price,
            velocity_per_day=velo_per_day,
            velocity_potential_per_day=velo_potential_per_day,
            velocity_basis=velo_basis,
            fob_thb_unit=float(margin_info["fob_thb_unit"]),
            gp_commission_pct=float(margin_info["gp_commission_pct"]),
            margin_per_unit_thb=float(margin_info["margin_per_unit_thb"]),
            item_size_class=size_class,
            item_size_basis=size_basis,
            item_size_evidence=size_evidence,
            location_class=loc_class,
            location_basis=loc_basis,
            location_evidence=loc_evidence,
            shelf_capacity=shelf_cap,
            shelf_capacity_basis=shelf_basis,
            shelf_capacity_modifiers=tuple(shelf_modifiers),
            target_stock=target,
            surplus=surplus,
            deficit=deficit,
            sold_qty_lifetime=float(row.get("sold_qty_lifetime", 0) or 0),
            sold_thb_lifetime=float(row.get("sold_thb_lifetime", 0) or 0),
        ))

    return states
