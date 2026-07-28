"""Score candidate transfers — separable cost matrix.

For every (item, source, destination) candidate:

    unit_score[s, d] = margin_i × source_bonus(s) × dest_multiplier(d)

This is **separable** by construction — source_bonus depends only on the
source, dest_multiplier only on the destination. That makes greedy provably
equal to LP optimum per blueprint §4.6.1.

The factors are deliberately mild (range ~0.5×–1.5×) so health and dead-stock
factors *tilt* the ranking without overwhelming the raw profit signal.
"""
from __future__ import annotations

from app.stock_bot.domain.models import ItemLocationState


# Tunable in the unlikely case we need to dial them; not config because they
# are part of the score model, not operational thresholds.
#
# Warehouses are PREFERRED sources by a wide margin — they exist to be drawn
# from. Shops are sources only when they have stock that isn't selling at
# their location ("dead-at-this-location"). A healthy shop should never have
# stock drained from it as long as a warehouse has the item.
_WAREHOUSE_SOURCE_BONUS = 2.0            # warehouses are the preferred source
_SHOP_DEAD_STOCK_BONUS = 1.5             # shop holding zero-velocity stock
_SHOP_SLOW_BONUS_AT_DAYS = (545.0, 1.5)  # shop with > 545 days cover
_SHOP_NEUTRAL_BONUS_AT_DAYS = (180.0, 0.8)  # shop with ≤ 180 days cover — penalise
                                            # draining a healthy shop

# Source-side location-class multipliers — applied ON TOP of the
# cover/dead-stock base bonus. Intent: when warehouses are empty and
# the bot has to pull from a shop, prefer to drain UNDERPERFORMING
# stores (boutique tier) before touching stronger ones. A boutique
# with dead stock combined with these multipliers (1.5 × 1.3 = 1.95)
# almost matches a warehouse (2.0), so the bot will reach for the
# boutique once warehouses are out — while never disturbing a healthy
# flagship's display (worst-case bonus 0.8 × 0.7 = 0.56).
_SOURCE_LOCATION_CLASS_MULTIPLIERS = {
    "boutique": 1.3,     # underperformers — drain first
    "standard": 1.0,
    "flagship": 0.7,     # protect strong-store display
    "warehouse": 1.0,    # multiplier irrelevant (warehouse path short-circuits)
}

_DEST_MULTIPLIER_MIN = 0.6               # bottom percentile of locations
_DEST_MULTIPLIER_MAX = 1.0               # top percentile of locations
_DEST_MULTIPLIER_SLOPE = (
    _DEST_MULTIPLIER_MAX - _DEST_MULTIPLIER_MIN
)


def source_bonus(source_state: ItemLocationState) -> float:
    """Higher = more preferred as source.

    Two factors combine:

    1. **Cover/dead-stock base** — warehouses always win (2.0). Shops
       with zero velocity (dead stock) or very high days-of-cover get
       a moderate bonus to encourage clearing them. Shops with healthy
       turnover get penalised (0.8) to protect productive displays.

    2. **Source location-class multiplier** (NEW). Applied on top of
       the base. Boutique sources get 1.3× (prefer to drain weak
       stores), flagship sources get 0.7× (protect strong-store
       displays). Combined: a boutique with dead stock scores 1.95 —
       just below a warehouse — so the bot reaches for the boutique
       only when warehouses are empty, never the flagship unless every
       other option is exhausted.
    """
    if source_state.location_class == "warehouse":
        return _WAREHOUSE_SOURCE_BONUS

    if source_state.velocity_per_day <= 0:
        # Zero velocity at a *shop* with stock = dead-at-this-location → clear it.
        base = _SHOP_DEAD_STOCK_BONUS
    else:
        days_cover = source_state.on_hand / source_state.velocity_per_day
        slow_days, slow_bonus = _SHOP_SLOW_BONUS_AT_DAYS
        neut_days, neut_bonus = _SHOP_NEUTRAL_BONUS_AT_DAYS

        if days_cover <= neut_days:
            base = neut_bonus
        elif days_cover >= slow_days:
            base = slow_bonus
        else:
            # Linear interpolation between (neut_days, neut_bonus) and (slow_days, slow_bonus).
            span = slow_days - neut_days
            progress = (days_cover - neut_days) / span
            base = neut_bonus + (slow_bonus - neut_bonus) * progress

    loc_mult = _SOURCE_LOCATION_CLASS_MULTIPLIERS.get(
        source_state.location_class, 1.0
    )
    return base * loc_mult


def dest_multiplier(dest_state: ItemLocationState) -> float:
    """1.0 for top-percentile locations, ramping down to 0.6 for bottom.

    Uses location class as a proxy: flagship → 1.0, standard → 0.8,
    boutique → 0.6, warehouse → 0 (warehouses should never be destinations
    anyway — the filter drops them — but defensive zeroing makes any leak
    visible).
    """
    if dest_state.location_class == "warehouse":
        return 0.0
    if dest_state.location_class == "flagship":
        return _DEST_MULTIPLIER_MAX
    if dest_state.location_class == "standard":
        return _DEST_MULTIPLIER_MIN + 0.5 * _DEST_MULTIPLIER_SLOPE
    return _DEST_MULTIPLIER_MIN   # boutique


def unit_score(
    margin_per_unit_thb: float,
    source_state: ItemLocationState,
    dest_state: ItemLocationState,
) -> float:
    """Per-unit score. Multiply by qty to get total proposal score."""
    return (
        float(margin_per_unit_thb)
        * source_bonus(source_state)
        * dest_multiplier(dest_state)
    )


def is_separable(matrix: dict[tuple[str, str], float], tol: float = 1e-6) -> bool:
    """Verify a score matrix factors as f(s)·g(d).

    Used by greedy.py as a debug-mode invariant check. If this returns False
    on a non-trivial matrix, greedy is not guaranteed to be optimal — the LP
    solver must be used.

    Args:
        matrix: dict {(source, dest): score}.
        tol: relative tolerance for the ratio test.

    Returns:
        True if the matrix is separable (within tolerance), False otherwise.
        Trivially-small matrices (0 or 1 edges) are vacuously separable.
    """
    # Group by source.
    by_source: dict[str, dict[str, float]] = {}
    for (s, d), v in matrix.items():
        by_source.setdefault(s, {})[d] = v

    sources = list(by_source.keys())
    if len(sources) < 2:
        return True

    # Pick a reference source. For every other source s2, the ratio
    # matrix[s1, d] / matrix[s2, d] should be the same across all d
    # (it equals f(s1)/f(s2)).
    s_ref = sources[0]
    for s2 in sources[1:]:
        common_dests = set(by_source[s_ref]) & set(by_source[s2])
        ratios: list[float] = []
        for d in common_dests:
            v1 = by_source[s_ref][d]
            v2 = by_source[s2][d]
            if v2 == 0:
                if v1 != 0:
                    return False  # one zero, one nonzero → not factorable
                continue
            ratios.append(v1 / v2)
        if len(ratios) < 2:
            continue
        ref = ratios[0]
        for r in ratios[1:]:
            denom = max(abs(ref), abs(r), 1.0)
            if abs(r - ref) / denom > tol:
                return False
    return True
