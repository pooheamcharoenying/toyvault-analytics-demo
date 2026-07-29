"""Per-location Product-Market Fit via lift analysis.

For each location, compute the "lift" of every brand, brand×line, and price
band against the company-wide baseline. Lift = share at this location ÷
share company-wide. > 1 means this location over-indexes on that cell; < 1
means it under-indexes. Bayesian shrinkage protects against small-sample
noise; a hard sample-size filter drops cells with too little data to mean
anything.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from app.utils import nichi_stock as nstk
from app.utils.location_analytics import _add_master_revenue, _channel_dedup_sale
from app.utils.location_consolidation import add_consolidated_column


# ---------------------------------------------------------------------------
# Price-band tiers — REUSE the Stock Bot vocabulary so it's consistent app-wide.
# ---------------------------------------------------------------------------

_PRICE_BANDS = (
    # (upper_exclusive_thb, band_key, band_label)
    (200.0,         "small",     "<฿200"),
    (1500.0,        "normal",    "฿200–1,500"),
    (3500.0,        "large",     "฿1,500–3,500"),
    (float("inf"),  "oversized", ">฿3,500"),
)


def _assign_price_band(price: float) -> tuple[str, str]:
    """Return (band_key, band_label) for a Master Price. Defaults to 'normal'
    if price is missing / non-positive — same convention as stock_bot."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return ("normal", "฿200–1,500")
    if p <= 0 or p != p:  # NaN check
        return ("normal", "฿200–1,500")
    for upper, key, label in _PRICE_BANDS:
        if p < upper:
            return (key, label)
    return ("oversized", ">฿3,500")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_product_market_fit(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    *,
    location: str,
    year_list: Optional[list[int]] = None,
    top_n: int = 5,
    shrinkage_k: float = 0.10,
    min_units_brand: int = 20,
    min_units_line: int = 10,
    min_units_price: int = 50,
    min_skus_brand: int = 3,
    min_skus_line: int = 2,
    min_skus_price: int = 5,
    strong_lift_threshold: float = 1.5,
    weak_lift_threshold: float = 0.7,
) -> dict[str, Any]:
    """Per-location product-market fit via lift analysis on three dimensions."""
    empty_response = _empty_response(location, year_list)
    if df_whs_code is None or df_whs_code.empty:
        return empty_response

    # --- 1. Prepare, consolidate, year-filter ---
    df_sale_prep, _, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    sale = _channel_dedup_sale(df_sale_prep)
    if sale.empty:
        return empty_response

    sale = _add_master_revenue(sale, df_item_master)

    # Attach WhsName and apply consolidation so we filter on the same
    # canonical location names that other views use.
    whs_map = df_whs_code[["WhsCode", "WhsName"]].copy()
    whs_map["WhsCode"] = whs_map["WhsCode"].astype(str).str.strip()
    sale["WhsCode"] = sale["WhsCode"].astype(str).str.strip()
    sale = sale.merge(whs_map, on="WhsCode", how="left")
    sale = sale.dropna(subset=["WhsName"])

    _whs_lookup = dict(zip(whs_map["WhsCode"], whs_map["WhsName"]))
    sale = add_consolidated_column(sale, _whs_lookup)
    sale["WhsName"] = sale["ConsolidatedLocation"]

    if year_list:
        sale = sale[sale["DocDate"].dt.year.isin(year_list)]
        if sale.empty:
            return empty_response

    # --- 2. Attach price band + ensure required columns ---
    if "Master Price" not in sale.columns:
        # Fall back via Item Master merge if prep didn't attach it
        im = df_item_master[["ItemCode", "Price"]].rename(columns={"Price": "Master Price"})
        im["ItemCode"] = im["ItemCode"].astype(str).str.strip()
        sale["ItemCode"] = sale["ItemCode"].astype(str).str.strip()
        sale = sale.merge(im, on="ItemCode", how="left")

    if "Brand" not in sale.columns:
        sale["Brand"] = "Unknown"
    sale["Brand"] = sale["Brand"].fillna("Unknown")

    if "Cate" not in sale.columns:
        # Cate ("product line") isn't always carried through prep — re-merge from Item
        # Master when that sheet has it. The anonymized demo Item Master has no Cate
        # column, so fall back to a single "(unspecified)" line rather than KeyError;
        # the brand and price-band lift dimensions are unaffected.
        if "Cate" in df_item_master.columns:
            im_cate = df_item_master[["ItemCode", "Cate"]].copy()
            im_cate["ItemCode"] = im_cate["ItemCode"].astype(str).str.strip()
            sale = sale.merge(im_cate, on="ItemCode", how="left")
        else:
            sale["Cate"] = "(unspecified)"
    sale["Cate"] = sale["Cate"].fillna("(unspecified)")

    band_info = sale["Master Price"].apply(_assign_price_band)
    sale["price_band_key"] = band_info.apply(lambda t: t[0])
    sale["price_band_label"] = band_info.apply(lambda t: t[1])

    # --- 3. Split into location vs company-wide ---
    loc_sale = sale[sale["WhsName"] == location].copy()
    if loc_sale.empty:
        return empty_response

    total_loc_revenue = float(loc_sale["LineTotal"].sum())
    total_co_revenue = float(sale["LineTotal"].sum())
    if total_loc_revenue <= 0 or total_co_revenue <= 0:
        return empty_response

    as_of = pd.to_datetime(sale["DocDate"], errors="coerce").max()
    totals = {
        "this_location_revenue_thb": round(total_loc_revenue, 2),
        "this_location_units_sold": int(loc_sale["Quantity"].sum()),
        "this_location_distinct_skus": int(loc_sale["ItemCode"].nunique()),
        "company_revenue_thb": round(total_co_revenue, 2),
    }

    # --- 4. Build per-dimension lift tables ---
    brand_lift = _compute_lift_table(
        loc_sale, sale, group_cols=["Brand"],
        total_loc=total_loc_revenue, total_co=total_co_revenue,
        min_units=min_units_brand, min_skus=min_skus_brand,
        k=shrinkage_k,
    )
    line_lift = _compute_lift_table(
        loc_sale, sale, group_cols=["Brand", "Cate"],
        total_loc=total_loc_revenue, total_co=total_co_revenue,
        min_units=min_units_line, min_skus=min_skus_line,
        k=shrinkage_k,
    )
    price_lift = _compute_lift_table(
        loc_sale, sale, group_cols=["price_band_key"],
        total_loc=total_loc_revenue, total_co=total_co_revenue,
        min_units=min_units_price, min_skus=min_skus_price,
        k=shrinkage_k,
        # Price bands are always shown (no strong/weak split) — keep all 4
        keep_all=True,
    )
    # Attach the human label back to price_lift rows
    label_map = {key: label for _, key, label in _PRICE_BANDS}
    if not price_lift.empty:
        price_lift["band_label"] = price_lift["price_band_key"].map(label_map)

    # --- 5. Split strong / weak ---
    brand_split = _split_strong_weak(
        brand_lift, top_n=top_n,
        strong_threshold=strong_lift_threshold,
        weak_threshold=weak_lift_threshold,
    )
    line_split = _split_strong_weak(
        line_lift, top_n=top_n,
        strong_threshold=strong_lift_threshold,
        weak_threshold=weak_lift_threshold,
    )

    # --- 6. Build response ---
    brand_fit = {
        "strong": [_brand_row_to_dict(r) for r in brand_split["strong"]],
        "weak":   [_brand_row_to_dict(r) for r in brand_split["weak"]],
    }
    line_fit = {
        "strong": [_line_row_to_dict(r) for r in line_split["strong"]],
        "weak":   [_line_row_to_dict(r) for r in line_split["weak"]],
    }
    price_band_fit = [_price_row_to_dict(r) for r in price_lift.to_dict("records")] \
        if not price_lift.empty else []
    # Show price bands in their natural order, not by lift.
    band_order = {k: i for i, (_, k, _) in enumerate(_PRICE_BANDS)}
    price_band_fit.sort(key=lambda r: band_order.get(r.get("band_key"), 999))

    summary = _build_summary(brand_fit, line_fit, price_band_fit)

    return {
        "location": location,
        "period": {
            "year_list": list(year_list) if year_list else None,
            "as_of": as_of.strftime("%Y-%m-%d") if pd.notna(as_of) else None,
        },
        "baseline": "company",
        "totals": totals,
        "brand_fit": brand_fit,
        "line_fit": line_fit,
        "price_band_fit": price_band_fit,
        "summary": summary,
        "diagnostics": {
            "shrinkage_k": shrinkage_k,
            "strong_lift_threshold": strong_lift_threshold,
            "weak_lift_threshold": weak_lift_threshold,
            "min_units_brand": min_units_brand,
            "min_units_line": min_units_line,
            "min_units_price": min_units_price,
            "min_skus_brand": min_skus_brand,
            "min_skus_line": min_skus_line,
            "min_skus_price": min_skus_price,
            "brands_evaluated": int(len(brand_lift)),
            "lines_evaluated": int(len(line_lift)),
            "price_bands_evaluated": int(len(price_lift)),
        },
    }


# ---------------------------------------------------------------------------
# Core lift math
# ---------------------------------------------------------------------------

def _compute_lift_table(
    loc_sale: pd.DataFrame,
    co_sale: pd.DataFrame,
    *,
    group_cols: list[str],
    total_loc: float,
    total_co: float,
    min_units: int,
    min_skus: int,
    k: float,
    keep_all: bool = False,
) -> pd.DataFrame:
    """Aggregate revenue / units / SKUs at location and company, then compute
    raw and shrinkage-adjusted lift. Apply the sample-size filter.

    Returns a DataFrame with one row per group_cols cell:
      group_cols..., revenue_thb, revenue_thb_master, units, skus_at_loc,
      share_loc, share_company, lift_raw, lift
    sorted by lift descending. Cells below the sample threshold are dropped
    (unless ``keep_all=True``, used for the 4 price bands).
    """
    if loc_sale.empty or total_loc <= 0 or total_co <= 0:
        return pd.DataFrame()

    loc_agg = (
        loc_sale.groupby(group_cols, as_index=False)
        .agg(
            revenue_thb=("LineTotal", "sum"),
            revenue_thb_master=("Revenue_Master_THB", "sum"),
            units=("Quantity", "sum"),
            skus_at_loc=("ItemCode", "nunique"),
        )
    )
    co_agg = (
        co_sale.groupby(group_cols, as_index=False)
        .agg(co_revenue_thb=("LineTotal", "sum"))
    )

    merged = loc_agg.merge(co_agg, on=group_cols, how="left")
    merged["co_revenue_thb"] = merged["co_revenue_thb"].fillna(0.0)

    # share_loc, share_company
    merged["share_loc"] = merged["revenue_thb"] / total_loc
    merged["share_company"] = merged["co_revenue_thb"] / total_co

    # Raw lift: undefined when share_company == 0 (cell exists only at this
    # location), but pandas division gives inf; mark as None for display.
    merged["lift_raw"] = merged.apply(
        lambda r: r["share_loc"] / r["share_company"]
        if r["share_company"] > 0 else None,
        axis=1,
    )

    # Bayesian-shrunk lift:
    #   adjusted_share = (rev_at_cell + k * share_co * total_loc) / (total_loc * (1 + k))
    #   adjusted_lift  = adjusted_share / share_co
    # Small samples are pulled toward share_co → lift toward 1.0.
    denom = total_loc * (1.0 + k)
    merged["adjusted_share"] = (
        merged["revenue_thb"] + k * merged["share_company"] * total_loc
    ) / denom
    merged["lift"] = merged.apply(
        lambda r: r["adjusted_share"] / r["share_company"]
        if r["share_company"] > 0 else None,
        axis=1,
    )

    if not keep_all:
        merged = merged[
            (merged["units"] >= min_units) & (merged["skus_at_loc"] >= min_skus)
        ]

    merged = merged.dropna(subset=["lift"])

    # Round for display.
    merged["lift"] = merged["lift"].round(2)
    merged["lift_raw"] = merged["lift_raw"].round(2)
    merged["share_loc_pct"] = (merged["share_loc"] * 100).round(2)
    merged["share_company_pct"] = (merged["share_company"] * 100).round(2)
    merged["revenue_thb"] = merged["revenue_thb"].round(2)
    merged["revenue_thb_master"] = merged["revenue_thb_master"].round(2)
    merged["units"] = merged["units"].astype(int)
    merged["skus_at_loc"] = merged["skus_at_loc"].astype(int)

    return merged.sort_values("lift", ascending=False).reset_index(drop=True)


def _split_strong_weak(
    lift_df: pd.DataFrame,
    *,
    top_n: int,
    strong_threshold: float,
    weak_threshold: float,
) -> dict[str, list]:
    """Split a lift DataFrame into top-N over-performers and top-N
    under-performers (excluding cells in the 'neutral' band between
    weak_threshold and strong_threshold)."""
    if lift_df.empty:
        return {"strong": [], "weak": []}
    strong_df = (
        lift_df[lift_df["lift"] > strong_threshold]
        .sort_values("lift", ascending=False)
        .head(top_n)
    )
    weak_df = (
        lift_df[lift_df["lift"] < weak_threshold]
        .sort_values("lift", ascending=True)
        .head(top_n)
    )
    return {
        "strong": strong_df.to_dict("records"),
        "weak": weak_df.to_dict("records"),
    }


# ---------------------------------------------------------------------------
# Row serialisers — keep the JSON shape consistent and explicit
# ---------------------------------------------------------------------------

def _brand_row_to_dict(r: dict) -> dict:
    return {
        "brand": r["Brand"],
        "lift": r["lift"],
        "lift_raw": r["lift_raw"],
        "revenue_thb": r["revenue_thb"],
        "revenue_thb_master": r["revenue_thb_master"],
        "units": r["units"],
        "skus_at_loc": r["skus_at_loc"],
        "share_loc_pct": r["share_loc_pct"],
        "share_company_pct": r["share_company_pct"],
    }


def _line_row_to_dict(r: dict) -> dict:
    return {
        "brand": r["Brand"],
        "line": r["Cate"],
        "lift": r["lift"],
        "lift_raw": r["lift_raw"],
        "revenue_thb": r["revenue_thb"],
        "revenue_thb_master": r["revenue_thb_master"],
        "units": r["units"],
        "skus_at_loc": r["skus_at_loc"],
        "share_loc_pct": r["share_loc_pct"],
        "share_company_pct": r["share_company_pct"],
    }


def _price_row_to_dict(r: dict) -> dict:
    return {
        "band_key": r["price_band_key"],
        "band_label": r.get("band_label", ""),
        "lift": r["lift"],
        "lift_raw": r["lift_raw"],
        "revenue_thb": r["revenue_thb"],
        "revenue_thb_master": r["revenue_thb_master"],
        "units": r["units"],
        "skus_at_loc": r["skus_at_loc"],
        "share_loc_pct": r["share_loc_pct"],
        "share_company_pct": r["share_company_pct"],
    }


# ---------------------------------------------------------------------------
# Summary template — deterministic, no LLM
# ---------------------------------------------------------------------------

def _build_summary(brand_fit: dict, line_fit: dict, price_band_fit: list) -> str:
    """Assemble a 2-3 sentence English summary from the strong/weak picks."""
    parts: list[str] = []

    strong_brands = brand_fit.get("strong", [])
    if strong_brands:
        names = ", ".join(
            f"{b['brand']} ({b['lift']:.1f}×)" for b in strong_brands[:3]
        )
        parts.append(f"Strongly favors {names}")

    strong_lines = line_fit.get("strong", [])
    if strong_lines:
        names = ", ".join(
            f"{l['brand']} / {l['line']} ({l['lift']:.1f}×)"
            for l in strong_lines[:2]
        )
        parts.append(f"especially {names}")

    # Best price band (single highest-lift band)
    if price_band_fit:
        best = max(price_band_fit, key=lambda r: r.get("lift") or 0)
        if best.get("lift") and best["lift"] > 1.2:
            parts.append(f"best for {best['band_label']} ({best['lift']:.1f}×)")

    # Capitalize only the first character of the first part — don't use
    # str.capitalize() which would lowercase brand names like "BrandA".
    def _cap_first(s: str) -> str:
        return s[0].upper() + s[1:] if s else s
    head = ", ".join(_cap_first(p) if i == 0 else p for i, p in enumerate(parts))
    if head:
        head = head + "."

    avoid_parts: list[str] = []
    weak_brands = brand_fit.get("weak", [])
    if weak_brands:
        weak_names = ", ".join(
            f"{b['brand']} ({b['lift']:.1f}×)" for b in weak_brands[:2]
        )
        avoid_parts.append(weak_names)
    if price_band_fit:
        worst = min(price_band_fit, key=lambda r: r.get("lift") or 999)
        if worst.get("lift") is not None and worst["lift"] < 0.5:
            avoid_parts.append(f"{worst['band_label']} ({worst['lift']:.1f}×)")
    tail = ""
    if avoid_parts:
        tail = " Avoid " + " and ".join(avoid_parts) + "."

    if not head and not tail:
        return (
            "No clear product-market fit signal at this location — "
            "either low sales volume in the selected period or balanced mix."
        )
    return (head + tail).strip()


# ---------------------------------------------------------------------------
# Empty / fallback response
# ---------------------------------------------------------------------------

def _empty_response(location: str, year_list: Optional[list[int]]) -> dict[str, Any]:
    return {
        "location": location,
        "period": {
            "year_list": list(year_list) if year_list else None,
            "as_of": None,
        },
        "baseline": "company",
        "totals": {
            "this_location_revenue_thb": 0.0,
            "this_location_units_sold": 0,
            "this_location_distinct_skus": 0,
            "company_revenue_thb": 0.0,
        },
        "brand_fit": {"strong": [], "weak": []},
        "line_fit": {"strong": [], "weak": []},
        "price_band_fit": [],
        "summary": (
            "No sales recorded at this location in the selected period."
        ),
        "diagnostics": {},
    }
