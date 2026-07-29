"""AI Suggested Planogram — demand-ceiling engine.

THE PROBLEM
-----------
Observed sales are *censored by supply*. If a location only ever held 5 units of
an item, its "sales" can never exceed 5 — so sizing a shelf from historical sales
permanently caps that location at its past under-stocking. We estimate instead the
*unconstrained* monthly demand: what the location would sell if it never ran out.

THE PIPELINE (per item @ consolidated location)
------------------------------------------------
1. Monthly panel reconstruction (validated against compute_item_at_location_trend):
     available(m) = onhand_start + received - transfers_out     (sellable ceiling)
     onhand_end(m) reconstructed backward from the current snapshot.
2. Classify each month:
     censored  = stocked out (end ~ 0) AND sold ~ all supply    -> demand hidden
     clean     = otherwise                                       -> demand = sold
3. Uncensor censored months with in-stock velocity:
     demand = sold / in_stock_days * days_in_month   (floored at available)
4. Partial current month (data cut off mid-month):
     >= 10 days elapsed -> promote to a full month (clean: scale by days elapsed;
       censored: velocity already projects to a full month)
     <  10 days         -> drop the month
5. Seasonality (multiplicative, pooled per retail channel, censoring-corrected,
   recency-weighted, normalized to mean 1.0). Wholesale channels excluded.
6. Base level = recency-weighted mean of *deseasonalized* monthly demand.
   Planogram(month) = base x seasonal_index(channel, month).   No safety padding
   ("size to demand") — the seasonal peak month is base x max_index.
7. Confidence / "ceiling-tested" status: whether a recent well-stocked month
   actually revealed demand, plus history length.

Everything is pure-pandas over the GLOBAL_DF frames; no I/O here.
"""
from __future__ import annotations

import calendar
from typing import Iterable, Optional

import numpy as np
import pandas as pd

# ---- tunables -------------------------------------------------------------
STOCKOUT_ABS = 0.5          # onhand_end <= this counts as "empty"
STOCKOUT_FRAC = 0.05        # ...or <= 5% of the month's supply
SELLTHROUGH_TAU = 0.85      # sold/supply at/above this + empty => supply-constrained
MIN_CENSOR_UNITS = 4        # a stockout month must have sold >= this to be treated
                            # as censored — selling 1-3 units then "running out" of a
                            # tiny supply is not evidence of real demand pressure
PARTIAL_MIN_DAYS = 10       # latest month: >= this -> extrapolate; else drop
RECENCY_HALFLIFE_M = 15.0   # months; exponential recency decay
RECENT_WINDOW_M = 12        # months considered "recent" for ceiling-tested status
BASE_WINDOW_M = 18          # base demand is estimated from the last N months only
                            # (excludes stale peaks; captures >1 seasonal cycle)
DEAD_SALES_UNITS = 1.0      # < this many units sold in RECENT_WINDOW_M => dead here
SHORT_HISTORY_M = 6         # fewer than this many months => low confidence
SEASONAL_MIN_ITEMMONTHS = 60  # a channel needs this many demand points for its own curve
MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ===========================================================================
# 1. Monthly panel reconstruction
# ===========================================================================
def _loc_map(df_whs_code: pd.DataFrame) -> dict:
    from app.utils.location_consolidation import add_consolidated_column
    w = df_whs_code[["WhsCode", "WhsName"]].copy()
    w["WhsCode"] = w["WhsCode"].astype(str).str.strip()
    w["WhsName"] = w["WhsName"].astype(str)
    w = add_consolidated_column(w, dict(zip(w["WhsCode"], w["WhsName"])))
    return dict(zip(w["WhsCode"], w["ConsolidatedLocation"]))


def _prep(df: pd.DataFrame, loc_map: dict, want_day: bool = False) -> pd.DataFrame:
    df = df.copy()
    df["ItemCode"] = df["ItemCode"].astype(str).str.strip()
    df["WhsCode"] = df["WhsCode"].astype(str).str.strip()
    df["loc"] = df["WhsCode"].map(loc_map).fillna(df["WhsCode"])
    df["DocDate"] = pd.to_datetime(df["DocDate"], errors="coerce")
    df = df.dropna(subset=["DocDate"])
    df["month"] = df["DocDate"].dt.to_period("M").dt.start_time
    df["q"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).abs()
    if want_day:
        df["day"] = df["DocDate"].dt.day
    return df


def build_panel(df_sale, df_grpo_detail, df_tr_in, df_tr_out, df_onhand, df_whs_code):
    """Monthly panel per (ItemCode, loc, month) with reconstructed on-hand.

    Returns (panel, loc_map, sale_prepped). ``sale_prepped`` carries GroupName +
    day-of-month so callers can derive channel and in-stock velocity.
    """
    loc_map = _loc_map(df_whs_code)
    sale = _prep(df_sale, loc_map, want_day=True)
    grpo = _prep(df_grpo_detail, loc_map)
    tri = _prep(df_tr_in, loc_map)
    tro = _prep(df_tr_out, loc_map)

    sold = sale.groupby(["ItemCode", "loc", "month"])["q"].sum().rename("sold")
    recv = (grpo.groupby(["ItemCode", "loc", "month"])["q"].sum()
            .add(tri.groupby(["ItemCode", "loc", "month"])["q"].sum(), fill_value=0)).rename("received")
    trout = tro.groupby(["ItemCode", "loc", "month"])["q"].sum().rename("trout")
    span = sale.groupby(["ItemCode", "loc", "month"]).agg(
        first_day=("day", "min"), last_day=("day", "max")).reset_index()

    panel = pd.concat([sold, recv, trout], axis=1).fillna(0.0).reset_index()
    panel = panel.merge(span, on=["ItemCode", "loc", "month"], how="left")
    panel = panel.sort_values(["ItemCode", "loc", "month"]).reset_index(drop=True)

    onh = df_onhand.copy()
    onh["ItemCode"] = onh["ItemCode"].astype(str).str.strip()
    onh["WhsCode"] = onh["WhsCode"].astype(str).str.strip()
    onh["loc"] = onh["WhsCode"].map(loc_map).fillna(onh["WhsCode"])
    onh["OnHand"] = pd.to_numeric(onh["OnHand"], errors="coerce").fillna(0)
    onhnow = onh.groupby(["ItemCode", "loc"])["OnHand"].sum().rename("onhand_now")

    panel["netflow"] = panel["received"] - panel["sold"] - panel["trout"]
    grp = panel.groupby(["ItemCode", "loc"])["netflow"]
    panel["cumnet"] = grp.cumsum()
    panel["tot"] = grp.transform("sum")
    panel = panel.merge(onhnow, on=["ItemCode", "loc"], how="left")
    panel["onhand_now"] = panel["onhand_now"].fillna(0.0)
    panel["onhand_end"] = panel["onhand_now"] - (panel["tot"] - panel["cumnet"])
    panel["onhand_start"] = panel["onhand_end"] - panel["netflow"]
    panel["available"] = panel["onhand_start"] + panel["received"] - panel["trout"]
    return panel, loc_map, sale


# ===========================================================================
# 2-4. Per-month demand estimate (censoring + partial-month rule)
# ===========================================================================
def estimate_month_demand(panel: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Add ``demand`` (uncensored monthly demand estimate) and helper flags.
    Drops rows that carry no signal (no stock and no sale) and the too-short
    partial current month."""
    p = panel.copy()
    month = pd.to_datetime(p["month"])
    p["dim"] = month.dt.days_in_month.astype(float)
    cur_month = as_of.to_period("M").start_time
    as_of_day = int(as_of.day)
    p["is_current"] = month.values == np.datetime64(cur_month)
    days_elapsed = np.where(p["is_current"], as_of_day, p["dim"])

    # Data-sanity floor: a month's available stock can't be less than what sold
    # that month (you can't sell what you never had). This corrects the
    # reconstruction's impossible negatives / oversells BEFORE any demand math,
    # without touching the raw series the item-detail chart shows.
    avail = np.maximum(p["available"], p["sold"]).clip(lower=0.0)
    stockout = p["onhand_end"] <= np.maximum(STOCKOUT_ABS, STOCKOUT_FRAC * avail)
    sellthrough = np.where(avail > 0, p["sold"] / avail.replace(0, np.nan), 0.0)
    sellthrough = np.nan_to_num(sellthrough, nan=0.0)
    p["censored"] = (stockout.values & (sellthrough >= SELLTHROUGH_TAU)
                     & (p["sold"].values >= MIN_CENSOR_UNITS))

    in_stock_days = p["last_day"].fillna(p["dim"]).clip(lower=1.0)
    velocity_demand = np.maximum((p["sold"] / in_stock_days) * p["dim"], avail)
    clean_demand = np.where(p["is_current"], p["sold"] * p["dim"] / np.maximum(days_elapsed, 1),
                            p["sold"])
    p["demand"] = np.where(p["censored"], velocity_demand, clean_demand)

    # drop the too-short partial month, and months with no stock and no sale
    drop_partial = p["is_current"].values & (as_of_day < PARTIAL_MIN_DAYS)
    no_signal = (avail.values <= 0) & (p["sold"].values <= 0)
    p = p[~(drop_partial | no_signal)].copy()

    months_ago = ((cur_month.year - month.dt.year) * 12 + (cur_month.month - month.dt.month))
    p["months_ago"] = months_ago.reindex(p.index)
    p["recency_w"] = 0.5 ** (p["months_ago"] / RECENCY_HALFLIFE_M)
    p["cmonth"] = pd.to_datetime(p["month"]).dt.month
    p["year"] = pd.to_datetime(p["month"]).dt.year
    return p


# ===========================================================================
# 5. Seasonal index — per retail channel, censoring-corrected, recency-weighted
# ===========================================================================
def location_channels(sale: pd.DataFrame) -> dict:
    """Dominant sales channel (GroupName) per consolidated location."""
    g = (sale.groupby(["loc", "GroupName"])["q"].sum().reset_index()
         .sort_values("q", ascending=False).drop_duplicates("loc"))
    return dict(zip(g["loc"], g["GroupName"]))


def _normalize_index(by_cmonth: pd.Series) -> dict:
    """A pandas Series indexed 1..12 (some maybe missing) -> {1..12: multiplier},
    normalized so the present months average 1.0; missing months default to 1.0."""
    if by_cmonth.empty or by_cmonth.mean() == 0:
        return {m: 1.0 for m in range(1, 13)}
    norm = by_cmonth / by_cmonth.mean()
    return {m: (round(float(norm[m]), 4) if m in norm.index else 1.0) for m in range(1, 13)}


def compute_seasonality(pdemand: pd.DataFrame, loc_channel: dict,
                        retail_channels: set) -> dict:
    """Return {channel: {1..12: multiplier}} plus a '__company__' retail-pooled
    fallback. Built from censoring-corrected demand, ratio-to-annual-average,
    recency-weighted across years, wholesale channels excluded."""
    d = pdemand.copy()
    d["channel"] = d["loc"].map(loc_channel)
    d = d[d["channel"].isin(retail_channels)]
    # exclude the partial current month from the seasonal shape (prior years carry it)
    d = d[~d["is_current"]]
    if d.empty:
        return {"__company__": {m: 1.0 for m in range(1, 13)}}

    def curve(sub: pd.DataFrame) -> dict:
        # sum demand by (year, cmonth); ratio to that year's average month
        m = sub.groupby(["year", "cmonth"])["demand"].sum().reset_index()
        yavg = m.groupby("year")["demand"].mean().rename("yavg")
        m = m.join(yavg, on="year")
        m = m[m["yavg"] > 0]
        if m.empty:
            return {mm: 1.0 for mm in range(1, 13)}
        m["ratio"] = m["demand"] / m["yavg"]
        now_year = int(sub["year"].max())
        m["w"] = 0.5 ** (((now_year - m["year"]) * 12.0) / RECENCY_HALFLIFE_M)
        m["wr"] = m["ratio"] * m["w"]
        agg = m.groupby("cmonth").agg(wr=("wr", "sum"), w=("w", "sum"))
        wr = agg["wr"] / agg["w"]
        return _normalize_index(wr)

    out = {"__company__": curve(d)}
    for ch, sub in d.groupby("channel"):
        out[ch] = curve(sub) if len(sub) >= SEASONAL_MIN_ITEMMONTHS else out["__company__"]
    return out


# ===========================================================================
# 6-7. Base level, seasonal profile, confidence
# ===========================================================================
def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Recency-weighted quantile — the demand level the shelf should cover.
    q≈0.85 means 'stock for a busy month', not the average (which stocks out half
    the time). Reproduces observed peaks better than the mean (validated on items
    with a real December)."""
    if len(values) == 0 or weights.sum() <= 0:
        return 0.0
    order = np.argsort(values)
    v, w = np.asarray(values)[order], np.asarray(weights)[order]
    cw = np.cumsum(w) - 0.5 * w
    cw /= w.sum()
    return float(np.interp(q, cw, v))


BASE_QUANTILE = 0.85


def _confidence(n_months: int, has_recent_clean: bool, has_clean: bool) -> str:
    if n_months < SHORT_HISTORY_M or not has_clean:
        return "low"
    if has_recent_clean:
        return "high"
    return "medium"


def _status(has_recent_clean: bool, has_clean: bool, short: bool) -> str:
    if has_recent_clean:
        return "short history" if short else "ceiling-tested recently"
    if has_clean:
        return "not ceiling-tested recently"
    return "never ceiling-tested"


def compute_ai_planograms(df_sale, df_item_master, df_onhand, df_grpo_detail,
                          df_tr_in, df_tr_out, df_whs_code,
                          scope_locs: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """Top-level: per (ItemCode, loc) AI Suggested Planogram.

    Columns: item_code, loc, channel, base_demand, planogram_current, planogram_peak,
    peak_month, profile (list of 12), status, confidence, months_of_history,
    current_onhand, seasonal_source.
    """
    panel, loc_map, sale = build_panel(df_sale, df_grpo_detail, df_tr_in,
                                       df_tr_out, df_onhand, df_whs_code)
    as_of = pd.to_datetime(sale["DocDate"]).max()
    cur_cmonth = int(as_of.month)
    pdemand = estimate_month_demand(panel, as_of)

    loc_channel = location_channels(sale)
    scope = set(map(str, scope_locs)) if scope_locs is not None else None
    retail_channels = (set(loc_channel[l] for l in scope if l in loc_channel)
                       if scope is not None else set(loc_channel.values()))
    seasonality = compute_seasonality(pdemand, loc_channel, retail_channels)

    def idx_for(channel, cmonth):
        src = seasonality.get(channel, seasonality["__company__"])
        return src.get(cmonth, 1.0)

    work = pdemand if scope is None else pdemand[pdemand["loc"].isin(scope)]
    work = work.copy()
    work["channel"] = work["loc"].map(loc_channel)
    work["s_index"] = [idx_for(c, m) for c, m in zip(work["channel"], work["cmonth"])]
    work["deseason"] = work["demand"] / work["s_index"].replace(0, 1.0)
    work["is_clean"] = ~work["censored"]
    # "ceiling-tested recently" requires a recent, well-stocked month that ACTUALLY
    # SOLD — a recent month with stock but zero sales is evidence of NO demand.
    work["recent_clean"] = (work["is_clean"] & (work["months_ago"] < RECENT_WINDOW_M)
                            & (work["sold"] > 0))
    work["in_base_window"] = work["months_ago"] < BASE_WINDOW_M

    onhnow = (panel.groupby(["ItemCode", "loc"])["onhand_now"].first())

    rows = []
    for (item, loc), sub in work.groupby(["ItemCode", "loc"]):
        # Base demand from the RECENT window only, so stale peaks don't inflate a
        # now-dead item and recent decline is trusted over old highs.
        base_rows = sub[sub["in_base_window"]]
        if len(base_rows):
            base = _weighted_quantile(base_rows["deseason"].to_numpy(),
                                      base_rows["recency_w"].to_numpy(), BASE_QUANTILE)
        else:
            base = 0.0
        recent_sold = float(sub.loc[sub["months_ago"] < RECENT_WINDOW_M, "sold"].sum())
        channel = loc_channel.get(loc, "?")
        seas_src = channel if channel in seasonality else "__company__"
        n = int(sub["month"].nunique())
        has_recent_clean = bool(sub["recent_clean"].any())
        has_clean = bool(sub["is_clean"].any())
        short = n < SHORT_HISTORY_M
        # Dead here: nothing sold in a full year -> no shelf, flag for liquidation.
        if recent_sold < DEAD_SALES_UNITS:
            base = 0.0
            status, confidence = "no recent sales", "low"
        else:
            status = _status(has_recent_clean, has_clean, short)
            confidence = _confidence(n, has_recent_clean, has_clean)
        profile = {m: round(base * idx_for(channel, m), 1) for m in range(1, 13)}
        peak_m = max(profile, key=profile.get) if profile else cur_cmonth
        rows.append({
            "item_code": item, "loc": loc, "channel": channel,
            "base_demand": round(base, 1),
            "planogram_current": int(np.ceil(profile.get(cur_cmonth, base))),
            "planogram_peak": int(np.ceil(profile[peak_m])) if profile else int(np.ceil(base)),
            "peak_month": MONTH_ABBR[peak_m],
            "profile": [profile[m] for m in range(1, 13)],
            "status": status,
            "confidence": confidence,
            "months_of_history": n,
            "current_onhand": float(onhnow.get((item, loc), 0.0)),
            "seasonal_source": "own channel" if seas_src == channel else "retail avg",
        })
    return pd.DataFrame(rows)
