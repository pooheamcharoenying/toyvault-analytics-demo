"""Shelf capacity model — the heart of the bot's "no over-stocking" rule.

See STOCK_BOT_BLUEPRINT.md §4.4 for the rationale.

  Five units of an SKU on a shelf is already a strong display presence.
  Ten is very generous. Twenty is only justified for a best-seller that
  genuinely sells in the hundreds per month at that location. Thirty, fifty,
  a hundred — those numbers only make sense for items that are physically
  small *or* sell in the four-figure-per-month range at that specific
  location.

The formula:

    cap = velocity_tier_baseline   (5 / 10 / 20 / 50 / 100 by monthly velocity)
         × item_size_multiplier   (×2.0 small, ×1.0 normal, ×0.5 large, ×0.25 oversized)
         × location_multiplier    (×1.5 flagship, ×1.0 standard, ×0.6 boutique)

with a few short-circuits:

  - explicit per-(location, item) override in policy.yaml → wins outright
  - location class = warehouse → unbounded (WAREHOUSE_UNBOUNDED_CAP, default 10,000)

Pure function. No pandas. No I/O. Trivially unit-testable.
"""
from __future__ import annotations

import math
from typing import Optional

from app.stock_bot import config


# Audit basis values surfaced on every proposal.
BASIS_POLICY_OVERRIDE = "policy_override"
BASIS_WAREHOUSE_UNBOUNDED = "warehouse_unbounded"
BASIS_VELOCITY_TIER = "velocity_tier"


def compute_shelf_capacity(
    monthly_velocity: float,
    item_size_class: str,
    location_class: str,
    policy_override: Optional[float] = None,
) -> tuple[int, str, list[str]]:
    """Compute the shelf capacity for one (item × location) pair.

    Args:
        monthly_velocity: Expected sales per month at this location for this
            item, in units. Use `velocity_potential` (§4.3) — i.e., the
            velocity the location *would* absorb if well-stocked, not the
            observed velocity of a chronically-empty shelf.
        item_size_class: One of small | normal | large | oversized
            (from ``adapters.item_size.classify_item_size``).
        location_class: One of flagship | standard | boutique | warehouse
            (from ``adapters.location_class.classify_location_class``).
        policy_override: An explicit cap from
            ``policy.yaml.location_shelf_caps[whs_code][item_code]``. Wins
            outright.

    Returns:
        (cap_units, basis, modifiers) where:
          - cap_units: integer capacity (rounded down so we never recommend
            stocking beyond a tier's intent).
          - basis ∈ {policy_override, warehouse_unbounded, velocity_tier}.
          - modifiers: ordered list of human-readable strings describing the
            multipliers that fired, e.g.
            ["tier:<30/mo→5", "location:flagship×1.5", "size:normal×1.0"].
            Empty for policy_override and warehouse_unbounded.

    Raises:
        ValueError: if either class label is unknown.
    """
    # Layer 1: explicit policy override wins.
    if policy_override is not None:
        if policy_override < 0:
            raise ValueError(
                f"policy.yaml shelf cap override must be non-negative, "
                f"got {policy_override!r}"
            )
        return (int(policy_override), BASIS_POLICY_OVERRIDE, [])

    # Validate class labels up front so a stray typo doesn't silently produce
    # zero capacity.
    if item_size_class not in config.SIZE_CLASS_MULTIPLIERS:
        raise ValueError(
            f"Unknown item_size_class {item_size_class!r}; expected one of "
            f"{sorted(config.SIZE_CLASS_MULTIPLIERS)}"
        )
    if location_class not in config.LOCATION_CLASS_MULTIPLIERS:
        raise ValueError(
            f"Unknown location_class {location_class!r}; expected one of "
            f"{sorted(config.LOCATION_CLASS_MULTIPLIERS)}"
        )

    # Layer 2: warehouses are unbounded — pure storage, no display shelf.
    if location_class == "warehouse":
        return (
            config.WAREHOUSE_UNBOUNDED_CAP,
            BASIS_WAREHOUSE_UNBOUNDED,
            [],
        )

    # Layer 3: velocity-tier baseline.
    velocity = _safe_velocity(monthly_velocity)
    baseline, tier_label = _baseline_from_velocity(velocity)

    size_mult = config.SIZE_CLASS_MULTIPLIERS[item_size_class]
    loc_mult = config.LOCATION_CLASS_MULTIPLIERS[location_class]

    # loc_mult is None for warehouse (caught above) — defensive assert.
    assert loc_mult is not None, "warehouse should have short-circuited"

    raw_cap = baseline * size_mult * loc_mult
    # Round down — never recommend stocking beyond a tier's intent. Floor of
    # at least 1 so we don't accidentally produce 0 for a real velocity tier
    # (the modifiers can multiply baseline 5 × 0.25 × 0.6 = 0.75 → 0; we want
    # at least 1 unit displayable for any non-zero velocity).
    cap = max(1, int(math.floor(raw_cap))) if baseline > 0 else 0

    # Safety floor — cap must be at least 2× the monthly velocity at this
    # location. Without this, a boutique-class store (×0.6) holding a
    # fast-selling item could end up with a cap WAY below what it actually
    # turns over in a month — leading to chronic stockouts.
    #
    # The cap can exceed 2× monthly velocity (that's the tier-baseline
    # path) — the floor only protects against the multipliers dragging it
    # below that level. It does NOT cap from above.
    velocity_floor = int(math.ceil(velocity * MIN_COVER_MONTHS))
    if velocity_floor > cap:
        cap = velocity_floor
        modifiers = [
            f"tier:{tier_label}→{baseline}",
            f"size:{item_size_class}×{size_mult:g}",
            f"location:{location_class}×{loc_mult:g}",
            f"velocity-floor:{MIN_COVER_MONTHS:g}mo→{velocity_floor}",
        ]
    else:
        modifiers = [
            f"tier:{tier_label}→{baseline}",
            f"size:{item_size_class}×{size_mult:g}",
            f"location:{location_class}×{loc_mult:g}",
        ]
    return (cap, BASIS_VELOCITY_TIER, modifiers)


# Minimum months of cover the shelf cap must provide, regardless of how
# small the multipliers drag the tier baseline. The cap CAN exceed this
# (and usually does — the velocity tiers provide ~2-3 months at the lower
# end) — this is a floor, not a ceiling.
MIN_COVER_MONTHS = 2.0


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _safe_velocity(v: float) -> float:
    try:
        if v is None or v != v or v < 0:  # NaN check + negative
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _baseline_from_velocity(monthly_velocity: float) -> tuple[int, str]:
    """Return (baseline_cap_units, human_readable_tier_label)."""
    prev_threshold = 0.0
    for threshold, cap in config.VELOCITY_TIER_CAPS:
        if monthly_velocity < threshold:
            label = _format_tier_label(prev_threshold, threshold)
            return (cap, label)
        prev_threshold = threshold
    # Unreachable — last tier has threshold = +inf.
    last_cap = config.VELOCITY_TIER_CAPS[-1][1]
    return (last_cap, "overflow")


def _format_tier_label(lo: float, hi: float) -> str:
    if lo == 0.0:
        return f"<{int(hi)}/mo"
    if hi == float("inf"):
        return f">{int(lo)}/mo"
    return f"{int(lo)}–{int(hi)}/mo"
