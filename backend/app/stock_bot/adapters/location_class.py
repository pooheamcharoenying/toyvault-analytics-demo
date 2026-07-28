"""Auto-classify locations into size classes (flagship / standard / boutique / warehouse).

See STOCK_BOT_BLUEPRINT.md §4.4.2 for the rationale.

A location's share of company-wide revenue is a direct, trustworthy proxy for
its physical size and shelf depth — flagships generate the most revenue
precisely because they're big and busy. So we tier locations by revenue
percentile against the rest of the company.

Warehouses are detected separately by a ratio test: a location with
essentially-zero direct revenue, OR with an on-hand-to-revenue ratio so high
that it can't possibly be a retail store, is flagged as a warehouse and gets
unbounded shelf capacity (it's pure storage, not customer-facing display).

Pure function. No pandas. No I/O. Trivially unit-testable.
"""
from __future__ import annotations

from typing import Optional

from app.stock_bot import config


# Audit basis values surfaced on every proposal so a manager can challenge
# any classification.
BASIS_POLICY_OVERRIDE = "policy_override"
BASIS_WAREHOUSE_LOW_REVENUE = "warehouse_low_revenue"
BASIS_WAREHOUSE_HIGH_RATIO = "warehouse_high_ratio"
BASIS_REVENUE_PERCENTILE = "revenue_percentile"


def classify_location_class(
    annual_revenue_thb: float,
    on_hand_thb: float,
    percentile_rank: float,
    policy_override: Optional[str] = None,
) -> tuple[str, str, str]:
    """Classify a single location.

    Args:
        annual_revenue_thb: Trailing-12-month sales revenue at this location.
            Negative / NaN values are treated as zero.
        on_hand_thb: Current on-hand value at master price.
        percentile_rank: Rank of this location's revenue among all locations,
            expressed as a fraction in [0.0, 1.0] where **smaller = better**.
            Top 10% = 0.0 to 0.10. Bottom 50% = 0.50 to 1.00. This is the
            convention used by pandas' ``Series.rank(pct=True, ascending=False)``.
        policy_override: An explicit class from ``policy.yaml.location_class``.
            Always wins.

    Returns:
        (class_label, basis, evidence).
        ``class_label`` ∈ {flagship, standard, boutique, warehouse}.
        ``basis`` ∈ {policy_override, warehouse_low_revenue,
        warehouse_high_ratio, revenue_percentile}.
        ``evidence`` is a human-readable string for audit, e.g.
        "top 4% — flagship" or "rev=12,000 THB < 100,000 → warehouse".

    Raises:
        ValueError: if ``policy_override`` is provided but isn't a known class
            or if ``percentile_rank`` is outside [0, 1].
    """
    # Layer 1: explicit policy override always wins.
    if policy_override is not None:
        if policy_override not in config.LOCATION_CLASS_MULTIPLIERS:
            raise ValueError(
                f"policy.yaml.location_class contains unknown class "
                f"{policy_override!r}; expected one of "
                f"{sorted(config.LOCATION_CLASS_MULTIPLIERS)}"
            )
        return (
            policy_override,
            BASIS_POLICY_OVERRIDE,
            f"override → {policy_override}",
        )

    # Coerce nonsense values defensively. We never want a stray NaN to flow
    # into the rest of the pipeline.
    revenue = _safe_nonneg(annual_revenue_thb)
    onhand = _safe_nonneg(on_hand_thb)

    if not 0.0 <= percentile_rank <= 1.0:
        raise ValueError(
            f"percentile_rank must be in [0, 1], got {percentile_rank!r}"
        )

    # Layer 2a: warehouse by low revenue.
    if revenue < config.WAREHOUSE_REVENUE_THRESHOLD:
        return (
            "warehouse",
            BASIS_WAREHOUSE_LOW_REVENUE,
            (
                f"revenue {revenue:,.0f} THB < "
                f"{config.WAREHOUSE_REVENUE_THRESHOLD:,.0f} THB → warehouse"
            ),
        )

    # Layer 2b: warehouse by high inventory-to-revenue ratio.
    # By the time we get here, revenue ≥ WAREHOUSE_REVENUE_THRESHOLD, so the
    # division is safe.
    ratio = onhand / revenue if revenue > 0 else float("inf")
    if ratio > config.WAREHOUSE_INVENTORY_TO_REVENUE_RATIO:
        return (
            "warehouse",
            BASIS_WAREHOUSE_HIGH_RATIO,
            (
                f"on-hand/revenue = {ratio:.1f} > "
                f"{config.WAREHOUSE_INVENTORY_TO_REVENUE_RATIO:.1f} → warehouse"
            ),
        )

    # Layer 3: revenue percentile tier.
    return _classify_by_percentile(percentile_rank)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _safe_nonneg(x: float) -> float:
    try:
        if x is None or x != x or x < 0.0:  # NaN or negative
            return 0.0
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _classify_by_percentile(rank: float) -> tuple[str, str, str]:
    if rank <= config.FLAGSHIP_PERCENTILE:
        return (
            "flagship",
            BASIS_REVENUE_PERCENTILE,
            f"top {rank * 100:.1f}% by revenue → flagship",
        )
    if rank <= config.STANDARD_PERCENTILE:
        return (
            "standard",
            BASIS_REVENUE_PERCENTILE,
            f"top {rank * 100:.1f}% by revenue → standard",
        )
    return (
        "boutique",
        BASIS_REVENUE_PERCENTILE,
        f"bottom {(1 - rank) * 100:.1f}% by revenue → boutique",
    )
