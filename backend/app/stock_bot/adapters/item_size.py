"""Auto-classify items into size classes (small / normal / large / oversized).

See STOCK_BOT_BLUEPRINT.md §4.4.1 for the rationale.

Item Master has no physical dimension fields, so we use Master Price as the
sole signal. Price is both a size proxy (expensive toys tend to be bigger)
*and* a capital-exposure proxy (you wouldn't put 100 facings of a 3,500 THB
SKU on a shelf regardless of physical size). Both pressures push the same
way — one signal captures both concerns.

Pure function. No pandas. No I/O. Trivially unit-testable.
"""
from __future__ import annotations

from typing import Optional

from app.stock_bot import config


ValidSizeClass = str  # "small" | "normal" | "large" | "oversized"

# Audit basis values surfaced on every proposal so a manager can challenge
# any classification with one disclosure click.
BASIS_POLICY_OVERRIDE = "policy_override"
BASIS_PRICE_TIER = "price_tier"
BASIS_MISSING_PRICE = "missing_price_default"


def classify_item_size(
    master_price: Optional[float],
    policy_override: Optional[str] = None,
) -> tuple[str, str, str]:
    """Classify a single item by its Master Price.

    Args:
        master_price: List price in THB from Item Master. None / NaN / 0
            triggers the missing-price fallback.
        policy_override: An explicit class from ``policy.yaml.item_size_class``.
            If present and valid, wins outright.

    Returns:
        (class_label, basis, evidence) where:
          - class_label ∈ {small, normal, large, oversized}
          - basis ∈ {policy_override, price_tier, missing_price_default}
          - evidence: human-readable string for the audit field, e.g.
            "745 THB → normal (200–1,500)".

    Raises:
        ValueError: if ``policy_override`` is provided but isn't a known class.
    """
    # Layer 1: explicit policy override always wins.
    if policy_override is not None:
        if policy_override not in config.SIZE_CLASS_MULTIPLIERS:
            raise ValueError(
                f"policy.yaml.item_size_class contains unknown class "
                f"{policy_override!r}; expected one of "
                f"{sorted(config.SIZE_CLASS_MULTIPLIERS)}"
            )
        return (
            policy_override,
            BASIS_POLICY_OVERRIDE,
            f"override → {policy_override}",
        )

    # Layer 2: missing / zero / negative / NaN price → fall back to normal.
    if master_price is None or _is_invalid_price(master_price):
        return (
            "normal",
            BASIS_MISSING_PRICE,
            f"price={master_price!r} — no signal, defaulted to normal",
        )

    # Layer 3: price tier.
    return _classify_by_price_tier(float(master_price))


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _is_invalid_price(p: float) -> bool:
    # Catches NaN, zero, and negative. The `p != p` trick is the standard
    # NaN check that works without importing math.
    try:
        return p != p or p <= 0.0
    except (TypeError, ValueError):
        return True


def _classify_by_price_tier(price: float) -> tuple[str, str, str]:
    prev_threshold = 0.0
    for threshold, class_label in config.ITEM_SIZE_PRICE_TIERS:
        if price < threshold:
            band = _format_band(prev_threshold, threshold)
            return (
                class_label,
                BASIS_PRICE_TIER,
                f"{price:,.0f} THB → {class_label} ({band})",
            )
        prev_threshold = threshold
    # Unreachable because the last tier has threshold = +inf, but mypy doesn't
    # know that — return the last tier defensively.
    last_label = config.ITEM_SIZE_PRICE_TIERS[-1][1]
    return (
        last_label,
        BASIS_PRICE_TIER,
        f"{price:,.0f} THB → {last_label} (overflow)",
    )


def _format_band(lo: float, hi: float) -> str:
    if lo == 0.0:
        return f"< {hi:,.0f}"
    if hi == float("inf"):
        return f"> {lo:,.0f}"
    return f"{lo:,.0f}–{hi:,.0f}"
