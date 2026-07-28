"""Stock Bot — tunable knobs.

This file holds *numeric* configuration. Business policy (overrides, no-go
pairs, item-size corrections) lives in policy.yaml. Keep them separate.

Every constant here is read by exactly one engine module, and every read
site documents which constant it uses. Grep `config.` to see all references.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Target-stock model (§4.2 of the blueprint)
# ---------------------------------------------------------------------------
TARGET_COVER_DAYS = 56          # 8 weeks — matches reorder_analysis convention
MIN_SOURCE_BUFFER_DAYS = 14     # never drain a source below this
HORIZON_DAYS = 90               # window over which we project profit uplift

# ---------------------------------------------------------------------------
# Transfer thresholds (§4.6.1)
# ---------------------------------------------------------------------------
# Tuned 2026-06-03 — loosened in tandem with the new "target = shelf_cap"
# logic in engine/targets.py. The previous values were defensive against
# a per-SAP-code allocation regime that produced lots of 1-2 unit chunks
# from velocity-clamped targets; both root causes were fixed (consolidation
# + target = shelf_cap), so we can let real-but-small transfers through.
#
# A 1-unit transfer at a physical store IS a meaningful action. A ฿200
# profit on a small replenishment IS worth surfacing — that's the
# difference between "shelf had 0" and "shelf had 4" for a planner.
MIN_QTY_PER_TRANSFER = 1
MAX_QTY_PER_TRANSFER = 200
MIN_UPLIFT_THB = 100.0          # was 500 — let small-margin top-ups through
MIN_IMPACT_THB = 200.0          # was 1000 — same intent at the proposal level
# 2026-06-03: caps raised again. The previous 50-per-dest cap was binding
# hard at flagships — Siam Paragon had 80-150 items needing replenishment
# but only 50 made it through, dropping meaningful top-up recommendations
# in favour of pure-stockout ones (because the urgency-boosted priority
# score favours zero-on-hand items over partial-deficit items).
#
# Raise the caps so every real deficit at a flagship surfaces. This is
# the right move even if the output gets longer — the planner can scroll
# / filter. Better to over-recommend than to hide things they'd want to
# see.
MAX_TRANSFERS_TOTAL = 10_000        # was 1000 — was capping at 20 dests × 50
MAX_TRANSFERS_PER_DESTINATION = 500  # was 50 — flagships can need 100+

# ---------------------------------------------------------------------------
# Margin estimation (§4.5)
# ---------------------------------------------------------------------------
TYPICAL_GP_COMMISSION_PCT = 33.0   # used when U_ACT_GP is missing on a row

# ---------------------------------------------------------------------------
# Shelf capacity — velocity tiers (§4.4) and item-size price tiers (§4.4.1)
# ---------------------------------------------------------------------------
# Monthly velocity at (item × location) → baseline shelf cap (units).
#
# Tuned 2026-06-03 — both axes lowered:
#   * Finer resolution at the bottom (3 / 5 / 10 / 30 thresholds) so we can
#     distinguish a 1/mo trickle from a 6/mo steady seller — the old "<30/mo"
#     mega-bucket lumped them all in at baseline 5.
#   * Threshold compression at the top (÷3 vs the old 100 / 500 / 1000 edges)
#     so the 30-150/mo cohort gets treated as a strong seller instead of
#     "merely average," which matches the real shape of a per-store SKU mix.
#   * Baselines anchored on a business rule: a 3/mo seller needs roughly
#     6 units in store to maintain strong display + buffer between deliveries.
#     The rest follow ~2 months of cover at the lower tiers, gradually
#     flattening as velocity rises (high-velocity SKUs are refilled more
#     often, and no real store stocks 1,000 units of one SKU).
VELOCITY_TIER_CAPS = (
    (3,    6),      # < 3/mo    — barely moves; minimum strong display
    (5,    10),     # 3-5/mo    — trickle
    (10,   20),     # 5-10/mo   — slow but real
    (30,   50),     # 10-30/mo  — steady
    (150,  100),    # 30-150/mo — strong seller
    (300,  200),    # 150-300/mo — very strong
    (float("inf"), 300),  # >300/mo — hero SKU (shelf-capped)
)

# Item-size class multipliers (applied to baseline cap)
SIZE_CLASS_MULTIPLIERS = {
    "small":     2.0,
    "normal":    1.0,
    "large":     0.5,
    "oversized": 0.25,
}

# Master Price (THB) → item-size class auto-classifier
ITEM_SIZE_PRICE_TIERS = (
    (200.0,   "small"),
    (1500.0,  "normal"),
    (3500.0,  "large"),
    (float("inf"), "oversized"),
)

# ---------------------------------------------------------------------------
# Location class — revenue percentile auto-classifier (§4.4.2)
# ---------------------------------------------------------------------------
LOCATION_CLASS_MULTIPLIERS = {
    "flagship":  1.5,
    "standard":  1.0,
    "boutique":  0.6,
    "warehouse": None,   # sentinel → unbounded; see WAREHOUSE_UNBOUNDED_CAP
}
WAREHOUSE_UNBOUNDED_CAP = 10_000   # effective ceiling for warehouse-class locations

# Percentile thresholds — top N% by revenue → flagship, etc.
FLAGSHIP_PERCENTILE = 0.10         # top 10%
STANDARD_PERCENTILE = 0.50         # next 40% (so top 50% total)
# Everything below STANDARD_PERCENTILE → boutique

# Warehouse detection — either condition triggers
WAREHOUSE_REVENUE_THRESHOLD = 100_000.0     # essentially-zero direct revenue
WAREHOUSE_INVENTORY_TO_REVENUE_RATIO = 5.0  # on_hand_thb / annual_revenue > this

# ---------------------------------------------------------------------------
# Solvers (§4.6)
# ---------------------------------------------------------------------------
USE_COMPARING_SOLVER = True        # run greedy + LP and verify they agree
# Tolerance below which a per-item greedy-vs-LP objective gap is treated
# as numerical noise rather than a real algorithmic divergence.
#
# Raised 2026-06-03 from 1.0 → 100.0 to match the new problem scale.
# Now that target_stock = shelf_cap (vs the old velocity-clamped target)
# and the 2× velocity floor is in play, per-item subproblems can have
# total values around ฿50K. HiGHS LP and the incremental greedy can
# diverge by ~0.1-0.2% on these (different rounding paths, primal-dual
# vs greedy integer math). 100 THB = 0.2% of a ฿50K problem catches
# any REAL separability violation (those produce >5% gaps) while
# ignoring this kind of numerical noise.
COMPARISON_TOLERANCE_THB = 100.0
SEPARABILITY_ASSERTION_TOLERANCE = 1e-6  # relative tolerance for the separability check
SEPARABILITY_ASSERTION_TOLERANCE = 1e-6  # relative tolerance for the separability check

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = 600
